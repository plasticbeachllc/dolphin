"""Unified Dolphin CLI - Main entry point for all dolphin commands.

This module provides a single entry point for all dolphin functionality,
including knowledge base management, API serving, and persona management.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Annotated, Any, TypedDict

import typer
import uvicorn

from kb.api_key import get_or_create_kb_api_key
from kb.config import ConfigNotFoundError, load_config
from kb.ingest.cli import (
    add_repo as kb_add_repo,
    index as kb_index,
    init as kb_init,
    list_files as kb_list_files,
    prune_ignored as kb_prune_ignored,
    rm_repo as kb_rm_repo,
    status as kb_status,
)
from kb.observability import StructuredLogger
from kb.store import SQLiteMetadataStore
from kb.terminal import print_hint, print_status


def get_version() -> str:
    """Get installed package version."""
    try:
        from importlib.metadata import version

        return version("pb-dolphin")
    except Exception:
        return "unknown"  # Fallback version


def version_callback(version: bool = False) -> None:
    """Show the dolphin version."""
    if version:
        typer.echo(f"🐬 dolphin version {get_version()}")
        raise typer.Exit()


# Create main Dolphin app
app = typer.Typer(
    name="dolphin",
    help="Unified CLI for 🐬 dolphin knowledge base and AI tools",
    add_completion=False,
    pretty_exceptions_enable=False,
)


@app.callback(invoke_without_command=True)
def dolphin_callback(
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit"),
):
    version_callback(version)


_log = StructuredLogger("kb.cli", {"component": "dolphin_cli"})
MAX_SNIPPET_LINES_DISPLAY = 8


# ==============================================================================
# Top-Level Knowledge Base Commands
# ==============================================================================


@app.command()
def init(
    config_path: Path | None = typer.Option(None, "--config", help="Optional config path."),
) -> None:
    """Initialize the knowledge store (config + SQLite + LanceDB collections)."""
    kb_init(config_path)

    # Ensure the shared KB API key exists for future processes
    try:
        get_or_create_kb_api_key()
    except Exception as exc:  # pragma: no cover - defensive logging
        _log.warning(
            "Failed to initialize KB API key",
            {"command": "init"},
            error=exc,
        )


@app.command()
def add_repo(
    name: str = typer.Argument(..., help="Logical name for the repository."),
    path: Path = typer.Argument(..., help="Absolute path to the repository root."),
) -> None:
    """Register or update a repository in the metadata store."""
    kb_add_repo(name=name, path=path)


@app.command()
def rm_repo(
    name: str = typer.Argument(..., help="Repository name to remove."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt."),
) -> None:
    """Remove a repository and all its data from the knowledge store."""
    kb_rm_repo(name=name, force=force)


@app.command()
def index(
    name: str = typer.Argument(..., help="Name of the repository to index."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run without persisting."),
    force: bool = typer.Option(False, "--force", help="Bypass clean working tree check."),
    full: bool = typer.Option(False, "--full", help="Process all files instead of incremental diff."),
    parallel: bool = typer.Option(True, "--parallel/--no-parallel", help="Use parallel indexing (default: True)."),
    workers: int | None = typer.Option(None, "--workers", "-w", help="Number of worker processes (default: auto)."),
) -> None:
    """Run the full indexing pipeline for the specified repository."""
    kb_index(name=name, dry_run=dry_run, force=force, full=full, parallel=parallel, workers=workers)


@app.command()
def status(
    name: str | None = typer.Argument(None, help="Optional repository name."),
) -> None:
    """Report knowledge store status with detailed repository listing."""
    kb_status(name)


@app.command()
def prune_ignored(
    name: str = typer.Argument(..., help="Repository name to clean up."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed without persisting."),
) -> None:
    """Remove chunks for files that match the ignore patterns."""
    kb_prune_ignored(name, dry_run)


@app.command()
def list_files(
    name: str = typer.Argument(..., help="Repository name."),
) -> None:
    """List all indexed files in a repository."""
    kb_list_files(name)


class _SearchArgs(TypedDict):
    """Shared keyword arguments for local and remote search functions."""

    query: str
    repos: list[str] | None
    path_prefix: list[str] | None
    exclude_paths: list[str] | None
    exclude_patterns: list[str] | None
    top_k: int
    score_cutoff: float
    max_snippets: int
    context_before: int
    context_after: int
    include_graph_context: bool


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query."),
    repos: list[str] | None = typer.Option(None, "--repo", "-r", help="Repository name(s) to search."),
    path_prefix: list[str] | None = typer.Option(None, "--path", "-p", help="Filter by path prefix."),
    exclude_paths: list[str] | None = typer.Option(None, "--exclude-path", help="Exclude path prefix."),
    exclude_patterns: list[str] | None = typer.Option(None, "--exclude-pattern", "-x", help="Exclude glob pattern."),
    lang: list[str] | None = typer.Option(None, "--lang", help="Language filter (py, ts, js, md, etc.)."),
    top_k: int = typer.Option(8, "--top-k", "-k", help="Number of results to return."),
    score_cutoff: float = typer.Option(0.0, "--score-cutoff", "-s", help="Minimum similarity score."),
    max_snippets: int = typer.Option(0, "--max-snippets", help="Number of hits to include snippets for."),
    context_before: int = typer.Option(0, "--context-before", help="Context lines before snippet match."),
    context_after: int = typer.Option(0, "--context-after", help="Context lines after snippet match."),
    include_graph_context: bool = typer.Option(
        False,
        "--graph-context/--no-graph-context",
        help="Include graph context in search hits.",
    ),
    local: bool = typer.Option(False, "--local", "-l", help="Use local backend (no server required)."),
    show_content: bool = typer.Option(False, "--show-content", "-c", help="Display snippets in terminal output."),
    verbose: bool = typer.Option(False, "--verbose", help="Show detailed hit metadata and snippets."),
    json_output: bool = typer.Option(False, "--json", help="Emit stable JSON output for scripting."),
    max_lines: int = typer.Option(
        MAX_SNIPPET_LINES_DISPLAY,
        "--max-lines",
        help="Maximum snippet lines to display per hit (default: 8).",
    ),
) -> None:
    """Search indexed code semantically.

    Examples:
        dolphin search "authentication logic" --repo myapp --top-k 5
        dolphin search "database migration" --path src/db --exclude-pattern "*.test.ts"
        dolphin search "oauth callback" --lang py --verbose
        dolphin search "cache invalidation" --json
    """
    normalized_langs = [_normalize_lang_token(item) for item in (lang or []) if item and item.strip()]

    # If language filtering is requested, fetch a broader candidate set and trim post-filter.
    request_top_k = top_k
    if normalized_langs:
        request_top_k = min(max(top_k * 5, top_k), 100)

    snippet_limit = max_snippets
    if snippet_limit <= 0 and (show_content or verbose):
        snippet_limit = min(top_k, 3)

    _common_search_args: _SearchArgs = {
        "query": query,
        "repos": repos,
        "path_prefix": path_prefix,
        "exclude_paths": exclude_paths,
        "exclude_patterns": exclude_patterns,
        "top_k": request_top_k,
        "score_cutoff": score_cutoff,
        "max_snippets": snippet_limit,
        "context_before": context_before,
        "context_after": context_after,
        "include_graph_context": include_graph_context,
    }

    result: tuple[list[dict[str, object]], dict[str, object], SQLiteMetadataStore | None] | None = None

    if not local:
        result = _search_remote(**_common_search_args)
        if result is None:
            _log.debug("Server unavailable, falling back to local search")

    if local or result is None:
        hits, meta, sql_store = _search_local(**_common_search_args)
    else:
        hits, meta, sql_store = result

    if normalized_langs:
        hits = _apply_language_filter(hits, normalized_langs)

    # Always trim back to user-requested top_k after optional post-filters.
    hits = hits[:top_k]

    if (show_content or verbose or json_output) and sql_store is not None:
        _hydrate_missing_content(hits, sql_store)

    if json_output:
        _emit_search_json(
            query=query,
            hits=hits,
            meta=meta,
            local=local,
            repos=repos,
            path_prefix=path_prefix,
            exclude_paths=exclude_paths,
            exclude_patterns=exclude_patterns,
            languages=normalized_langs,
            top_k=top_k,
        )
        return

    _display_results(
        query=query,
        hits=hits,
        show_content=show_content,
        verbose=verbose,
        meta=meta,
        languages=normalized_langs,
        max_lines=max(1, max_lines),
    )


def _search_local(
    *,
    query: str,
    repos: list[str] | None,
    path_prefix: list[str] | None,
    exclude_paths: list[str] | None,
    exclude_patterns: list[str] | None,
    top_k: int,
    score_cutoff: float,
    max_snippets: int,
    context_before: int,
    context_after: int,
    include_graph_context: bool,
) -> tuple[list[dict[str, object]], dict[str, object], SQLiteMetadataStore | None]:
    """Search using local backend without API server."""
    from kb.api.app import SearchRequest
    from kb.api.search_backend import create_search_backend
    from kb.config import load_config

    config = load_config()

    try:
        # Create search backend
        backend = create_search_backend(
            store_root=config.resolved_store_root(),
            embedding_provider_type=config.embedding_provider,
            hybrid_search_enabled=True,
        )

        # Suppress verbose structured logs from the search backend in CLI mode
        # unless the user explicitly opted into a log level via DOLPHIN_LOG_LEVEL.
        # We set the level on the stdlib logger directly (backend.logger.logger)
        # after creation, which overrides the default INFO that StructuredLogger sets.
        if not os.environ.get("DOLPHIN_LOG_LEVEL", "").strip():
            backend.logger.logger.setLevel(logging.WARNING)

        # Create search request
        request = SearchRequest(
            query=query,
            repos=repos,
            path_prefix=path_prefix,
            exclude_paths=exclude_paths,
            exclude_patterns=exclude_patterns,
            top_k=top_k,
            score_cutoff=score_cutoff,
            max_snippets=max_snippets,
            context_lines_before=context_before,
            context_lines_after=context_after,
            include_graph_context=include_graph_context,
        )

        # Execute search
        hits, next_cursor = backend.search(request)
        result_hits = list(hits)

        # Enrich hits with snippets (mirrors the API layer in app.py)
        if max_snippets > 0 and backend.sql_store is not None:
            from kb.api.app import _enrich_hits_with_snippets

            snippet_limit = max(0, min(max_snippets, len(result_hits)))
            result_hits[:snippet_limit] = _enrich_hits_with_snippets(
                result_hits[:snippet_limit], request, backend.sql_store
            )

        meta = {
            "top_k": top_k,
            "max_snippets": max_snippets,
            "context_before": context_before,
            "context_after": context_after,
            "include_graph_context": include_graph_context,
            "model": config.default_embed_model,
            "next_cursor": next_cursor,
        }
        return result_hits, meta, backend.sql_store

    except Exception as e:
        typer.echo(f"Error: Local search failed: {e}", err=True)
        raise typer.Exit(1)


def _search_remote(
    *,
    query: str,
    repos: list[str] | None,
    path_prefix: list[str] | None,
    exclude_paths: list[str] | None,
    exclude_patterns: list[str] | None,
    top_k: int,
    score_cutoff: float,
    max_snippets: int,
    context_before: int,
    context_after: int,
    include_graph_context: bool,
) -> tuple[list[dict[str, object]], dict[str, object], SQLiteMetadataStore | None] | None:
    """Search using remote API server. Returns None on connection failure."""
    import requests
    import requests.exceptions  # Import the exceptions module explicitly

    from kb.api_key import load_kb_api_key
    from kb.config import load_config

    config = load_config()
    endpoint = f"http://{config.endpoint}/v1/search"

    payload = {
        "query": query,
        "top_k": top_k,
        "score_cutoff": score_cutoff,
        "max_snippets": max_snippets,
        "context_lines_before": context_before,
        "context_lines_after": context_after,
        "include_graph_context": include_graph_context,
    }

    if repos:
        payload["repos"] = repos
    if path_prefix:
        payload["path_prefix"] = path_prefix
    if exclude_paths:
        payload["exclude_paths"] = exclude_paths
    if exclude_patterns:
        payload["exclude_patterns"] = exclude_patterns

    try:
        api_key = load_kb_api_key()
        if not api_key:
            typer.echo(
                "Error: No KB API key configured. Set DOLPHIN_API_KEY (or DOLPHIN_KB_API_KEY) to match the server.",
                err=True,
            )
            raise typer.Exit(1)

        response = requests.post(
            endpoint,
            json=payload,
            headers={"X-API-Key": api_key},
            timeout=30,
        )
        response.raise_for_status()

        result = response.json()
        hits = result.get("hits", [])
        raw_meta = result.get("meta", {})
        meta = dict(raw_meta) if isinstance(raw_meta, dict) else {}
        meta.setdefault("top_k", top_k)
        meta.setdefault("max_snippets", max_snippets)
        meta.setdefault("context_before", context_before)
        meta.setdefault("context_after", context_after)
        meta.setdefault("include_graph_context", include_graph_context)
        return list(hits), meta, None

    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.RequestException as e:
        typer.echo(f"Error: Search request failed: {e}", err=True)
        raise typer.Exit(1)


_LANG_ALIASES: dict[str, str] = {
    "py": "python",
    "python": "python",
    "ts": "typescript",
    "typescript": "typescript",
    "js": "javascript",
    "javascript": "javascript",
    "jsx": "javascript",
    "tsx": "typescript",
    "md": "markdown",
    "markdown": "markdown",
    "sql": "sql",
    "svelte": "svelte",
}


def _normalize_lang_token(value: str) -> str:
    token = value.strip().lower()
    return _LANG_ALIASES.get(token, token)


def _detect_hit_language(hit: dict[str, object]) -> str:
    language = hit.get("language") or hit.get("lang")
    if isinstance(language, str) and language.strip():
        return _normalize_lang_token(language)

    from kb.chunkers.registry import detect_language_from_extension

    path = str(hit.get("path") or hit.get("file_path") or "")
    detected = detect_language_from_extension(Path(path))
    if isinstance(detected, str) and detected:
        return _normalize_lang_token(detected)
    return "unknown"


def _apply_language_filter(hits: list[dict[str, object]], languages: list[str]) -> list[dict[str, object]]:
    if not languages:
        return hits
    wanted = set(languages)
    return [hit for hit in hits if _detect_hit_language(hit) in wanted]


def _hydrate_missing_content(hits: list[dict[str, object]], sql_store: SQLiteMetadataStore) -> None:
    chunk_ids: list[str] = []
    for hit in hits:
        if hit.get("content"):
            continue
        chunk_id = hit.get("chunk_id")
        if isinstance(chunk_id, str) and chunk_id:
            chunk_ids.append(chunk_id)

    if not chunk_ids:
        return

    content_map = sql_store.get_chunk_contents(chunk_ids)
    for hit in hits:
        if hit.get("content"):
            continue
        chunk_id = hit.get("chunk_id")
        if isinstance(chunk_id, str) and chunk_id in content_map:
            hit["content"] = content_map[chunk_id]


def _emit_search_json(
    *,
    query: str,
    hits: list[dict[str, object]],
    meta: dict[str, object],
    local: bool,
    repos: list[str] | None,
    path_prefix: list[str] | None,
    exclude_paths: list[str] | None,
    exclude_patterns: list[str] | None,
    languages: list[str],
    top_k: int,
) -> None:
    normalized_hits: list[dict[str, object]] = []
    for idx, hit in enumerate(hits, start=1):
        normalized: dict[str, object] = {
            "rank": idx,
            "chunk_id": hit.get("chunk_id"),
            "repo": hit.get("repo"),
            "path": hit.get("path") or hit.get("file_path"),
            "file_path": hit.get("file_path") or hit.get("path"),
            "start_line": hit.get("start_line"),
            "end_line": hit.get("end_line"),
            "score": hit.get("score"),
            "language": _detect_hit_language(hit),
            "symbol_kind": hit.get("symbol_kind"),
            "symbol_name": hit.get("symbol_name"),
            "symbol_path": hit.get("symbol_path"),
            "text_hash": hit.get("text_hash"),
            "commit": hit.get("commit"),
            "branch": hit.get("branch"),
            "token_count": hit.get("token_count"),
            "resource_link": hit.get("resource_link"),
            "content": hit.get("content"),
            "snippet": hit.get("snippet"),
        }
        graph_context = hit.get("graph_context")
        if graph_context is not None:
            normalized["graph_context"] = graph_context
        normalized_hits.append(normalized)

    payload = {
        "query": query,
        "mode": "local" if local else "remote",
        "result_count": len(normalized_hits),
        "filters": {
            "repos": repos or [],
            "path_prefix": path_prefix or [],
            "exclude_paths": exclude_paths or [],
            "exclude_patterns": exclude_patterns or [],
            "lang": languages,
            "top_k": top_k,
        },
        "meta": meta,
        "hits": normalized_hits,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _extract_snippet_text(hit: dict[str, object], show_content: bool, verbose: bool) -> str | None:
    """Extract displayable snippet text from a search hit."""
    if not (show_content or verbose):
        return None
    snippet_obj = hit.get("snippet")
    content = hit.get("content")
    snippet_text = None
    if isinstance(snippet_obj, dict) and "text" in snippet_obj:
        # snippet_obj is typed as object; after isinstance narrowing, ty still
        # sees dict[Unknown, Unknown].  The explicit key check above makes
        # the subscript safe at runtime.
        snippet_text = snippet_obj["text"]  # type: ignore[index]
    if not snippet_text and isinstance(content, str):
        snippet_text = content
    if isinstance(snippet_text, str) and snippet_text.strip():
        return snippet_text
    return None


_LANGUAGE_TO_LEXER_OVERRIDES: dict[str, str] = {
    "svelte": "html",
    "shell": "bash",
}


def _rich_lexer_for_language(language: str) -> str:
    """Map dolphin language names to Pygments lexer names."""
    lang = language.lower()
    return _LANGUAGE_TO_LEXER_OVERRIDES.get(lang, lang)


def _score_style(score: float) -> str:
    """Return a rich style string based on score value."""
    if score >= 0.7:
        return "bold sea_green2"
    if score >= 0.4:
        return "dark_goldenrod"
    return "dim"


def _render_graph_context_rich(graph_ctx: dict[str, Any], renderables: list[Any]) -> None:
    """Append graph context renderables (nodes + relationships) to the panel body."""
    from rich.markup import escape
    from rich.text import Text

    nodes: list[dict[str, Any]] = graph_ctx.get("nodes") or []
    relationships: list[dict[str, Any]] = graph_ctx.get("relationships") or []

    if nodes:
        header = Text.from_markup("[bold steel_blue1]Graph Context[/bold steel_blue1]")
        renderables.append(header)
        for node in nodes:
            ntype = node.get("type", "")
            qname = node.get("qualified_name") or node.get("name", "")
            sig = node.get("signature", "")
            lr = node.get("line_range")
            parts = [f"[cyan]{escape(str(ntype))}[/cyan] [bold]{escape(str(qname))}[/bold]"]
            if sig:
                parts.append(f"[dim]{escape(str(sig))}[/dim]")
            if isinstance(lr, (list, tuple)) and len(lr) == 2:
                parts.append(f"[dim]L{lr[0]}-{lr[1]}[/dim]")
            renderables.append(Text.from_markup("  " + "  ".join(parts)))

    if relationships:
        renderables.append(Text.from_markup("[bold]Relationships[/bold]"))
        for rel in relationships:
            rtype = rel.get("type", "")
            direction = rel.get("direction", "")
            if direction == "outgoing":
                target: dict[str, Any] = rel.get("target") or {}
                tname = target.get("qualified_name") or target.get("name", "")
                arrow = "\u2192"
            elif direction == "incoming":
                source: dict[str, Any] = rel.get("source") or {}
                tname = source.get("qualified_name") or source.get("name", "")
                arrow = "\u2190"
            else:
                continue
            line_num = rel.get("line_number")
            line_part = f" [dim]L{line_num}[/dim]" if line_num is not None else ""
            markup = f"  [dim]{escape(str(rtype))}[/dim] {arrow} [bold]{escape(str(tname))}[/bold]{line_part}"
            renderables.append(Text.from_markup(markup))


def _render_graph_context_plain(graph_ctx: dict[str, Any]) -> None:
    """Print graph context in plain text for non-TTY output."""
    nodes: list[dict[str, Any]] = graph_ctx.get("nodes") or []
    relationships: list[dict[str, Any]] = graph_ctx.get("relationships") or []

    if nodes:
        typer.echo("   Graph Context:")
        for node in nodes:
            ntype = node.get("type", "")
            qname = node.get("qualified_name") or node.get("name", "")
            sig = node.get("signature", "")
            lr = node.get("line_range")
            line_part = f" L{lr[0]}-{lr[1]}" if isinstance(lr, (list, tuple)) and len(lr) == 2 else ""
            sig_part = f" - {sig}" if sig else ""
            typer.echo(f"     {ntype} {qname}{sig_part}{line_part}")

    if relationships:
        typer.echo("   Relationships:")
        for rel in relationships:
            rtype = rel.get("type", "")
            direction = rel.get("direction", "")
            if direction == "outgoing":
                target: dict[str, Any] = rel.get("target") or {}
                tname = target.get("qualified_name") or target.get("name", "")
                arrow = "->"
            elif direction == "incoming":
                source: dict[str, Any] = rel.get("source") or {}
                tname = source.get("qualified_name") or source.get("name", "")
                arrow = "<-"
            else:
                continue
            line_num = rel.get("line_number")
            line_part = f" L{line_num}" if line_num is not None else ""
            typer.echo(f"     {rtype} {arrow} {tname}{line_part}")


def _display_results(
    *,
    query: str,
    hits: list[dict[str, object]],
    show_content: bool,
    verbose: bool,
    meta: dict[str, object],
    languages: list[str],
    max_lines: int = MAX_SNIPPET_LINES_DISPLAY,
) -> None:
    """Display search results using rich panels with syntax highlighting.

    Falls back to plain text when stdout is not a TTY (for piping/scripting).
    """
    from kb.terminal import STDOUT_CONSOLE, is_tty

    if not is_tty():
        _display_results_plain(
            query=query,
            hits=hits,
            show_content=show_content,
            verbose=verbose,
            meta=meta,
            languages=languages,
            max_lines=max_lines,
        )
        return

    from pygments.util import ClassNotFound
    from rich.console import Group, RenderableType
    from rich.markup import escape
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text

    console = STDOUT_CONSOLE

    if not hits:
        console.print()
        console.print("[dim]No results found.[/dim]")
        print_hint("Try broadening your query, removing filters, or indexing more repositories.")
        return

    safe_query = escape(query)
    count = len(hits)
    plural = "s" if count != 1 else ""
    console.print(f'\nFound [bold]{count}[/bold] result{plural} for [steel_blue1]"{safe_query}"[/steel_blue1]')
    if languages:
        console.print(f"[dim]Language filter: {', '.join(languages)}[/dim]")
    if verbose and meta:
        top_k = meta.get("top_k")
        model = meta.get("model")
        latency = meta.get("latency_ms")
        console.print(f"[dim]Meta: top_k={top_k} model={escape(str(model))} latency_ms={latency}[/dim]")
    console.print()

    for i, hit in enumerate(hits, 1):
        score_value = hit.get("score", 0.0)
        score = float(score_value) if isinstance(score_value, (int, float)) else 0.0
        repo = str(hit.get("repo", "unknown"))
        path = str(hit.get("path") or hit.get("file_path") or "unknown")
        start_line = hit.get("start_line")
        end_line = hit.get("end_line")
        language = _detect_hit_language(hit)
        symbol_name = hit.get("symbol_name")
        symbol_kind = hit.get("symbol_kind")

        # Build location string
        if isinstance(start_line, int) and isinstance(end_line, int):
            location = f"{repo}/{path}:{start_line}-{end_line}"
        else:
            location = f"{repo}/{path}"

        # Panel title and subtitle
        style = _score_style(score)
        title = f"[bold]{i}. {escape(location)}[/bold]"
        subtitle = f"[{style}]{score:.2f}[/{style}]"

        # Build panel body
        renderables: list[RenderableType] = []

        # Symbol + language info line
        info_parts: list[str] = []
        if isinstance(symbol_name, str) and symbol_name:
            kind_label = str(symbol_kind) if symbol_kind else "symbol"
            info_parts.append(f"[cyan]{escape(kind_label)}:{escape(symbol_name)}[/cyan]")
        info_parts.append(f"[dim]{escape(language)}[/dim]")

        if verbose:
            chunk_id = hit.get("chunk_id")
            if chunk_id:
                info_parts.append(f"[dim]chunk_id={escape(str(chunk_id))}[/dim]")
            resource_link = hit.get("resource_link")
            if resource_link:
                info_parts.append(f"[dim]resource={escape(str(resource_link))}[/dim]")

        renderables.append(Text.from_markup("  ".join(info_parts)))

        # Code snippet
        snippet_text = _extract_snippet_text(hit, show_content, verbose)
        if snippet_text:
            lines = snippet_text.splitlines()
            display_lines = lines[:max_lines]
            code = "\n".join(display_lines)
            if len(lines) > max_lines:
                code += f"\n... ({len(lines) - max_lines} more lines)"

            lexer = _rich_lexer_for_language(language)
            try:
                syntax = Syntax(code, lexer, theme="one-dark", line_numbers=False, word_wrap=True)
            except ClassNotFound:
                syntax = Syntax(code, "text", theme="one-dark", line_numbers=False, word_wrap=True)
            renderables.append(syntax)

        # Graph context (only present when --graph-context is used)
        graph_ctx = hit.get("graph_context")
        if isinstance(graph_ctx, dict) and (graph_ctx.get("nodes") or graph_ctx.get("relationships")):
            renderables.append(Text(""))  # blank line separator
            _render_graph_context_rich(graph_ctx, renderables)

        console.print(Panel(Group(*renderables), title=title, subtitle=subtitle, expand=True, padding=(0, 1)))

    if not verbose:
        print_hint("pass --verbose for chunk IDs and metadata.")


def _display_results_plain(
    *,
    query: str,
    hits: list[dict[str, object]],
    show_content: bool,
    verbose: bool,
    meta: dict[str, object],
    languages: list[str],
    max_lines: int = MAX_SNIPPET_LINES_DISPLAY,
) -> None:
    """Plain-text fallback for non-TTY output (piping, scripts)."""
    if not hits:
        typer.echo("No results found.")
        return

    typer.echo(f'Found {len(hits)} result(s) for "{query}"')
    if languages:
        typer.echo(f"Language filter: {', '.join(languages)}")
    if verbose and meta:
        top_k = meta.get("top_k")
        model = meta.get("model")
        latency = meta.get("latency_ms")
        typer.echo(f"Meta: top_k={top_k} model={model} latency_ms={latency}")
    typer.echo()

    for i, hit in enumerate(hits, 1):
        score_value = hit.get("score", 0.0)
        score = float(score_value) if isinstance(score_value, (int, float)) else 0.0
        repo = str(hit.get("repo", "unknown"))
        path = str(hit.get("path") or hit.get("file_path") or "unknown")
        start_line = hit.get("start_line")
        end_line = hit.get("end_line")
        language = _detect_hit_language(hit)
        symbol_name = hit.get("symbol_name")
        symbol_kind = hit.get("symbol_kind")
        symbol_part = ""
        if isinstance(symbol_name, str) and symbol_name:
            symbol_label = str(symbol_kind) if symbol_kind else "symbol"
            symbol_part = f"{symbol_label}:{symbol_name}"

        if isinstance(start_line, int) and isinstance(end_line, int):
            location = f"{repo}/{path}:{start_line}-{end_line}"
        else:
            location = f"{repo}/{path}"

        extras = [f"score={score:.4f}", f"lang={language}"]
        if symbol_part:
            extras.append(symbol_part)
        typer.echo(f"{i}. {location}  " + "  ".join(extras))

        if verbose:
            chunk_id = hit.get("chunk_id")
            if chunk_id:
                typer.echo(f"   chunk_id={chunk_id}")
            resource_link = hit.get("resource_link")
            if resource_link:
                typer.echo(f"   resource={resource_link}")

        snippet_text = _extract_snippet_text(hit, show_content=show_content, verbose=verbose)
        if snippet_text:
            lines = snippet_text.splitlines()
            typer.echo("   ---")
            for line in lines[:max_lines]:
                typer.echo(f"   {line}")
            if len(lines) > max_lines:
                typer.echo(f"   ... ({len(lines) - max_lines} more lines)")
            typer.echo("   ---")

        # Graph context (only present when --graph-context is used)
        graph_ctx = hit.get("graph_context")
        if isinstance(graph_ctx, dict) and (graph_ctx.get("nodes") or graph_ctx.get("relationships")):
            typer.echo("")
            _render_graph_context_plain(graph_ctx)

    if not verbose:
        typer.echo("\nTip: pass --verbose for chunk IDs and metadata.")


@app.command()
def repos(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output for scripting."),
) -> None:
    """List all registered repositories."""
    config = load_config()
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
    metadata.initialize()

    all_repos = metadata.list_all_repos()
    if not all_repos:
        if json_output:
            typer.echo(json.dumps({"repos": []}))
        else:
            typer.echo("No repositories registered.")
        return

    if json_output:
        all_counts = metadata.get_all_repo_counts()
        repo_list = []
        for repo in all_repos:
            counts = all_counts.get(repo["id"], {"files": 0, "chunks": 0})
            repo_list.append(
                {
                    "name": repo["name"],
                    "root_path": repo["root_path"],
                    "default_embed_model": repo["default_embed_model"],
                    "files": counts["files"],
                    "chunks": counts["chunks"],
                }
            )
        typer.echo(json.dumps({"repos": repo_list}, indent=2))
    else:
        typer.echo(f"\nRegistered Repositories ({len(all_repos)}):\n")
        for repo in all_repos:
            typer.echo(f"  - {repo['name']}")
            typer.echo(f"    Path: {repo['root_path']}")
            typer.echo(f"    Model: {repo['default_embed_model']}")
            typer.echo(f"    ID: {repo['id']}")
            typer.echo()


@app.command()
def chunk(
    chunk_id: str = typer.Argument(..., help="The chunk ID to fetch."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output for scripting."),
) -> None:
    """Fetch a chunk by its ID and display its content."""
    config = load_config()
    store_root = config.resolved_store_root()
    metadata = SQLiteMetadataStore(store_root / "metadata.db")
    metadata.initialize()

    chunk_meta = metadata.get_chunk_by_id(chunk_id)
    if not chunk_meta:
        if json_output:
            typer.echo(json.dumps({"error": f"Chunk not found: {chunk_id}"}))
        else:
            typer.echo(f"Error: Chunk not found: {chunk_id}", err=True)
        raise typer.Exit(1)

    content_map = metadata.get_chunk_contents([chunk_id])
    content = content_map.get(chunk_id, "")

    repo_name = chunk_meta.get("repo_name")
    file_path = chunk_meta.get("path", "")

    if json_output:
        payload = {
            "chunk_id": chunk_meta["chunk_id"],
            "repo": repo_name,
            "path": chunk_meta.get("path"),
            "start_line": chunk_meta.get("start_line"),
            "end_line": chunk_meta.get("end_line"),
            "language": chunk_meta.get("language"),
            "symbol_kind": chunk_meta.get("symbol_kind"),
            "symbol_name": chunk_meta.get("symbol_name"),
            "symbol_path": chunk_meta.get("symbol_path"),
            "content": content,
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        start = chunk_meta.get("start_line", "?")
        end = chunk_meta.get("end_line", "?")
        lang = chunk_meta.get("language") or ""
        location = f"{repo_name or '?'}/{file_path}:{start}-{end}"
        typer.echo(f"Chunk: {chunk_id}")
        typer.echo(f"Location: {location}")
        if chunk_meta.get("symbol_name"):
            typer.echo(f"Symbol: {chunk_meta.get('symbol_kind', '')}:{chunk_meta['symbol_name']}")
        typer.echo()
        if content:
            typer.echo(f"```{lang}")
            typer.echo(content)
            typer.echo("```")
        else:
            typer.echo("(no content available)")


@app.command()
def reset_all(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt."),
) -> None:
    """Reset the entire knowledge store (delete everything).

    WARNING: This will remove ALL repositories and data.
    Configuration will be preserved.
    """
    from kb.ingest.cli import reset_all as kb_reset_all

    kb_reset_all(force=force)


# ==============================================================================
# Core Service Commands
# ==============================================================================


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host", help="Host to bind to")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Port to bind to")] = 7777,
    watch: Annotated[list[str] | None, typer.Option("--watch", help="Repositories to watch")] = None,
    no_watch: bool = typer.Option(False, "--no-watch", help="Disable automatic file watching"),
) -> None:
    """Start the dolphin API server."""

    # Configure watcher environment variables BEFORE starting uvicorn
    # Default behavior: watch all repos unless disabled or specific repos requested
    repo_list: list[str] = []

    if no_watch:
        # Explicitly disabled
        repo_list = []
    elif watch:
        # User specified specific repos
        repo_list = [r for r in watch if r.strip()]
    else:
        # Default: watch all registered repos
        try:
            config = load_config()
            metadata = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
            metadata.initialize()
            repos = metadata.list_all_repos()
            repo_list = [repo["name"] for repo in repos]

            # Warn about embedding model mismatches
            config_model = config.default_embed_model
            for repo in repos:
                repo_model = repo.get("default_embed_model", "large")
                if repo_model != config_model:
                    print_status(
                        f"Embedding model changed for '{repo['name']}': "
                        f"indexed with '{repo_model}', config now '{config_model}'. "
                        f"Will re-index automatically on startup.",
                        level="warn",
                    )
        except ConfigNotFoundError:
            raise
        except Exception as e:
            print_status(
                "Failed to list repositories for automatic watcher startup.",
                level="warn",
                context={"error": str(e)},
            )

    # Deduplicate
    repo_list = sorted(list(set(repo_list)))

    if repo_list:
        os.environ["DOLPHIN_WATCH_REPOS"] = ",".join(repo_list)
        print_status(
            "Configured repository watchers.",
            level="success",
            context={"repos": ",".join(repo_list)},
        )
    elif "DOLPHIN_WATCH_REPOS" in os.environ:
        # If no repos to watch, clear the env var to prevent inheriting it
        del os.environ["DOLPHIN_WATCH_REPOS"]
        print_status("Watcher configuration cleared (no repositories selected).", level="info")

    if not os.environ.get("DOLPHIN_API_KEY") and not os.environ.get("DOLPHIN_KB_API_KEY"):
        os.environ["DOLPHIN_API_KEY"] = get_or_create_kb_api_key()
        print_status("Generated per-user API key for local server start.", level="success")

    print_status(
        "Starting API server.",
        level="step",
        context={"host": host, "port": port},
    )
    uvicorn.run("kb.api.server:app_with_lifespan", host=host, port=port, reload=False)


async def _watch_repo(repo_name: str) -> None:
    """Async implementation of watch command."""
    try:
        from kb.config import load_config
        from kb.ingest.pipeline import IngestionPipeline
        from kb.ingest.watcher import RepoWatcher
        from kb.store import LanceDBStore, SQLiteMetadataStore
        from kb.store.graph_store import GraphStore

        config = load_config()

        # Construct proper paths for store initialization
        store_root = config.resolved_store_root()
        lancedb_path = store_root / "lancedb"
        metadata_path = store_root / "metadata.db"

        # Initialize stores with proper paths
        lancedb = LanceDBStore(lancedb_path)
        metadata = SQLiteMetadataStore(metadata_path)

        # Initialize pipeline
        pipeline = IngestionPipeline(
            config=config, lancedb=lancedb, metadata=metadata, graph_store=GraphStore(metadata_path)
        )

        watcher = RepoWatcher(repo_name, config, pipeline)
        await watcher.watch()
    except Exception as e:
        _log.error("Watcher failed", error=e)
        sys.exit(1)


@app.command()
def watch(
    repo_name: Annotated[str, typer.Argument(help="Name of repository to watch")],
) -> None:
    """Start file watcher for a repository (standalone)."""
    print_status("Starting standalone watcher.", level="step", context={"repo": repo_name})
    try:
        asyncio.run(_watch_repo(repo_name))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print_status("Watcher stopped.", level="warn")


@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
    check: bool = typer.Option(False, "--check", help="Validate configuration settings"),
) -> None:
    """Manage dolphin configuration."""
    if show:
        from kb.config import load_config

        config = load_config()
        typer.echo("Current configuration:")
        typer.echo(f"  Store root: {config.store_root}")
        typer.echo(f"  Endpoint: {config.endpoint}")
        typer.echo(f"  Default embed model: {config.default_embed_model}")
        typer.echo(f"  Embedding provider: {config.embedding_provider}")
    elif check:
        # Validate configuration
        try:
            import shutil

            from kb.config import load_config

            config = load_config()
            print_status("Configuration validation", level="step")

            # Check 1: Store Root
            store_root = config.resolved_store_root()
            if store_root.exists():
                print_status("Store root exists.", level="success", context={"path": store_root})
                if os.access(store_root, os.W_OK):
                    print_status("Store root is writable.", level="success")
                else:
                    print_status("Store root is not writable.", level="error")
            else:
                print_status("Store root does not exist.", level="error", context={"path": store_root})

            # Check 2: API Keys
            if config.embedding_provider == "openai":
                if os.environ.get(config.openai_api_key_env):
                    print_status(
                        "OpenAI API key is present.",
                        level="success",
                        context={"env": config.openai_api_key_env},
                    )
                else:
                    print_status(
                        "OpenAI API key is missing.",
                        level="error",
                        context={"env": config.openai_api_key_env},
                    )
                    print_hint(f"Set `{config.openai_api_key_env}` before indexing/searching with OpenAI.")
            else:
                print_status(
                    "Embedding provider configured.",
                    level="info",
                    context={"provider": config.embedding_provider},
                )

            # Check 3: Dependencies (Simple check)
            if shutil.which("uv"):
                print_status("`uv` command found in PATH.", level="success")
            else:
                print_status("`uv` command not found in PATH.", level="warn")
                print_hint("Install uv to run dolphin commands consistently.")

        except Exception as e:
            print_status("Configuration validation failed.", level="error", context={"error": str(e)})
            raise typer.Exit(1)
    else:
        typer.echo("Use 'dolphin init' to initialize configuration")
        typer.echo("Use 'dolphin config --show' to view current config")
        typer.echo("Use 'dolphin config --check' to validate config")


def main() -> None:
    """Entry point for the dolphin CLI."""
    try:
        app()
    except ConfigNotFoundError as e:
        print_status(str(e), level="error", stderr=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
