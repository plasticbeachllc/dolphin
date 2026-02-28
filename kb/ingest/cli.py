# from __future__ import annotations
import asyncio
import contextlib
import logging
import os
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import typer
from pathspec import PathSpec
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn
from rich.table import Table

from ..api_key import get_kb_key_path, get_or_create_kb_api_key, load_kb_api_key
from ..config import DEFAULT_CONFIG_PATH, ConfigNotFoundError, KBConfig, load_config
from ..embeddings.provider import create_provider, set_default_provider
from ..ignores import build_ignore_set, load_repo_ignores
from ..store import LanceDBStore, SQLiteMetadataStore
from ..terminal import print_status
from .pipeline import IngestionPipeline

_log = logging.getLogger(__name__)


@dataclass
class ResetStats:
    """Accumulator for repo-reset statistics."""

    repos_removed: int = 0
    files_deleted: int = 0
    content_deleted: int = 0
    locations_deleted: int = 0
    sessions_deleted: int = 0
    vectors_deleted: int = 0
    errors: list[str] = field(default_factory=list)


app = typer.Typer(help="Unified knowledge store ingestion CLI.")

_CONFIG_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "config_template.toml"
_METADATA_DB_NAME = "metadata.db"
_LANCEDB_DIR_NAME = "lancedb"


def _read_config_template() -> str:
    return _CONFIG_TEMPLATE_PATH.read_text(encoding="utf-8")


_ChecklistStatus = Literal["ok", "missing", "pending"]

_STATUS_STYLES: dict[_ChecklistStatus, str] = {
    "ok": "[sea_green2]ok[/sea_green2]",
    "missing": "[indian_red1]missing[/indian_red1]",
    "pending": "[dim]pending[/dim]",
}


_CHECKLIST_STATUS_WIDTH = 10
_CHECKLIST_LABEL_WIDTH = 15


def _checklist_row(status: _ChecklistStatus, label: str, detail: str = "") -> str:
    """Format a single readiness-checklist row with consistent alignment."""
    styled = _STATUS_STYLES[status]
    # Pad so the visible status text occupies a fixed width, keeping labels aligned.
    pad = max(0, _CHECKLIST_STATUS_WIDTH - len(status))
    col_width = max(_CHECKLIST_LABEL_WIDTH, len(label) + 1)
    return f"    {styled}{' ' * pad}{label:<{col_width}}{detail}"


def _print_readiness_checklist(console: Console, config: KBConfig, config_path: Path) -> None:
    """Print a pass/fail readiness checklist after init."""
    store_root = config.resolved_store_root()

    console.print()
    console.print("  [bold]Readiness check:[/bold]")

    # 1. Config file
    status = "ok" if config_path.exists() else "missing"
    console.print(_checklist_row(status, "Config", escape(str(config_path))))

    # 2. SQLite
    db_path = store_root / _METADATA_DB_NAME
    status = "ok" if db_path.exists() else "missing"
    console.print(_checklist_row(status, "SQLite", escape(str(db_path))))

    # 3. LanceDB
    lance_path = store_root / _LANCEDB_DIR_NAME
    status = "ok" if lance_path.exists() else "missing"
    console.print(_checklist_row(status, "LanceDB", escape(str(lance_path))))

    # 4. KB API Key
    key_path = get_kb_key_path()
    if load_kb_api_key():
        console.print(_checklist_row("ok", "KB API Key", escape(str(key_path))))
    else:
        console.print(_checklist_row("pending", "KB API Key", "(will retry on [bold]dolphin serve[/bold])"))

    # 5. Embedding provider API key check
    # TODO: extend for other providers (Cohere, Anthropic, etc.) when supported
    missing_steps: list[str] = []
    if config.embedding_provider == "openai":
        env_var = config.openai_api_key_env
        if os.environ.get(env_var):
            console.print(_checklist_row("ok", env_var))
        else:
            console.print(_checklist_row("missing", env_var, f'(set with: [bold]export {env_var}="sk-..."[/bold])'))
            missing_steps.append(f'export {env_var}="sk-..."')

    # Next steps
    console.print()
    console.print("  [bold]Next steps:[/bold]")
    all_steps = [*missing_steps, "[bold]dolphin add-repo[/bold] <name> <path>", "[bold]dolphin index[/bold] <name>"]
    for i, cmd in enumerate(all_steps, 1):
        console.print(f"    {i}. {cmd}")


def _build_pipeline(config: KBConfig) -> IngestionPipeline:
    lancedb = LanceDBStore(config.resolved_store_root() / _LANCEDB_DIR_NAME)
    metadata = SQLiteMetadataStore(config.resolved_store_root() / _METADATA_DB_NAME)
    metadata.initialize()  # Ensure schema (and migrations) are applied before use

    # Configure embedding provider for ingestion pipeline
    provider_type = config.embedding_provider
    provider_kwargs: dict[str, object] = {}
    if provider_type == "openai":
        api_key = os.environ.get(config.openai_api_key_env)
        if not api_key:
            raise RuntimeError(f"{config.openai_api_key_env} environment variable is required for OpenAI embeddings.")
        provider_kwargs["api_key"] = api_key
        provider_kwargs["batch_size"] = config.embedding_batch_size

    provider = create_provider(provider_type, **provider_kwargs)
    set_default_provider(provider)

    return IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)


@app.command()
def init(
    config_path: Path | None = typer.Option(None, help="Optional config path."),
) -> None:
    """Initialize the knowledge store (config + SQLite + LanceDB collections).

    Idempotent: safe to run multiple times.
    """
    target = config_path or DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    created = False

    # Load existing or template content
    console = Console()
    if target.exists():
        console.print(f"[dim]Config already exists at {target}[/dim]")
        config_content = target.read_text(encoding="utf-8")
    else:
        config_content = _read_config_template()
        created = True

    if created:
        target.write_text(config_content, encoding="utf-8")
        console.print(f"Created knowledge store config at [bold sea_green2]{target}[/bold sea_green2]")

    # Load config and initialize storage backends.
    config = load_config(target)
    store_root = config.resolved_store_root()
    store_root.mkdir(parents=True, exist_ok=True)

    metadata = SQLiteMetadataStore(store_root / _METADATA_DB_NAME)
    metadata.initialize()
    console.print(f"SQLite initialized at [bold steel_blue1]{metadata.db_path}[/bold steel_blue1]")

    lancedb = LanceDBStore(store_root / _LANCEDB_DIR_NAME)
    lancedb.initialize_collections()
    console.print(f"LanceDB root initialized at [bold steel_blue1]{lancedb.root}[/bold steel_blue1]")

    # Ensure KB API key exists so the checklist can report it
    try:
        get_or_create_kb_api_key()
    except Exception:
        _log.warning("Could not pre-create KB API key; checklist will show 'pending'.", exc_info=True)
        console.print("[dim]Warning: could not create KB API key (check permissions)[/dim]")

    _print_readiness_checklist(console, config, target)


@app.command("add-repo")
def add_repo(
    name: str = typer.Argument(..., help="Logical name for the repository."),
    path: Path = typer.Argument(..., help="Absolute path to the repository root."),
    no_index: bool = typer.Option(False, "--no-index", help="Skip indexing prompt."),
) -> None:
    """Register or update a repository in the metadata store."""
    repo_path = path.expanduser().resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        typer.echo(f"Error: path does not exist or is not a directory: {repo_path}")
        raise typer.Exit(code=2)

    config = load_config()
    # Use the global default model from config
    model = config.default_embed_model

    metadata = SQLiteMetadataStore(config.resolved_store_root() / _METADATA_DB_NAME)
    metadata.initialize()
    metadata.record_repo(name=name, path=repo_path, default_embed_model=model)

    typer.echo(f"Repository registered: name='{name}', path='{repo_path}'")

    # Note: We rely on 'dolphin index' to handle any model mismatch if this was an update
    # to an existing repo that had a different model.

    # Only prompt for indexing in interactive mode (skip in tests or if --no-index)
    if not no_index and sys.stdin is not None and sys.stdin.isatty():
        if typer.confirm(f"Do you want to index '{name}' now?", default=False):
            typer.echo(f"Starting index for {name}...")
            pipeline = _build_pipeline(config)
            try:
                pipeline.index(name, dry_run=False, force=False)
                typer.echo(f"⛵ Indexing complete for {name}")
            except Exception as e:
                _log.error("Indexing failed during add-repo prompt for %s", name, exc_info=True)
                typer.echo(f"🚩 Indexing failed: {e}", err=True)


def _create_progress_display() -> tuple[Progress | None, Callable[[dict[str, Any]], None]]:
    """Create a Rich progress bar and return (progress, callback).

    Returns (None, line_callback) when stdout is not a TTY.
    Returns (Progress, rich_callback) when stdout is a TTY.
    """
    from ..terminal import STDERR_CONSOLE, is_tty

    if not is_tty():
        # Non-TTY: periodic line output to stderr
        _last_n = 0
        _started = False

        def _line_callback(data: dict[str, Any]) -> None:
            nonlocal _last_n, _started
            n = data.get("files_done", 0)
            total = data.get("total_files", 0)
            if not _started and total > 0:
                STDERR_CONSOLE.print(f"  Indexing {total} files...")
                _started = True
            step = max(1, total // 10) if total > 0 else 1
            if n - _last_n >= step or (n == total and total > 0):
                STDERR_CONSOLE.print(
                    f"  Progress: {n}/{total} files processed, {data.get('chunks_indexed', 0):,} chunks"
                )
                _last_n = n

        return None, _line_callback

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold deep_sky_blue3]Indexing"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("files"),
        TextColumn("[dim]{task.fields[chunks]:,} chunks[/dim]"),
        TimeElapsedColumn(),
        transient=True,
    )
    _task_id: TaskID = progress.add_task("indexing", total=None, chunks=0)

    def _rich_callback(data: dict[str, Any]) -> None:
        total = data.get("total_files", 0)
        done = data.get("files_done", 0)
        chunks = data.get("chunks_indexed", 0)
        # Use total or None so Rich shows a spinner when total is unknown/zero
        progress.update(_task_id, total=total or None, completed=done, chunks=chunks)

    return progress, _rich_callback


@app.command()
def index(
    name: str = typer.Argument(..., help="Name of the repository to index."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run without persisting."),
    force: bool = typer.Option(False, "--force", help="Bypass clean working tree check."),
    full: bool = typer.Option(False, "--full", help="Process all files instead of incremental diff."),
    parallel: bool = typer.Option(True, "--parallel/--no-parallel", help="Use parallel indexing (default: True)."),
    workers: int | None = typer.Option(None, "--workers", "-w", help="Number of worker processes (default: auto)."),
) -> None:
    """Run the full indexing pipeline for the specified repository.

    Requirements:
      - The repository MUST already be registered in the metadata store.
        Register once with: uv run dolphin add-repo <name> <abs/repo/path>
    """
    config = load_config()

    # Require repo to be pre-registered via: uv run dolphin add-repo <name> <abs/repo/path>
    metadata = SQLiteMetadataStore(config.resolved_store_root() / _METADATA_DB_NAME)
    metadata.initialize()
    repo_record = metadata.get_repo_by_name(name)
    if not repo_record:
        typer.echo(
            "Error: Repository not registered. Register once with: uv run dolphin add-repo <name> <abs/repo/path>",
            err=True,
        )
        raise typer.Exit(code=2)

    pipeline = _build_pipeline(config)

    # Crash recovery: abort any sessions left running from a prior CLI invocation
    # (the server does this on startup, but CLI callers need it too)
    aborted = metadata.abort_stale_sessions(
        repo_id=int(repo_record["id"]),
        reason="Aborted on CLI startup: previous indexing session did not complete cleanly",
    )
    if aborted:
        typer.echo(f"Recovered {aborted} stale session(s) from a previous run.")

    # Install SIGINT handler so Ctrl-C stops cleanly between files
    _original_sigint = signal.getsignal(signal.SIGINT)

    def _sigint_handler(signum, frame):
        typer.echo("\nInterrupt received — stopping after current files…")
        pipeline.request_cancel()

    signal.signal(signal.SIGINT, _sigint_handler)

    progress_display, progress_callback = _create_progress_display()

    mode = "parallel" if parallel else "sequential"
    ctx: dict[str, object] = {"mode": mode}
    if parallel:
        ctx["workers"] = workers or "auto"
    print_status(f"Indexing {name}", level="step", context=ctx)

    t0 = time.monotonic()
    progress_ctx = progress_display if progress_display is not None else contextlib.nullcontext()
    try:
        with progress_ctx:
            if parallel:
                result = asyncio.run(
                    pipeline.index_parallel(
                        name,
                        dry_run=dry_run,
                        force=force,
                        full_reindex=full,
                        max_workers=workers,
                        progress_callback=progress_callback,
                    )
                )
            else:
                result = pipeline.index(
                    name,
                    dry_run=dry_run,
                    force=force,
                    full_reindex=full,
                    progress_callback=progress_callback,
                )

    except Exception as e:
        from .pipeline import _CancelledError

        if isinstance(e, (KeyboardInterrupt, _CancelledError)):
            typer.echo("Indexing interrupted. Progress up to the last completed file has been saved.")
            typer.echo("Run the same command again to continue from where you left off.")
            raise typer.Exit(code=130)
        typer.echo(f"Indexing failed: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        signal.signal(signal.SIGINT, _original_sigint)

    elapsed = time.monotonic() - t0
    elapsed_str = f"{int(elapsed)}s" if elapsed < 60 else f"{int(elapsed // 60)}m{int(elapsed % 60):02d}s"

    files_indexed = result.get("files_indexed", 0)
    chunks_indexed = result.get("chunks_indexed", 0)
    files_skipped_ignored = result.get("files_skipped_ignored", 0)
    files_error = result.get("files_error", 0)
    chunks_pruned = result.get("chunks_pruned", 0)

    summary_ctx: dict[str, object] = {
        "files": files_indexed,
        "chunks": f"{chunks_indexed:,}",
        "elapsed": elapsed_str,
    }
    print_status("Indexing complete", level="success", context=summary_ctx)

    skips: list[str] = []
    if files_skipped_ignored:
        skips.append(f"{files_skipped_ignored} ignored")
    if files_error:
        skips.append(f"{files_error} error{'s' if files_error != 1 else ''}")
    if skips:
        typer.echo(f"     Skipped: {', '.join(skips)}.")

    if chunks_pruned:
        typer.echo(f"     Pruned {chunks_pruned:,} stale chunk{'s' if chunks_pruned != 1 else ''}.")

    # Prune chunks for files matching ignore patterns (e.g., after ignore config changes)
    if not dry_run:
        try:
            prune_result = _prune_ignored_files(name, pipeline.metadata, pipeline.lancedb, config, dry_run=False)
            pruned_count = prune_result.get("chunks_pruned", 0)
            if pruned_count:
                typer.echo(f"  Pruned {pruned_count:,} chunk{'s' if pruned_count != 1 else ''} for ignored files.")
        except Exception as e:
            typer.echo(f"Warning: Failed to prune ignored files: {e}", err=True)

    # Notify server to reload
    _notify_server_reload(config)


def _notify_server_reload(config: KBConfig) -> None:
    """Notify the running server to reload its backend."""
    import httpx

    from ..api_key import load_kb_api_key

    endpoint = f"http://{config.endpoint}/v1/admin/reload"
    try:
        api_key = load_kb_api_key()
    except Exception:
        # API key might not exist yet if only indexing
        _log.debug("Could not load API key; skipping server notification.", exc_info=True)
        return

    if not api_key:
        _log.debug("No API key available; skipping server notification.")
        return

    try:
        response = httpx.post(endpoint, headers={"X-API-Key": api_key}, timeout=2.0)
        if response.status_code == 200:
            typer.echo(f"🧭 Server notified: {response.json().get('message')}")
        elif response.status_code != 404:  # Ignore 404 if old server running
            typer.echo(f"⚠️  Server reload failed: {response.status_code}", err=True)
    except httpx.HTTPError:
        # Server probably not running, which is fine
        pass


@app.command()
def status(name: str | None = typer.Argument(None, help="Optional repo name.")) -> None:
    """Report knowledge store status with detailed repository listing."""
    config = load_config()
    metadata = SQLiteMetadataStore(config.resolved_store_root() / _METADATA_DB_NAME)
    # Ensure DB and schema exist before summarizing.
    metadata.initialize()

    # Get aggregate counts
    summary = metadata.summarize()

    console = Console()

    # Summary Table
    console.print("\n[bold]🗺️  Knowledge Store Summary[/bold]")
    summary_table = Table(show_header=False, box=box.SIMPLE)
    summary_table.add_column("Metric", style="steel_blue1")
    summary_table.add_column("Value", style="bold white")
    summary_table.add_row("Total Repositories", str(summary["repos"]))
    summary_table.add_row("Total Files", str(summary["files"]))
    summary_table.add_row("Total Chunks", str(summary["chunks"]))
    console.print(summary_table)

    # List all registered repositories
    repos = metadata.list_all_repos()
    if repos:
        console.print("\n[bold]⚓ Registered Repositories[/bold]")
        repo_table = Table(box=box.ROUNDED)
        repo_table.add_column("Name", style="sea_green2")
        repo_table.add_column("Path", style="dim")
        repo_table.add_column("Embed Model")
        repo_table.add_column("Created", style="dim")

        for repo in repos:
            repo_table.add_row(
                repo["name"], str(repo["root_path"]), repo["default_embed_model"], str(repo["created_at"])
            )
        console.print(repo_table)
    else:
        console.print("\n[dark_goldenrod]No repositories registered.[/dark_goldenrod]")

    # Reranking status
    console.print("\n[bold]🔭 Reranking[/bold]")
    reranking_cfg = config.retrieval.reranking
    if not reranking_cfg.enabled:
        console.print("  [dim]Disabled (set reranking.enabled = true in config to enable)[/dim]")
    else:
        try:
            from sentence_transformers import CrossEncoder as _CE  # noqa: F401

            console.print(f"  [sea_green2]Enabled[/sea_green2] — model: {reranking_cfg.model}")
        except ImportError:
            console.print(
                "  [indian_red1]Enabled in config but dependencies are missing.[/indian_red1]\n"
                "  Install with: [bold]uv pip install pb-dolphin\\[reranking][/bold]"
            )

    console.print()


def _prune_ignored_files(
    name: str,
    metadata: SQLiteMetadataStore,
    lancedb: LanceDBStore,
    config: KBConfig,
    dry_run: bool = False,
) -> dict[str, int]:
    """Prune chunks for files matching ignore patterns.

    Returns dict with 'chunks_pruned' and 'files_pruned' counts.
    """
    # Resolve repo and get its root path
    repo_record = metadata.get_repo_by_name(name)
    if not repo_record:
        return {"chunks_pruned": 0, "files_pruned": 0}

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
    if repo_level_patterns:
        ignore_patterns.update(repo_level_patterns)
    # Apply repo-level exceptions
    if repo_level_exceptions:
        ignore_patterns = build_ignore_set(ignore_patterns, repo_level_exceptions)
    ignore_patterns.update(extra_security)

    # Manually add bun.lock patterns to test
    ignore_patterns.add("bun.lock")
    ignore_patterns.add("**/bun.lock")

    ignore_spec = PathSpec.from_lines("gitignore", ignore_patterns)

    # Get all files for this repo
    files = metadata.get_all_files_for_repo(repo_id)

    total_chunks_pruned = 0
    pruned_files = []
    for file_record in files:
        file_path = cast(str, file_record["path"])
        file_id = cast(int, file_record["id"])

        # Check if file matches ignore patterns
        matches = ignore_spec.match_file(file_path)

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

                # Delete the file record itself so it doesn't show up again on subsequent runs
                metadata.delete_file(repo_id, file_id)
            else:
                # In dry-run, just count what would be pruned
                file_chunks = metadata.get_chunks_for_file(repo_id, file_path)
                total_chunks_pruned += len(file_chunks) if file_chunks else 0

    # Rebuild FTS5 index after bulk deletes to prevent corruption
    if not dry_run and pruned_files:
        try:
            with metadata._connect() as conn:
                cur = conn.cursor()
                cur.execute("PRAGMA integrity_check")
                result = cur.fetchone()
                if result and result[0] != "ok":
                    _log.warning(f"FTS5 index integrity issue detected, rebuilding: {result[0]}")
                cur.execute("INSERT INTO chunks_fts(chunks_fts, rank) VALUES('rebuild', -1)")
                conn.commit()
        except Exception as e:
            _log.warning(f"Failed to rebuild FTS5 index: {e}")

    return {"chunks_pruned": total_chunks_pruned, "files_pruned": len(pruned_files)}


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

    metadata = SQLiteMetadataStore(repo / _METADATA_DB_NAME)
    metadata.initialize()

    lancedb = LanceDBStore(repo / _LANCEDB_DIR_NAME)
    lancedb.initialize_collections()

    result = _prune_ignored_files(name, metadata, lancedb, config, dry_run=dry_run)
    total_chunks_pruned = result["chunks_pruned"]
    files_pruned = result["files_pruned"]

    if dry_run:
        typer.echo("[DRY RUN] Would prune:")
        typer.echo(f"  Files: {files_pruned}")
        typer.echo(f"  Chunks: {total_chunks_pruned}")
    else:
        typer.echo(f"⛵ Pruned ignored content from '{name}':")
        typer.echo(f"  Files: {files_pruned}")
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
    metadata = SQLiteMetadataStore(config.resolved_store_root() / _METADATA_DB_NAME)
    metadata.initialize()

    lancedb = LanceDBStore(config.resolved_store_root() / _LANCEDB_DIR_NAME)

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
        typer.echo("  Use --force to override and abort active sessions.", err=True)
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
        typer.echo(f"\n⛵ Repository '{name}' removed successfully.")
        typer.echo("\nCleanup Statistics:")
        typer.echo(f"  Files deleted: {stats['files_deleted']}")
        typer.echo(f"  Chunk content deleted: {stats['content_deleted']}")
        typer.echo(f"  Chunk locations deleted: {stats['locations_deleted']}")
        typer.echo(f"  Sessions deleted: {stats['sessions_deleted']}")

        # FTS5 cleanup details
        fts_stats = stats["fts5_entries"]
        typer.echo("\n  FTS5 Cleanup:")
        typer.echo(f"    By content_id: {fts_stats['by_content_id']}")
        typer.echo(f"    By repo name: {fts_stats['by_repo_name']}")
        typer.echo(f"    Orphaned entries: {fts_stats['orphaned']}")

        # LanceDB cleanup details
        lance_stats = stats["lancedb_vectors"]
        typer.echo("\n  LanceDB Cleanup:")
        typer.echo(f"    Small model vectors: {lance_stats['small_deleted']}")
        typer.echo(f"    Large model vectors: {lance_stats['large_deleted']}")

        # Show warnings if any
        if "lancedb_warnings" in result:
            typer.echo("\n⚠️  Warnings:")
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
        "large",
        "--default-embed-model",
        help="Default embedding model for the Repo (small|large).",
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
    metadata = SQLiteMetadataStore(config.resolved_store_root() / _METADATA_DB_NAME)
    metadata.initialize()
    lancedb = LanceDBStore(config.resolved_store_root() / _LANCEDB_DIR_NAME)

    # If repo exists, wipe it (no confirmation, force=True for automatic cleanup)
    repo = metadata.get_repo_by_name(name)
    if repo:
        typer.echo(f"Removing all data for '{name}' using enhanced cleanup...")

        try:
            # Use enhanced removal with force=True (skip confirmation, abort active sessions)
            result = metadata.rm_repo_with_lancedb(lancedb, name, force=True)

            # Display brief cleanup summary
            stats = result["cleanup_stats"]
            typer.echo(
                f"✓ Removed: {stats['files_deleted']} files, "
                f"{stats['content_deleted']} chunks, "
                f"{stats['lancedb_vectors']['small_deleted'] + stats['lancedb_vectors']['large_deleted']} vectors"
            )

            # Show warnings if any
            if "lancedb_warnings" in result and result["lancedb_warnings"]:
                typer.echo(f"⚠️  Cleanup warnings: {len(result['lancedb_warnings'])}", err=True)

        except Exception as e:
            _log.warning("Enhanced cleanup failed for %s, continuing anyway", name, exc_info=True)
            typer.echo(f"Warning: Enhanced cleanup failed, continuing anyway: {e}", err=True)

    # Re-register repo
    metadata.record_repo(name=name, path=repo_path, default_embed_model=model)
    typer.echo(f"⛵ Repository '{name}' re-registered: path='{repo_path}', default_embed_model='{model}'")


@app.command()
def prune(
    name: str = typer.Argument(..., help="Repository name to prune."),
    older_than: str = typer.Option("30d", "--older-than", help="Age cutoff for pruning sessions."),
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
    metadata = SQLiteMetadataStore(config.resolved_store_root() / _METADATA_DB_NAME)
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
    show_content: bool = typer.Option(False, "--show-content", "-c", help="Display code snippets."),
) -> None:
    """Search indexed code semantically (local backend).

    Examples:
        dolphin search "authentication logic" --repo myapp
        dolphin search "database migration" --path src/db --top-k 5
        dolphin search "error handling" --show-content
    """
    from ..api.app import SearchRequest
    from ..api.search_backend import create_search_backend

    config = load_config()

    try:
        # Create search backend
        backend = create_search_backend(
            store_root=config.resolved_store_root(),
            embedding_provider_type=config.embedding_provider,
            default_embed_model=config.default_embed_model,
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

        # Display results
        if not hits:
            typer.echo("No results found.")
            return

        typer.echo(f"\n🔭 Found {len(hits)} result(s):\n")

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
                        typer.secho(
                            f"   ... ({len(content.splitlines()) - 10} more lines)",
                            fg="yellow",
                        )
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
    metadata = SQLiteMetadataStore(config.resolved_store_root() / _METADATA_DB_NAME)
    metadata.initialize()

    lancedb = LanceDBStore(config.resolved_store_root() / _LANCEDB_DIR_NAME)

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
            typer.echo(f"\n  ✓ Repository '{name}' is consistent.")
        else:
            typer.echo(f"\n🚩 Repository '{name}' has consistency issues:", err=True)
            for issue in report["issues"]:
                typer.echo(f"  - {issue}", err=True)

        # Display statistics
        stats = report["statistics"]
        typer.echo("\nStatistics:")
        typer.echo(f"  Files: {stats['metadata_files']}")
        typer.echo(f"  Chunks: {stats['metadata_chunks']}")
        typer.echo(f"  Locations: {stats['metadata_locations']}")
        typer.echo(f"  Orphaned locations: {stats['orphaned_locations']}")
        typer.echo(f"  Orphaned FTS entries: {stats['orphaned_fts']}")
        typer.echo(f"  Orphaned content: {stats['orphaned_content']}")
        typer.echo(f"  Orphaned files: {stats['orphaned_files']}")

        # LanceDB stats
        lancedb_stats = report["lancedb"]
        typer.echo("\nLanceDB Vectors:")
        for model, count in lancedb_stats["vector_counts"].items():
            typer.echo(f"  {model}: {count}")

        if not report["valid"]:
            typer.echo(f"\nTip: Run 'dolphin repair-repo {name}' to fix these issues.")
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
    metadata = SQLiteMetadataStore(config.resolved_store_root() / _METADATA_DB_NAME)
    metadata.initialize()

    lancedb = LanceDBStore(config.resolved_store_root() / _LANCEDB_DIR_NAME)

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

        typer.echo("\n[DRY RUN] Would repair the following issues:")
        for issue in report["issues"]:
            typer.echo(f"  - {issue}")

        stats = report["statistics"]
        total_repairs = (
            stats["orphaned_locations"] + stats["orphaned_fts"] + stats["orphaned_content"] + stats["orphaned_files"]
        )
        typer.echo(f"\nTotal items that would be repaired: {total_repairs}")
        return

    # Perform repair
    typer.echo(f"Repairing repository '{name}'...")
    try:
        repair_report = metadata.repair_repository_consistency(repo_id, name)

        if repair_report["success"]:
            if repair_report["repairs_performed"]:
                typer.echo(f"\n⛵ Repository '{name}' repaired successfully.")
                typer.echo("\nRepairs performed:")
                for repair in repair_report["repairs_performed"]:
                    typer.echo(f"  - {repair}")
            else:
                typer.echo(f"\n  ✓ No repairs needed for '{name}'.")
        else:
            typer.echo("\n🚩 Repair completed with errors:", err=True)
            for error in repair_report["errors"]:
                typer.echo(f"  - {error}", err=True)
            raise typer.Exit(code=1)

    except Exception as e:
        typer.echo(f"Error: Repair failed: {e}", err=True)
        raise typer.Exit(code=1)


@app.command("list-repos")
def list_repos() -> None:
    """List all registered repositories."""
    config = load_config()
    metadata = SQLiteMetadataStore(config.resolved_store_root() / _METADATA_DB_NAME)
    metadata.initialize()

    repos = metadata.list_all_repos()
    if not repos:
        typer.echo("No repositories registered.")
        return

    typer.echo(f"\n⚓ Registered Repositories ({len(repos)}):\n")
    for repo in repos:
        typer.echo(f"  • {repo['name']}")
        typer.echo(f"    Path: {repo['root_path']}")
        typer.echo(f"    Model: {repo['default_embed_model']}")
        typer.echo(f"    ID: {repo['id']}")
        typer.echo()


@app.command("reset-all")
def reset_all(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt."),
) -> None:
    """Reset the entire knowledge store (delete everything).

    WARNING: This will:
    - Remove ALL repositories
    - Delete ALL metadata (files, chunks, locations, sessions, FTS)
    - Delete ALL vectors from LanceDB
    - Preserve configuration

    This is a nuclear option for complete cleanup.
    """
    config = load_config()
    metadata = SQLiteMetadataStore(config.resolved_store_root() / _METADATA_DB_NAME)
    metadata.initialize()

    lancedb = LanceDBStore(config.resolved_store_root() / _LANCEDB_DIR_NAME)

    # Get all repos for cleanup
    repos = metadata.list_all_repos()

    if not repos:
        typer.echo("No repositories to clean up.")
        return

    # Show what will be deleted
    summary = metadata.summarize()
    typer.echo("\n⚠️  WARNING: This will delete EVERYTHING:")
    typer.echo(f"  • {len(repos)} repositories")
    typer.echo(f"  • {summary['files']} files")
    typer.echo(f"  • {summary['chunks']} chunks")
    typer.echo("\nRepositories to be removed:")
    for repo in repos:
        typer.echo(f"  - {repo['name']} ({repo['root_path']})")

    # Confirm unless --force
    if not force:
        typer.echo()
        confirm = typer.confirm("Are you absolutely sure you want to delete everything?")
        if not confirm:
            typer.echo("Aborted.")
            raise typer.Exit(code=0)

    # Remove all repos using enhanced cleanup
    typer.echo("\n🧹 Removing all repositories with comprehensive cleanup...")
    total_stats = ResetStats()

    for repo in repos:
        try:
            result = metadata.rm_repo_with_lancedb(lancedb, repo["name"], force=True)
            stats = result["cleanup_stats"]

            total_stats.repos_removed += 1
            total_stats.files_deleted += stats["files_deleted"]
            total_stats.content_deleted += stats["content_deleted"]
            total_stats.locations_deleted += stats["locations_deleted"]
            total_stats.sessions_deleted += stats["sessions_deleted"]
            total_stats.vectors_deleted += (
                stats["lancedb_vectors"]["small_deleted"] + stats["lancedb_vectors"]["large_deleted"]
            )

            typer.echo(f"  ✓ Removed {repo['name']}")

            # Capture any warnings
            if "lancedb_warnings" in result:
                total_stats.errors.extend(result["lancedb_warnings"])

        except Exception as e:
            error_msg = f"Failed to remove {repo['name']}: {e}"
            _log.error("Failed to remove repo %s during reset", repo["name"], exc_info=True)
            total_stats.errors.append(error_msg)
            typer.echo(f"  🚩 {error_msg}", err=True)

    # Display final summary
    typer.echo("\n⛵ Reset complete!")
    typer.echo("\nCleanup Statistics:")
    typer.echo(f"  Repositories removed: {total_stats.repos_removed}")
    typer.echo(f"  Files deleted: {total_stats.files_deleted}")
    typer.echo(f"  Chunks deleted: {total_stats.content_deleted}")
    typer.echo(f"  Locations deleted: {total_stats.locations_deleted}")
    typer.echo(f"  Sessions deleted: {total_stats.sessions_deleted}")
    typer.echo(f"  Vectors deleted: {total_stats.vectors_deleted}")

    if total_stats.errors:
        typer.echo(f"\n⚠️  Warnings ({len(total_stats.errors)}):")
        for error in total_stats.errors:
            typer.echo(f"  - {error}", err=True)

    typer.echo(f"\nConfiguration preserved at: {config.resolved_store_root()}")
    typer.echo("You can now run 'dolphin add-repo' to register new repositories.")


def main() -> None:
    try:
        app()
    except ConfigNotFoundError as e:
        print_status(str(e), level="error", stderr=True)
        raise typer.Exit(1) from None


if __name__ == "__main__":
    main()
