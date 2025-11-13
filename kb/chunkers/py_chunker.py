from __future__ import annotations

import bisect
import logging
import re
from typing import List, NamedTuple, Optional, Tuple

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

from .graph_types import GraphEdge, GraphNode
from .token_utils import count_tokens, get_tokenizer, window_text_by_tokens
from .types import Chunk

_log = logging.getLogger(__name__)

__all__ = ["chunk_source", "extract_graph_data"]

# Cache the Python parser so we don't reinitialize it per call
_PY_PARSER: Optional[Parser] = None


def _get_python_parser() -> Parser:
    """Return a cached tree-sitter Parser configured for Python.

    Uses tree-sitter 0.25+ API with Language wrapper.
    """
    global _PY_PARSER
    if _PY_PARSER is None:
        PY_LANGUAGE = Language(tspython.language())
        _PY_PARSER = Parser(PY_LANGUAGE)
    return _PY_PARSER


class Symbol(NamedTuple):
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
    model: str = "small",
    token_target: int = 400,
    overlap_pct: float = 0.10,
) -> list[Chunk]:
    """Chunk a Python source file into symbol-aware chunks using Tree-sitter.

    - Extract class/function/method symbols via Tree-sitter.
    - For each symbol, include full construct (signature + body); if large, window by tokens.
    - Map window texts back to 1-based line ranges using a line-start offsets index + bisect.
    - Trim leading/trailing newlines in each window; recompute token_count on trimmed text.
    - Fallback: if parse fails or no symbols, window the entire file.
    """
    try:
        source_bytes = source.encode("utf-8")
        parser = _get_python_parser()
        # Support both legacy and newer tree_sitter Parser APIs
        parse_fn = getattr(parser, "parse", None)
        if callable(parse_fn):
            tree = parse_fn(source_bytes)
        else:
            # Fallback for API variants (unlikely)
            tree = parser.parse_bytes(source_bytes)  # type: ignore[attr-defined]
        root = tree.root_node
    except Exception as e:
        _log.warning("Tree-sitter parse failed; falling back to token windows: %s", e)
        return _fallback_token_windows(
            source, model=model, token_target=token_target, overlap_pct=overlap_pct
        )

    symbols = list(_extract_symbols(root, source))

    if not symbols:
        return _fallback_token_windows(
            source, model=model, token_target=token_target, overlap_pct=overlap_pct
        )

    chunks: List[Chunk] = []
    tok = get_tokenizer(model)
    overlap = max(0, int(token_target * overlap_pct))

    for sym in symbols:
        kind, name, path, start_byte, end_byte, start_row, end_row = sym
        # Slice the full symbol text (signature + body)
        try:
            symbol_text = source_bytes[start_byte:end_byte].decode("utf-8")
        except Exception as e:
            _log.debug("Skipping symbol %s due to decode error: %s", name, e)
            continue

        # If symbol is small enough, emit as one chunk; else window
        windows = window_text_by_tokens(
            symbol_text, model=model, target=token_target, overlap=overlap
        )

        # Build line-start offsets for mapping within this construct
        line_offsets = _build_line_offsets(symbol_text)

        # Map each window to (start_line, end_line) within original file
        for raw_text, start_char, end_char in windows:
            if not raw_text:
                continue
            abs_start_line = _offset_to_abs_line(start_row, line_offsets, start_char)
            abs_end_line = abs_start_line + raw_text.count("\n")

            trimmed_text, token_count, lead_trim, trail_trim = _trim_and_tokenize(
                raw_text, tok
            )
            if not trimmed_text:
                continue

            adj_start = abs_start_line + lead_trim
            adj_end = max(adj_start, abs_end_line - trail_trim)

            chunks.append(
                Chunk(
                    text=trimmed_text,
                    start_line=adj_start,
                    end_line=adj_end,
                    token_count=token_count,
                    symbol_kind=kind,
                    symbol_name=name,
                    symbol_path=path,
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
    """Fallback: simple token-windowing across the entire file."""
    tok = get_tokenizer(model)
    overlap = max(0, int(token_target * overlap_pct))
    windows = window_text_by_tokens(
        source, model=model, target=token_target, overlap=overlap
    )
    # Build line-start offsets for entire file
    line_offsets = _build_line_offsets(source)

    chunks: List[Chunk] = []
    for raw_text, start_char, end_char in windows:
        if not raw_text:
            continue
        abs_start_line = _offset_to_abs_line(0, line_offsets, start_char)
        abs_end_line = abs_start_line + raw_text.count("\n")

        trimmed_text, token_count, lead_trim, trail_trim = _trim_and_tokenize(
            raw_text, tok
        )
        if not trimmed_text:
            continue

        adj_start = abs_start_line + lead_trim
        adj_end = max(adj_start, abs_end_line - trail_trim)

        chunks.append(
            Chunk(
                text=trimmed_text,
                start_line=adj_start,
                end_line=adj_end,
                token_count=token_count,
                symbol_kind=None,
                symbol_name=None,
                symbol_path=None,
            )
        )
    return chunks


def _build_line_offsets(text: str) -> List[int]:
    """Return character offsets where each line starts: offsets[i] = char index of line (i+1)."""
    offsets: List[int] = [0]
    for idx, ch in enumerate(text):
        if ch == "\n":
            offsets.append(idx + 1)
    return offsets


def _offset_to_abs_line(start_row: int, line_offsets: List[int], offset: int) -> int:
    """Convert a local character offset within a symbol to absolute 1-based line number."""
    line_idx = bisect.bisect_right(line_offsets, offset) - 1
    return (start_row + 1) + max(0, line_idx)


def _trim_and_tokenize(raw_text: str, tokenizer) -> Tuple[str, int, int, int]:
    """Trim leading/trailing newlines and compute token_count.

    Returns: (trimmed_text, token_count, lead_trim, trail_trim)
    """
    lead_trim = len(raw_text) - len(raw_text.lstrip("\n"))
    trail_trim = len(raw_text) - len(raw_text.rstrip("\n"))
    trimmed = raw_text.strip("\n")
    if not trimmed:
        return "", 0, lead_trim, trail_trim
    token_count = count_tokens(trimmed, tokenizer)
    return trimmed, token_count, lead_trim, trail_trim


def _extract_symbols(root, source: str) -> List[Symbol]:
    """Return list of symbols detected in the Python AST.

    - class_definition → kind='class', name='ClassName'
    - function_definition → kind='function'
    - function_definition inside class → kind='method', path='Class.method'
    """
    results: List[Symbol] = []

    class_stack: List[str] = []

    def visit(node):
        ntype = node.type
        # Enter class
        if ntype == "class_definition":
            name_node = node.child_by_field_name("name")
            class_name = None
            if name_node is not None:
                class_name = source[name_node.start_byte : name_node.end_byte]
            class_stack.append(class_name or "<class>")
            # Record class symbol itself
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
            # Visit children
            for child in node.children:
                visit(child)
            class_stack.pop()
            return

        if ntype == "function_definition":
            name_node = node.child_by_field_name("name")
            func_name = None
            if name_node is not None:
                func_name = source[name_node.start_byte : name_node.end_byte]
            if class_stack:
                # method
                symbol_path = f"{class_stack[-1]}.{func_name or '<method>'}"
                kind = "method"
            else:
                symbol_path = func_name
                kind = "function"
            results.append(
                Symbol(
                    kind,
                    func_name,
                    symbol_path,
                    node.start_byte,
                    node.end_byte,
                    node.start_point[0],
                    node.end_point[0],
                )
            )
            # Visit children anyway (nested defs)
            for child in node.children:
                visit(child)
            return

        # Generic recursion
        for child in node.children:
            visit(child)

    visit(root)
    return results


def extract_graph_data(source: str) -> Tuple[List[GraphNode], List[GraphEdge]]:
    """Extract graph nodes and edges from Python source for code graph.

    Nodes:
    - Classes, functions, methods

    Edges:
    - Imports (from X import Y, import X)
    - Function calls
    - Class inheritance
    - Decorator usage

    Args:
        source: Python source code

    Returns:
        Tuple of (nodes, edges) for graph database insertion
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    try:
        source_bytes = source.encode("utf-8")
        parser = _get_python_parser()
        parse_fn = getattr(parser, "parse", None)
        if callable(parse_fn):
            tree = parse_fn(source_bytes)
        else:
            tree = parser.parse_bytes(source_bytes)  # type: ignore[attr-defined]
        root = tree.root_node
    except Exception as e:
        _log.warning("Tree-sitter parse failed for graph extraction: %s", e)
        return [], []

    # Extract symbols as nodes
    symbols = list(_extract_symbols(root, source))
    for sym in symbols:
        nodes.append(
            GraphNode(
                node_type=sym.kind,
                name=sym.name or "",
                qualified_name=sym.path or sym.name or "",
                start_line=sym.start_row + 1,
                end_line=sym.end_row + 1,
            )
        )

    # Extract edges (imports, calls, inheritance)
    _extract_edges(root, source, edges)

    _log.debug(
        "Extracted %d graph nodes and %d edges from Python", len(nodes), len(edges)
    )
    return nodes, edges


def _extract_edges(root, source: str, edges: List[GraphEdge]):
    """Extract graph edges (imports, calls, inheritance) from Python AST."""

    def node_text(n) -> str:
        if n is None:
            return ""
        return source[n.start_byte : n.end_byte]

    def visit(node, current_context: Optional[str] = None):
        """Visit nodes and extract edges."""
        ntype = node.type

        # Track current class/function context
        if ntype == "class_definition":
            name_node = node.child_by_field_name("name")
            class_name = node_text(name_node) if name_node else None

            # Extract base classes (inheritance)
            arg_list = node.child_by_field_name("superclasses")
            if arg_list:
                for child in arg_list.children:
                    if child.type == "identifier" or child.type == "attribute":
                        base_class = node_text(child)
                        if base_class and class_name:
                            edges.append(
                                GraphEdge(
                                    source_name=class_name,
                                    target_name=base_class,
                                    edge_type="inherits",
                                    line_number=node.start_point[0] + 1,
                                )
                            )

            # Recurse with new context
            for child in node.children:
                visit(child, class_name)
            return

        if ntype == "function_definition":
            name_node = node.child_by_field_name("name")
            func_name = node_text(name_node) if name_node else None
            if current_context:
                qualified = (
                    f"{current_context}.{func_name}" if func_name else current_context
                )
            else:
                qualified: Optional[str] = func_name

            # Extract decorators
            for child in node.children:
                if child.type == "decorator":
                    # decorator node has a child that's the decorator name
                    for dec_child in child.children:
                        if dec_child.type in ("identifier", "attribute"):
                            decorator_name = node_text(dec_child)
                            if decorator_name and qualified:
                                edges.append(
                                    GraphEdge(
                                        source_name=qualified,
                                        target_name=decorator_name,
                                        edge_type="decorated_by",
                                        line_number=child.start_point[0] + 1,
                                    )
                                )

            # Recurse to find calls within function
            for child in node.children:
                visit(child, qualified)
            return

        # Import statements
        if ntype == "import_statement":
            # import X, Y, Z
            for child in node.children:
                if child.type == "dotted_name" or child.type == "identifier":
                    module_name = node_text(child)
                    edges.append(
                        GraphEdge(
                            source_name="<module>",
                            target_name=module_name,
                            edge_type="imports",
                            line_number=node.start_point[0] + 1,
                        )
                    )
            for child in node.children:
                visit(child, current_context)
            return

        if ntype == "import_from_statement":
            # from X import Y, Z
            module_node = node.child_by_field_name("module_name")
            module_name: Optional[str] = node_text(module_node) if module_node else None

            # Extract imported names
            for child in node.children:
                if child.type == "dotted_name" or child.type == "identifier":
                    imported = node_text(child)
                    if module_name and imported != module_name:
                        edges.append(
                            GraphEdge(
                                source_name="<module>",
                                target_name=f"{module_name}.{imported}",
                                edge_type="imports",
                                line_number=node.start_point[0] + 1,
                            )
                        )
            for child in node.children:
                visit(child, current_context)
            return

        # Function/method calls
        if ntype == "call":
            func_node = node.child_by_field_name("function")
            if func_node:
                called_name = node_text(func_node)
                if called_name and current_context:
                    edges.append(
                        GraphEdge(
                            source_name=current_context,
                            target_name=called_name,
                            edge_type="calls",
                            line_number=node.start_point[0] + 1,
                        )
                    )
            for child in node.children:
                visit(child, current_context)
            return

        # Generic recursion
        for child in node.children:
            visit(child, current_context)

    visit(root)
