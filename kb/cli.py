"""Unified Dolphin CLI - Main entry point for all Dolphin commands.

This module provides a single entry point for all Dolphin functionality,
including knowledge base management, API serving, and persona management.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

# Import subcommand apps
from kb.ingest.cli import app as kb_app
from kb.api.server import main as api_main

app = typer.Typer(
    name="dolphin",
    help="Unified CLI for Dolphin knowledge base and AI tools",
    add_completion=False,
)


@app.command()
def init(
    repo: bool = typer.Option(False, "--repo", help="Initialize repo-specific config in current directory"),
) -> None:
    """Initialize Dolphin configuration.
    
    By default, initializes user config at ~/.dolphin/config.toml (auto-created on first use).
    With --repo flag, creates a repo-specific config in ./.dolphin/config.toml.
    """
    if repo:
        # Create repo-specific config
        repo_config_path = Path.cwd() / ".dolphin" / "config.toml"
        
        if repo_config_path.exists():
            typer.echo(f"Repo config already exists at {repo_config_path}")
            raise typer.Exit(0)
        
        # Read template
        from kb.config import _read_template
        template = _read_template()
        
        if not template:
            typer.echo("Error: Could not find config template", err=True)
            raise typer.Exit(1)
        
        # Create repo config
        repo_config_path.parent.mkdir(parents=True, exist_ok=True)
        repo_config_path.write_text(template, encoding="utf-8")
        typer.echo(f"✅ Created repo config at {repo_config_path}")
        typer.echo("Edit this file to customize chunking behavior for this repository.")
    else:
        # Initialize user config (will be auto-created if missing)
        from kb.config import _ensure_user_config
        config_path = _ensure_user_config()
        typer.echo(f"✅ User config ready at {config_path}")
        typer.echo("This config is used globally unless overridden by repo-specific config.")


@app.command()
def index(
    name: str = typer.Argument(..., help="Name of the repository to index"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run without persisting"),
    force: bool = typer.Option(False, "--force", help="Bypass clean working tree check"),
    full: bool = typer.Option(False, "--full", help="Process all files instead of incremental"),
) -> None:
    """Index a repository into the knowledge base."""
    # Delegate to kb subcommand
    from kb.ingest.cli import index as kb_index
    kb_index(name=name, dry_run=dry_run, force=force, full=full)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
    repos: str = typer.Option(None, "--repos", "-r", help="Comma-separated repo names"),
) -> None:
    """Search the knowledge base."""
    typer.echo(f"Searching for: {query}")
    typer.echo("(Search functionality will be connected to kb-search CLI)")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(7777, "--port", help="Port to bind to"),
) -> None:
    """Start the Dolphin API server."""
    typer.echo(f"Starting Dolphin API server on {host}:{port}")
    # Note: api_main expects to be called directly, not with params
    # For now, just call it as-is; we can enhance it later
    api_main()


@app.command()
def add_repo(
    name: str = typer.Argument(..., help="Repository name"),
    path: Path = typer.Argument(..., help="Path to repository root"),
    embed_model: str = typer.Option("large", "--embed-model", help="Embedding model (small|large)"),
) -> None:
    """Register a repository with the knowledge base."""
    from kb.ingest.cli import add_repo as kb_add_repo
    kb_add_repo(name=name, path=path, default_embed_model=embed_model)


@app.command()
def status(
    name: str = typer.Argument(None, help="Optional repository name"),
) -> None:
    """Show knowledge base status."""
    from kb.ingest.cli import status as kb_status
    kb_status(name=name)


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
        typer.echo("Use 'dolphin init --repo' for repo-specific config")
        typer.echo("Use 'dolphin config --show' to view current config")


def main() -> None:
    """Entry point for the dolphin CLI."""
    app()


if __name__ == "__main__":
    main()