import asyncio
import concurrent.futures
import contextvars
import datetime
import logging
import threading
import time
from pathlib import Path

from watchfiles import Change, awatch

from ..config import KBConfig
from ..ingest.branch_tracker import detect_branch_switch, get_current_branch_state
from ..ingest.error_logging import ErrorLogger
from ..ingest.pipeline import IngestionPipeline
from ..store.sqlite_meta import ActiveSessionError

logger = logging.getLogger(__name__)


class RepoWatcher:
    def __init__(self, repo_name: str, config: KBConfig, pipeline: IngestionPipeline):
        self.repo_name = repo_name
        self.config = config
        self.pipeline = pipeline
        self.metadata = pipeline.metadata

        # Get repository details
        repo = self.metadata.get_repo_by_name(repo_name)
        if not repo:
            raise ValueError(f"Repository not registered: {repo_name}")

        self.repo_id = int(repo["id"])
        self.root = Path(repo["root_path"])
        self.embed_model = str(repo.get("default_embed_model", config.default_embed_model))

        # Initialize branch state
        try:
            self.current_branch_state = get_current_branch_state(self.root)
        except Exception as e:
            logger.warning(f"Could not get initial branch state for {repo_name}: {e}")
            self.current_branch_state = None

        # Build ignore spec using shared utility
        from ..ignores import build_ignore_pathspec

        self.ignore_spec = build_ignore_pathspec(self.config.ignore, self.config.ignore_exceptions, self.root)

        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._stop_event: asyncio.Event | None = None
        self._stop_requested = threading.Event()
        self._executor_closed = False
        self._last_missing_cleanup = 0.0

    def request_stop(self) -> None:
        """Request watcher loop shutdown."""
        self._stop_requested.set()
        if self._stop_event is not None:
            self._stop_event.set()

    def _should_stop(self) -> bool:
        """Return True when shutdown has been requested."""
        return self._stop_requested.is_set() or (self._stop_event is not None and self._stop_event.is_set())

    def _shutdown_executor(self) -> None:
        """Shutdown internal executor once to avoid lingering threads on process exit."""
        if self._executor_closed:
            return
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._executor_closed = True

    async def watch(self):
        """Start watching the repository for changes."""
        self._stop_event = asyncio.Event()
        self._stop_requested.clear()
        logger.info("Starting watcher for %s at %s", self.repo_name, self.root)

        try:
            try:
                aborted = self.metadata.abort_stale_sessions(
                    repo_id=self.repo_id,
                    reason="Aborted on startup: previous watcher session did not complete cleanly",
                )
                if aborted:
                    logger.warning("Aborted %d stale session(s) for %s", aborted, self.repo_name)
            except Exception as e:
                logger.warning(f"Failed to abort stale sessions for {self.repo_name}: {e}", exc_info=True)

            if self._should_stop():
                return

            # Perform startup sync to ensure index is up to date with HEAD.
            # We use force=True to allow dirty working tree (since we are watching for edits).
            logger.info("Performing startup sync for %s", self.repo_name)
            try:
                # Explicitly copy context so the embedding provider ContextVar
                # propagates to the executor thread (Python <3.14 does not do
                # this automatically in run_in_executor).
                ctx = contextvars.copy_context()
                _do_index = lambda: self.pipeline.index(self.repo_name, dry_run=False, force=True)  # noqa: E731
                await asyncio.get_running_loop().run_in_executor(self._executor, ctx.run, _do_index)
                logger.info("Startup sync complete for %s", self.repo_name)
            except Exception as e:
                logger.error(f"Startup sync failed for {self.repo_name}: {e}", exc_info=True)

            if self._should_stop():
                return

            # Seed pending changes for untracked or modified files created during startup sync.
            await self._seed_working_tree_changes()
            if self._should_stop():
                return

            # Process any pending changes from previous run first.
            await self._process_pending_changes()
            if self._should_stop():
                return

            # Main watch loop
            async for changes in awatch(self.root, stop_event=self._stop_event, debounce=1000, step=500):
                if self._should_stop():
                    break

                # Check for branch switch
                await self._check_branch_switch()

                # Filter and batch changes
                interesting_changes = self._filter_changes(changes)
                if not interesting_changes:
                    continue

                # Record to pending_changes table (crash safety)
                await self._record_changes(interesting_changes)

                # Process changes
                await self._process_pending_changes()

        except asyncio.CancelledError:
            logger.info("Watcher cancelled for %s", self.repo_name)
            self.request_stop()
            raise
        except Exception as e:
            logger.error(f"Watcher failed for {self.repo_name}: {e}", exc_info=True)
        finally:
            self.request_stop()
            self._shutdown_executor()

    def _filter_changes(self, changes: set[tuple[Change, str]]) -> list[tuple[Change, str]]:
        filtered = []
        for change_type, path_str in changes:
            try:
                path = Path(path_str)
                # Convert to relative path
                rel_path = path.relative_to(self.root)
                rel_path_str = str(rel_path)

                # Skip .git directory and ignored files
                if ".git" in rel_path.parts:
                    continue

                if self.ignore_spec.match_file(rel_path_str):
                    continue

                filtered.append((change_type, rel_path_str))
            except ValueError:
                # Path not relative to root (shouldn't happen with watchfiles)
                continue
        return filtered

    async def _check_branch_switch(self):
        try:
            new_state = await asyncio.get_running_loop().run_in_executor(
                self._executor, get_current_branch_state, self.root
            )

            if self.current_branch_state and detect_branch_switch(self.current_branch_state, new_state):
                logger.info("Branch switch detected: %s -> %s", self.current_branch_state.branch, new_state.branch)
                self.current_branch_state = new_state

                # Trigger branch reconciliation
                await asyncio.get_running_loop().run_in_executor(
                    self._executor, self.pipeline.reconcile_branch_switch, self.repo_name
                )
            else:
                self.current_branch_state = new_state

        except Exception as e:
            logger.error(f"Error checking branch state: {e}", exc_info=True)

    async def _seed_working_tree_changes(self) -> None:
        """Capture working tree changes before the watch loop starts."""
        try:
            from ..ingest.incremental import detect_changed_files

            modified_files, deleted_files = detect_changed_files(self.root, self.metadata, self.repo_name)
        except Exception as e:
            logger.warning(f"Failed to seed working tree changes for {self.repo_name}: {e}")
            return

        changes: list[tuple[Change, str]] = []
        for path in modified_files:
            if path:
                changes.append((Change.modified, path))
        for path in deleted_files:
            if path:
                changes.append((Change.deleted, path))

        if changes:
            await self._record_changes(changes)

    async def _record_changes(self, changes: list[tuple[Change, str]]):
        """Record detected changes to the database."""
        # Convert Change enum to string
        # Change.added = 1, modified = 2, deleted = 3
        type_map = {Change.added: "added", Change.modified: "modified", Change.deleted: "deleted"}

        def _db_op():
            with self.metadata._connect() as conn:
                cur = conn.cursor()
                for change_type, path in changes:
                    c_type_str = type_map.get(change_type, "modified")
                    if c_type_str != "deleted" and not (self.root / path).exists():
                        c_type_str = "deleted"

                    # Check if already pending
                    cur.execute(
                        """
                        SELECT id, change_type
                        FROM pending_changes
                        WHERE repo_id = ? AND file_path = ? AND processed = 0
                        """,
                        (self.repo_id, path),
                    )
                    existing = cur.fetchone()

                    if existing:
                        existing_id, existing_type = existing
                        # If new event is a deletion, always update to deleted to prevent stale chunks
                        # Otherwise, keep the existing event (first one wins for modify/add)
                        if c_type_str == "deleted":
                            cur.execute(
                                """
                                UPDATE pending_changes
                                SET change_type = ?, detected_at = ?
                                WHERE id = ?
                                """,
                                (c_type_str, datetime.datetime.now(datetime.UTC), existing_id),
                            )
                        # If existing is deleted and new is modify/add, the file was recreated - update to modified
                        elif existing_type == "deleted" and c_type_str in ("added", "modified"):
                            cur.execute(
                                """
                                UPDATE pending_changes
                                SET change_type = 'modified', detected_at = ?
                                WHERE id = ?
                                """,
                                (datetime.datetime.now(datetime.UTC), existing_id),
                            )
                        # Otherwise keep existing (modify/add already pending, just update timestamp)
                        else:
                            cur.execute(
                                "UPDATE pending_changes SET detected_at = ? WHERE id = ?",
                                (datetime.datetime.now(datetime.UTC), existing_id),
                            )
                    else:
                        # No existing row, insert new
                        cur.execute(
                            """
                            INSERT INTO pending_changes (repo_id, file_path, change_type, detected_at, processed)
                            VALUES (?, ?, ?, ?, 0)
                            """,
                            (self.repo_id, path, c_type_str, datetime.datetime.now(datetime.UTC)),
                        )
                conn.commit()

        await asyncio.get_running_loop().run_in_executor(self._executor, _db_op)

    async def _process_pending_changes(self):
        """Process all pending changes in the database."""
        ctx = contextvars.copy_context()
        await asyncio.get_running_loop().run_in_executor(self._executor, ctx.run, self._process_pending_sync)

    def _process_pending_sync(self):
        """Synchronous processing logic (runs in thread pool)."""
        if self._should_stop():
            return

        # Fetch pending changes
        changes = self.metadata.get_pending_changes(self.repo_id, limit=500)
        if not changes:
            return

        logger.info("Processing %d pending changes for %s", len(changes), self.repo_name)

        # Group by type
        to_process = []  # modified or added
        to_delete = []
        change_ids = []
        has_added = False

        for c in changes:
            change_ids.append(c["id"])
            file_path = c["file_path"]
            change_type = c["change_type"]
            if change_type == "added":
                has_added = True
            if change_type == "deleted":
                to_delete.append(file_path)
            else:
                to_process.append(file_path)

        # Treat missing files in to_process as deletions (rename/create+delete races).
        existing_process = []
        for path in to_process:
            if (self.root / path).exists():
                existing_process.append(path)
            else:
                to_delete.append(path)
        to_process = existing_process

        # Start a micro-session
        # We need commit_sha and branch for the session
        try:
            branch_state = get_current_branch_state(self.root)
            commit_sha = branch_state.commit_sha
            branch = branch_state.branch
        except Exception:
            logger.debug("Could not determine git branch state; using placeholders.", exc_info=True)
            commit_sha = "unknown"
            branch = "unknown"

        try:
            session_id = self.metadata.begin_session(self.repo_id, commit_sha, branch, self.embed_model)
        except ActiveSessionError as e:
            logger.warning(f"Skipping pending change processing for {self.repo_name}: {e}")
            return
        error_logger = ErrorLogger(self.root, str(session_id))

        try:
            # Process files
            if to_process:
                self.pipeline.process_files(
                    repo_id=self.repo_id,
                    repo_name=self.repo_name,
                    root=self.root,
                    files=to_process,
                    ignore_spec=self.ignore_spec,
                    embed_model=self.embed_model,
                    session_id=session_id,
                    commit_sha=commit_sha,
                    branch=branch,
                    dry_run=False,
                    error_logger=error_logger,
                )

            # Process deletions
            if to_delete:
                self.pipeline.process_deletions(
                    repo_id=self.repo_id,
                    repo_name=self.repo_name,
                    files=to_delete,
                    embed_model=self.embed_model,
                    dry_run=False,
                    error_logger=error_logger,
                )

            # Fallback cleanup: if we saw adds but no delete events, prune missing DB files.
            if has_added and (time.time() - self._last_missing_cleanup) > 5.0:
                missing_paths = self._find_missing_files_in_db()
                missing_paths = [p for p in missing_paths if p not in to_delete]
                if missing_paths:
                    self.pipeline.process_deletions(
                        repo_id=self.repo_id,
                        repo_name=self.repo_name,
                        files=missing_paths,
                        embed_model=self.embed_model,
                        dry_run=False,
                        error_logger=error_logger,
                    )
                self._last_missing_cleanup = time.time()

            # Mark processed
            self.metadata.mark_changes_processed(change_ids)

            # Close session
            self.metadata.set_session_status(session_id, "succeeded")
            logger.info("Batch processed successfully (session %s)", session_id)

        except Exception as e:
            if self.pipeline.is_cancel_requested():
                logger.info("Batch processing interrupted by shutdown request for %s", self.repo_name)
                self.metadata.set_session_status(session_id, "aborted", notes="interrupted by shutdown")
            else:
                logger.error(f"Error processing batch: {e}", exc_info=True)
                self.metadata.set_session_status(session_id, "failed")

    def _find_missing_files_in_db(self) -> list[str]:
        """Return file paths that exist in metadata but not on disk."""
        missing = []
        try:
            for entry in self.metadata.get_all_files_for_repo(self.repo_id):
                path = entry.get("path")
                if not path:
                    continue
                if not (self.root / path).exists():
                    missing.append(path)
        except Exception as e:
            logger.warning(f"Failed to scan for missing files: {e}")
        return missing
