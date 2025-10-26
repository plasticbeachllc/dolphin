from __future__ import annotations

from pathlib import Path

import typer

from ..config import DEFAULT_CONFIG_PATH, KBConfig, load_config
from ..store import LanceDBStore, SQLiteMetadataStore
from .pipeline import IngestionPipeline

app = typer.Typer(help="Unified knowledge store ingestion CLI.")

_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config.yaml"
)


def _read_config_template() -> str:
    return _CONFIG_PATH.read_text(encoding="utf-8")


def _build_pipeline(config: KBConfig) -> IngestionPipeline:
    lancedb = LanceDBStore(config.resolved_store_root() / "lancedb")
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "knowledge.db")
    return IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)


@app.command()
def init(config_path: Path | None = typer.Option(None, help="Optional config path.")) -> None:
    """Initialize the knowledge store (config + SQLite + LanceDB collections).

    Idempotent: safe to run multiple times.
    """
    target = config_path or DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    created = False
    if target.exists():
        typer.echo(f"Config already exists at {target}")
    else:
        target.write_text(_read_config_template(), encoding="utf-8")
        typer.echo(f"Created knowledge store config at {target}")
        created = True

    # Load config and initialize storage backends.
    config = load_config(target)
    store_root = config.resolved_store_root()
    store_root.mkdir(parents=True, exist_ok=True)

    metadata = SQLiteMetadataStore(store_root / "knowledge.db")
    metadata.initialize()
    typer.echo(f"SQLite initialized at {metadata.db_path}")

    lancedb = LanceDBStore(store_root / "lancedb")
    lancedb.initialize_collections()
    typer.echo(f"LanceDB root initialized at {lancedb.root}")

    if created:
        typer.echo("Initialization complete. You can now run 'kb add-repo' and 'kb index'.")
    else:
        typer.echo("Initialization verified. Nothing else to do.")


@app.command("add-repo")
def add_repo(
    name: str = typer.Argument(..., help="Logical name for the repository."),
    path: Path = typer.Argument(..., help="Absolute path to the repository root."),
    default_embed_model: str = typer.Option(
        "small", "--default-embed-model", help="Default embedding model for the Repo."
    ),
) -> None:
    """Register a repository with the metadata store (stub)."""
    _ = (name, path, default_embed_model)
    typer.echo("Repository registration will be implemented in Phase 2.")


@app.command()
def index(
    name: str = typer.Argument(..., help="Name of the repository to index."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run without persisting."),
) -> None:
    """Index the specified repository (stub)."""
    config = load_config()
    pipeline = _build_pipeline(config)
    _ = (name, dry_run, pipeline)
    typer.echo("Indexing pipeline is not yet implemented.")


@app.command()
def status(name: str | None = typer.Argument(None, help="Optional repo name.")) -> None:
    """Report knowledge store status."""
    config = load_config()
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "knowledge.db")
    # Ensure DB and schema exist before summarizing.
    metadata.initialize()
    summary = metadata.summarize()
    _ = name
    typer.echo(f"Knowledge store summary: {summary}")


@app.command()
def prune(
    name: str = typer.Argument(..., help="Repository name to prune."),
    older_than: str = typer.Option(
        "30d", "--older-than", help="Age cutoff for pruning sessions."
    ),
) -> None:
    """Remove older data for the specified repository (stub)."""
    _ = (name, older_than)
    typer.echo("Prune functionality will arrive after ingestion is wired up.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
