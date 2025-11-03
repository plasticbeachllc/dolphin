"""Unified Dolphin CLI - Main entry point for all Dolphin commands.

This module provides a single entry point for all Dolphin functionality,
including knowledge base management, API serving, and persona management.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

# Import subcommand apps
from kb.ingest.cli import app as kb_app
from personas.src.personas import app as personas_app
from kb.api.server import app_with_lifespan

# Import kb CLI functions for top-level commands
from kb.ingest.cli import (
    init as kb_init,
    add_repo as kb_add_repo,
    rm_repo as kb_rm_repo,
    index as kb_index,
    status as kb_status,
    prune_ignored as kb_prune_ignored,
    list_files as kb_list_files,
)

# Create main Dolphin app
app = typer.Typer(
    name="dolphin",
    help="Unified CLI for 🐬 Dolphin knowledge base and AI tools",
    add_completion=False,
)

# Add subcommand apps
app.add_typer(kb_app, name="kb", help="Knowledge base management commands")
app.add_typer(personas_app, name="personas", help="Persona management and generation commands")


# ==============================================================================
# Top-Level Knowledge Base Commands
# ==============================================================================

@app.command()
def init(
    config_path: Optional[Path] = typer.Option(None, "--config", help="Optional config path."),
) -> None:
    """Initialize the knowledge store (config + SQLite + LanceDB collections)."""
    kb_init(config_path)


@app.command()
def add_repo(
    name: str = typer.Argument(..., help="Logical name for the repository."),
    path: Path = typer.Argument(..., help="Absolute path to the repository root."),
    default_embed_model: str = typer.Option("large", "--default-embed-model", help="Default embedding model (small|large)."),
) -> None:
    """Register or update a repository in the metadata store."""
    kb_add_repo(name=name, path=path, default_embed_model=default_embed_model)


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
) -> None:
    """Run the full indexing pipeline for the specified repository."""
    kb_index(name=name, dry_run=dry_run, force=force, full=full)


@app.command()
def status(
    name: Optional[str] = typer.Argument(None, help="Optional repository name."),
) -> None:
    """Report knowledge store status."""
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


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query."),
    repos: Optional[list[str]] = typer.Option(None, "--repo", "-r", help="Repository name(s) to search."),
    path_prefix: Optional[list[str]] = typer.Option(None, "--path", "-p", help="Filter by path prefix."),
    top_k: int = typer.Option(8, "--top-k", "-k", help="Number of results to return."),
    score_cutoff: float = typer.Option(0.0, "--score-cutoff", "-s", help="Minimum similarity score."),
    embed_model: str = typer.Option("large", "--embed-model", "-m", help="Embedding model to use (small|large)."),
    local: bool = typer.Option(False, "--local", "-l", help="Use local backend (no server required)."),
    show_content: bool = typer.Option(False, "--show-content", "-c", help="Display code snippets."),
) -> None:
    """Search indexed code semantically.
    
    Examples:
        dolphin search "authentication logic" --repo myapp
        dolphin search "database migration" --path src/db --top-k 5
        dolphin search "error handling" --local --show-content
    """
    if local:
        _search_local(query, repos, path_prefix, top_k, score_cutoff, embed_model, show_content)
    else:
        _search_remote(query, repos, path_prefix, top_k, score_cutoff, embed_model, show_content)


def _search_local(
    query: str,
    repos: Optional[list[str]],
    path_prefix: Optional[list[str]],
    top_k: int,
    score_cutoff: float,
    embed_model: str,
    show_content: bool,
) -> None:
    """Search using local backend without API server."""
    from kb.config import load_config
    from kb.api.search_backend import create_search_backend
    from kb.api.app import SearchRequest
    
    config = load_config()
    
    try:
        # Create search backend
        backend = create_search_backend(
            store_root=config.resolved_store_root(),
            embedding_provider_type=config.embedding_provider,
            hybrid_search_enabled=True,
        )
        
        # Create search request
        request = SearchRequest(
            query=query,
            repos=repos,
            path_prefix=path_prefix,
            top_k=top_k,
            score_cutoff=score_cutoff,
            embed_model=embed_model,
        )
        
        # Execute search
        hits = list(backend.search(request))
        
        _display_results(hits, show_content, backend.sql_store)
        
    except Exception as e:
        typer.echo(f"Error: Local search failed: {e}", err=True)
        raise typer.Exit(1)


def _search_remote(
    query: str,
    repos: Optional[list[str]],
    path_prefix: Optional[list[str]],
    top_k: int,
    score_cutoff: float,
    embed_model: str,
    show_content: bool,
) -> None:
    """Search using remote API server."""
    import requests
    from kb.config import load_config
    
    config = load_config()
    endpoint = f"http://{config.endpoint}/search"
    
    payload = {
        "query": query,
        "top_k": top_k,
        "score_cutoff": score_cutoff,
        "embed_model": embed_model,
    }
    
    if repos:
        payload["repos"] = repos
    if path_prefix:
        payload["path_prefix"] = path_prefix
    
    try:
        response = requests.post(endpoint, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        hits = result.get("hits", [])
        
        _display_results(hits, show_content, None)
        
    except requests.exceptions.ConnectionError:
        typer.echo("Error: Could not connect to Dolphin API server.", err=True)
        typer.echo("Tip: Use --local flag to search without server, or start server with: dolphin serve", err=True)
        raise typer.Exit(1)
    except requests.exceptions.RequestException as e:
        typer.echo(f"Error: Search request failed: {e}", err=True)
        raise typer.Exit(1)


def _display_results(hits: list, show_content: bool, sql_store=None) -> None:
    """Display search results with optional content."""
    if not hits:
        typer.echo("No results found.")
        return
    
    typer.echo(f"\n🔍 Found {len(hits)} result(s):\n")
    
    for i, hit in enumerate(hits, 1):
        score = hit.get("score", 0.0)
        repo = hit.get("repo", "unknown")
        path = hit.get("path", "unknown")
        start_line = hit.get("start_line", 0)
        end_line = hit.get("end_line", 0)
        
        # Header
        typer.secho(f"\n{i}. {repo}/{path}:{start_line}-{end_line}", fg="cyan", bold=True)
        typer.echo(f"   Score: {score:.10f}")
        
        # Symbol info
        symbol_name = hit.get("symbol_name")
        symbol_kind = hit.get("symbol_kind")
        if symbol_name and symbol_kind:
            typer.secho(f"   {symbol_kind}: {symbol_name}", fg="green")
        
        # Show content if requested
        if show_content:
            chunk_id = hit.get("chunk_id")
            content = hit.get("content")
            
            # Fetch content if not present and sql_store is available
            if not content and chunk_id and sql_store:
                content_map = sql_store.get_chunk_contents([chunk_id])
                content = content_map.get(chunk_id, "")
            
            if content:
                typer.echo("\n   " + "─" * 70)
                for line in content.splitlines()[:10]:  # Show first 10 lines
                    typer.echo(f"   {line}")
                if len(content.splitlines()) > 10:
                    typer.secho(f"   ... ({len(content.splitlines()) - 10} more lines)", fg="yellow")
                typer.echo("   " + "─" * 70)
    
    typer.echo()


# ==============================================================================
# Core Service Commands
# ==============================================================================

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(7777, "--port", help="Port to bind to"),
) -> None:
    """Start the Dolphin API server."""
    import uvicorn
    uvicorn.run("kb.api.server:app_with_lifespan", host=host, port=port, reload=False)


@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
) -> None:
    """Manage Dolphin configuration."""
    if show:
        from kb.config import load_config
        config = load_config()
        typer.echo("Current configuration:")
        typer.echo(f"  Store root: {config.store_root}")
        typer.echo(f"  Endpoint: {config.endpoint}")
        typer.echo(f"  Default embed model: {config.default_embed_model}")
        typer.echo(f"  Embedding provider: {config.embedding_provider}")
    else:
        typer.echo("Use 'dolphin init' to initialize configuration")
        typer.echo("Use 'dolphin config --show' to view current config")


def main() -> None:
    """Entry point for the dolphin CLI."""
    app()


if __name__ == "__main__":
    main()