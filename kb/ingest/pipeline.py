from __future__ import annotations

import asyncio
import datetime
import logging
import sqlite3
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pathspec import PathSpec

from ..cache import QueryCache
from ..chunkers.registry import chunk_file as chunk_file_with_config, detect_language_from_extension
from ..config import KBConfig
from ..constants.retrieval_config import RETRIEVAL_PARAMS
from ..embeddings.provider import embed_texts_with_retry
from ..graph_intelligence.graph_manager import GraphManager
from ..hashing import hash_text
from ..ignores import build_ignore_set, load_repo_ignores
from ..ingest._helpers import (
    build_desired_map,
    get_all_tracked_files,
    git_changed_files_deleted,
    git_changed_files_modified_added,
    representative_text_for_hash,
)
from ..ingest.dedup import ChunkDeduplicator
from ..ingest.error_logging import ErrorLogger
from ..ingest.graph_helpers import (
    cleanup_graph_for_file,
    cleanup_graph_for_repo,
    extract_graph_from_file,
    store_graph_data,
)
from ..ingest.scanner import FileCandidate, scan_repo
from ..store import LanceDBStore, SQLiteMetadataStore
from ..store.graph_store import GraphStore
from ..store.sqlite_meta import generate_fts_content_id

# Parallel indexing imports
from .async_embedder import EmbeddingQueue, RateLimitedEmbedder
from .dynamic_pool import DynamicWorkerPool, WorkloadEstimator
from .parallel_parser import ParseJob, parse_files_parallel
from .parallel_scanner import scan_repo_parallel

logger = logging.getLogger(__name__)

# Type alias for optional progress callback
ProgressCallback = Callable[[dict[str, Any]], None] | None


def _progress_event(event: str, *, done: int, total: int, chunks: int, path: str) -> dict[str, Any]:
    """Build a progress callback event dict."""
    return {"event": event, "files_done": done, "total_files": total, "chunks_indexed": chunks, "current_file": path}


class _CancelledError(Exception):
    """Raised when an indexing operation is cancelled via Ctrl-C / request_cancel()."""


@dataclass
class IngestionPipeline:
    """Coordinates scanning, chunking, and persistence."""

    config: KBConfig
    lancedb: LanceDBStore
    metadata: SQLiteMetadataStore
    graph_store: GraphStore | None = None
    graph_managers: dict[int, GraphManager] | None = None  # repo_id -> GraphManager
    cache: QueryCache | None = None
    _cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def __post_init__(self):
        """Initialize graph store if not provided."""
        if self.graph_store is None:
            self.graph_store = GraphStore(self.metadata.db_path)
        if self.graph_managers is None:
            self.graph_managers = {}
        self._bm25_stats_path: Path | None = self._resolve_bm25_stats_path()
        self._configure_bm25_statistics()

    def request_cancel(self) -> None:
        """Signal the pipeline to stop after the current file completes."""
        self._cancel_event.set()

    def is_cancel_requested(self) -> bool:
        """Return True if cancellation has been requested."""
        return self._cancel_event.is_set()

    def _check_cancelled(self) -> None:
        """Raise ``_CancelledError`` if cancellation was requested."""
        if self._cancel_event.is_set():
            raise _CancelledError("Indexing cancelled")

    def get_graph_manager(self, repo_id: int) -> GraphManager:
        """Get or create GraphManager for a repository.

        Args:
            repo_id: Repository ID

        Returns:
            GraphManager instance for the repository
        """
        if self.graph_managers is None:
            self.graph_managers = {}
        if repo_id not in self.graph_managers:
            # Use the database engine from the graph_store
            db_engine = self.graph_store.db if self.graph_store else None
            if db_engine is None:
                # Fallback to creating engine from metadata db_path
                from sqlmodel import create_engine

                db_engine = create_engine(f"sqlite:///{self.metadata.db_path}")

            self.graph_managers[repo_id] = GraphManager(
                db=db_engine,
                repo_id=repo_id,
                edge_change_threshold=5,
                cache_ttl_minutes=10,
            )
        return self.graph_managers[repo_id]

    def _resolve_bm25_stats_path(self) -> Path:
        config_path = self.config.retrieval.bm25_normalization.stats_path
        if config_path:
            return Path(config_path).expanduser()
        return self.config.resolved_store_root() / RETRIEVAL_PARAMS.BM25_NORMALIZATION.stats_filename

    def _configure_bm25_statistics(self) -> None:
        if not hasattr(self.metadata, "configure_bm25_statistics"):
            return
        try:
            self.metadata.configure_bm25_statistics(self._bm25_stats_path)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to enable BM25 statistics collection", exc_info=exc)

    def _invalidate_cache_for_repo(self, repo_name: str, *, dry_run: bool) -> None:
        if dry_run or not self.cache:
            return
        try:
            self.cache.invalidate_repo(repo_name)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to invalidate cache for repo %s", repo_name, exc_info=exc)

    def _flush_bm25_statistics(self) -> None:
        if not hasattr(self.metadata, "flush_bm25_statistics"):
            return
        try:
            path = self.metadata.flush_bm25_statistics()
            if path:
                logger.info(f"  BM25 score statistics written to {path}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to flush BM25 statistics", exc_info=exc)

    def _cleanup_deleted_file_dependencies(self, repo_id: int, repo_name: str, file_id: int, path: str) -> int:
        """Clean dependent data for a deleted file before deleting the file row."""
        total_pruned = 0
        for model_name in ("small", "large"):
            pruned_count = self.metadata.prune_invalidated_content_for_file(
                repo_id,
                file_id,
                embed_model=model_name,
                current_hashes=set(),
            )
            if pruned_count:
                total_pruned += pruned_count
            self.lancedb.prune_file_rows(repo_name, path, model=model_name)

        edges_deleted = 0
        nodes_deleted = 0
        if self.graph_store:
            nodes_deleted, edges_deleted = cleanup_graph_for_file(self.graph_store, file_id)

        if self.graph_store and (edges_deleted > 0 or nodes_deleted > 0):
            graph_manager = self.get_graph_manager(repo_id)
            if edges_deleted > 0:
                graph_manager.on_edges_changed(edges_deleted)
            else:
                graph_manager.invalidate_cache()

        # Delete file record last so all dependent cleanup runs first.
        self.metadata.delete_file(repo_id, file_id)
        return total_pruned

    def _format_deletion_error(self, path: str, file_id: int | None, exc: Exception) -> str:
        """Format concise deletion errors with actionable context."""
        if isinstance(exc, sqlite3.IntegrityError):
            return (
                f"Error processing deleted file {path}: foreign-key cleanup incomplete "
                f"(file_id={file_id}). Ensure startup migration to canonical schema has run. "
                f"Details: {exc}"
            )
        return f"Error processing deleted file {path}: {exc}"

    def _format_index_summary(self, path: str, chunk_count: int, new_count: int, skipped_count: int) -> str:
        """Format a single high-signal summary line for file indexing progress."""
        if new_count <= 0:
            return f"  {path}: unchanged ({chunk_count} chunks, {skipped_count} skipped)"
        if skipped_count <= 0:
            return f"  {path}: {chunk_count} chunks, {new_count} new"
        return f"  {path}: {chunk_count} chunks, {new_count} new, {skipped_count} skipped"

    def compute_graph_metrics(self, repo_id: int) -> dict[str, Any]:
        """Compute and store graph metrics for a repository.

        This method should be called after indexing to compute PageRank,
        centrality, and other graph metrics.

        Args:
            repo_id: Repository ID

        Returns:
            Dictionary with metrics summary
        """
        graph_manager = self.get_graph_manager(repo_id)

        # Get the graph (will rebuild if needed)
        graph = graph_manager.get_graph()

        if graph.number_of_nodes() == 0:
            return {
                "repo_id": repo_id,
                "node_count": 0,
                "edge_count": 0,
                "metrics_computed": False,
            }

        # Compute metrics
        metrics = graph_manager.compute_metrics()

        # Store metrics
        graph_manager.store_metrics(metrics)

        return {
            "repo_id": repo_id,
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "metrics_computed": True,
            "pagerank_nodes": len(metrics.get("pagerank", {})),
            "betweenness_nodes": len(metrics.get("betweenness_centrality", {})),
            "communities": (len(set(metrics.get("community", {}).values())) if "community" in metrics else 0),
        }

    def _git(self, root: Path, *args: str) -> str:
        try:
            out = subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT)
            return out.decode("utf-8")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(e.output.decode("utf-8", errors="ignore"))

    def _ensure_clean_working_tree(self, root: Path) -> None:
        # only consider tracked files
        try:
            subprocess.check_call(["git", "-C", str(root), "update-index", "-q", "--refresh"])
            subprocess.check_call(["git", "-C", str(root), "diff-index", "--quiet", "HEAD", "--"])
        except subprocess.CalledProcessError:
            raise RuntimeError("Working tree has tracked changes; commit or stash before indexing.")

    def _drop_repo_index(self, repo_id: int, repo_name: str) -> None:
        """Drop all indexed data for a repository (vectors and metadata).

        This clears:
        - All chunk content and locations from metadata
        - All vectors from LanceDB (both small and large models)
        - All FTS5 index entries
        - All code graph data (nodes and edges)

        Args:
            repo_id: Repository ID
            repo_name: Repository name
        """
        # Delete from LanceDB (both models)
        logger.info("  Clearing vectors from LanceDB...")
        for model in ["small", "large"]:
            try:
                self.lancedb.delete_repo(repo_name, model=model)
            except Exception:
                logger.warning("Could not delete %s vectors for repo %s", model, repo_name, exc_info=True)

        # Delete code graph data
        if self.graph_store:
            logger.info("  Clearing code graph data...")
            try:
                nodes_deleted = cleanup_graph_for_repo(self.graph_store, repo_id)
                logger.info(f"  Deleted {nodes_deleted} graph nodes and associated edges")
            except Exception:
                logger.warning("Could not delete graph data for repo_id=%s", repo_id, exc_info=True)

        # Delete from metadata database
        logger.info("  Clearing metadata...")
        with self.metadata._connect() as conn:
            cur = conn.cursor()

            # Helper to check if table exists
            def table_exists(table_name: str) -> bool:
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                )
                return cur.fetchone() is not None

            try:
                # Get all file IDs for this repo
                cur.execute("SELECT id FROM files WHERE repo_id = ?", (repo_id,))
                file_ids = [row[0] for row in cur.fetchall()]

                # Delete in correct order respecting foreign key constraints:

                # 1. Delete code graph data (references code_nodes and files)
                # Check table existence first to avoid swallowing real FK errors
                if table_exists("node_aliases"):
                    cur.execute(
                        "DELETE FROM node_aliases WHERE file_id IN (SELECT id FROM files WHERE repo_id = ?)",
                        (repo_id,),
                    )

                if table_exists("cross_repo_references"):
                    cur.execute(
                        "DELETE FROM cross_repo_references WHERE file_id IN (SELECT id FROM files WHERE repo_id = ?)",
                        (repo_id,),
                    )

                if table_exists("code_edges"):
                    cur.execute(
                        "DELETE FROM code_edges WHERE source_node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)",
                        (repo_id,),
                    )
                    cur.execute(
                        "DELETE FROM code_edges WHERE target_node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)",
                        (repo_id,),
                    )

                if table_exists("code_nodes"):
                    cur.execute("DELETE FROM code_nodes WHERE repo_id = ?", (repo_id,))

                # 2. Delete chunk locations (references chunk_content)
                for file_id in file_ids:
                    cur.execute(
                        """
                        DELETE FROM chunk_locations
                        WHERE content_id IN (
                            SELECT id FROM chunk_content WHERE file_id = ?
                        )
                    """,
                        (file_id,),
                    )

                # 3. Delete chunk content (references files)
                cur.execute("DELETE FROM chunk_content WHERE repo_id = ?", (repo_id,))

                # 4. Delete from FTS5
                cur.execute("DELETE FROM chunks_fts WHERE repo = ?", (repo_name,))

                # 5. Delete file snapshots (references files)
                if table_exists("file_snapshots"):
                    cur.execute("DELETE FROM file_snapshots WHERE repo_id = ?", (repo_id,))

                # 6. Delete files
                cur.execute("DELETE FROM files WHERE repo_id = ?", (repo_id,))

                # 7. Delete sessions
                cur.execute("DELETE FROM sessions WHERE repo_id = ?", (repo_id,))

                # 8. Delete pending changes
                if table_exists("pending_changes"):
                    cur.execute("DELETE FROM pending_changes WHERE repo_id = ?", (repo_id,))

                conn.commit()
                logger.info("  Metadata cleared successfully")
            except Exception:
                conn.rollback()
                logger.error("Error clearing metadata for repo_id=%s", repo_id, exc_info=True)
                raise

    def scan(self, repo_name: str, *, dry_run: bool = False, force: bool = False) -> dict:
        """Perform scanning for the named repository and persist file catalog.

        Returns a summary dictionary with counts and session info.
        """
        repo = self.metadata.get_repo_by_name(repo_name)
        if not repo:
            raise ValueError(f"Repository not registered: {repo_name}")

        repo_id = int(repo["id"])
        root = Path(repo["root_path"])
        embed_model = str(repo.get("default_embed_model", self.config.default_embed_model))
        # Validate embed model early
        from ..embeddings.provider import SUPPORTED_MODELS

        if embed_model not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported embed model configured for repo {repo_name}: {embed_model}")

        # Ensure clean working tree and capture provenance (unless forced)
        if not force:
            self._ensure_clean_working_tree(root)
        else:
            logger.warning(f"force=True, skipping clean working tree check for {repo_name}")
        commit_sha = self._git(root, "rev-parse", "HEAD").strip()
        branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()

        # Start session
        session_id = self.metadata.begin_session(repo_id, commit_sha, branch, embed_model)

        # Build ignore patterns using shared utility (returns set, not PathSpec)
        # For scan, we need the pattern set directly, not PathSpec
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
        ignore_patterns = build_ignore_set(self.config.ignore, self.config.ignore_exceptions)
        # Merge repo-level ignores from .dolphin/config.toml
        repo_level_patterns, repo_level_exceptions = load_repo_ignores(root)
        if repo_level_patterns:
            ignore_patterns.update(repo_level_patterns)
        # Apply repo-level exceptions
        if repo_level_exceptions:
            ignore_patterns = build_ignore_set(ignore_patterns, repo_level_exceptions)
        ignore_patterns.update(extra_security)

        # Scan
        candidates: list[FileCandidate] = scan_repo(root, ignore_patterns)

        summary = {
            "repo": repo_name,
            "repo_id": repo_id,
            "session_id": session_id,
            "commit": commit_sha,
            "branch": branch,
            "files_tracked": None,
            "files_kept": len(candidates),
        }

        # Persist file catalog unless dry_run
        if not dry_run:
            for c in candidates:
                self.metadata.upsert_file(
                    repo_id,
                    path=c.rel_path,
                    ext=c.ext,
                    language=c.language,
                    is_binary=c.is_binary,
                    size_bytes=c.size_bytes,
                )
            self.metadata.bump_session_counters(session_id, files_indexed=len(candidates))
            # Leave session running if next phases will proceed; here we mark succeeded for scan-only
            self.metadata.set_session_status(session_id, "succeeded")
        else:
            # Dry run: leave session as running but record file count
            self.metadata.bump_session_counters(session_id, files_indexed=len(candidates))

        summary["files_kept"] = len(candidates)
        return summary

    def run(self, repo_name: str, repo_path: Path, *, dry_run: bool = False) -> None:
        """Compatibility wrapper: call scan and print a summary."""
        _ = repo_path
        result = self.scan(repo_name, dry_run=dry_run)
        logger.info(f"Scan complete for {repo_name}: files_kept={result['files_kept']}, session={result['session_id']}")

    def process_files(
        self,
        repo_id: int,
        repo_name: str,
        root: Path,
        files: list[str],
        ignore_spec: PathSpec,
        embed_model: str,
        session_id: int,
        commit_sha: str,
        branch: str,
        dry_run: bool,
        error_logger: ErrorLogger,
        progress_callback: ProgressCallback = None,
    ) -> dict[str, int]:
        """Process a list of modified or added files."""
        stats = {
            "files_done": 0,
            "files_skipped_ignored": 0,
            "files_skipped_missing": 0,
            "files_error": 0,
            "chunks_indexed": 0,
            "chunks_skipped": 0,
            "vectors_written": 0,
            "chunks_pruned": 0,
            "graph_nodes_created": 0,
            "graph_edges_created": 0,
        }

        # Lazy load config
        from ..chunkers.repo_config import load_repo_chunking_config

        repo_config = load_repo_chunking_config(root)

        def _fire(event: str, path: str) -> None:
            if progress_callback is not None:
                done = (
                    stats["files_done"]
                    + stats["files_skipped_ignored"]
                    + stats["files_skipped_missing"]
                    + stats["files_error"]
                )
                progress_callback(
                    _progress_event(event, done=done, total=len(files), chunks=stats["chunks_indexed"], path=path)
                )

        for path in files:
            # Cooperative cancellation: stop cleanly between files
            self._check_cancelled()

            try:
                if ignore_spec.match_file(path):
                    stats["files_skipped_ignored"] += 1
                    logger.info(f"  {path}: skipped (ignored pattern)")
                    if not dry_run:
                        file_id = self.metadata.get_file_id(repo_id, path)
                        if file_id:
                            for model_name in ("small", "large"):
                                pruned = self.metadata.prune_invalidated_content_for_file(
                                    repo_id,
                                    file_id,
                                    model_name,
                                    current_hashes=set(),
                                )
                                if pruned:
                                    stats["chunks_pruned"] += pruned
                                self.lancedb.prune_file_rows(repo_name, path, model=model_name)
                    _fire("file_skipped", path)
                    continue

                # Skip missing/directory files (distinct from processing errors)
                file_path = root / path
                if not file_path.exists() or file_path.is_dir():
                    stats["files_skipped_missing"] += 1
                    _fire("file_skipped", path)
                    continue

                # Resolve or upsert file_id
                file_id = self.metadata.upsert_file(
                    repo_id=repo_id,
                    path=path,
                    ext=file_path.suffix,
                    language=None,  # Will be detected by chunker
                    is_binary=False,
                    size_bytes=file_path.stat().st_size,
                )

                # Determine language and chunk the file using repo config
                language = detect_language_from_extension(file_path) or "text"
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception as e:
                    stats["files_error"] += 1
                    error_logger.log_file_error(path, e)
                    logger.error(f"Error reading {path}: {e}")
                    continue

                chunks = chunk_file_with_config(
                    abs_path=file_path,
                    rel_path=path,
                    language=language,
                    text=text,
                    repo_config=repo_config,
                    model=embed_model,
                )

                # Compute text_hash for each chunk
                for chunk in chunks:
                    chunk.text_hash = hash_text(chunk.text)

                # Extract and store code graph data
                if self.graph_store and not dry_run:
                    try:
                        nodes, edges = extract_graph_from_file(file_path, language, text, repo_config)  # type: ignore[arg-type]
                        if nodes or edges:
                            graph_stats = store_graph_data(
                                self.graph_store,
                                nodes,
                                edges,
                                repo_id=repo_id,
                                file_id=file_id,
                                language=language,
                                commit_sha=commit_sha,
                                branch=branch,
                            )
                            stats["graph_nodes_created"] += graph_stats["nodes_created"]
                            stats["graph_edges_created"] += graph_stats["edges_created"]

                            # Initialize cache state if this is first indexing
                            graph_manager = self.get_graph_manager(repo_id)
                            cache_state = graph_manager.validator._get_cache_state()
                            if cache_state is None:
                                # Initialize cache state on first indexing
                                graph_manager.validator.update_cache_state(
                                    commit_sha=commit_sha,
                                    node_count=0,  # Will be updated after full index
                                    edge_count=0,  # Will be updated after full index
                                    reset_changes=True,
                                )

                            # Track edge changes for cache invalidation
                            if graph_stats["edges_created"] > 0:
                                graph_manager.on_edges_changed(graph_stats["edges_created"])
                    except Exception as e:
                        error_logger.log_file_error(f"graph: {path}", e)
                        # Don't fail the entire file if graph extraction fails
                        pass

                # Build desired map
                desired = build_desired_map(chunks)
                desired_row_ids: set[str] = set()

                # Deduplicate by text_hash
                dedup = ChunkDeduplicator(self.metadata)
                changed_chunks, unchanged_chunks = dedup.filter_unchanged_chunks(chunks, repo_id, file_id, embed_model)
                new_hashes = {c.text_hash for c in changed_chunks}
                skipped_occurrences = len(unchanged_chunks)

                # Embed only new hashes (batched)
                hash_to_vec: dict[str, Any] = {}
                if new_hashes and not dry_run:
                    hashes_list = sorted(new_hashes)
                    batch_size = 128
                    for i in range(0, len(hashes_list), batch_size):
                        batch_hashes = hashes_list[i : i + batch_size]
                        texts_to_embed = [representative_text_for_hash(h, chunks) for h in batch_hashes]
                        if not texts_to_embed:
                            continue
                        vectors = embed_texts_with_retry(embed_model, texts_to_embed)
                        hash_to_vec.update(dict(zip(batch_hashes, vectors)))

                # Upsert metadata and locations; prune invalidated
                if not dry_run:
                    mapping = self.metadata.ensure_content_rows_for_file(
                        repo_id, file_id, embed_model, list(desired.keys())
                    )

                    for h, occs in desired.items():
                        cid = mapping.get(h)
                        if cid:
                            self.metadata.sync_locations_for_content_row(cid, occs)

                    self.metadata.prune_invalidated_content_for_file(repo_id, file_id, embed_model, set(desired.keys()))

                    # Build a quick lookup for token_count by occurrence position
                    occ_token_counts: dict[tuple[int, int], int] = {
                        (ch.start_line, ch.end_line): getattr(ch, "token_count", 0) for ch in chunks
                    }

                    # Persist vectors to LanceDB (per occurrence)
                    payload = []
                    fts_chunks = []  # For FTS5 indexing
                    for h, occs in desired.items():
                        content_id = mapping.get(h)
                        vec = hash_to_vec.get(h)
                        for idx, occ in enumerate(occs):
                            row_id = f"{repo_id}:{file_id}:{embed_model}:{h}:{occ['start_line']}:{occ['end_line']}"
                            desired_row_ids.add(row_id)
                            if vec is None:
                                continue  # unchanged hash
                            payload.append(
                                {
                                    "id": row_id,
                                    "vector": vec,
                                    "repo": repo_name,
                                    "path": path,
                                    "start_line": occ["start_line"],
                                    "end_line": occ["end_line"],
                                    "text_hash": h,
                                    "commit": commit_sha,
                                    "branch": branch,
                                    "embed_model": embed_model,
                                    "language": language,
                                    "symbol_kind": occ.get("symbol_kind"),
                                    "symbol_name": occ.get("symbol_name"),
                                    "symbol_path": occ.get("symbol_path"),
                                    "heading_h1": occ.get("heading_h1"),
                                    "heading_h2": occ.get("heading_h2"),
                                    "heading_h3": occ.get("heading_h3"),
                                    "token_count": occ_token_counts.get((occ["start_line"], occ["end_line"]), 0),
                                    "created_at": datetime.datetime.now(datetime.UTC),
                                }
                            )

                            # Prepare chunk for FTS5 indexing (only for first occurrence per hash)
                            if content_id and idx == 0:  # First occurrence only
                                # Find the chunk text for this hash
                                chunk_text = None
                                for chunk in chunks:
                                    if chunk.text_hash == h:
                                        chunk_text = chunk.text
                                        break

                                if chunk_text:
                                    # Generate deterministic FTS5 content_id (independent of embed_model)
                                    fts_content_id = generate_fts_content_id(repo_id, file_id, h)

                                    fts_chunks.append(
                                        {
                                            "content_id": fts_content_id,
                                            "repo": repo_name,
                                            "path": path,
                                            "text_hash": h,
                                            "content": chunk_text,
                                            "symbol_name": occ.get("symbol_name"),
                                            "symbol_path": occ.get("symbol_path"),
                                        }
                                    )

                    if payload:
                        self.lancedb.upsert_chunks(repo_name, payload, model=embed_model)

                    # Index chunks in FTS5 for BM25 search
                    if fts_chunks and not dry_run:
                        self.metadata.bulk_index_chunks_for_fts(fts_chunks)

                    # Prune any stale vectors for this file/model
                    if desired_row_ids:
                        self.lancedb.prune_file_rows(repo_name, path, model=embed_model, keep_ids=desired_row_ids)
                    else:
                        self.lancedb.prune_file_rows(repo_name, path, model=embed_model)

                # Update counters
                stats["files_done"] += 1
                stats["chunks_indexed"] += len(new_hashes)
                stats["chunks_skipped"] += skipped_occurrences
                stats["vectors_written"] += len(new_hashes)

                # Log per-file summary
                logger.info(self._format_index_summary(path, len(chunks), len(new_hashes), skipped_occurrences))

                _fire("file_complete", path)

            except Exception as e:
                stats["files_error"] += 1
                error_logger.log_file_error(path, e)
                logger.error(f"Error processing {path}: {e}")
                _fire("file_error", path)
                continue

        return stats

    def process_deletions(
        self,
        repo_id: int,
        repo_name: str,
        files: list[str],
        embed_model: str,
        dry_run: bool,
        error_logger: ErrorLogger,
    ) -> dict[str, int]:
        """Process a list of deleted files."""
        _ = embed_model  # Deletions always prune both models for correctness.
        stats = {
            "files_done": 0,
            "chunks_pruned": 0,
        }

        for path in files:
            # Cooperative cancellation: stop cleanly between files
            self._check_cancelled()
            file_id: int | None = None
            try:
                file_id = self.metadata.get_file_id(repo_id, path)
                if not file_id:
                    continue

                if dry_run:
                    stats["files_done"] += 1
                    logger.info(f"  {path}: dry-run, would delete")
                    continue

                total_pruned = self._cleanup_deleted_file_dependencies(repo_id, repo_name, file_id, path)

                stats["files_done"] += 1
                stats["chunks_pruned"] += total_pruned
                logger.info(f"  {path}: deleted, {total_pruned} chunks pruned")
            except Exception as e:
                error_logger.log_file_error(f"deleted: {path}", e)
                logger.error(self._format_deletion_error(path, file_id, e))
                continue

        return stats

    def reconcile_branch_switch(self, repo_name: str) -> None:
        """Reconcile the index after a branch switch (using diff-based approach).

        This is a convenience wrapper for index() with intelligent defaults.
        It relies on the existing index() logic which handles merge-base diffing
        correctly when `full_reindex=False`.
        """
        # Calling index(..., force=True) to allow indexing even if working tree is dirty
        # (user preference for watcher mode).
        logger.info(f"Reconciling branch switch for {repo_name}...")
        self.index(repo_name, force=True)

    def index(
        self,
        repo_name: str,
        *,
        dry_run: bool = False,
        force: bool = False,
        full_reindex: bool = False,
        progress_callback: ProgressCallback = None,
    ) -> dict[str, Any]:
        """Perform full indexing pipeline for the named repository.

        This method implements the Phase 6 indexing pipeline:
        - Git diff gating for incremental indexing
        - Content hashing and deduplication
        - Embedding only new unique content
        - Metadata and vector persistence
        - Error handling and logging

        Args:
            repo_name: Name of the repository to index
            dry_run: If True, don't persist changes
            force: If True, skip clean working tree check
            full_reindex: If True, drop existing index and process all files

        Returns:
            Dictionary with session summary and counters
        """
        # Resolve repo and Git state
        repo = self.metadata.get_repo_by_name(repo_name)
        if not repo:
            raise ValueError(f"Repository not registered: {repo_name}")

        repo_id = int(repo["id"])
        root = Path(repo["root_path"])

        self._invalidate_cache_for_repo(repo_name, dry_run=dry_run)

        # Phase 2 Option B: Global Standardization
        # Target model is ALWAYS the global config default
        target_model = self.config.default_embed_model.strip().lower()

        # Check what the repo was last indexed with (or "large" if legacy/missing)
        # We rely on the DB to tell us the "last state"
        last_model = str(repo.get("default_embed_model", "large")).strip().lower()

        # If this is an existing repo (has successful commits) and models differ, we MUST migrate
        last_success = self.metadata.get_last_successful_commit(repo_id)
        is_fresh_index = last_success is None

        if target_model != last_model:
            logger.warning(f"Global model '{target_model}' differs from repo model '{last_model}'.")

            if not is_fresh_index:
                logger.info(f"   Triggering full re-index and migration for {repo_name}...")
                full_reindex = True
            else:
                logger.info(f"   Updating repo configuration for {repo_name}...")

            # Update repo record to new model immediately so this session is recorded correctly
            self.metadata.record_repo(repo_name, root, default_embed_model=target_model)

            # We also need to clean up the OLD model's vectors to avoid garbage
            # The _drop_repo_index call below (if full_reindex) clears *everything* usually,
            # but let's be explicit solely about the old model if we wanted to be granular.
            # However, _drop_repo_index clears ALL models for the repo, which is perfect for a full re-index.
            # So setting full_reindex=True is sufficient to trigger _drop_repo_index below.

        embed_model = target_model

        # Validate embed model early
        from ..embeddings.provider import SUPPORTED_MODELS

        if embed_model not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported embed model configured for repo {repo_name}: {embed_model}")

        # Ensure clean working tree and capture provenance (unless forced)
        if not force:
            self._ensure_clean_working_tree(root)
        else:
            logger.warning(f"force=True, skipping clean working tree check for {repo_name}")

        commit_sha = self._git(root, "rev-parse", "HEAD").strip()
        branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()

        # Drop existing index if full_reindex is requested
        if full_reindex and not dry_run:
            logger.info(f"Full reindex requested: dropping existing index for {repo_name}...")
            self._drop_repo_index(repo_id, repo_name)

        # Get last successful commit
        last_success = self.metadata.get_last_successful_commit(repo_id)

        # Quick consistency repair: clean up orphaned metadata from prior crashes
        # (lightweight — only touches SQLite, skipped on fresh/full reindex)
        if last_success is not None and not full_reindex:
            try:
                repair = self.metadata.repair_repository_consistency(repo_id, repo_name)
                if repair["repairs_performed"]:
                    for msg in repair["repairs_performed"]:
                        logger.info(f"  [auto-repair] {msg}")
            except Exception as exc:
                logger.warning("Auto-repair failed for %s, continuing anyway", repo_name, exc_info=exc)

        # Start session
        session_id = self.metadata.begin_session(repo_id, commit_sha, branch, embed_model)

        # Initialize error logger (lazy file creation on first error)
        error_logger = ErrorLogger(root, str(session_id))

        try:
            # Build ignore spec using shared utility
            from ..ignores import build_ignore_pathspec

            ignore_spec = build_ignore_pathspec(self.config.ignore, self.config.ignore_exceptions, root)

            # Determine changed files list
            if full_reindex or last_success is None:
                logger.info(f"Full reindex mode: processing all tracked files for {repo_name}")
                changed_files = get_all_tracked_files(root)
                deleted_files = []
            else:
                logger.info(f"Incremental mode: processing files changed since {last_success[:8]}")
                changed_files = git_changed_files_modified_added(root, last_success, commit_sha)
                deleted_files = git_changed_files_deleted(root, last_success, commit_sha)

            # Initialize counters
            files_done = chunks_indexed = chunks_skipped = vectors_written = chunks_pruned = 0
            files_skipped_ignored = files_skipped_missing = files_error = 0
            graph_nodes_created = graph_edges_created = 0

            # Process modified/added files
            stats = self.process_files(
                repo_id=repo_id,
                repo_name=repo_name,
                root=root,
                files=changed_files,
                ignore_spec=ignore_spec,
                embed_model=embed_model,
                session_id=session_id,
                commit_sha=commit_sha,
                branch=branch,
                dry_run=dry_run,
                error_logger=error_logger,
                progress_callback=progress_callback,
            )
            files_done += stats["files_done"]
            files_skipped_ignored += stats["files_skipped_ignored"]
            files_skipped_missing += stats["files_skipped_missing"]
            files_error += stats["files_error"]
            chunks_indexed += stats["chunks_indexed"]
            chunks_skipped += stats["chunks_skipped"]
            vectors_written += stats["vectors_written"]
            chunks_pruned += stats["chunks_pruned"]
            graph_nodes_created += stats["graph_nodes_created"]
            graph_edges_created += stats["graph_edges_created"]

            # Process deleted files
            del_stats = self.process_deletions(
                repo_id=repo_id,
                repo_name=repo_name,
                files=deleted_files,
                embed_model=embed_model,
                dry_run=dry_run,
                error_logger=error_logger,
            )
            files_done += del_stats["files_done"]
            chunks_pruned += del_stats["chunks_pruned"]

            # Prune any ignored files that were previously indexed
            # This handles files that were committed before being added to .gitignore
            if not dry_run:
                logger.info(f"Pruning previously-indexed ignored files for {repo_name}...")
                all_files = self.metadata.get_all_files_for_repo(repo_id)
                for file_record in all_files:
                    file_path = file_record["path"]
                    file_id = file_record["id"]

                    # Check if file matches ignore patterns
                    if ignore_spec.match_file(file_path):
                        # Prune all content for this file across all embedding models
                        for model in ["small", "large"]:
                            pruned_count = self.metadata.prune_invalidated_content_for_file(
                                repo_id, file_id, embed_model=model, current_hashes=set()
                            )
                            if pruned_count > 0:
                                chunks_pruned += pruned_count
                                logger.info(f"  {file_path}: pruned {pruned_count} ignored chunks (model={model})")
                            self.lancedb.prune_file_rows(repo_name, file_path, model=model)

                        # Clean up graph data for ignored file
                        edges_deleted = 0
                        nodes_deleted = 0
                        if self.graph_store:
                            nodes_deleted, edges_deleted = cleanup_graph_for_file(self.graph_store, file_id)

                        if self.graph_store and (edges_deleted > 0 or nodes_deleted > 0):
                            graph_manager = self.get_graph_manager(repo_id)
                            if edges_deleted > 0:
                                graph_manager.on_edges_changed(edges_deleted)
                            else:
                                graph_manager.invalidate_cache()

            # Update session counters
            if not dry_run:
                self.metadata.bump_session_counters(
                    session_id,
                    files_indexed=files_done,
                    chunks_indexed=chunks_indexed,
                    chunks_skipped=chunks_skipped,
                    vectors_written=vectors_written,
                    chunks_pruned=chunks_pruned,
                )
                self.metadata.set_session_status(session_id, "succeeded")
                self._flush_bm25_statistics()
            else:
                self.metadata.set_session_status(session_id, "succeeded", notes="dry_run")
                logger.info(f"Dry run: would have updated counters for session {session_id}")

            # Update cache state with final counts after indexing
            if not dry_run and self.graph_store:
                graph_manager = self.get_graph_manager(repo_id)
                # Force rebuild to get accurate total counts from database
                # This ensures cache state reflects TOTAL graph size, not just incremental changes
                graph_manager.get_graph(force_rebuild=True)
                # Cache state is automatically updated in _rebuild_graph() with total counts

            # Log summary
            summary_lines = [
                f"Indexing complete for {repo_name}:",
                f"  Files processed: {files_done}",
            ]
            if files_skipped_ignored:
                summary_lines.append(f"  Files skipped (ignored): {files_skipped_ignored}")
            if files_skipped_missing:
                summary_lines.append(f"  Files skipped (missing): {files_skipped_missing}")
            if files_error:
                summary_lines.append(f"  Files with errors: {files_error}")
            summary_lines.append(f"  Chunks indexed: {chunks_indexed}")
            summary_lines.append(f"  Chunks skipped (dedup): {chunks_skipped}")
            summary_lines.append(f"  Chunks pruned (deleted): {chunks_pruned}")
            summary_lines.append(f"  Vectors written: {vectors_written}")
            if graph_nodes_created > 0 or graph_edges_created > 0:
                summary_lines.append(f"  Graph nodes created: {graph_nodes_created}")
                summary_lines.append(f"  Graph edges created: {graph_edges_created}")
            summary_lines.append(f"  Session: {session_id}")

            # Only mention error log if something was actually written
            try:
                if error_logger.had_errors():
                    lp = error_logger.get_log_path()
                    if lp.exists() and lp.stat().st_size > 0:
                        summary_lines.append(f"  Errors logged to: {lp}")
            except Exception:
                logger.debug("Could not check error logger state.", exc_info=True)

            logger.info("\n".join(summary_lines))

            return {
                "repo": repo_name,
                "repo_id": repo_id,
                "session_id": session_id,
                "commit": commit_sha,
                "branch": branch,
                "files_indexed": files_done,
                "files_skipped_ignored": files_skipped_ignored,
                "files_skipped_missing": files_skipped_missing,
                "files_error": files_error,
                "chunks_indexed": chunks_indexed,
                "chunks_skipped": chunks_skipped,
                "vectors_written": vectors_written,
                "chunks_pruned": chunks_pruned,
                "graph_nodes_created": graph_nodes_created,
                "graph_edges_created": graph_edges_created,
                "dry_run": dry_run,
            }
        except (KeyboardInterrupt, _CancelledError):
            self.metadata.set_session_status(session_id, "aborted", notes="interrupted")
            raise
        except Exception as exc:
            self.metadata.set_session_status(session_id, "failed", notes=str(exc))
            raise

    def _setup_parallel_session(
        self,
        repo_name: str,
        force: bool,
        full_reindex: bool,
        dry_run: bool,
        max_workers: int | None,
    ) -> tuple[int, Path, str, str, str, int, ErrorLogger, set[str], list[str], list[str], int]:
        """Setup parallel indexing session and discover changed files.

        Returns:
            Tuple of (repo_id, root, embed_model, commit_sha, branch, session_id,
                     error_logger, ignore_patterns, changed_files, deleted_files,
                     files_skipped_ignored)
        """
        # Resolve repo and Git state
        repo = self.metadata.get_repo_by_name(repo_name)
        if not repo:
            raise ValueError(f"Repository not registered: {repo_name}")

        repo_id = int(repo["id"])
        root = Path(repo["root_path"])

        from ..embeddings.provider import SUPPORTED_MODELS

        # Detect model mismatch between global config and repo metadata
        target_model = self.config.default_embed_model.strip().lower()
        last_model = str(repo.get("default_embed_model", "large")).strip().lower()

        last_success = self.metadata.get_last_successful_commit(repo_id)
        is_fresh_index = last_success is None

        if target_model != last_model:
            logger.warning(f"Global model '{target_model}' differs from repo model '{last_model}'.")

            if not is_fresh_index:
                logger.info(f"   Triggering full re-index and migration for {repo_name}...")
                full_reindex = True
            else:
                logger.info(f"   Updating repo configuration for {repo_name}...")

            self.metadata.record_repo(repo_name, root, default_embed_model=target_model)

        embed_model = target_model

        if embed_model not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported embed model configured for repo {repo_name}: {embed_model}")

        if not force:
            self._ensure_clean_working_tree(root)
        else:
            logger.warning(f"force=True, skipping clean working tree check for {repo_name}")

        # Get git info
        commit_sha = self._git(root, "rev-parse", "HEAD").strip()
        branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()

        # Drop existing index if full_reindex is requested
        if full_reindex and not dry_run:
            logger.info(f"Full reindex requested: dropping existing index for {repo_name}...")
            self._drop_repo_index(repo_id, repo_name)

        # Quick consistency repair: clean up orphaned metadata from prior crashes
        if last_success is not None and not full_reindex:
            try:
                repair = self.metadata.repair_repository_consistency(repo_id, repo_name)
                if repair["repairs_performed"]:
                    for msg in repair["repairs_performed"]:
                        logger.info(f"  [auto-repair] {msg}")
            except Exception as exc:
                logger.warning("Auto-repair failed for %s, continuing anyway", repo_name, exc_info=exc)

        # Start session
        session_id = self.metadata.begin_session(repo_id, commit_sha, branch, embed_model)

        # Initialize error logger
        error_logger = ErrorLogger(root, str(session_id))

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
        ignore_patterns = build_ignore_set(self.config.ignore, self.config.ignore_exceptions)
        repo_level_patterns, repo_level_exceptions = load_repo_ignores(root)
        if repo_level_patterns:
            ignore_patterns.update(repo_level_patterns)
        if repo_level_exceptions:
            ignore_patterns = build_ignore_set(ignore_patterns, repo_level_exceptions)
        ignore_patterns.update(extra_security)

        # Determine changed files
        files_skipped_ignored = 0
        if full_reindex or last_success is None:
            logger.info(f"Full reindex mode: scanning all files for {repo_name}")
            with DynamicWorkerPool(max_workers=max_workers) as pool:
                candidates = scan_repo_parallel(root, ignore_patterns, pool=pool)
            changed_files = [c.rel_path for c in candidates]
            deleted_files = []
            # Ignored files are excluded by scan_repo_parallel; count not available here
        else:
            logger.info(f"Incremental mode: processing files changed since {last_success[:8]}")
            raw_changed = git_changed_files_modified_added(root, last_success, commit_sha)
            deleted_files = git_changed_files_deleted(root, last_success, commit_sha)

            # Filter ignored files from changed list and count them
            ignore_spec = PathSpec.from_lines("gitignore", ignore_patterns)
            changed_files = [f for f in raw_changed if not ignore_spec.match_file(f)]
            files_skipped_ignored = len(raw_changed) - len(changed_files)

        return (
            repo_id,
            root,
            embed_model,
            commit_sha,
            branch,
            session_id,
            error_logger,
            ignore_patterns,
            changed_files,
            deleted_files,
            files_skipped_ignored,
        )

    async def index_parallel(
        self,
        repo_name: str,
        *,
        dry_run: bool = False,
        force: bool = False,
        full_reindex: bool = False,
        max_workers: int | None = None,
        progress_callback: ProgressCallback = None,
    ) -> dict[str, Any]:
        """Parallel indexing with dynamic worker scaling.

        Args:
            repo_name: Name of the repository to index
            dry_run: If True, don't persist changes
            force: If True, skip clean working tree check
            full_reindex: If True, drop existing index and process all files
            max_workers: Max concurrent workers (None = auto-scale)

        Returns:
            Dictionary with session summary and counters
        """
        # Setup session, discover files, and initialize
        (
            repo_id,
            root,
            embed_model,
            commit_sha,
            branch,
            session_id,
            error_logger,
            ignore_patterns,
            changed_files,
            deleted_files,
            files_skipped_ignored,
        ) = self._setup_parallel_session(repo_name, force, full_reindex, dry_run, max_workers)

        self._invalidate_cache_for_repo(repo_name, dry_run=dry_run)

        # Counters
        files_done = chunks_indexed = chunks_skipped = vectors_written = chunks_pruned = 0
        files_skipped_missing = files_error = 0
        graph_nodes_created = graph_edges_created = 0

        # Setup Async Embedder
        embedder = RateLimitedEmbedder(provider_model=embed_model)
        embedding_queue = EmbeddingQueue(embedder)
        embedding_queue.start()

        # Total includes pre-filtered ignored files for consistent progress reporting.
        # Note: the sequential path (process_files) handles ignore checking inline and fires
        # individual file_skipped callbacks, so it doesn't need this initial bulk callback.
        total_files = len(changed_files) + files_skipped_ignored

        # Closure reads outer-scope counters by value at call time (Python late binding).
        # Callers must increment counters *before* calling _fire so done reflects the update.
        def _fire(event: str, path: str) -> None:
            if progress_callback is not None:
                done = files_done + files_skipped_ignored + files_skipped_missing + files_error
                progress_callback(
                    _progress_event(event, done=done, total=total_files, chunks=chunks_indexed, path=path)
                )

        # Fire initial callback for pre-filtered ignored files so progress starts correctly
        if files_skipped_ignored > 0:
            _fire("file_skipped", "<pre-filtered>")

        try:
            # Phase 1: Parallel Parsing
            logger.info(f"Processing {len(changed_files)} files...")

            batch_size = 50
            from ..chunkers.repo_config import load_repo_chunking_config

            repo_config = load_repo_chunking_config(root)

            # Create dynamic pool
            pool = DynamicWorkerPool(max_workers=max_workers)
            estimator = WorkloadEstimator()

            # Determine optimal batch size based on worker count and file count
            actual_workers = pool._optimal_workers
            batch_size = estimator.estimate_batch_size(
                total_items=len(changed_files), worker_count=actual_workers, min_batch=10, max_batch=100
            )
            logger.info(f"Using batch size: {batch_size} for {len(changed_files)} files and {actual_workers} workers")
            with pool as executor:
                # Process in batches to manage memory and flow
                for i in range(0, len(changed_files), batch_size):
                    # Cooperative cancellation: stop cleanly between batches
                    self._check_cancelled()

                    batch_paths = changed_files[i : i + batch_size]

                    parse_jobs = []
                    for path in batch_paths:
                        file_path = root / path
                        if not file_path.exists() or file_path.is_dir():
                            files_skipped_missing += 1
                            _fire("file_skipped", path)
                            continue

                        # Quick metadata update
                        if not dry_run:
                            # Prune invalidated content if re-indexing existing file
                            file_id = self.metadata.get_file_id(repo_id, path)
                            if file_id:
                                for model_name in ("small", "large"):
                                    pruned = self.metadata.prune_invalidated_content_for_file(
                                        repo_id, file_id, model_name, current_hashes=set()
                                    )
                                    if pruned:
                                        chunks_pruned += pruned
                                    self.lancedb.prune_file_rows(repo_name, path, model=model_name)

                        try:
                            # Read content (I/O bound but fast for source files)
                            text = file_path.read_text(encoding="utf-8", errors="ignore")
                            language = detect_language_from_extension(file_path) or "text"

                            # Update metadata catalog
                            if not dry_run:
                                file_id = self.metadata.upsert_file(
                                    repo_id=repo_id,
                                    path=path,
                                    ext=file_path.suffix,
                                    language=language,
                                    is_binary=False,
                                    size_bytes=file_path.stat().st_size,
                                )

                            parse_jobs.append(
                                ParseJob(
                                    file_path=file_path,
                                    content=text,
                                    language=language,
                                    model=embed_model,
                                    token_target=repo_config.get_window_size_for_language(language),
                                    overlap_pct=repo_config.overlap_pct,
                                )
                            )
                        except Exception as e:
                            files_error += 1
                            error_logger.log_file_error(path, e)
                            _fire("file_error", path)
                            continue

                    # Execute Parallel Parsing
                    parse_results = parse_files_parallel(parse_jobs, pool=executor)

                    # Sequential Processing of Results (dedup, graph, queuing)
                    embedding_tasks = []  # Collect embedding futures for concurrent processing

                    for res in parse_results:
                        if not res.success:
                            files_error += 1
                            error = Exception(res.error) if res.error else Exception("Unknown error")
                            error_logger.log_file_error(str(res.file_path), error)
                            _fire("file_error", str(res.file_path))
                            continue

                        chunks = res.chunks
                        path = str(res.file_path.relative_to(root))

                        # Graph Extraction (Main Thread)
                        if self.graph_store and not dry_run:
                            try:
                                # We need text for graph extraction. Ideally we passed it through or re-read
                                # But we have it in ParseJob... reusing here would require mapping back
                                # Re-reading might be safer or pass through ParseResult?
                                # Let's assume re-read is cached by OS or cheap enough.
                                text = res.file_path.read_text(encoding="utf-8", errors="ignore")
                                language = detect_language_from_extension(res.file_path) or "text"  # Re-detect

                                nodes, edges = extract_graph_from_file(res.file_path, language, text, vars(repo_config))
                                if nodes or edges:
                                    # Need file_id...
                                    file_id = self.metadata.get_file_id(repo_id, path)
                                    if file_id:
                                        graph_stats = store_graph_data(
                                            self.graph_store,
                                            nodes,
                                            edges,
                                            repo_id=repo_id,
                                            file_id=file_id,
                                            language=language,
                                            commit_sha=commit_sha,
                                            branch=branch,
                                        )
                                        graph_nodes_created += graph_stats["nodes_created"]
                                        graph_edges_created += graph_stats["edges_created"]

                                        # Track changes for graph validation
                                        if graph_stats["edges_created"] > 0:
                                            graph_manager = self.get_graph_manager(repo_id)
                                            graph_manager.on_edges_changed(graph_stats["edges_created"])

                            except Exception as e:
                                error_logger.log_file_error(f"graph: {path}", e)

                        # Deduplication
                        for c in chunks:
                            c.text_hash = hash_text(c.text)

                        dedup = ChunkDeduplicator(self.metadata)
                        file_id = self.metadata.get_file_id(repo_id, path)
                        if not file_id:
                            continue

                        try:
                            changed_chunks, unchanged_chunks = dedup.filter_unchanged_chunks(
                                chunks, repo_id, file_id, embed_model
                            )
                        except Exception as dedup_err:
                            files_error += 1
                            error_logger.log_file_error(path, dedup_err)
                            _fire("file_error", path)
                            continue
                        skipped_occurrences = len(unchanged_chunks)
                        chunks_skipped += skipped_occurrences

                        # Prepare for embedding
                        new_hashes = {c.text_hash for c in changed_chunks}

                        if new_hashes and not dry_run:
                            # Submit to Async Queue
                            unique_changed = []
                            seen = set()
                            for c in changed_chunks:
                                if c.text_hash not in seen:
                                    unique_changed.append(c)
                                    seen.add(c.text_hash)

                            texts = [c.text for c in unique_changed]
                            hashes = [c.text_hash for c in unique_changed]

                            # Submit embedding request (non-blocking) and collect for batch processing
                            embedding_future = embedding_queue.submit(texts, metadata={"path": path})

                            # Store task with associated data for concurrent processing
                            embedding_tasks.append(
                                {
                                    "future": embedding_future,
                                    "hashes": hashes,
                                    "chunks": chunks,
                                    "path": path,
                                    "file_id": file_id,
                                    "new_hashes": new_hashes,
                                    "skipped_occurrences": skipped_occurrences,
                                    "repo_id": repo_id,
                                    "embed_model": embed_model,
                                }
                            )

                    # Concurrent Embedding Processing - await all embedding tasks concurrently
                    if embedding_tasks:
                        logger.info(f"Processing {len(embedding_tasks)} embedding requests concurrently...")

                        # Await all futures concurrently
                        results = await asyncio.gather(
                            *[task["future"] for task in embedding_tasks], return_exceptions=True
                        )

                        # Process each result with its associated data
                        for task_data, vectors in zip(embedding_tasks, results):
                            if isinstance(vectors, Exception):
                                files_error += 1
                                error_logger.log_file_error(task_data["path"], vectors)
                                _fire("file_error", task_data["path"])
                                continue

                            # Extract task data
                            hashes = task_data["hashes"]
                            chunks = task_data["chunks"]
                            path = task_data["path"]
                            file_id = task_data["file_id"]
                            new_hashes = task_data["new_hashes"]
                            skipped_occurrences = task_data["skipped_occurrences"]
                            repo_id = task_data["repo_id"]
                            embed_model = task_data["embed_model"]

                            # Build mapping
                            mapping = dict(zip(hashes, vectors))

                            # Persist (Existing Logic)
                            desired = build_desired_map(chunks)

                            content_mapping = self.metadata.ensure_content_rows_for_file(
                                repo_id, file_id, embed_model, list(desired.keys())
                            )

                            for h, occs in desired.items():
                                cid = content_mapping.get(h)
                                if cid:
                                    self.metadata.sync_locations_for_content_row(cid, occs)

                            self.metadata.prune_invalidated_content_for_file(
                                repo_id, file_id, embed_model, set(desired.keys())
                            )

                            # LanceDB Payload
                            payload = []
                            occ_token_counts = {
                                (c.start_line, c.end_line): getattr(c, "token_count", 0) for c in chunks
                            }
                            desired_row_ids = set()

                            for h, occs in desired.items():
                                vec = mapping.get(h)

                                for occ in occs:
                                    row_id = (
                                        f"{repo_id}:{file_id}:{embed_model}:{h}:{occ['start_line']}:{occ['end_line']}"
                                    )
                                    desired_row_ids.add(row_id)
                                    if vec is None:
                                        continue

                                    payload.append(
                                        {
                                            "id": row_id,
                                            "vector": vec,
                                            "repo": repo_name,
                                            "path": path,
                                            "start_line": occ["start_line"],
                                            "end_line": occ["end_line"],
                                            "text_hash": h,
                                            "commit": commit_sha,
                                            "branch": branch,
                                            "embed_model": embed_model,
                                            "language": language,
                                            "symbol_kind": occ.get("symbol_kind"),
                                            "symbol_name": occ.get("symbol_name"),
                                            "symbol_path": occ.get("symbol_path"),
                                            "heading_h1": occ.get("heading_h1"),
                                            "heading_h2": occ.get("heading_h2"),
                                            "heading_h3": occ.get("heading_h3"),
                                            "token_count": occ_token_counts.get(
                                                (occ["start_line"], occ["end_line"]), 0
                                            ),
                                            "created_at": datetime.datetime.now(datetime.UTC),
                                        }
                                    )

                            if payload:
                                self.lancedb.upsert_chunks(repo_name, payload, model=embed_model)
                                vectors_written += len(mapping)

                            # Prune LanceDB
                            if desired_row_ids:
                                self.lancedb.prune_file_rows(
                                    repo_name, path, model=embed_model, keep_ids=desired_row_ids
                                )
                            else:
                                self.lancedb.prune_file_rows(repo_name, path, model=embed_model)

                            # Build FTS chunks for BM25 indexing
                            fts_chunks = []
                            for h, occs in desired.items():
                                chunk_text = representative_text_for_hash(h, chunks)
                                fts_content_id = content_mapping.get(h)
                                if fts_content_id:
                                    for occ in occs:
                                        fts_chunks.append(
                                            {
                                                "content_id": fts_content_id,
                                                "repo": repo_name,
                                                "path": path,
                                                "text_hash": h,
                                                "content": chunk_text,
                                                "symbol_name": occ.get("symbol_name"),
                                                "symbol_path": occ.get("symbol_path"),
                                            }
                                        )

                            # Index chunks in FTS5 for BM25 search
                            if fts_chunks and not dry_run:
                                self.metadata.bulk_index_chunks_for_fts(fts_chunks)

                            chunks_indexed += len(new_hashes)
                            files_done += 1
                            logger.info(
                                self._format_index_summary(path, len(chunks), len(new_hashes), skipped_occurrences)
                            )
                            _fire("file_complete", path)

            # Process deleted files using shared sync/async-safe logic.
            del_stats = self.process_deletions(
                repo_id=repo_id,
                repo_name=repo_name,
                files=deleted_files,
                embed_model=embed_model,
                dry_run=dry_run,
                error_logger=error_logger,
            )
            files_done += del_stats["files_done"]
            chunks_pruned += del_stats["chunks_pruned"]

        except (KeyboardInterrupt, _CancelledError):
            self.metadata.set_session_status(session_id, "aborted", notes="interrupted")
            raise
        except Exception as exc:
            self.metadata.set_session_status(session_id, "failed", notes=str(exc))
            raise
        finally:
            await embedding_queue.stop()

        # Update session counters (same as sync behavior)
        if not dry_run:
            self.metadata.bump_session_counters(
                session_id,
                files_indexed=files_done,
                chunks_indexed=chunks_indexed,
                chunks_skipped=chunks_skipped,
                vectors_written=vectors_written,
                chunks_pruned=chunks_pruned,
            )
            self.metadata.set_session_status(session_id, "succeeded")
            self._flush_bm25_statistics()
        else:
            self.metadata.set_session_status(session_id, "succeeded", notes="dry_run")

        # Graph cache updates
        if not dry_run and self.graph_store:
            graph_manager = self.get_graph_manager(repo_id)
            graph_manager.get_graph(force_rebuild=True)

        # Log summary (parallel pipeline does not log one during processing)
        summary_lines = [
            f"Indexing complete for {repo_name}:",
            f"  Files processed: {files_done}",
        ]
        if files_skipped_ignored:
            summary_lines.append(f"  Files skipped (ignored): {files_skipped_ignored}")
        if files_skipped_missing:
            summary_lines.append(f"  Files skipped (missing): {files_skipped_missing}")
        if files_error:
            summary_lines.append(f"  Files with errors: {files_error}")
        summary_lines.append(f"  Chunks indexed: {chunks_indexed}")
        summary_lines.append(f"  Chunks skipped (dedup): {chunks_skipped}")
        summary_lines.append(f"  Chunks pruned (deleted): {chunks_pruned}")
        summary_lines.append(f"  Vectors written: {vectors_written}")
        if graph_nodes_created > 0 or graph_edges_created > 0:
            summary_lines.append(f"  Graph nodes created: {graph_nodes_created}")
            summary_lines.append(f"  Graph edges created: {graph_edges_created}")
        summary_lines.append(f"  Session: {session_id}")
        try:
            if error_logger.had_errors():
                lp = error_logger.get_log_path()
                if lp.exists() and lp.stat().st_size > 0:
                    summary_lines.append(f"  Errors logged to: {lp}")
        except Exception:
            pass
        logger.info("\n".join(summary_lines))

        return {
            "repo": repo_name,
            "repo_id": repo_id,
            "session_id": session_id,
            "commit": commit_sha,
            "branch": branch,
            "files_indexed": files_done,
            "files_skipped_ignored": files_skipped_ignored,
            "files_skipped_missing": files_skipped_missing,
            "files_error": files_error,
            "chunks_indexed": chunks_indexed,
            "chunks_skipped": chunks_skipped,
            "vectors_written": vectors_written,
            "chunks_pruned": chunks_pruned,
            "graph_nodes_created": graph_nodes_created,
            "graph_edges_created": graph_edges_created,
            "dry_run": dry_run,
        }
