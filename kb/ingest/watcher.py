import asyncio
import logging
import datetime
from pathlib import Path
from typing import Set, Tuple
from watchfiles import awatch, Change
import concurrent.futures

from ..config import KBConfig
from ..ingest.pipeline import IngestionPipeline
from ..ingest.branch_tracker import get_current_branch_state, detect_branch_switch
from ..ingest.error_logging import ErrorLogger
from ..ingest.scanner import FileCandidate
from pathspec import PathSpec
from ..ignores import build_ignore_set, load_repo_ignores

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

        # Build ignore spec
        # Note: This duplicates some logic from pipeline.py, logic reuse could be improved
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
        repo_level_patterns, repo_level_exceptions = load_repo_ignores(self.root)
        if repo_level_patterns:
            ignore_patterns.update(repo_level_patterns)
        if repo_level_exceptions:
            ignore_patterns = build_ignore_set(ignore_patterns, repo_level_exceptions)
        ignore_patterns.update(extra_security)
        self.ignore_spec = PathSpec.from_lines("gitwildmatch", ignore_patterns)
        
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    async def watch(self):
        """Start watching the repository for changes."""
        print(f"Starting watcher for {self.repo_name} at {self.root}")
        
        # Perform startup sync to ensure index is up to date with HEAD
        # We use force=True to allow dirty working tree (since we are watching for edits)
        print(f"Performing startup sync for {self.repo_name}...")
        try:
            await asyncio.get_event_loop().run_in_executor(
                self._executor,
                lambda: self.pipeline.index(self.repo_name, dry_run=False, force=True)
            )
            print(f"Startup sync complete for {self.repo_name}")
        except Exception as e:
            logger.error(f"Startup sync failed for {self.repo_name}: {e}")
        
        # Process any pending changes from previous run first
        await self._process_pending_changes()

        stop_event = asyncio.Event()

        try:
            # Main watch loop
            async for changes in awatch(self.root, stop_event=stop_event, debounce=1000, step=500):
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
                
        except Exception as e:
            logger.error(f"Watcher failed for {self.repo_name}: {e}", exc_info=True)

    def _filter_changes(self, changes: Set[Tuple[Change, str]]) -> list[Tuple[Change, str]]:
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
            new_state = await asyncio.get_event_loop().run_in_executor(
                self._executor, get_current_branch_state, self.root
            )
            
            if self.current_branch_state and detect_branch_switch(self.current_branch_state, new_state):
                print(f"Branch switch detected: {self.current_branch_state.branch} -> {new_state.branch}")
                self.current_branch_state = new_state
                
                # Trigger branch reconciliation
                await asyncio.get_event_loop().run_in_executor(
                    self._executor, self.pipeline.reconcile_branch_switch, self.repo_name
                )
            else:
                self.current_branch_state = new_state
                
        except Exception as e:
            logger.error(f"Error checking branch state: {e}")

    async def _record_changes(self, changes: list[Tuple[Change, str]]):
        """Record detected changes to the database."""
        # Convert Change enum to string
        # Change.added = 1, modified = 2, deleted = 3
        type_map = {
            Change.added: "added",
            Change.modified: "modified",
            Change.deleted: "deleted"
        }
        
        def _db_op():
            with self.metadata._connect() as conn:
                cur = conn.cursor()
                for change_type, path in changes:
                    c_type_str = type_map.get(change_type, "modified")
                    
                    # Check if already pending to avoid duplicates
                    cur.execute(
                        "SELECT id FROM pending_changes WHERE repo_id = ? AND file_path = ? AND processed = 0",
                        (self.repo_id, path)
                    )
                    if cur.fetchone():
                        # Update timestamp? Or just skip.
                        continue
                        
                    cur.execute(
                        """
                        INSERT INTO pending_changes (repo_id, file_path, change_type, detected_at, processed)
                        VALUES (?, ?, ?, ?, 0)
                        """,
                        (self.repo_id, path, c_type_str, datetime.datetime.now(datetime.UTC))
                    )
                conn.commit()

        await asyncio.get_event_loop().run_in_executor(self._executor, _db_op)

    async def _process_pending_changes(self):
        """Process all pending changes in the database."""
        await asyncio.get_event_loop().run_in_executor(self._executor, self._process_pending_sync)

    def _process_pending_sync(self):
        """Synchronous processing logic (runs in thread pool)."""
        # Fetch pending changes
        changes = self.metadata.get_pending_changes(self.repo_id, limit=500)
        if not changes:
            return

        print(f"Processing {len(changes)} pending changes for {self.repo_name}...")
        
        # Group by type
        to_process = [] # modified or added
        to_delete = []
        change_ids = []
        
        for c in changes:
            change_ids.append(c["id"])
            if c["change_type"] == "deleted":
                to_delete.append(c["file_path"])
            else:
                to_process.append(c["file_path"])
        
        # Start a micro-session
        # We need commit_sha and branch for the session
        try:
            branch_state = get_current_branch_state(self.root)
            commit_sha = branch_state.commit_sha
            branch = branch_state.branch
        except Exception:
            commit_sha = "unknown"
            branch = "unknown"

        session_id = self.metadata.begin_session(self.repo_id, commit_sha, branch, self.embed_model)
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
                    error_logger=error_logger
                )
            
            # Process deletions
            if to_delete:
                self.pipeline.process_deletions(
                    repo_id=self.repo_id,
                    repo_name=self.repo_name,
                    files=to_delete,
                    embed_model=self.embed_model,
                    dry_run=False,
                    error_logger=error_logger
                )
            
            # Mark processed
            self.metadata.mark_changes_processed(change_ids)
            
            # Close session
            self.metadata.set_session_status(session_id, "succeeded")
            print(f"Batch processed successfully (session {session_id})")
            
        except Exception as e:
            logger.error(f"Error processing batch: {e}", exc_info=True)
            self.metadata.set_session_status(session_id, "failed")

