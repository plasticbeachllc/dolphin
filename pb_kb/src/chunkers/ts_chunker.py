"""Tree-sitter based chunker for TypeScript/TSX/JavaScript.

This module extracts symbol-aware chunks from source code using Tree-sitter.
If parsing or symbol extraction fails, it falls back to simple token windows.

Conventions:
- Line numbers in Chunk are 1-based to match existing consumers.
- Overlap is specified as a fraction of the target token count and is clamped to [0, 1].
"""
from __future__ import annotations

import bisect
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Tuple

import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser

from .token_utils import get_tokenizer, window_text_by_tokens, count_tokens
from .types import Chunk

_log = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {"typescript", "tsx", "javascript"}
LINE_NUMBER_BASE = 1  # Maintain 1-based lines for compatibility


@lru_cache(maxsize=8)
def _get_parser(lang: str) -> Parser:
    """Return a cached Tree-sitter parser for TypeScript/TSX/JavaScript.
    
    Uses tree-sitter 0.25+ API with Language wrapper.
    All three languages (typescript, tsx, javascript) use the same parser.
    """
    # tree-sitter-javascript handles all JS/TS variants
    JS_LANGUAGE = Language(tsjs.language())
    return Parser(JS_LANGUAGE)


@dataclass(frozen=True)
class Symbol:
    kind: str
    name: Optional[str]
    path: Optional[str]
    start_byte: int
    end_byte: int
    start_row: int
    end_row: int


def chunk_source(
    source: str,
    *,
    lang: str = "typescript",
    model: str = "small",
    token_target: int = 400,
    overlap_pct: float = 0.10,
) -> list[Chunk]:
    """Chunk a TS/TSX/JS source file into symbol-aware chunks using Tree-sitter.

    Supported lang values: "typescript", "tsx", "javascript".
    Returns a list of Chunk with 1-based line numbers.
    """
    if token_target <= 0:
        raise ValueError(f"token_target must be > 0, got {token_target}")

    lang_key = lang.lower()
    if lang_key not in SUPPORTED_LANGUAGES:
        _log.warning("Unsupported language '%s'; falling back to token windows", lang)
        return _fallback_token_windows(source, model=model, token_target=token_target, overlap_pct=overlap_pct)

    # Clamp overlap percentage
    if not (0.0 <= overlap_pct <= 1.0):
        _log.debug("Clamping overlap_pct from %s to range [0,1]", overlap_pct)
        overlap_pct = max(0.0, min(1.0, overlap_pct))
    overlap_tokens = max(0, min(int(token_target * overlap_pct), max(0, token_target - 1)))

    # Prepare parser and parse tree
    try:
        source_bytes = source.encode("utf-8")
        parser = _get_parser(lang_key)
        # Robust parse invocation (align with py_chunker)
        parse_fn = getattr(parser, "parse", None)
        if callable(parse_fn):
            tree = parse_fn(source_bytes)
        else:
            tree = parser.parse_bytes(source_bytes)  # type: ignore[attr-defined]
        root = tree.root_node
    except Exception as e:  # noqa: BLE001
        _log.warning("Tree-sitter parse failed for %s; falling back to token windows: %s", lang, e)
        return _fallback_token_windows(source, model=model, token_target=token_target, overlap_pct=overlap_pct)

    # Extract symbols
    symbols = list(_extract_symbols(root, source))
    if not symbols:
        return _fallback_token_windows(source, model=model, token_target=token_target, overlap_pct=overlap_pct)

    tokenizer = get_tokenizer(model)
    chunks: list[Chunk] = []

    # Build chunks per symbol
    for sym in symbols:
        try:
            symbol_text = source_bytes[sym.start_byte:sym.end_byte].decode("utf-8")
        except Exception as e:  # noqa: BLE001
            _log.debug("Skipping symbol %s due to decode error: %s", sym.name, e)
            continue

        chunks.extend(
            _build_chunks_for_text(
                symbol_text,
                base_start_row=sym.start_row,
                tokenizer=tokenizer,
                model=model,
                token_target=token_target,
                overlap_tokens=overlap_tokens,
                symbol_kind=sym.kind,
                symbol_name=sym.name,
                symbol_path=sym.path,
            )
        )

    return chunks


def _build_chunks_for_text(
    text: str,
    *,
    base_start_row: int,
    tokenizer,
    model: str,
    token_target: int,
    overlap_tokens: int,
    symbol_kind: Optional[str],
    symbol_name: Optional[str],
    symbol_path: Optional[str],
) -> list[Chunk]:
    """Window text by tokens and convert to Chunk objects.

    - base_start_row: the 0-based starting row of the text within the source.
    - Maintains 1-based line numbers for returned Chunk.
    """
    windows = window_text_by_tokens(text, model=model, target=token_target, overlap=overlap_tokens)
    line_offsets = _build_line_offsets(text)

    chunks: list[Chunk] = []
    search_from = 0
    pos = 0  # expected start position of the next window in text
    for raw_text, start_char, end_char in windows:
        if not raw_text:
            continue
        abs_start_line = _offset_to_abs_line(base_start_row, line_offsets, start_char)
        abs_end_line = abs_start_line + raw_text.count("\n")

        trimmed_text, token_count, lead_newlines, trail_newlines = _trim_and_tokenize(raw_text, tokenizer)
        if not trimmed_text:
            continue
        adj_start = abs_start_line + lead_newlines
        adj_end = max(adj_start, abs_end_line - trail_newlines)

        chunks.append(
            Chunk(
                text=trimmed_text,
                start_line=adj_start,
                end_line=adj_end,
                token_count=token_count,
                symbol_kind=symbol_kind,
                symbol_name=symbol_name,
                symbol_path=symbol_path,
            )
        )

    return chunks


def _fallback_token_windows(
    source: str,
    *,
    model: str,
    token_target: int,
    overlap_pct: float,
) -> List[Chunk]:
    """Fallback chunking using token windows across the entire source."""
    tokenizer = get_tokenizer(model)
    if not (0.0 <= overlap_pct <= 1.0):
        overlap_pct = max(0.0, min(1.0, overlap_pct))
    overlap_tokens = max(0, min(int(token_target * overlap_pct), max(0, token_target - 1)))

    return _build_chunks_for_text(
        source,
        base_start_row=0,
        tokenizer=tokenizer,
        model=model,
        token_target=token_target,
        overlap_tokens=overlap_tokens,
        symbol_kind=None,
        symbol_name=None,
        symbol_path=None,
    )


def _build_line_offsets(text: str) -> List[int]:
    """Return character offsets where each line starts (0-based)."""
    offsets: List[int] = [0]
    for idx, ch in enumerate(text):
        if ch == "\n":
            offsets.append(idx + 1)
    return offsets


def _offset_to_abs_line(start_row: int, line_offsets: List[int], offset: int) -> int:
    """Convert a character offset within text to an absolute 1-based line number.

    start_row is 0-based row of the text's first line within the full source.
    """
    line_idx = bisect.bisect_right(line_offsets, offset) - 1
    return (start_row + LINE_NUMBER_BASE) + max(0, line_idx)


def _trim_and_tokenize(raw_text: str, tokenizer) -> Tuple[str, int, int, int]:
    """Trim leading and trailing newlines and count tokens.

    Returns (trimmed_text, token_count, leading_newlines, trailing_newlines).
    """
    lead_trim = len(raw_text) - len(raw_text.lstrip("\n"))
    trail_trim = len(raw_text) - len(raw_text.rstrip("\n"))
    trimmed = raw_text.strip("\n")
    if not trimmed:
        return "", 0, lead_trim, trail_trim
    token_count = count_tokens(trimmed, tokenizer)
    return trimmed, token_count, lead_trim, trail_trim


def _extract_symbols(root, source: str) -> List[Symbol]:
    """Extract TS/TSX/JS symbols.

    Captures:
    - class_declaration → kind='class', name='ClassName'
    - method_definition inside class → kind='method', path='Class.method'
    - class fields initialized with arrow functions → kind='method', path='Class.field'
    - function_declaration → kind='function', name='fn'
    - variable_declarator with function/arrow_function initializer → kind='function', name='constName'
    - assignment_expression with function/arrow_function RHS → kind='function', path='lhs'
    - interface_declaration → kind='interface', name='Iface'
    - type_alias_declaration → kind='type_alias', name='Alias'
    - enum_declaration → kind='enum', name='Enum'
    """
    results: List[Symbol] = []

    class_stack: List[str] = []

    def node_text(n) -> str:
        if n is None:
            return ""
        return source[n.start_byte:n.end_byte]

    def simple_name_from_path(path_text: str) -> Optional[str]:
        # Best-effort: take last identifier in a dotted path or plain identifier
        m = re.search(r"([A-Za-z_$][A-Za-z0-9_$]*)$", path_text)
        return m.group(1) if m else None

    def visit(node):  # noqa: C901 - traversal is a bit complex but contained
        ntype = node.type

        if ntype == "class_declaration":
            name_node = node.child_by_field_name("name")
            class_name = node_text(name_node) or None
            class_stack.append(class_name or "<class>")
            results.append(
                Symbol(
                    "class",
                    class_name,
                    class_name,
                    node.start_byte,
                    node.end_byte,
                    node.start_point[0],
                    node.end_point[0],
                )
            )
            # Recurse into class body
            for child in node.children:
                visit(child)
            class_stack.pop()
            return

        # Class fields that are initialized with arrow/function expressions (TS/JS)
        if ntype in ("public_field_definition", "field_definition", "property_declaration"):
            name_node = node.child_by_field_name("name")
            init_node = node.child_by_field_name("value") or node.child_by_field_name("initializer")
            if init_node is not None and init_node.type in ("arrow_function", "function"):
                fld_name = node_text(name_node) or None
                symbol_path = f"{class_stack[-1]}.{fld_name or '<field>'}" if class_stack else fld_name
                results.append(
                    Symbol(
                        "method",
                        fld_name,
                        symbol_path,
                        node.start_byte,
                        node.end_byte,
                        node.start_point[0],
                        node.end_point[0],
                    )
                )
            # Recurse
            for ch in node.children:
                visit(ch)
            return

        if ntype == "method_definition":
            # method name may be an identifier under 'name' field or a property_identifier child
            name_node = node.child_by_field_name("name")
            meth_name = node_text(name_node) or None
            if not meth_name:
                # Try property_identifier or identifier token
                for ch in node.children:
                    if ch.type in ("property_identifier", "identifier"):
                        meth_name = node_text(ch) or None
                        break
            symbol_path = f"{class_stack[-1]}.{meth_name or '<method>'}" if class_stack else meth_name
            results.append(
                Symbol(
                    "method",
                    meth_name,
                    symbol_path,
                    node.start_byte,
                    node.end_byte,
                    node.start_point[0],
                    node.end_point[0],
                )
            )
            # Recurse in case of nested declarations
            for child in node.children:
                visit(child)
            return

        if ntype == "function_declaration":
            name_node = node.child_by_field_name("name")
            func_name = node_text(name_node) or None
            results.append(
                Symbol(
                    "function",
                    func_name,
                    func_name,
                    node.start_byte,
                    node.end_byte,
                    node.start_point[0],
                    node.end_point[0],
                )
            )
            for child in node.children:
                visit(child)
            return

        # Interface, type alias, enum (TypeScript)
        if ntype == "interface_declaration":
            name_node = node.child_by_field_name("name")
            iface_name = node_text(name_node) or None
            results.append(
                Symbol(
                    "interface",
                    iface_name,
                    iface_name,
                    node.start_byte,
                    node.end_byte,
                    node.start_point[0],
                    node.end_point[0],
                )
            )
            for child in node.children:
                visit(child)
            return

        if ntype == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            alias_name = node_text(name_node) or None
            results.append(
                Symbol(
                    "type_alias",
                    alias_name,
                    alias_name,
                    node.start_byte,
                    node.end_byte,
                    node.start_point[0],
                    node.end_point[0],
                )
            )
            for child in node.children:
                visit(child)
            return

        if ntype == "enum_declaration":
            name_node = node.child_by_field_name("name")
            enum_name = node_text(name_node) or None
            results.append(
                Symbol(
                    "enum",
                    enum_name,
                    enum_name,
                    node.start_byte,
                    node.end_byte,
                    node.start_point[0],
                    node.end_point[0],
                )
            )
            for child in node.children:
                visit(child)
            return

        # Variable declarations (const/let/var) with function or arrow function initializers
        if ntype in ("lexical_declaration", "variable_statement"):
            for child in node.children:
                if child.type in ("variable_declarator", "variable_declaration"):
                    # variable_declarator (TS/JS) → name & initializer
                    name_node = child.child_by_field_name("name")
                    init_node = child.child_by_field_name("value") or child.child_by_field_name("initializer")
                    if init_node is not None and init_node.type in ("arrow_function", "function"):
                        const_name = node_text(name_node) or None
                        results.append(
                            Symbol(
                                "function",
                                const_name,
                                const_name,
                                child.start_byte,
                                child.end_byte,
                                child.start_point[0],
                                child.end_point[0],
                            )
                        )
            # Recurse
            for ch in node.children:
                visit(ch)
            return

        # Assignment: lhs = arrow_function | function
        if ntype == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if right is not None and right.type in ("arrow_function", "function"):
                lhs_text = node_text(left)
                simple = simple_name_from_path(lhs_text)
                results.append(
                    Symbol(
                        "function",
                        simple,
                        lhs_text or simple,
                        node.start_byte,
                        node.end_byte,
                        node.start_point[0],
                        node.end_point[0],
                    )
                )
            # Recurse
            for ch in node.children:
                visit(ch)
            return

        # Export default class/function (TS/JS)
        if ntype in ("export_statement", "export_declaration", "export_default_declaration"):
            for ch in node.children:
                visit(ch)
            return

        # Generic recursion
        for ch in node.children:
            visit(ch)

    visit(root)
    return results
