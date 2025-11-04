# from __future__ import annotations
from pathlib import Path
import os
from typing import cast

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
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
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

    metadata = SQLiteMetadataStore(store_root / "metadata.db")
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
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
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
    """Run the full indexing pipeline for the specified repository.

    Requirements:
      - The repository MUST already be registered in the metadata store.
        Register once with: uv run dolphin add-repo <name> <abs/repo/path>
    """
    config = load_config()

    # Require repo to be pre-registered via: uv run dolphin add-repo <name> <abs/repo/path>
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
    metadata.initialize()
    repo_record = metadata.get_repo_by_name(name)
    if not repo_record:
        typer.echo(
            "Error: Repository not registered. Register once with: uv run dolphin add-repo <name> <abs/repo/path>",
            err=True
        )
        raise typer.Exit(code=2)

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
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
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
    
    metadata = SQLiteMetadataStore(repo / "metadata.db")
    metadata.initialize()
    
    lancedb = LanceDBStore(repo / "lancedb")
    lancedb.initialize_collections()
    
    # Resolve repo and get its root path
    repo_record = metadata.get_repo_by_name(name)
    if not repo_record:
        typer.echo(f"Error: Repository '{name}' not registered.")
        raise typer.Exit(code=1)
    
    repo_id = int(repo_record["id"])
    repo_root = Path(str(repo_record["root_path"]))
    
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
    ignore_patterns = build_ignore_set(config.ignore, config.ignore_exceptions)
    repo_level_patterns, repo_level_exceptions = load_repo_ignores(repo_root)
    if dry_run:
        typer.echo(f"Debug: repo_level ignores loaded: {len(repo_level_patterns)} patterns", err=True)
        # Check if bun.lock patterns are in repo_level
        bun_in_repo = [p for p in repo_level_patterns if "bun" in p.lower()]
        if bun_in_repo:
            typer.echo(f"Debug: bun patterns in repo_level: {bun_in_repo}", err=True)
        else:
            typer.echo(f"Debug: NO bun patterns in repo_level", err=True)
    if repo_level_patterns:
        ignore_patterns.update(repo_level_patterns)
    # Apply repo-level exceptions
    if repo_level_exceptions:
        ignore_patterns = build_ignore_set(ignore_patterns, repo_level_exceptions)
    ignore_patterns.update(extra_security)
    
    # Manually add bun.lock patterns to test
    ignore_patterns.add("bun.lock")
    ignore_patterns.add("**/bun.lock")
    
    ignore_spec = PathSpec.from_lines("gitwildmatch", ignore_patterns)
    
    # Debug: show which patterns we're using
    if dry_run:
        typer.echo(f"Debug: Using {len(ignore_patterns)} ignore patterns", err=True)
        bun_patterns = [p for p in ignore_patterns if "bun" in p.lower()]
        if bun_patterns:
            typer.echo(f"Debug: bun-related patterns: {bun_patterns}", err=True)
        else:
            typer.echo(f"Debug: NO bun patterns found!", err=True)
    # Get all files for this repo
    files = metadata.get_all_files_for_repo(repo_id)
    
    total_chunks_pruned = 0
    pruned_files = []
    for file_record in files:
        file_path = cast(str, file_record["path"])
        file_id = cast(int, file_record["id"])
        
        # Check if file matches ignore patterns
        matches = ignore_spec.match_file(file_path)
        if dry_run and "bun.lock" in file_path:
            typer.echo(f"Debug: {file_path} matches={matches}", err=True)

        if matches:
            pruned_files.append(file_path)

            # Prune all content for this file across all embedding models
            if not dry_run:
                # Get all embed models used for this file and prune each
                for embed_model in ["small", "large"]:
                    pruned_count = metadata.prune_invalidated_content_for_file(
                        repo_id, file_id, embed_model=embed_model, current_hashes=set()
                    )
                    total_chunks_pruned += pruned_count
                    lancedb.prune_file_rows(name, file_path, model=embed_model)
                
                # Also delete any orphaned FTS5 entries for this file
                with metadata._connect() as conn:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM chunks_fts WHERE path = ?", (file_path,))
                    conn.commit()
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


@app.command("rm-repo")
def rm_repo(
    name: str = typer.Argument(..., help="Repository name to remove."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation and active session checks."),
) -> None:
    """Remove a repository and all its data from the knowledge store.
    
    This will delete:
    - Repository registration
    - All indexed files metadata
    - All chunk content and locations
    - All vectors (embeddings)
    - All indexing sessions
    
    Enhanced with Phase 2 Fix 2.1:
    - Validates active sessions before deletion
    - Deletes in proper foreign key order
    - Validates cleanup was comprehensive
    - Provides detailed statistics
    """
    config = load_config()
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
    metadata.initialize()
    
    lancedb = LanceDBStore(config.resolved_store_root() / "lancedb")
    
    # Get repo info
    repo = metadata.get_repo_by_name(name)
    if not repo:
        typer.echo(f"Error: Repository '{name}' not found.", err=True)
        raise typer.Exit(code=1)
    
    repo_id = int(repo["id"])
    repo_path = repo["root_path"]
    
    # Check for active sessions
    active_sessions = metadata.get_active_sessions(repo_id)
    if active_sessions and not force:
        typer.echo(f"Error: Cannot remove repository '{name}':", err=True)
        typer.echo(f"  Found {len(active_sessions)} active indexing session(s).", err=True)
        typer.echo(f"  Use --force to override and abort active sessions.", err=True)
        raise typer.Exit(code=1)
    
    # Confirm deletion unless --force
    if not force:
        typer.echo(f"This will remove repository '{name}' and all its data:")
        typer.echo(f"  Path: {repo_path}")
        typer.echo(f"  Repo ID: {repo_id}")
        typer.echo()
        confirm = typer.confirm("Are you sure you want to continue?")
        if not confirm:
            typer.echo("Aborted.")
            raise typer.Exit(code=0)
    
    # Use enhanced removal with comprehensive cleanup validation
    typer.echo(f"Removing repository '{name}' with comprehensive cleanup validation...")
    try:
        result = metadata.rm_repo_with_lancedb(lancedb, name, force=force)
        
        # Display cleanup statistics
        stats = result["cleanup_stats"]
        typer.echo(f"\n✓ Repository '{name}' removed successfully.")
        typer.echo(f"\nCleanup Statistics:")
        typer.echo(f"  Files deleted: {stats['files_deleted']}")
        typer.echo(f"  Chunk content deleted: {stats['content_deleted']}")
        typer.echo(f"  Chunk locations deleted: {stats['locations_deleted']}")
        typer.echo(f"  Sessions deleted: {stats['sessions_deleted']}")
        
        # FTS5 cleanup details
        fts_stats = stats['fts5_entries']
        typer.echo(f"\n  FTS5 Cleanup:")
        typer.echo(f"    By content_id: {fts_stats['by_content_id']}")
        typer.echo(f"    By repo name: {fts_stats['by_repo_name']}")
        typer.echo(f"    Orphaned entries: {fts_stats['orphaned']}")
        
        # LanceDB cleanup details
        lance_stats = stats['lancedb_vectors']
        typer.echo(f"\n  LanceDB Cleanup:")
        typer.echo(f"    Small model vectors: {lance_stats['small_deleted']}")
        typer.echo(f"    Large model vectors: {lance_stats['large_deleted']}")
        
        # Show warnings if any
        if "lancedb_warnings" in result:
            typer.echo(f"\n⚠️  Warnings:")
            for warning in result["lancedb_warnings"]:
                typer.echo(f"    {warning}", err=True)
        
    except Exception as e:
        typer.echo(f"Error: Repository removal failed: {e}", err=True)
        raise typer.Exit(code=1)

@app.command("reset-repo")
def reset_repo(
    name: str = typer.Argument(..., help="Repository name to reset."),
    path: Path = typer.Argument(..., help="Absolute path to the repository root."),
    default_embed_model: str = typer.Option(
        "large", "--default-embed-model", help="Default embedding model for the Repo (small|large)."
    ),
) -> None:
    """Wipe all stores for the repo and re-register it in one step.

    This will:
      - Delete all vectors (small and large) from LanceDB
      - Delete all metadata rows (files, chunk_content, chunk_locations, sessions, FTS)
      - Delete the repo row
      - Re-register the repo with the provided path and embed model
      
    Enhanced with Phase 2 Fix 2.1:
      - Uses comprehensive cleanup validation
      - Validates deletion was successful
    """
    # Validate embed model
    model = default_embed_model.strip().lower()
    if model not in {"small", "large"}:
        typer.echo("Error: --default-embed-model must be 'small' or 'large'.")
        raise typer.Exit(code=2)

    # Validate path
    repo_path = path.expanduser().resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        typer.echo(f"Error: path does not exist or is not a directory: {repo_path}")
        raise typer.Exit(code=2)

    # Load config and stores
    config = load_config()
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
    metadata.initialize()
    lancedb = LanceDBStore(config.resolved_store_root() / "lancedb")

    # If repo exists, wipe it (no confirmation, force=True for automatic cleanup)
    repo = metadata.get_repo_by_name(name)
    if repo:
        typer.echo(f"Removing all data for '{name}' using enhanced cleanup...")
        
        try:
            # Use enhanced removal with force=True (skip confirmation, abort active sessions)
            result = metadata.rm_repo_with_lancedb(lancedb, name, force=True)
            
            # Display brief cleanup summary
            stats = result["cleanup_stats"]
            typer.echo(f"✓ Removed: {stats['files_deleted']} files, "
                      f"{stats['content_deleted']} chunks, "
                      f"{stats['lancedb_vectors']['small_deleted'] + stats['lancedb_vectors']['large_deleted']} vectors")
            
            # Show warnings if any
            if "lancedb_warnings" in result and result["lancedb_warnings"]:
                typer.echo(f"⚠️  Cleanup warnings: {len(result['lancedb_warnings'])}", err=True)
                
        except Exception as e:
            typer.echo(f"Warning: Enhanced cleanup failed, continuing anyway: {e}", err=True)

    # Re-register repo
    metadata.record_repo(name=name, path=repo_path, default_embed_model=model)
    typer.echo(
        f"✓ Repository '{name}' re-registered: path='{repo_path}', default_embed_model='{model}'"
    )


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
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
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


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query."),
    repos: list[str] | None = typer.Option(None, "--repo", "-r", help="Repository name(s) to search."),
    path_prefix: list[str] | None = typer.Option(None, "--path", "-p", help="Filter by path prefix."),
    top_k: int = typer.Option(8, "--top-k", "-k", help="Number of results to return."),
    score_cutoff: float = typer.Option(0.0, "--score-cutoff", "-s", help="Minimum similarity score."),
    embed_model: str = typer.Option("large", "--embed-model", "-m", help="Embedding model to use (small|large)."),
    show_content: bool = typer.Option(False, "--show-content", "-c", help="Display code snippets."),
) -> None:
    """Search indexed code semantically (local backend).
    
    Examples:
        dolphin kb search "authentication logic" --repo myapp
        dolphin kb search "database migration" --path src/db --top-k 5
        dolphin kb search "error handling" --show-content
    """
    from ..api.search_backend import create_search_backend
    from ..api.app import SearchRequest
    
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
        
        # Display results
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
            typer.echo(f"   Score: {score:.3f}")
            
            # Symbol info
            symbol_name = hit.get("symbol_name")
            symbol_kind = hit.get("symbol_kind")
            if symbol_name and symbol_kind:
                typer.secho(f"   {symbol_kind}: {symbol_name}", fg="green")
            
            # Show content if requested
            if show_content:
                chunk_id = hit.get("chunk_id")
                content = hit.get("content")
                
                # Normalize types
                if not isinstance(content, str):
                    content = ""
                
                # Fetch content if not present and we have a string chunk_id
                if not content and isinstance(chunk_id, str):
                    content_map = backend.sql_store.get_chunk_contents([chunk_id])
                    content = content_map.get(chunk_id, "") or ""
                
                if content:
                    typer.echo("\n   " + "─" * 70)
                    for line in content.splitlines()[:10]:  # Show first 10 lines
                        typer.echo(f"   {line}")
                    if len(content.splitlines()) > 10:
                        typer.secho(f"   ... ({len(content.splitlines()) - 10} more lines)", fg="yellow")
                    typer.echo("   " + "─" * 70)
        
        typer.echo()
        
    except Exception as e:
        typer.echo(f"Error: Search failed: {e}", err=True)
        raise typer.Exit(1)


@app.command("validate-repo")
def validate_repo(
    name: str = typer.Argument(..., help="Repository name to validate."),
) -> None:
    """Validate repository consistency across metadata and vector stores.
    
    This checks for:
    - Orphaned chunk locations without content
    - Orphaned FTS entries without content
    - Orphaned chunk content without files
    - Orphaned files without repos
    - LanceDB vector consistency
    """
    config = load_config()
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
    metadata.initialize()
    
    lancedb = LanceDBStore(config.resolved_store_root() / "lancedb")
    
    # Get repo info
    repo = metadata.get_repo_by_name(name)
    if not repo:
        typer.echo(f"Error: Repository '{name}' not found.", err=True)
        raise typer.Exit(code=1)
    
    repo_id = int(repo["id"])
    
    # Run validation
    typer.echo(f"Validating repository '{name}'...")
    try:
        report = metadata.validate_repo_consistency(lancedb, repo_id, name)
        
        # Display results
        if report["valid"]:
            typer.echo(f"\n✓ Repository '{name}' is consistent.")
        else:
            typer.echo(f"\n⚠️  Repository '{name}' has consistency issues:", err=True)
            for issue in report["issues"]:
                typer.echo(f"  - {issue}", err=True)
        
        # Display statistics
        stats = report["statistics"]
        typer.echo(f"\nStatistics:")
        typer.echo(f"  Files: {stats['metadata_files']}")
        typer.echo(f"  Chunks: {stats['metadata_chunks']}")
        typer.echo(f"  Locations: {stats['metadata_locations']}")
        typer.echo(f"  Orphaned locations: {stats['orphaned_locations']}")
        typer.echo(f"  Orphaned FTS entries: {stats['orphaned_fts']}")
        typer.echo(f"  Orphaned content: {stats['orphaned_content']}")
        typer.echo(f"  Orphaned files: {stats['orphaned_files']}")
        
        # LanceDB stats
        lancedb_stats = report["lancedb"]
        typer.echo(f"\nLanceDB Vectors:")
        for model, count in lancedb_stats["vector_counts"].items():
            typer.echo(f"  {model}: {count}")
        
        if not report["valid"]:
            typer.echo(f"\nTip: Run 'kb repair-repo {name}' to fix these issues.")
            raise typer.Exit(code=1)
            
    except Exception as e:
        typer.echo(f"Error: Validation failed: {e}", err=True)
        raise typer.Exit(code=1)


@app.command("repair-repo")
def repair_repo(
    name: str = typer.Argument(..., help="Repository name to repair."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be repaired without making changes."),
) -> None:
    """Repair consistency issues in a repository.
    
    This will:
    - Remove orphaned chunk locations
    - Remove orphaned FTS entries
    - Remove orphaned chunk content
    - Remove orphaned files
    """
    config = load_config()
    metadata = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
    metadata.initialize()
    
    lancedb = LanceDBStore(config.resolved_store_root() / "lancedb")
    
    # Get repo info
    repo = metadata.get_repo_by_name(name)
    if not repo:
        typer.echo(f"Error: Repository '{name}' not found.", err=True)
        raise typer.Exit(code=1)
    
    repo_id = int(repo["id"])
    
    if dry_run:
        # Run validation to show what would be repaired
        typer.echo(f"[DRY RUN] Checking what would be repaired for '{name}'...")
        report = metadata.validate_repo_consistency(lancedb, repo_id, name)
        
        if report["valid"]:
            typer.echo(f"\n✓ No repairs needed for '{name}'.")
            return
        
        typer.echo(f"\n[DRY RUN] Would repair the following issues:")
        for issue in report["issues"]:
            typer.echo(f"  - {issue}")
        
        stats = report["statistics"]
        total_repairs = (
            stats["orphaned_locations"] +
            stats["orphaned_fts"] +
            stats["orphaned_content"] +
            stats["orphaned_files"]
        )
        typer.echo(f"\nTotal items that would be repaired: {total_repairs}")
        return
    
    # Perform repair
    typer.echo(f"Repairing repository '{name}'...")
    try:
        repair_report = metadata.repair_repository_consistency(repo_id, name)
        
        if repair_report["success"]:
            if repair_report["repairs_performed"]:
                typer.echo(f"\n✓ Repository '{name}' repaired successfully.")
                typer.echo(f"\nRepairs performed:")
                for repair in repair_report["repairs_performed"]:
                    typer.echo(f"  - {repair}")
            else:
                typer.echo(f"\n✓ No repairs needed for '{name}'.")
        else:
            typer.echo(f"\n⚠️  Repair completed with errors:", err=True)
            for error in repair_report["errors"]:
                typer.echo(f"  - {error}", err=True)
            raise typer.Exit(code=1)
            
    except Exception as e:
        typer.echo(f"Error: Repair failed: {e}", err=True)
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
