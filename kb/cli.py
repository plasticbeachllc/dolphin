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