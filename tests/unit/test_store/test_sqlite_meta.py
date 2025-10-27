"""Unit tests for SQLite metadata store operations."""

import sqlite3
import tempfile
from pathlib import Path
from typing import Any
import pytest

from pb_kb.store.sqlite_meta import SQLiteMetadataStore


class TestSQLiteMetadataStore:
    """Test SQLite metadata store CRUD operations and session management."""

    def test_repo_operations(self, temp_db_path):
        """Test repository creation, retrieval, and duplicate handling."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        # Test record_repo and get_repo_by_name
        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path, default_embed_model="small")
        repo = store.get_repo_by_name("test-repo")
        
        assert repo is not None, "Repo should be found after record_repo"
        assert isinstance(repo["id"], int) and repo["id"] > 0
        assert repo["root_path"] == str(repo_path)
        assert repo["default_embed_model"] == "small"

        # Test duplicate repo handling - record_repo doesn't return ID, so we get it again
        store.record_repo("test-repo", repo_path)
        same_repo = store.get_repo_by_name("test-repo")
        assert same_repo["id"] == repo["id"], "Duplicate repo should return same ID"

    def test_session_management(self, temp_db_path):
        """Test session lifecycle and status transitions."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        repo_id = int(repo["id"])

        # Test session creation
        session_id = store.begin_session(repo_id, "a" * 40, "main", "small")
        assert isinstance(session_id, int) and session_id > 0

        # Test counter updates - provide all required counters to avoid NULL constraints
        # Note: The bump_session_counters method only updates provided counters, doesn't set others to NULL
        store.bump_session_counters(
            session_id, 
            files_indexed=5, 
            chunks_indexed=2
        )
        
        # Verify counter updates
        def _query_one(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> tuple | None:
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            con.close()
            return row

        row = _query_one(temp_db_path, "SELECT files_indexed, chunks_indexed, vectors_written FROM sessions WHERE id = ?", (session_id,))
        assert row is not None
        assert row[0] == 5
        assert row[1] == 2
        assert row[2] == 0

        # Test session status transitions
        store.set_session_status(session_id, "succeeded", notes="done")
        row = _query_one(temp_db_path, "SELECT status, notes, ended_at FROM sessions WHERE id = ?", (session_id,))
        assert row is not None
        assert row[0] == "succeeded"
        assert "done" in (row[1] or "")
        assert row[2] is not None, "ended_at should be set for terminal status"

        # Test invalid repo session creation
        with pytest.raises((sqlite3.IntegrityError, Exception)):
            store.begin_session(999999, "b" * 40, "main", "small")

    def test_file_operations(self, temp_db_path):
        """Test file upsert operations and commit tracking."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        repo_id = int(repo["id"])

        # Test file upsert idempotency
        file_id = store.upsert_file(
            repo_id, path="src/a.py", ext=".py", language="python", 
            is_binary=False, size_bytes=123
        )
        assert isinstance(file_id, int) and file_id > 0

        # Second upsert returns same id and does not create duplicates
        file_id2 = store.upsert_file(
            repo_id, path="src/a.py", ext=".py", language="python", 
            is_binary=False, size_bytes=456
        )
        assert file_id == file_id2

        # Verify only one record exists and size was updated
        row = _query_one(temp_db_path, "SELECT COUNT(1), size_bytes FROM files WHERE repo_id = ? AND path = ?", (repo_id, "src/a.py"))
        assert row is not None
        assert row[0] == 1
        assert row[1] == 456

        # Test commit tracking
        store.set_file_latest_commit(repo_id, "src/a.py", "c" * 40)
        row = _query_one(temp_db_path, "SELECT latest_commit_sha FROM files WHERE repo_id = ? AND path = ?", (repo_id, "src/a.py"))
        assert row is not None
        assert row[0] == "c" * 40

    def test_chunk_content_operations(self, temp_db_path):
        """Test chunk content storage and hash-based deduplication."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        repo_id = int(repo["id"])
        
        file_id = store.upsert_file(
            repo_id, path="src/a.py", ext=".py", language="python", 
            is_binary=False, size_bytes=123
        )

        # Test chunk content hashing APIs start empty
        assert store.get_existing_content_hashes_for_file(repo_id, file_id, "small") == set()

        # Test content upsert
        hash_a = "a" * 64
        cid_a1 = store.upsert_chunk_content_row(repo_id, file_id, hash_a, "small")
        assert isinstance(cid_a1, str) and len(cid_a1) > 0

        # Re-upsert should return same id and just bump last_indexed_at
        cid_a2 = store.upsert_chunk_content_row(repo_id, file_id, hash_a, "small")
        assert cid_a1 == cid_a2
        assert store.get_existing_content_hashes_for_file(repo_id, file_id, "small") == {hash_a}

    def test_location_synchronization(self, temp_db_path):
        """Test chunk location tracking and synchronization."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        repo_id = int(repo["id"])
        
        file_id = store.upsert_file(
            repo_id, path="src/a.py", ext=".py", language="python", 
            is_binary=False, size_bytes=123
        )

        hash_a = "a" * 64
        cid_a = store.upsert_chunk_content_row(repo_id, file_id, hash_a, "small")

        # Test location sync insert/update/delete operations
        first_locations = [
            {"start_line": 1, "end_line": 5, "symbol_kind": "class", "symbol_name": "Widget", "symbol_path": "Widget"},
            {"start_line": 8, "end_line": 12, "symbol_kind": "method", "symbol_name": "Widget.render", "symbol_path": "Widget.render"},
        ]
        stats = store.sync_locations_for_content_row(cid_a, first_locations)
        assert stats == {"inserted": 2, "updated": 0, "deleted": 0}

        locations_after_first = store.get_existing_locations_for_content_ids([cid_a])
        assert cid_a in locations_after_first
        assert len(locations_after_first[cid_a]) == 2

        # Test location updates and deletions
        second_locations = [
            {"start_line": 1, "end_line": 5, "symbol_kind": "class", "symbol_name": "WidgetRenamed", "symbol_path": "WidgetRenamed"},
            {"start_line": 20, "end_line": 24, "symbol_kind": "method", "symbol_name": "Widget.debug", "symbol_path": "Widget.debug"},
        ]
        stats = store.sync_locations_for_content_row(cid_a, second_locations)
        assert stats == {"inserted": 1, "updated": 1, "deleted": 1}

        locations_after_second = store.get_existing_locations_for_content_ids([cid_a])
        assert len(locations_after_second[cid_a]) == 2
        names = {loc["symbol_name"] for loc in locations_after_second[cid_a]}
        assert names == {"WidgetRenamed", "Widget.debug"}

    def test_pruning_operations(self, temp_db_path):
        """Test pruning of invalidated content."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        repo_id = int(repo["id"])
        
        file_id = store.upsert_file(
            repo_id, path="src/a.py", ext=".py", language="python", 
            is_binary=False, size_bytes=123
        )

        # Create multiple content entries
        hash_a = "a" * 64
        hash_b = "b" * 64
        cid_a = store.upsert_chunk_content_row(repo_id, file_id, hash_a, "small")
        cid_b = store.upsert_chunk_content_row(repo_id, file_id, hash_b, "small")
        assert cid_b != cid_a

        # Prune should remove content not in current hashes
        pruned = store.prune_invalidated_content_for_file(repo_id, file_id, "small", {hash_a})
        assert pruned == 1
        hashes_after_prune = store.get_existing_content_hashes_for_file(repo_id, file_id, "small")
        assert hashes_after_prune == {hash_a}

    def test_sync_file_state_end_to_end(self, temp_db_path):
        """Test complete file state synchronization."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        repo_id = int(repo["id"])
        
        file_id = store.upsert_file(
            repo_id, path="src/a.py", ext=".py", language="python", 
            is_binary=False, size_bytes=123
        )

        # Test sync_file_state with multiple content entries
        desired = {
            "a" * 64: [{"start_line": 1, "end_line": 5, "symbol_kind": "class", "symbol_name": "WidgetRenamed", "symbol_path": "WidgetRenamed"}],
            "c" * 64: [{"start_line": 30, "end_line": 40, "symbol_kind": None, "symbol_name": None, "symbol_path": None}],
        }
        stats = store.sync_file_state(repo_id, file_id, "small", desired)
        assert stats["content_upserted"] == len(desired)
        assert stats["locations_inserted"] >= 1
        
        hashes_final = store.get_existing_content_hashes_for_file(repo_id, file_id, "small")
        assert hashes_final == set(desired.keys())

    def test_summarize_operations(self, temp_db_path):
        """Test store summarization functionality."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        
        summary = store.summarize()
        assert summary["repos"] >= 1
        assert summary["files"] >= 0  # Could be 0 if no files added


# Helper function for direct database queries
def _query_one(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> tuple | None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    con.close()
    return row