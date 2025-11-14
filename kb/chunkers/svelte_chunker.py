"""Svelte component chunker with support for single-file components.

This module chunks Svelte .svelte files into logical units by parsing:
- <script> sections (using TypeScript chunker)
- <style> sections (kept as single chunks)
- Template sections (HTML markup with Svelte directives)

It also extracts graph data for component relationships, imports, stores, and props.

Architecture:
- HTML parser for component structure
- Delegates to ts_chunker for <script> sections
- Basic CSS extraction for <style> sections
- Template chunking by component usage and size
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser

from .graph_types import GraphEdge, GraphNode
from .token_utils import count_tokens, get_tokenizer
from .ts_chunker import chunk_source as chunk_typescript
from .types import Chunk

_log = logging.getLogger(__name__)

__all__ = ["chunk_source", "extract_graph_data"]


class SvelteComponentParser(HTMLParser):
    """Parse Svelte component structure into sections.

    Extracts:
    - <script> blocks (may be multiple if module context used)
    - <style> blocks
    - Template content (everything outside script/style)
    """

    def __init__(self):
        super().__init__()
        self.sections = {"script": [], "style": [], "template": []}
        self.current_section = None
        self.current_data = []
        self.current_attrs = {}
        self.line_tracker = 1
        self.section_lines = {}

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.current_section = tag
            self.current_data = []
            self.current_attrs = dict(attrs)
            self.section_lines[tag] = self.line_tracker

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.current_section == tag:
            content = "".join(self.current_data)
            self.sections[tag].append(
                {
                    "content": content,
                    "attrs": self.current_attrs,
                    "start_line": self.section_lines.get(tag, 1),
                }
            )
            self.current_section = None
            self.current_attrs = {}

    def handle_data(self, data):
        self.line_tracker += data.count("\n")

        if self.current_section:
            self.current_data.append(data)
        else:
            # Template content
            self.sections["template"].append(data)


def chunk_source(
    source: str,
    *,
    model: str = "small",
    token_target: int = 400,
    overlap_pct: float = 0.10,
) -> list[Chunk]:
    """Chunk Svelte component into logical units.

    Strategy:
    - Extract <script>, <style>, <template> sections
    - Chunk <script> using TypeScript chunker
    - Chunk template by component structure
    - Keep <style> as single chunk (usually small)

    Args:
        source: Svelte component source code
        model: Tokenizer model ("small" or "large")
        token_target: Target tokens per chunk
        overlap_pct: Overlap percentage (passed to TypeScript chunker)

    Returns:
        List of Chunk objects with Svelte metadata
    """
    if not source or not source.strip():
        return []

    chunks = []
    tok = get_tokenizer(model)

    # Parse component structure
    parser = SvelteComponentParser()
    try:
        parser.feed(source)
    except Exception as e:
        _log.warning("Svelte parser failed, using fallback: %s", e)
        return _fallback_chunking(source, model, token_target)

    current_line = 1

    # Chunk <script> section(s)
    for script_data in parser.sections["script"]:
        script_content = script_data["content"]
        script_start = script_data["start_line"]

        if not script_content.strip():
            continue

        # Check if this is a module script (context="module")
        is_module = script_data["attrs"].get("context") == "module"

        # Use TypeScript chunker for script content
        try:
            script_chunks = chunk_typescript(
                script_content,
                lang="typescript",  # Svelte typically uses TS syntax
                model=model,
                token_target=token_target,
                overlap_pct=overlap_pct,
            )
        except Exception as e:
            _log.warning("TypeScript chunker failed for Svelte script: %s", e)
            # Fallback: simple chunk
            token_count = count_tokens(script_content, tok)
            script_chunks = [
                Chunk(
                    text=script_content,
                    start_line=script_start,
                    end_line=script_start + script_content.count("\n"),
                    token_count=token_count,
                    symbol_kind="svelte_script",
                    symbol_name=None,
                    symbol_path=None,
                )
            ]

        # Adjust line numbers and symbol kinds
        for chunk in script_chunks:
            kind_prefix = "svelte_module_" if is_module else "svelte_script_"
            chunks.append(
                Chunk(
                    text=chunk.text,
                    start_line=script_start + chunk.start_line - 1,
                    end_line=script_start + chunk.end_line - 1,
                    token_count=chunk.token_count,
                    symbol_kind=(f"{kind_prefix}{chunk.symbol_kind}" if chunk.symbol_kind else f"{kind_prefix}code"),
                    symbol_name=chunk.symbol_name,
                    symbol_path=chunk.symbol_path,
                )
            )

        current_line = script_start + script_content.count("\n") + 1

    # Chunk <style> section (usually small, keep as single chunk)
    for style_data in parser.sections["style"]:
        style_content = style_data["content"]
        style_start = style_data["start_line"]

        if not style_content.strip():
            continue

        # Check if scoped
        is_scoped = "scoped" in style_data["attrs"]

        token_count = count_tokens(style_content, tok)
        chunks.append(
            Chunk(
                text=style_content,
                start_line=style_start,
                end_line=style_start + style_content.count("\n"),
                token_count=token_count,
                symbol_kind="svelte_style_scoped" if is_scoped else "svelte_style",
                symbol_name=None,
                symbol_path=None,
            )
        )
        current_line = style_start + style_content.count("\n") + 1

    # Chunk template section
    template = "".join(parser.sections["template"])
    if template.strip():
        # Extract component tags for metadata
        template_chunks = _chunk_template(template, current_line, tok, token_target)
        chunks.extend(template_chunks)

    if not chunks:
        _log.warning("No chunks extracted, using fallback")
        return _fallback_chunking(source, model, token_target)

    _log.info("Chunked Svelte component into %d chunks", len(chunks))
    return chunks


def _chunk_template(template: str, start_line: int, tokenizer, token_target: int) -> list[Chunk]:
    """Chunk Svelte template by component usage and control flow.

    Identifies:
    - Component usages (capitalized tags)
    - Control flow blocks ({#if}, {#each}, etc.)
    - Event handlers (on:click, etc.)
    """
    chunks = []

    # Extract component usages for metadata
    component_pattern = r"<([A-Z][A-Za-z0-9]*)[^>]*>"
    re.findall(component_pattern, template)

    # If template is small, keep as single chunk
    token_count = count_tokens(template, tokenizer)
    if token_count <= token_target:
        chunks.append(
            Chunk(
                text=template,
                start_line=start_line,
                end_line=start_line + template.count("\n"),
                token_count=token_count,
                symbol_kind="svelte_template",
                symbol_name=None,
                symbol_path=None,
            )
        )
    else:
        # Split into smaller chunks (simple line-based for now)
        lines = template.split("\n")
        chunk_lines = []
        chunk_start = start_line

        for i, line in enumerate(lines):
            chunk_lines.append(line)
            chunk_text = "\n".join(chunk_lines)

            if count_tokens(chunk_text, tokenizer) > token_target:
                if len(chunk_lines) > 1:
                    prev_text = "\n".join(chunk_lines[:-1])
                    chunks.append(
                        Chunk(
                            text=prev_text,
                            start_line=chunk_start,
                            end_line=chunk_start + len(chunk_lines) - 2,
                            token_count=count_tokens(prev_text, tokenizer),
                            symbol_kind="svelte_template",
                            symbol_name=None,
                            symbol_path=None,
                        )
                    )
                    chunk_start += len(chunk_lines) - 1
                    chunk_lines = [line]

        # Add final chunk
        if chunk_lines:
            chunk_text = "\n".join(chunk_lines)
            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_line=chunk_start,
                    end_line=chunk_start + len(chunk_lines) - 1,
                    token_count=count_tokens(chunk_text, tokenizer),
                    symbol_kind="svelte_template",
                    symbol_name=None,
                    symbol_path=None,
                )
            )

    return chunks


def _fallback_chunking(source: str, model: str, token_target: int) -> list[Chunk]:
    """Fallback: simple token-based chunking."""
    from .fallback_chunker import chunk_text

    return chunk_text(source, model=model, token_target=token_target)


def extract_graph_data(source: str, component_name: str) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Extract graph nodes and edges from Svelte component.

    Nodes:
    - Component itself
    - Exported functions/variables (props)
    - Stores

    Edges:
    - Component usage (<MyComponent>)
    - Imports (import statements)
    - Store subscriptions ($store)
    - Props (export let)
    - Events (createEventDispatcher)

    Args:
        source: Svelte component source code
        component_name: Name of the component (from filename)

    Returns:
        Tuple of (nodes, edges) for graph database insertion
    """
    nodes = []
    edges: list[GraphEdge] = []

    # Create node for the component itself
    nodes.append(
        GraphNode(
            node_type="svelte_component",
            name=component_name,
            qualified_name=component_name,
            start_line=1,
            end_line=source.count("\n") + 1,
        )
    )

    # Parse component
    parser = SvelteComponentParser()
    try:
        parser.feed(source)
    except Exception as e:
        _log.warning("Failed to parse Svelte for graph extraction: %s", e)
        return nodes, edges

    # Extract from script sections
    for script_data in parser.sections["script"]:
        script_content = script_data["content"]

        # 1. Extract imports
        import_pattern = r'import\s+(?:{[^}]+}|\*\s+as\s+\w+|\w+)\s+from\s+["\']([^"\']+)["\']'
        imports = re.findall(import_pattern, script_content)
        for imp in imports:
            # Extract component name from path
            imported = imp.split("/")[-1].replace(".svelte", "")
            edges.append(
                GraphEdge(
                    source_name=component_name,
                    target_name=imported,
                    edge_type="imports",
                    line_number=script_data["start_line"],
                )
            )

        # 2. Extract props (export let)
        prop_pattern = r"export\s+let\s+(\w+)"
        props = re.findall(prop_pattern, script_content)
        for prop in props:
            nodes.append(
                GraphNode(
                    node_type="prop",
                    name=prop,
                    qualified_name=f"{component_name}.{prop}",
                    start_line=script_data["start_line"],
                    end_line=script_data["start_line"],
                )
            )
            edges.append(
                GraphEdge(
                    source_name=component_name,
                    target_name=prop,
                    edge_type="accepts_prop",
                    line_number=script_data["start_line"],
                )
            )

        # 3. Extract stores (writable/readable/derived)
        store_pattern = r'(?:writable|readable|derived)\s*\(\s*["\']?(\w+)["\']?'
        stores = re.findall(store_pattern, script_content)
        for store in stores:
            nodes.append(
                GraphNode(
                    node_type="store",
                    name=store,
                    qualified_name=f"{component_name}.{store}",
                    start_line=script_data["start_line"],
                    end_line=script_data["start_line"],
                )
            )

        # 4. Extract store subscriptions ($store)
        subscription_pattern = r"\$(\w+)"
        subscriptions = re.findall(subscription_pattern, script_content)
        for sub in set(subscriptions):  # Deduplicate
            edges.append(
                GraphEdge(
                    source_name=component_name,
                    target_name=sub,
                    edge_type="subscribes_to",
                    line_number=script_data["start_line"],
                )
            )

    # 5. Extract component usage (search entire source to catch all usage)
    component_pattern = r"<([A-Z][A-Za-z0-9]*)[^>]*>"
    used_components = re.findall(component_pattern, source)
    for comp in set(used_components):  # Deduplicate
        edges.append(
            GraphEdge(
                source_name=component_name,
                target_name=comp,
                edge_type="uses_component",
                line_number=1,  # Template line tracking would require more complex parsing
            )
        )

    # Also check for store subscriptions in template (outside script)
    subscription_pattern = r"\$(\w+)"
    all_subscriptions = re.findall(subscription_pattern, source)
    script_subscriptions = set()
    for script_data in parser.sections["script"]:
        script_subs = re.findall(subscription_pattern, script_data["content"])
        script_subscriptions.update(script_subs)

    # Add subscriptions from template that weren't already added from script
    for sub in set(all_subscriptions) - script_subscriptions:
        edges.append(
            GraphEdge(
                source_name=component_name,
                target_name=sub,
                edge_type="subscribes_to",
                line_number=1,
            )
        )

    # 6. Extract event dispatches
    dispatch_pattern = r'dispatch\s*\(\s*["\'](\w+)["\']'
    events = re.findall(dispatch_pattern, source)
    for event in set(events):  # Deduplicate
        edges.append(
            GraphEdge(
                source_name=component_name,
                target_name=event,
                edge_type="dispatches_event",
                line_number=1,
            )
        )

    _log.debug(
        "Extracted %d graph nodes and %d edges from Svelte component",
        len(nodes),
        len(edges),
    )
    return nodes, edges
