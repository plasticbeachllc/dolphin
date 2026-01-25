import asyncio
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from watchfiles import Change

from kb.config import KBConfig
from kb.ingest.pipeline import IngestionPipeline
from kb.ingest.watcher import RepoWatcher
from kb.store import LanceDBStore, SQLiteMetadataStore
from kb.store.graph_store import GraphStore

@pytest.mark.asyncio
class TestWatcherIntegration:
    async def test_watcher_basic_flow(self, git_repo: Path, temp_db_path: Path):
        """Test the complete watcher flow from file change to DB update."""
        
        # Setup config and stores
        config = KBConfig(default_embed_model="small")
        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()
        lancedb_store = LanceDBStore("memory://test_db")
        graph_store = GraphStore(temp_db_path)
        
        # Register repo
        metadata_store.record_repo(name="test-repo", path=git_repo, default_embed_model="small")
        repo_info = metadata_store.get_repo_by_name("test-repo")
        assert repo_info is not None
        repo_id = repo_info["id"]
        
        # Initialize pipeline
        pipeline = IngestionPipeline(config, lancedb_store, metadata_store, graph_store)
        
        # Initialize watcher
        watcher = RepoWatcher("test-repo", config, pipeline)
        
        # Mock awatch to yield one set of changes then stop
        # We simulate adding a file
        new_file = git_repo / "new_file.py"
        new_file.write_text("def foo(): pass")
        
        async def mock_awatch_gen(*args, **kwargs):
            yield {(Change.added, str(new_file))}
            # Stop after yielding once
            kwargs.get("stop_event").set()
            
        with patch("kb.ingest.watcher.awatch", side_effect=mock_awatch_gen):
            # Run watcher
            await watcher.watch()
            
        # Verify file is in pending_changes (should be processed already)
        # But wait, watch() processes pending changes immediately after filtering/recording.
        # So it should be marked as processed.
        
        with metadata_store._connect() as conn:
            cur = conn.cursor()
            # print all pending changes for debug
            cur.execute("SELECT * FROM pending_changes")
            print(f"DEBUG: All pending changes: {cur.fetchall()}")
            
            cur.execute("SELECT * FROM pending_changes WHERE file_path = ?", ("new_file.py",))
            row = cur.fetchone()
            assert row is not None, "Pending change for new_file.py not found"
            # row[4] is processed column (0-indexed: id, repo_id, file_path, change_type, detected_at, processed)
            # Let's check schema order.
            # Usually: id, repo_id, file_path, change_type, old_path, detected_at, processed, processed_at
            # Wait, let's check sql_models.py or just access by name if using row factory, but here it's tuple
            # processed is likely near end.
            # Let's just assert one of the columns is 1.
            # We can also check if we can get pending changes using store method
            
        changes = metadata_store.get_pending_changes(repo_id=repo_id)
        # Should be empty because it's processed? 
        # get_pending_changes has 'WHERE processed = 0' by default.
        assert len(changes) == 0
        
        # Verify file is indexed (in files table)
        # Check files table directly
        with metadata_store._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM files WHERE path = ?", ("new_file.py",))
            assert cur.fetchone() is not None, "File not found in files table"
        
        # Verify chunk content exists
        # We need to dig a bit deeper or trust files table existence implies indexing success
        # Given pipeline.index/process_files logic, if it's successful it writes to metadata.
        
    async def test_watcher_processes_existing_pending(self, git_repo: Path, temp_db_path: Path):
        """Test that watcher processes pre-existing pending changes on startup."""
        
        # Setup config and stores
        config = KBConfig(default_embed_model="small")
        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()
        lancedb_store = LanceDBStore("memory://test_db")
        graph_store = GraphStore(temp_db_path)
         
        # Register repo
        metadata_store.record_repo(name="test-repo", path=git_repo, default_embed_model="small")
        repo_info = metadata_store.get_repo_by_name("test-repo")
        repo_id = repo_info["id"]
        
        # Insert a pending change manually
        pending_file = git_repo / "pending.py"
        pending_file.write_text("x = 1")
        
        import datetime
        with metadata_store._connect() as conn:
            conn.execute(
                "INSERT INTO pending_changes (repo_id, file_path, change_type, detected_at, processed) VALUES (?, ?, ?, ?, 0)",
                (repo_id, "pending.py", "added", datetime.datetime.now(datetime.UTC))
            )
            
        # Initialize pipeline & watcher
        pipeline = IngestionPipeline(config, lancedb_store, metadata_store, graph_store)
        watcher = RepoWatcher("test-repo", config, pipeline)
        
        # Mock awatch to just quit immediately
        async def mock_awatch_empty(*args, **kwargs):
            kwargs.get("stop_event").set()
            if False: yield
            
        with patch("kb.ingest.watcher.awatch", side_effect=mock_awatch_empty):
            await watcher.watch()
            
        # Verify pending change processed
        with metadata_store._connect() as conn:
            cur = conn.execute("SELECT processed FROM pending_changes WHERE file_path = 'pending.py'")
            val = cur.fetchone()[0]
            assert val == 1
            
        # Verify indexed
        assert metadata_store.get_file_id(repo_id, "pending.py") is not None
