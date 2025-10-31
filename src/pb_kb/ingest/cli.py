from __future__ import annotations

from pathlib import Path
import os

import typer

from ..config import DEFAULT_CONFIG_PATH, KBConfig, load_config
from ..store import LanceDBStore, SQLiteMetadataStore
from .pipeline import IngestionPipeline
from ..embeddings.provider import create_provider, set_default_provider
from ..ignores import build_ignore_set, load_repo_ignores
from pathspec import PathSpec

app = typer.Typer(help="Unified knowledge store ingestion CLI.")

_CONFIG_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "config_template.toml"
)


def _read_config_template() -> str:
    return _CONFIG_TEMPLATE_PATH.read_text(encoding="utf-8")


def _build_pipeline(config: KBConfig) -> IngestionPipeline:
    lancedb = LanceDBStore(config.resolved_store_root() / "lancedb")
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "knowledge.db")
    metadata.initialize()  # Ensure schema (and migrations) are applied before use

    # Configure embedding provider for ingestion pipeline
    provider_type = config.embedding_provider
    provider_kwargs: dict[str, object] = {}
    if provider_type == "openai":
        api_key = os.environ.get(config.openai_api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{config.openai_api_key_env} environment variable is required for OpenAI embeddings."
            )
        provider_kwargs["api_key"] = api_key
        provider_kwargs["batch_size"] = config.embedding_batch_size

    provider = create_provider(provider_type, **provider_kwargs)
    set_default_provider(provider)

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
        "large", "--default-embed-model", help="Default embedding model for the Repo (small|large)."
    ),
) -> None:
    """Register or update a repository in the metadata store."""
    model = default_embed_model.strip().lower()
    if model not in {"small", "large"}:
        typer.echo("Error: --default-embed-model must be 'small' or 'large'.")
        raise typer.Exit(code=2)

    repo_path = path.expanduser().resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        typer.echo(f"Error: path does not exist or is not a directory: {repo_path}")
        raise typer.Exit(code=2)

    config = load_config()
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "knowledge.db")
    metadata.initialize()
    metadata.record_repo(name=name, path=repo_path, default_embed_model=model)

    typer.echo(
        f"Repository registered: name='{name}', path='{repo_path}', default_embed_model='{model}'"
    )


@app.command()
def index(
    name: str = typer.Argument(..., help="Name of the repository to index."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run without persisting."),
    force: bool = typer.Option(False, "--force", help="Bypass clean working tree check."),
    full: bool = typer.Option(False, "--full", help="Process all files instead of incremental diff."),
) -> None:
    """Run the full indexing pipeline for the specified repository."""
    config = load_config()
    pipeline = _build_pipeline(config)
    try:
        result = pipeline.index(name, dry_run=dry_run, force=force, full_reindex=full)
    except Exception as e:
        typer.echo(f"Indexing failed: {e}")
        raise
    typer.echo(f"Index complete for {name}: session={result.get('session_id')}")
    typer.echo(f"  files_indexed: {result.get('files_indexed')}")
    typer.echo(f"  chunks_indexed: {result.get('chunks_indexed')}")
    typer.echo(f"  chunks_skipped: {result.get('chunks_skipped')}")
    typer.echo(f"  vectors_written: {result.get('vectors_written')}")


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


@app.command("prune-ignored")
def prune_ignored(
    name: str = typer.Argument(..., help="Repository name to clean up."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed without persisting."),
) -> None:
    """Remove chunks for files that match the ignore patterns.
    
    Use this after updating ignore patterns to clean up previously-indexed
    files that should no longer be included.
    """
    config = load_config()
    repo = config.resolved_store_root()
    
    metadata = SQLiteMetadataStore(repo / "knowledge.db")
    metadata.initialize()
    
    lancedb = LanceDBStore(repo / "lancedb")
    lancedb.initialize_collections()
    
    # Resolve repo and get its root path
    repo_record = metadata.get_repo_by_name(name)
    if not repo_record:
        typer.echo(f"Error: Repository '{name}' not registered.")
        raise typer.Exit(code=1)
    
    repo_id = int(repo_record["id"])
    repo_root = Path(repo_record["root_path"])
    
    # Build ignore spec
    extra_security = {
        "**/id_rsa",
        "**/*.pem",
        "**/.aws/**",
        "**/gcloud/**",
        "**/secrets/**",
        "**/*keys.json",
        "**/*service_account.json",
        "**/*auth.json",
    }
    ignore_patterns = build_ignore_set(config.ignore)
    repo_level = load_repo_ignores(repo_root)
    if repo_level:
        ignore_patterns.update(repo_level)
    ignore_patterns.update(extra_security)
    ignore_spec = PathSpec.from_lines("gitwildmatch", ignore_patterns)
    
    # Get all files for this repo
    files = metadata.get_all_files_for_repo(repo_id)
    
    total_chunks_pruned = 0
    pruned_files = []
    
    for file_record in files:
        file_path = file_record["path"]
        file_id = file_record["id"]
        
        # Check if file matches ignore patterns
        if ignore_spec.match_file(file_path):
            pruned_files.append(file_path)
            
            # Prune all content for this file across all embedding models
            if not dry_run:
                # Get all embed models used for this file and prune each
                for embed_model in ["small", "large"]:
                    pruned_count = metadata.prune_invalidated_content_for_file(
                        repo_id, file_id, embed_model=embed_model, current_hashes=set()
                    )
                    total_chunks_pruned += pruned_count
            else:
                # In dry-run, just count what would be pruned
                file_chunks = metadata.get_chunks_for_file(file_id)
                total_chunks_pruned += len(file_chunks) if file_chunks else 0
    
    if dry_run:
        typer.echo(f"[DRY RUN] Would prune:")
        typer.echo(f"  Files: {len(pruned_files)}")
        typer.echo(f"  Chunks: {total_chunks_pruned}")
        for f in pruned_files[:10]:
            typer.echo(f"    - {f}")
        if len(pruned_files) > 10:
            typer.echo(f"    ... and {len(pruned_files) - 10} more")
    else:
        typer.echo(f"✅ Pruned ignored content from '{name}':")
        typer.echo(f"  Files: {len(pruned_files)}")
        typer.echo(f"  Chunks: {total_chunks_pruned}")


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


@app.command("list-files")
def list_files(
    name: str = typer.Argument(..., help="Repository name."),
) -> None:
    """List all indexed files in a repository.

    Output is one file path per line for easy grepping.
    """
    config = load_config()
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "knowledge.db")
    metadata.initialize()

    # Resolve repo
    repo_record = metadata.get_repo_by_name(name)
    if not repo_record:
        typer.echo(f"Error: Repository '{name}' not registered.", err=True)
        raise typer.Exit(code=1)

    repo_id = int(repo_record["id"])

    # Get all files for this repo
    files = metadata.get_all_files_for_repo(repo_id)

    if not files:
        typer.echo(f"No indexed files in repository '{name}'.", err=True)
        raise typer.Exit(code=0)

    # Print one file per line
    for file_record in files:
        typer.echo(file_record["path"])


def main() -> None:
    app()


if __name__ == "__main__":
    main()

