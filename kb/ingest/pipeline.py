from __future__ import annotations

import subprocess
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any

from pathspec import PathSpec

from ..config import KBConfig
from ..store import LanceDBStore, SQLiteMetadataStore
from ..store.graph_store import GraphStore
from ..store.sqlite_meta import generate_fts_content_id
from ..graph_intelligence.graph_manager import GraphManager
from ..ingest.scanner import FileCandidate, scan_repo
from ..ignores import build_ignore_set, load_repo_ignores
from ..ingest.dedup import ChunkDeduplicator
from ..ingest._helpers import (
    build_desired_map,
    git_changed_files_modified_added,
    git_changed_files_deleted,
    get_all_tracked_files,
    representative_text_for_hash,
)
from ..ingest.error_logging import ErrorLogger
from ..ingest.graph_helpers import (
    extract_graph_from_file,
    store_graph_data,
    cleanup_graph_for_file,
    cleanup_graph_for_repo,
)
from ..embeddings.provider import embed_texts_with_retry
from ..chunkers.registry import (
    detect_language_from_extension,
    chunk_file as chunk_file_with_config,
)
from ..hashing import hash_text


@dataclass
class IngestionPipeline:
    """Coordinates scanning, chunking, and persistence."""

    config: KBConfig
    lancedb: LanceDBStore
    metadata: SQLiteMetadataStore
    graph_store: GraphStore | None = None
    graph_managers: Dict[int, GraphManager] | None = None  # repo_id -> GraphManager

    def __post_init__(self):
        """Initialize graph store if not provided."""
        if self.graph_store is None:
            self.graph_store = GraphStore(self.metadata.db_path)
        if self.graph_managers is None:
            self.graph_managers = {}

    def get_graph_manager(self, repo_id: int) -> GraphManager:
        """Get or create GraphManager for a repository.

        Args:
            repo_id: Repository ID

        Returns:
            GraphManager instance for the repository
        """
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

    def compute_graph_metrics(self, repo_id: int) -> Dict[str, Any]:
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
            "communities": (
                len(set(metrics.get("community", {}).values()))
                if "community" in metrics
                else 0
            ),
        }

    def _git(self, root: Path, *args: str) -> str:
        try:
            out = subprocess.check_output(
                ["git", "-C", str(root), *args], stderr=subprocess.STDOUT
            )
            return out.decode("utf-8")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(e.output.decode("utf-8", errors="ignore"))

    def _ensure_clean_working_tree(self, root: Path) -> None:
        # only consider tracked files
        try:
            subprocess.check_call(
                ["git", "-C", str(root), "update-index", "-q", "--refresh"]
            )
            subprocess.check_call(
                ["git", "-C", str(root), "diff-index", "--quiet", "HEAD", "--"]
            )
        except subprocess.CalledProcessError:
            raise RuntimeError(
                "Working tree has tracked changes; commit or stash before indexing."
            )

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
        print("  Clearing vectors from LanceDB...")
        for model in ["small", "large"]:
            try:
                self.lancedb.delete_repo(repo_name, model=model)
            except Exception as e:
                print(f"  Warning: Could not delete {model} vectors: {e}")

        # Delete code graph data
        if self.graph_store:
            print("  Clearing code graph data...")
            try:
                nodes_deleted = cleanup_graph_for_repo(self.graph_store, repo_id)
                print(f"  Deleted {nodes_deleted} graph nodes and associated edges")
            except Exception as e:
                print(f"  Warning: Could not delete graph data: {e}")

        # Delete from metadata database
        print("  Clearing metadata...")
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
                if table_exists("code_node_aliases"):
                    cur.execute(
                        "DELETE FROM code_node_aliases WHERE file_id IN (SELECT id FROM files WHERE repo_id = ?)",
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
                    cur.execute(
                        "DELETE FROM file_snapshots WHERE repo_id = ?", (repo_id,)
                    )

                # 6. Delete files
                cur.execute("DELETE FROM files WHERE repo_id = ?", (repo_id,))

                # 7. Delete sessions
                cur.execute("DELETE FROM sessions WHERE repo_id = ?", (repo_id,))

                # 8. Delete pending changes
                if table_exists("pending_changes"):
                    cur.execute(
                        "DELETE FROM pending_changes WHERE repo_id = ?", (repo_id,)
                    )

                conn.commit()
                print("  Metadata cleared successfully")
            except Exception as e:
                conn.rollback()
                print(f"  Error clearing metadata: {e}")
                raise

    def scan(
        self, repo_name: str, *, dry_run: bool = False, force: bool = False
    ) -> dict:
        """Perform scanning for the named repository and persist file catalog.

        Returns a summary dictionary with counts and session info.
        """
        repo = self.metadata.get_repo_by_name(repo_name)
        if not repo:
            raise ValueError(f"Repository not registered: {repo_name}")

        repo_id = int(repo["id"])
        root = Path(repo["root_path"])
        embed_model = repo.get("default_embed_model", self.config.default_embed_model)
        # Validate embed model early
        from ..embeddings.provider import SUPPORTED_MODELS

        if embed_model not in SUPPORTED_MODELS:
            raise ValueError(
                f"Unsupported embed model configured for repo {repo_name}: {embed_model}"
            )

        # Ensure clean working tree and capture provenance (unless forced)
        if not force:
            self._ensure_clean_working_tree(root)
        else:
            print(
                f"Warning: force=True, skipping clean working tree check for {repo_name}"
            )
        commit_sha = self._git(root, "rev-parse", "HEAD").strip()
        branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()

        # Start session
        session_id = self.metadata.begin_session(
            repo_id, commit_sha, branch, embed_model
        )

        # Build ignore set (merge config + security patterns)
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
        ignore_patterns = build_ignore_set(
            self.config.ignore, self.config.ignore_exceptions
        )
        # Merge repo-level ignores from .dolphin/config.toml
        repo_level_patterns, repo_level_exceptions = load_repo_ignores(root)
        if repo_level_patterns:
            ignore_patterns.update(repo_level_patterns)
        # Apply repo-level exceptions
        if repo_level_exceptions:
            ignore_patterns = build_ignore_set(ignore_patterns, repo_level_exceptions)
        ignore_patterns.update(extra_security)

        # Scan
        candidates: List[FileCandidate] = scan_repo(root, ignore_patterns)

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
            self.metadata.bump_session_counters(
                session_id, files_indexed=len(candidates)
            )
            # Leave session running if next phases will proceed; here we mark succeeded for scan-only
            self.metadata.set_session_status(session_id, "succeeded")
        else:
            # Dry run: leave session as running but record file count
            self.metadata.bump_session_counters(
                session_id, files_indexed=len(candidates)
            )

        summary["files_kept"] = len(candidates)
        return summary

    def run(self, repo_name: str, repo_path: Path, *, dry_run: bool = False) -> None:
        """Compatibility wrapper: call scan and print a summary."""
        _ = repo_path
        result = self.scan(repo_name, dry_run=dry_run)
        print(
            f"Scan complete for {repo_name}: files_kept={result['files_kept']}, session={result['session_id']}"
        )

    def index(
        self,
        repo_name: str,
        *,
        dry_run: bool = False,
        force: bool = False,
        full_reindex: bool = False,
    ) -> Dict[str, Any]:
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
        embed_model = repo.get("default_embed_model", self.config.default_embed_model)
        # Validate embed model early
        from ..embeddings.provider import SUPPORTED_MODELS

        if embed_model not in SUPPORTED_MODELS:
            raise ValueError(
                f"Unsupported embed model configured for repo {repo_name}: {embed_model}"
            )

        # Ensure clean working tree and capture provenance (unless forced)
        if not force:
            self._ensure_clean_working_tree(root)
        else:
            print(
                f"Warning: force=True, skipping clean working tree check for {repo_name}"
            )

        commit_sha = self._git(root, "rev-parse", "HEAD").strip()
        branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()

        # Drop existing index if full_reindex is requested
        if full_reindex and not dry_run:
            print(f"Full reindex requested: dropping existing index for {repo_name}...")
            self._drop_repo_index(repo_id, repo_name)

        # Get last successful commit
        last_success = self.metadata.get_last_successful_commit(repo_id)

        # Start session
        session_id = self.metadata.begin_session(
            repo_id, commit_sha, branch, embed_model
        )

        # Initialize error logger (lazy file creation on first error)
        error_logger = ErrorLogger(root, str(session_id))

        # Build ignore spec for incremental processing
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
        ignore_patterns = build_ignore_set(
            self.config.ignore, self.config.ignore_exceptions
        )
        repo_level_patterns, repo_level_exceptions = load_repo_ignores(root)
        if repo_level_patterns:
            ignore_patterns.update(repo_level_patterns)
        # Apply repo-level exceptions
        if repo_level_exceptions:
            ignore_patterns = build_ignore_set(ignore_patterns, repo_level_exceptions)
        ignore_patterns.update(extra_security)
        ignore_spec = PathSpec.from_lines("gitwildmatch", ignore_patterns)

        # Determine changed files list
        if full_reindex or last_success is None:
            print(f"Full reindex mode: processing all tracked files for {repo_name}")
            changed_files = get_all_tracked_files(root)
            deleted_files = []
        else:
            print(
                f"Incremental mode: processing files changed since {last_success[:8]}"
            )
            changed_files = git_changed_files_modified_added(
                root, last_success, commit_sha
            )
            deleted_files = git_changed_files_deleted(root, last_success, commit_sha)

        # Initialize counters
        files_done = chunks_indexed = chunks_skipped = vectors_written = (
            chunks_pruned
        ) = 0
        graph_nodes_created = graph_edges_created = 0

        # Process modified/added files
        for path in changed_files:
            try:
                if ignore_spec.match_file(path):
                    print(f"  {path}: skipped (ignored pattern)")
                    if not dry_run:
                        file_id = self.metadata.get_file_id(repo_id, path)
                        if file_id:
                            for model_name in ("small", "large"):
                                pruned = (
                                    self.metadata.prune_invalidated_content_for_file(
                                        repo_id,
                                        file_id,
                                        model_name,
                                        current_hashes=set(),
                                    )
                                )
                                if pruned:
                                    chunks_pruned += pruned
                                self.lancedb.prune_file_rows(
                                    repo_name, path, model=model_name
                                )
                    continue
                # Skip binary files and files that don't exist
                file_path = root / path
                if not file_path.exists() or file_path.is_dir():
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
                    error_logger.log_file_error(path, e)
                    print(f"Error reading {path}: {e}")
                    continue

                from ..chunkers.repo_config import load_repo_chunking_config

                repo_config = load_repo_chunking_config(root)

                chunks = chunk_file_with_config(
                    abs_path=file_path,
                    rel_path=path,
                    language=language,
                    text=text,
                    repo_config=repo_config,
                )

                # Compute text_hash for each chunk
                for chunk in chunks:
                    chunk.text_hash = hash_text(chunk.text)

                # Extract and store code graph data
                if self.graph_store and not dry_run:
                    try:
                        nodes, edges = extract_graph_from_file(
                            file_path, language, text, repo_config
                        )
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
                            graph_nodes_created += graph_stats["nodes_created"]
                            graph_edges_created += graph_stats["edges_created"]

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
                                graph_manager.on_edges_changed(
                                    graph_stats["edges_created"]
                                )
                    except Exception as e:
                        error_logger.log_file_error(f"graph: {path}", e)
                        # Don't fail the entire file if graph extraction fails
                        pass

                # Build desired map
                desired = build_desired_map(chunks)
                desired_row_ids: set[str] = set()

                # Deduplicate by text_hash
                dedup = ChunkDeduplicator(self.metadata)
                changed_chunks, unchanged_chunks = dedup.filter_unchanged_chunks(
                    chunks, repo_id, file_id, embed_model
                )
                new_hashes = {c.text_hash for c in changed_chunks}
                skipped_occurrences = len(unchanged_chunks)

                # Embed only new hashes (batched)
                hash_to_vec: Dict[str, Any] = {}
                if new_hashes and not dry_run:
                    hashes_list = sorted(new_hashes)
                    batch_size = 128
                    for i in range(0, len(hashes_list), batch_size):
                        batch_hashes = hashes_list[i : i + batch_size]
                        texts_to_embed = [
                            representative_text_for_hash(h, chunks)
                            for h in batch_hashes
                        ]
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

                    self.metadata.prune_invalidated_content_for_file(
                        repo_id, file_id, embed_model, set(desired.keys())
                    )

                    # Build a quick lookup for token_count by occurrence position
                    occ_token_counts: Dict[tuple[int, int], int] = {
                        (ch.start_line, ch.end_line): getattr(ch, "token_count", 0)
                        for ch in chunks
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
                                    "token_count": occ_token_counts.get(
                                        (occ["start_line"], occ["end_line"]), 0
                                    ),
                                    "created_at": datetime.datetime.now(
                                        datetime.timezone.utc
                                    ),
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
                                    fts_content_id = generate_fts_content_id(
                                        repo_id, file_id, h
                                    )

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
                        self.lancedb.upsert_chunks(
                            repo_name, payload, model=embed_model
                        )

                    # Index chunks in FTS5 for BM25 search
                    if fts_chunks and not dry_run:
                        self.metadata.bulk_index_chunks_for_fts(fts_chunks)

                    # Prune any stale vectors for this file/model
                    if desired_row_ids:
                        self.lancedb.prune_file_rows(
                            repo_name, path, model=embed_model, keep_ids=desired_row_ids
                        )
                    else:
                        self.lancedb.prune_file_rows(repo_name, path, model=embed_model)

                # Update counters
                files_done += 1
                chunks_indexed += len(new_hashes)
                chunks_skipped += skipped_occurrences
                vectors_written += len(new_hashes)

                # Log per-file summary
                print(
                    f"  {path}: {len(chunks)} chunks, {len(new_hashes)} new, {skipped_occurrences} skipped"
                )

            except Exception as e:
                error_logger.log_file_error(path, e)
                print(f"Error processing {path}: {e}")
                continue

        # Process deleted files
        for path in deleted_files:
            try:
                file_id = self.metadata.get_file_id(repo_id, path)
                if file_id:
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

                    # Clean up graph data for deleted file
                    edges_deleted = 0
                    nodes_deleted = 0
                    if self.graph_store:
                        nodes_deleted, edges_deleted = cleanup_graph_for_file(
                            self.graph_store, file_id
                        )

                    if self.graph_store and (edges_deleted > 0 or nodes_deleted > 0):
                        graph_manager = self.get_graph_manager(repo_id)
                        if edges_deleted > 0:
                            graph_manager.on_edges_changed(edges_deleted)
                        else:
                            graph_manager.invalidate_cache()

                    files_done += 1
                    chunks_pruned += total_pruned
                    print(f"  {path}: deleted, {total_pruned} chunks pruned")
            except Exception as e:
                error_logger.log_file_error(f"deleted: {path}", e)
                print(f"Error processing deleted file {path}: {e}")
                continue

        # Prune any ignored files that were previously indexed
        # This handles files that were committed before being added to .gitignore
        if not dry_run:
            print(f"\nPruning previously-indexed ignored files for {repo_name}...")
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
                            print(
                                f"  {file_path}: pruned {pruned_count} ignored chunks (model={model})"
                            )
                        self.lancedb.prune_file_rows(repo_name, file_path, model=model)

                    # Clean up graph data for ignored file
                    edges_deleted = 0
                    nodes_deleted = 0
                    if self.graph_store:
                        nodes_deleted, edges_deleted = cleanup_graph_for_file(
                            self.graph_store, file_id
                        )

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
        else:
            print(f"Dry run: would have updated counters for session {session_id}")

        # Update cache state with final counts after indexing
        if not dry_run and self.graph_store:
            graph_manager = self.get_graph_manager(repo_id)
            # Force rebuild to get accurate total counts from database
            # This ensures cache state reflects TOTAL graph size, not just incremental changes
            graph = graph_manager.get_graph(force_rebuild=True)
            # Cache state is automatically updated in _rebuild_graph() with total counts

        # Print summary
        print(f"\nIndexing complete for {repo_name}:")
        print(f"  Files processed: {files_done}")
        print(f"  Chunks indexed: {chunks_indexed}")
        print(f"  Chunks skipped (dedup): {chunks_skipped}")
        print(f"  Chunks pruned (deleted): {chunks_pruned}")
        print(f"  Vectors written: {vectors_written}")
        if graph_nodes_created > 0 or graph_edges_created > 0:
            print(f"  Graph nodes created: {graph_nodes_created}")
            print(f"  Graph edges created: {graph_edges_created}")
        print(f"  Session: {session_id}")

        # Only mention error log if something was actually written
        try:
            if error_logger.had_errors():
                lp = error_logger.get_log_path()
                if lp.exists() and lp.stat().st_size > 0:
                    print(f"  Errors logged to: {lp}")
        except Exception:
            pass

        return {
            "repo": repo_name,
            "repo_id": repo_id,
            "session_id": session_id,
            "commit": commit_sha,
            "branch": branch,
            "files_indexed": files_done,
            "chunks_indexed": chunks_indexed,
            "chunks_skipped": chunks_skipped,
            "vectors_written": vectors_written,
            "chunks_pruned": chunks_pruned,
            "graph_nodes_created": graph_nodes_created,
            "graph_edges_created": graph_edges_created,
            "dry_run": dry_run,
        }
