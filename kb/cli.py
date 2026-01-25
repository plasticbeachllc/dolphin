"""Unified Dolphin CLI - Main entry point for all dolphin commands.

This module provides a single entry point for all dolphin functionality,
including knowledge base management, API serving, and persona management.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from rich import print as rprint

# Import kb CLI functions for top-level commands
# Import subcommand apps
from kb.api_key import get_or_create_kb_api_key
from kb.config import load_config
from kb.ingest.cli import (
    add_repo as kb_add_repo,
    app as kb_app,
    index as kb_index,
    init as kb_init,
    list_files as kb_list_files,
    prune_ignored as kb_prune_ignored,
    rm_repo as kb_rm_repo,
    status as kb_status,
)
from kb.observability import StructuredLogger
from kb.store import SQLiteMetadataStore


def get_version() -> str:
    """Get installed package version."""
    try:
        from importlib.metadata import version

        return version("pb-dolphin")
    except Exception:
        return "unkown"  # Fallback version


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


# Add subcommand apps
app.add_typer(kb_app, name="kb", help="Knowledge base management commands")


_log = StructuredLogger("kb.cli", {"component": "dolphin_cli"})


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
) -> None:
    """Run the full indexing pipeline for the specified repository."""
    kb_index(name=name, dry_run=dry_run, force=force, full=full)


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


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query."),
    repos: list[str] | None = typer.Option(None, "--repo", "-r", help="Repository name(s) to search."),
    path_prefix: list[str] | None = typer.Option(None, "--path", "-p", help="Filter by path prefix."),
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
    repos: list[str] | None,
    path_prefix: list[str] | None,
    top_k: int,
    score_cutoff: float,
    embed_model: str,
    show_content: bool,
) -> None:
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

        # Create search request
        request = SearchRequest(
            query=query,
            repos=repos,
            path_prefix=path_prefix,
            top_k=top_k,
            score_cutoff=score_cutoff,
        )

        # Execute search
        hits = list(backend.search(request))

        _display_results(hits, show_content, backend.sql_store)

    except Exception as e:
        typer.echo(f"Error: Local search failed: {e}", err=True)
        raise typer.Exit(1)


def _search_remote(
    query: str,
    repos: list[str] | None,
    path_prefix: list[str] | None,
    top_k: int,
    score_cutoff: float,
    embed_model: str,
    show_content: bool,
) -> None:
    """Search using remote API server."""
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
        "embed_model": embed_model,
    }

    if repos:
        payload["repos"] = repos
    if path_prefix:
        payload["path_prefix"] = path_prefix

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

        _display_results(hits, show_content, None)

    except requests.exceptions.ConnectionError:
        typer.echo("Error: Could not connect to dolphin API server.", err=True)
        typer.echo(
            "Tip: Use --local flag to search without server, or start server with: dolphin serve",
            err=True,
        )
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
                    typer.secho(
                        f"   ... ({len(content.splitlines()) - 10} more lines)",
                        fg="yellow",
                    )
                typer.echo("   " + "─" * 70)

    typer.echo()


@app.command()
def list_repos() -> None:
    """List all registered repositories."""
    from kb.ingest.cli import list_repos as kb_list_repos

    kb_list_repos()


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
        except Exception as e:
            rprint(f"[yellow]Warning: Failed to list repos for automatic watching: {e}[/yellow]")

    # Deduplicate
    repo_list = sorted(list(set(repo_list)))

    if repo_list:
        os.environ["DOLPHIN_WATCH_REPOS"] = ",".join(repo_list)
        rprint(f"[green]Configured to watch repositories: {', '.join(repo_list)}[/green]")
    elif "DOLPHIN_WATCH_REPOS" in os.environ:
        # If no repos to watch, clear the env var to prevent inheriting it
        del os.environ["DOLPHIN_WATCH_REPOS"]

    if not os.environ.get("DOLPHIN_API_KEY") and not os.environ.get("DOLPHIN_KB_API_KEY"):
        os.environ["DOLPHIN_API_KEY"] = get_or_create_kb_api_key()

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
    rprint(f"[bold blue]Starting watcher for {repo_name}...[/bold blue]")
    try:
        asyncio.run(_watch_repo(repo_name))
    except (KeyboardInterrupt, asyncio.CancelledError):
        rprint("\n[yellow]Watcher stopped.[/yellow]")


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
            rprint("\n[bold]Configuration Validation[/bold]")

            # Check 1: Store Root
            store_root = config.resolved_store_root()
            if store_root.exists():
                rprint(f"✅ Store Root: [green]{store_root}[/green]")
                if os.access(store_root, os.W_OK):
                    rprint("(Writable)")
                else:
                    rprint("[red](Not Writable)[/red]")
            else:
                rprint(f"❌ Store Root: [red]{store_root} (Does not exist)[/red]")

            # Check 2: API Keys
            if config.embedding_provider == "openai":
                if os.environ.get(config.openai_api_key_env):
                    rprint(f"✅ OpenAI API Key: [green]Present ({config.openai_api_key_env})[/green]")
                else:
                    rprint(f"❌ OpenAI API Key: [red]Missing ({config.openai_api_key_env})[/red]")
            else:
                rprint(f"ℹ️  Provider: {config.embedding_provider}")

            # Check 3: Dependencies (Simple check)
            if shutil.which("uv"):
                rprint("✅ 'uv' command: [green]Found[/green]")
            else:
                rprint("⚠️  'uv' command: [yellow]Not found (Recommended)[/yellow]")

        except Exception as e:
            rprint(f"[red]Validation failed: {e}[/red]")
            raise typer.Exit(1)
    else:
        typer.echo("Use 'dolphin init' to initialize configuration")
        typer.echo("Use 'dolphin config --show' to view current config")
        typer.echo("Use 'dolphin config --check' to validate config")


def main() -> None:
    """Entry point for the dolphin CLI."""
    app()


if __name__ == "__main__":
    main()
