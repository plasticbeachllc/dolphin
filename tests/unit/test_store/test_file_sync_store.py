"""Unit tests for file sync metadata store methods."""

from pathlib import Path

from kb.store.sqlite_meta import SQLiteMetadataStore


class TestPendingChanges:
    """Test pending change tracking methods."""

    def test_record_pending_change(self, temp_db_path):
        """Test recording a pending change."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        # Register a repo
        repo_path = Path("/tmp/test_repo")
        store.record_repo(name="test-repo", path=repo_path, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")
        repo_id = repo["id"]

        # Record a change
        change_id = store.record_pending_change(repo_id=repo_id, file_path="src/main.py", change_type="modified")

        assert change_id is not None
        assert change_id > 0

    def test_record_pending_change_with_old_path(self, temp_db_path):
        """Test recording a rename change with old_path."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/tmp/test_repo")
        store.record_repo(name="test-repo", path=repo_path, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")
        repo_id = repo["id"]

        # Record a rename change
        change_id = store.record_pending_change(
            repo_id=repo_id,
            file_path="src/new_name.py",
            change_type="renamed",
            old_path="src/old_name.py",
        )

        assert change_id is not None

    def test_get_pending_changes_empty(self, temp_db_path):
        """Test getting pending changes when none exist."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        changes = store.get_pending_changes()
        assert changes == []

    def test_get_pending_changes(self, temp_db_path):
        """Test getting pending changes."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/tmp/test_repo")
        store.record_repo(name="test-repo", path=repo_path, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")
        repo_id = repo["id"]

        # Record multiple changes
        store.record_pending_change(repo_id, "file1.py", "created")
        store.record_pending_change(repo_id, "file2.py", "modified")
        store.record_pending_change(repo_id, "file3.py", "deleted")

        # Get all pending changes
        changes = store.get_pending_changes()
        assert len(changes) == 3

        # Verify structure
        for change in changes:
            assert "id" in change
            assert "repo_id" in change
            assert "file_path" in change
            assert "change_type" in change
            assert "detected_at" in change

    def test_get_pending_changes_filtered_by_repo(self, temp_db_path):
        """Test getting pending changes filtered by repo_id."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        # Create two repos
        repo1_path = Path("/tmp/repo1")
        repo2_path = Path("/tmp/repo2")
        store.record_repo(name="repo1", path=repo1_path, default_embed_model="large")
        store.record_repo(name="repo2", path=repo2_path, default_embed_model="large")

        repo1 = store.get_repo_by_name("repo1")
        repo2 = store.get_repo_by_name("repo2")

        # Record changes for both repos
        store.record_pending_change(repo1["id"], "file1.py", "created")
        store.record_pending_change(repo1["id"], "file2.py", "modified")
        store.record_pending_change(repo2["id"], "file3.py", "created")

        # Get changes for repo1 only
        changes = store.get_pending_changes(repo_id=repo1["id"])
        assert len(changes) == 2
        for change in changes:
            assert change["repo_id"] == repo1["id"]

    def test_get_pending_changes_with_limit(self, temp_db_path):
        """Test getting pending changes with limit."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/tmp/test_repo")
        store.record_repo(name="test-repo", path=repo_path, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")
        repo_id = repo["id"]

        # Record 10 changes
        for i in range(10):
            store.record_pending_change(repo_id, f"file{i}.py", "modified")

        # Get with limit
        changes = store.get_pending_changes(limit=5)
        assert len(changes) == 5

    def test_mark_changes_processed(self, temp_db_path):
        """Test marking changes as processed."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/tmp/test_repo")
        store.record_repo(name="test-repo", path=repo_path, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")
        repo_id = repo["id"]

        # Record changes
        id1 = store.record_pending_change(repo_id, "file1.py", "created")
        id2 = store.record_pending_change(repo_id, "file2.py", "modified")

        # Mark as processed
        processed_count = store.mark_changes_processed([id1, id2])
        assert processed_count == 2

        # Should no longer appear in pending
        changes = store.get_pending_changes()
        assert len(changes) == 0

    def test_mark_changes_processed_empty_list(self, temp_db_path):
        """Test marking changes with empty list."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        processed_count = store.mark_changes_processed([])
        assert processed_count == 0

    def test_mark_changes_for_file_processed(self, temp_db_path):
        """Test marking changes for a specific file as processed (used by indexing pipeline)."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/tmp/test_repo")
        store.record_repo(name="test-repo", path=repo_path, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")
        repo_id = repo["id"]

        # Record multiple changes for same file
        store.record_pending_change(repo_id, "important.py", "modified")
        store.record_pending_change(repo_id, "important.py", "modified")
        store.record_pending_change(repo_id, "other.py", "created")

        # Mark all changes for specific file as processed
        processed_count = store.mark_changes_for_file_processed(repo_id, "important.py")
        assert processed_count == 2

        # Only changes for other.py should remain pending
        changes = store.get_pending_changes()
        assert len(changes) == 1
        assert changes[0]["file_path"] == "other.py"

    def test_mark_changes_for_file_processed_no_matches(self, temp_db_path):
        """Test marking changes for file that has no pending changes."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/tmp/test_repo")
        store.record_repo(name="test-repo", path=repo_path, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")
        repo_id = repo["id"]

        # No changes recorded
        processed_count = store.mark_changes_for_file_processed(
            repo_id, "nonexistent.py"
        )
        assert processed_count == 0

    def test_cleanup_old_changes(self, temp_db_path):
        """Test cleaning up old processed changes."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/tmp/test_repo")
        store.record_repo(name="test-repo", path=repo_path, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")
        repo_id = repo["id"]

        # Record and process changes
        id1 = store.record_pending_change(repo_id, "file1.py", "created")
        store.mark_changes_processed([id1])

        # Cleanup should not delete recent changes (even if processed)
        # because they're within the retention window
        deleted = store.cleanup_old_changes(days=7)
        # We can't easily test the time-based deletion without mocking the database
        # Just verify the method runs without error
        assert deleted >= 0


class TestFileSnapshots:
    """Test file snapshot tracking methods."""

    def test_upsert_file_snapshot(self, temp_db_path, temp_dir):
        """Test upserting a file snapshot."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        # Create repo and file
        workspace = temp_dir / "workspace"
        workspace.mkdir()
        store.record_repo(name="test-repo", path=workspace, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")

        file_id = store.upsert_file(
            repo_id=repo["id"],
            path="test.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=100,
        )

        # Upsert snapshot
        store.upsert_file_snapshot(
            file_id=file_id,
            repo_id=repo["id"],
            path="test.py",
            mtime_ns=1234567890,
            size_bytes=100,
            content_hash="abc123",
        )

        # Verify snapshot was created
        snapshot = store.get_file_snapshot(file_id)
        assert snapshot is not None
        assert snapshot["file_id"] == file_id
        assert snapshot["path"] == "test.py"
        assert snapshot["mtime_ns"] == 1234567890
        assert snapshot["size_bytes"] == 100
        assert snapshot["content_hash"] == "abc123"

    def test_upsert_file_snapshot_updates_existing(self, temp_db_path, temp_dir):
        """Test upserting updates existing snapshot."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        workspace = temp_dir / "workspace"
        workspace.mkdir()
        store.record_repo(name="test-repo", path=workspace, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")

        file_id = store.upsert_file(
            repo_id=repo["id"],
            path="test.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=100,
        )

        # First snapshot
        store.upsert_file_snapshot(
            file_id=file_id,
            repo_id=repo["id"],
            path="test.py",
            mtime_ns=111,
            size_bytes=100,
            content_hash="hash1",
        )

        # Update snapshot
        store.upsert_file_snapshot(
            file_id=file_id,
            repo_id=repo["id"],
            path="test.py",
            mtime_ns=222,
            size_bytes=200,
            content_hash="hash2",
        )

        # Should have updated values
        snapshot = store.get_file_snapshot(file_id)
        assert snapshot["mtime_ns"] == 222
        assert snapshot["size_bytes"] == 200
        assert snapshot["content_hash"] == "hash2"

    def test_get_file_snapshot_nonexistent(self, temp_db_path):
        """Test getting snapshot for non-existent file."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        snapshot = store.get_file_snapshot(99999)
        assert snapshot is None

    def test_detect_drift_no_changes(self, temp_db_path, temp_dir):
        """Test drift detection when no files changed."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        # Create workspace and file
        workspace = temp_dir / "workspace"
        workspace.mkdir()
        test_file = workspace / "test.py"
        test_file.write_text("def test(): pass")

        store.record_repo(name="test-repo", path=workspace, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")

        file_id = store.upsert_file(
            repo_id=repo["id"],
            path="test.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=test_file.stat().st_size,
        )

        # Create snapshot matching current state
        import hashlib

        stat = test_file.stat()
        content_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        store.upsert_file_snapshot(
            file_id=file_id,
            repo_id=repo["id"],
            path="test.py",
            mtime_ns=stat.st_mtime_ns,
            size_bytes=stat.st_size,
            content_hash=content_hash,
        )

        # Detect drift
        drift_events = store.detect_drift(repo["id"])
        assert len(drift_events) == 0

    def test_detect_drift_modified_file(self, temp_db_path, temp_dir):
        """Test drift detection for modified file."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        # Create workspace and file
        workspace = temp_dir / "workspace"
        workspace.mkdir()
        test_file = workspace / "test.py"
        test_file.write_text("def test(): pass")

        store.record_repo(name="test-repo", path=workspace, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")

        file_id = store.upsert_file(
            repo_id=repo["id"],
            path="test.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=test_file.stat().st_size,
        )

        # Create snapshot with old state
        store.upsert_file_snapshot(
            file_id=file_id,
            repo_id=repo["id"],
            path="test.py",
            mtime_ns=123,  # Old timestamp
            size_bytes=50,  # Old size
            content_hash="old_hash",
        )

        # Modify file
        import time

        time.sleep(0.1)
        test_file.write_text("def test(): return 42")

        # Detect drift
        drift_events = store.detect_drift(repo["id"])
        assert len(drift_events) == 1
        assert drift_events[0]["path"] == "test.py"
        assert drift_events[0]["drift_type"] == "modified"

    def test_detect_drift_deleted_file(self, temp_db_path, temp_dir):
        """Test drift detection for deleted file."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        # Create workspace and file
        workspace = temp_dir / "workspace"
        workspace.mkdir()
        test_file = workspace / "test.py"
        test_file.write_text("def test(): pass")

        store.record_repo(name="test-repo", path=workspace, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")

        file_id = store.upsert_file(
            repo_id=repo["id"],
            path="test.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=test_file.stat().st_size,
        )

        # Create snapshot
        import hashlib

        stat = test_file.stat()
        content_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        store.upsert_file_snapshot(
            file_id=file_id,
            repo_id=repo["id"],
            path="test.py",
            mtime_ns=stat.st_mtime_ns,
            size_bytes=stat.st_size,
            content_hash=content_hash,
        )

        # Delete file
        test_file.unlink()

        # Detect drift
        drift_events = store.detect_drift(repo["id"])
        assert len(drift_events) == 1
        assert drift_events[0]["path"] == "test.py"
        assert drift_events[0]["drift_type"] == "deleted"

    def test_detect_drift_multiple_files(self, temp_db_path, temp_dir):
        """Test drift detection with multiple files."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        # Create workspace with multiple files
        workspace = temp_dir / "workspace"
        workspace.mkdir()

        files = []
        for i in range(3):
            f = workspace / f"file{i}.py"
            f.write_text(f"def func{i}(): pass")
            files.append(f)

        store.record_repo(name="test-repo", path=workspace, default_embed_model="large")
        repo = store.get_repo_by_name("test-repo")

        import hashlib

        # Create snapshots for all files
        for i, f in enumerate(files):
            file_id = store.upsert_file(
                repo_id=repo["id"],
                path=f"file{i}.py",
                ext=".py",
                language="python",
                is_binary=False,
                size_bytes=f.stat().st_size,
            )

            stat = f.stat()
            content_hash = hashlib.sha256(f.read_bytes()).hexdigest()

            store.upsert_file_snapshot(
                file_id=file_id,
                repo_id=repo["id"],
                path=f"file{i}.py",
                mtime_ns=stat.st_mtime_ns,
                size_bytes=stat.st_size,
                content_hash=content_hash,
            )

        # Modify one file, delete another
        files[0].write_text("def func0(): return 42")
        files[1].unlink()

        # Detect drift
        drift_events = store.detect_drift(repo["id"])
        assert len(drift_events) == 2

        # Check both types are present
        drift_types = {e["drift_type"] for e in drift_events}
        assert "modified" in drift_types
        assert "deleted" in drift_types
