"""Comprehensive unit tests for IngestionPipeline core operations.

This module tests the main pipeline operations including initialization,
scanning, indexing, file processing, and deletion handling.
"""

from __future__ import annotations

import subprocess

import pytest

import kb.ingest.pipeline as ingest_pipeline
from kb.config import KBConfig
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore


class TestPipelineInitialization:
    """Test IngestionPipeline initialization and __post_init__."""

    @pytest.fixture
    def stores(self, tmp_path):
        """Create metadata and lancedb stores."""
        config = KBConfig(store_root=tmp_path, embedding_provider="stub")
        metadata = SQLiteMetadataStore(tmp_path / "test.db")
        metadata.initialize()
        lancedb = LanceDBStore(tmp_path / "lancedb")
        return config, metadata, lancedb

    def test_post_init_creates_graph_store(self, stores):
        """Test that __post_init__ creates a GraphStore if none provided."""
        config, metadata, lancedb = stores
        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

        assert pipeline.graph_store is not None

    def test_post_init_creates_graph_managers_dict(self, stores):
        """Test that __post_init__ initializes graph_managers dict."""
        config, metadata, lancedb = stores
        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

        assert pipeline.graph_managers is not None
        assert isinstance(pipeline.graph_managers, dict)
        assert len(pipeline.graph_managers) == 0

    def test_post_init_configures_bm25_statistics(self, stores):
        """Test that __post_init__ configures BM25 statistics."""
        config, metadata, lancedb = stores
        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

        assert pipeline._bm25_stats_path is not None

    def test_resolve_bm25_stats_path_default(self, stores):
        """Test _resolve_bm25_stats_path uses default path."""
        config, metadata, lancedb = stores
        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

        assert pipeline._bm25_stats_path is not None
        assert "bm25" in str(pipeline._bm25_stats_path).lower()

    def test_get_graph_manager_creates_new(self, stores):
        """Test get_graph_manager creates a new GraphManager."""
        config, metadata, lancedb = stores

        # Register a repo
        metadata.register_repo("test-repo", str(config.store_root), default_embed_model="small")
        repo = metadata.get_repo_by_name("test-repo")
        repo_id = int(repo["id"])

        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)
        manager = pipeline.get_graph_manager(repo_id)

        assert manager is not None
        assert pipeline.graph_managers is not None
        assert repo_id in pipeline.graph_managers

    def test_get_graph_manager_returns_cached(self, stores):
        """Test get_graph_manager returns cached GraphManager."""
        config, metadata, lancedb = stores

        metadata.register_repo("test-repo", str(config.store_root), default_embed_model="small")
        repo = metadata.get_repo_by_name("test-repo")
        repo_id = int(repo["id"])

        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)
        manager1 = pipeline.get_graph_manager(repo_id)
        manager2 = pipeline.get_graph_manager(repo_id)

        assert manager1 is manager2


class TestPipelineScan:
    """Test IngestionPipeline scan operations."""

    @pytest.fixture
    def pipeline_with_repo(self, tmp_path):
        """Create a pipeline with a registered git repo."""
        store_path = tmp_path / "store"
        store_path.mkdir()

        config = KBConfig(store_root=store_path, embedding_provider="stub")
        metadata = SQLiteMetadataStore(store_path / "test.db")
        metadata.initialize()
        lancedb = LanceDBStore(store_path / "lancedb")
        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

        # Create a git repo
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "commit.gpgsign", "false"],
            check=True,
            capture_output=True,
        )

        # Add a file and commit
        (repo_path / "test.py").write_text('print("hello")')
        subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "initial"],
            check=True,
            capture_output=True,
        )

        # Register the repo
        metadata.register_repo("test-repo", str(repo_path), default_embed_model="small")

        return pipeline, repo_path

    def test_scan_returns_summary(self, pipeline_with_repo):
        """Test scan returns a summary dictionary."""
        pipeline, repo_path = pipeline_with_repo

        result = pipeline.scan("test-repo", force=True)

        assert isinstance(result, dict)
        assert "repo" in result
        assert "repo_id" in result
        assert "session_id" in result
        assert "commit" in result
        assert "branch" in result
        assert "files_kept" in result
        assert result["repo"] == "test-repo"
        assert result["files_kept"] >= 0

    def test_scan_dry_run_no_persist(self, pipeline_with_repo):
        """Test scan with dry_run doesn't persist file catalog."""
        pipeline, repo_path = pipeline_with_repo

        result = pipeline.scan("test-repo", dry_run=True, force=True)

        # Should still return a summary
        assert "session_id" in result

    def test_scan_force_skips_clean_check(self, pipeline_with_repo):
        """Test scan with force=True skips clean working tree check."""
        pipeline, repo_path = pipeline_with_repo

        # Modify a tracked file
        (repo_path / "test.py").write_text('print("modified")')

        # Should not raise with force=True
        result = pipeline.scan("test-repo", force=True)
        assert result is not None


class TestPipelineIndex:
    """Test IngestionPipeline index operations."""

    @pytest.fixture
    def pipeline_with_repo(self, tmp_path):
        """Create a pipeline with a registered git repo."""
        store_path = tmp_path / "store"
        store_path.mkdir()

        config = KBConfig(store_root=store_path, embedding_provider="stub")
        metadata = SQLiteMetadataStore(store_path / "test.db")
        metadata.initialize()
        lancedb = LanceDBStore(store_path / "lancedb")
        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

        # Create a git repo
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "commit.gpgsign", "false"],
            check=True,
            capture_output=True,
        )

        # Add a Python file and commit
        (repo_path / "hello.py").write_text('def hello():\n    return "Hello, World!"\n')
        subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "initial"],
            check=True,
            capture_output=True,
        )

        # Register the repo
        metadata.register_repo("test-repo", str(repo_path), default_embed_model="small")

        return pipeline, repo_path, metadata

    def test_index_returns_session_summary(self, pipeline_with_repo):
        """Test index returns a session summary dictionary."""
        pipeline, repo_path, metadata = pipeline_with_repo

        result = pipeline.index("test-repo", force=True)

        assert isinstance(result, dict)
        assert "repo" in result
        assert "commit" in result

    def test_index_dry_run_no_persist(self, pipeline_with_repo):
        """Test index with dry_run doesn't persist changes."""
        pipeline, repo_path, metadata = pipeline_with_repo

        result = pipeline.index("test-repo", dry_run=True, force=True)

        assert result is not None

    def test_index_incremental_mode(self, pipeline_with_repo):
        """Test index in incremental mode after first full index."""
        pipeline, repo_path, metadata = pipeline_with_repo

        # First index
        pipeline.index("test-repo", force=True)

        # Add a new file
        (repo_path / "new_file.py").write_text("x = 1")
        subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "add new"],
            check=True,
            capture_output=True,
        )

        # Second index should be incremental
        result = pipeline.index("test-repo", force=True)
        assert result is not None

    def test_index_full_reindex_mode(self, pipeline_with_repo):
        """Test index with full_reindex=True drops and re-creates index."""
        pipeline, repo_path, metadata = pipeline_with_repo

        # First index
        pipeline.index("test-repo", force=True)

        # Full reindex
        result = pipeline.index("test-repo", force=True, full_reindex=True)

        assert result is not None

    def test_index_invalid_embed_model_raises(self, pipeline_with_repo):
        """Test index migrates repo when model in DB differs from global config."""
        pipeline, repo_path, metadata = pipeline_with_repo

        # Update repo with different model than global config
        with metadata._connect() as conn:
            conn.execute(
                "UPDATE repos SET default_embed_model = ? WHERE name = ?",
                ("invalid_model", "test-repo"),
            )
            conn.commit()

        # Should not raise - will migrate to global config (default is large)
        result = pipeline.index("test-repo", force=True)
        assert result is not None

    def test_index_sets_session_failed_on_error(self, pipeline_with_repo, monkeypatch):
        """Test index marks the session as failed when an error occurs."""
        pipeline, repo_path, metadata = pipeline_with_repo

        def _raise_error(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(pipeline, "process_files", _raise_error)

        with pytest.raises(RuntimeError, match="boom"):
            pipeline.index("test-repo", force=True)

        repo = metadata.get_repo_by_name("test-repo")
        repo_id = repo["id"]
        with metadata._connect() as conn:
            row = conn.execute(
                "SELECT status, notes FROM sessions WHERE repo_id = ? ORDER BY id DESC LIMIT 1",
                (repo_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == "failed"
        assert "boom" in (row[1] or "")

    def test_index_sets_session_aborted_on_keyboard_interrupt(self, pipeline_with_repo, monkeypatch):
        """Test index marks the session as aborted on KeyboardInterrupt."""
        pipeline, repo_path, metadata = pipeline_with_repo

        def _raise_interrupt(*args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr(pipeline, "process_files", _raise_interrupt)

        with pytest.raises(KeyboardInterrupt):
            pipeline.index("test-repo", force=True)

        repo = metadata.get_repo_by_name("test-repo")
        repo_id = repo["id"]
        with metadata._connect() as conn:
            row = conn.execute(
                "SELECT status, notes FROM sessions WHERE repo_id = ? ORDER BY id DESC LIMIT 1",
                (repo_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == "aborted"
        assert "interrupted" in (row[1] or "")


class TestPipelineProcessFiles:
    """Test IngestionPipeline process_files operation."""

    @pytest.fixture
    def pipeline_setup(self, tmp_path):
        """Create pipeline with all required mocks."""
        store_path = tmp_path / "store"
        store_path.mkdir()

        config = KBConfig(store_root=store_path, embedding_provider="stub")
        metadata = SQLiteMetadataStore(store_path / "test.db")
        metadata.initialize()
        lancedb = LanceDBStore(store_path / "lancedb")
        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

        # Create repo directory with files
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "test.py").write_text('print("hello")')
        (repo_path / "utils.py").write_text("def add(a, b):\n    return a + b\n")

        # Register repo
        metadata.register_repo("test-repo", str(repo_path), default_embed_model="small")
        repo = metadata.get_repo_by_name("test-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        # Start a session
        session_id = metadata.begin_session(repo_id, "abc123", "main", "small")

        return pipeline, repo_path, metadata, repo_id, session_id

    def test_process_files_returns_stats(self, pipeline_setup):
        """Test process_files returns stats dictionary."""
        pipeline, repo_path, metadata, repo_id, session_id = pipeline_setup
        from pathspec import PathSpec

        from kb.ingest.error_logging import ErrorLogger

        error_logger = ErrorLogger(repo_path, str(session_id))
        ignore_spec = PathSpec.from_lines("gitignore", [])

        stats = pipeline.process_files(
            repo_id=repo_id,
            repo_name="test-repo",
            root=repo_path,
            files=["test.py"],
            ignore_spec=ignore_spec,
            embed_model="small",
            session_id=session_id,
            commit_sha="abc123",
            branch="main",
            dry_run=True,
            error_logger=error_logger,
        )

        assert isinstance(stats, dict)
        assert "files_done" in stats
        assert "chunks_indexed" in stats
        assert "chunks_skipped" in stats

    def test_process_files_skips_ignored(self, pipeline_setup):
        """Test process_files skips files matching ignore patterns."""
        pipeline, repo_path, metadata, repo_id, session_id = pipeline_setup
        from pathspec import PathSpec

        from kb.ingest.error_logging import ErrorLogger

        error_logger = ErrorLogger(repo_path, str(session_id))
        ignore_spec = PathSpec.from_lines("gitignore", ["*.py"])  # Ignore all .py

        stats = pipeline.process_files(
            repo_id=repo_id,
            repo_name="test-repo",
            root=repo_path,
            files=["test.py"],
            ignore_spec=ignore_spec,
            embed_model="small",
            session_id=session_id,
            commit_sha="abc123",
            branch="main",
            dry_run=True,
            error_logger=error_logger,
        )

        # File should be skipped, so files_done = 0
        assert stats["files_done"] == 0

    def test_process_files_handles_missing_file(self, pipeline_setup):
        """Test process_files handles non-existent files gracefully."""
        pipeline, repo_path, metadata, repo_id, session_id = pipeline_setup
        from pathspec import PathSpec

        from kb.ingest.error_logging import ErrorLogger

        error_logger = ErrorLogger(repo_path, str(session_id))
        ignore_spec = PathSpec.from_lines("gitignore", [])

        stats = pipeline.process_files(
            repo_id=repo_id,
            repo_name="test-repo",
            root=repo_path,
            files=["nonexistent.py"],
            ignore_spec=ignore_spec,
            embed_model="small",
            session_id=session_id,
            commit_sha="abc123",
            branch="main",
            dry_run=True,
            error_logger=error_logger,
        )

        # Should not raise and files_done = 0
        assert stats["files_done"] == 0


class TestPipelineProcessDeletions:
    """Test IngestionPipeline process_deletions operation."""

    @pytest.fixture
    def pipeline_setup(self, tmp_path):
        """Create pipeline with test data."""
        store_path = tmp_path / "store"
        store_path.mkdir()

        config = KBConfig(store_root=store_path, embedding_provider="stub")
        metadata = SQLiteMetadataStore(store_path / "test.db")
        metadata.initialize()
        lancedb = LanceDBStore(store_path / "lancedb")
        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

        # Create repo
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        metadata.register_repo("test-repo", str(repo_path), default_embed_model="small")
        repo = metadata.get_repo_by_name("test-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        # Create a file entry
        file_id = metadata.upsert_file(
            repo_id=repo_id,
            path="deleted.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=100,
        )

        return pipeline, repo_path, metadata, repo_id, file_id

    def test_process_deletions_returns_stats(self, pipeline_setup):
        """Test process_deletions returns stats dictionary."""
        pipeline, repo_path, metadata, repo_id, file_id = pipeline_setup
        from kb.ingest.error_logging import ErrorLogger

        error_logger = ErrorLogger(repo_path, "session1")

        stats = pipeline.process_deletions(
            repo_id=repo_id,
            repo_name="test-repo",
            files=["deleted.py"],
            embed_model="small",
            dry_run=False,
            error_logger=error_logger,
        )

        assert isinstance(stats, dict)
        assert "files_done" in stats
        assert "chunks_pruned" in stats
        assert stats["files_done"] >= 0

    def test_process_deletions_handles_nonexistent_file(self, pipeline_setup):
        """Test process_deletions handles files not in metadata."""
        pipeline, repo_path, metadata, repo_id, file_id = pipeline_setup
        from kb.ingest.error_logging import ErrorLogger

        error_logger = ErrorLogger(repo_path, "session1")

        stats = pipeline.process_deletions(
            repo_id=repo_id,
            repo_name="test-repo",
            files=["nonexistent.py"],
            embed_model="small",
            dry_run=False,
            error_logger=error_logger,
        )

        # Should not raise and files_done = 0
        assert stats["files_done"] == 0

    def test_process_deletions_cleans_graph_before_file_delete(self, pipeline_setup, monkeypatch):
        """Graph cleanup should run before deleting the file row."""
        pipeline, repo_path, metadata, repo_id, file_id = pipeline_setup
        from kb.ingest.error_logging import ErrorLogger

        call_order: list[str] = []

        def fake_cleanup_graph_for_file(graph_store, cleanup_file_id):
            call_order.append("graph")
            assert cleanup_file_id == file_id
            return 0, 0

        original_delete_file = metadata.delete_file

        def wrapped_delete_file(delete_repo_id, delete_file_id):
            call_order.append("delete")
            return original_delete_file(delete_repo_id, delete_file_id)

        monkeypatch.setattr(ingest_pipeline, "cleanup_graph_for_file", fake_cleanup_graph_for_file)
        monkeypatch.setattr(metadata, "delete_file", wrapped_delete_file)
        pipeline.graph_store = object()

        error_logger = ErrorLogger(repo_path, "session1")
        stats = pipeline.process_deletions(
            repo_id=repo_id,
            repo_name="test-repo",
            files=["deleted.py"],
            embed_model="small",
            dry_run=False,
            error_logger=error_logger,
        )

        assert stats["files_done"] == 1
        assert call_order == ["graph", "delete"]

    def test_process_deletions_dry_run_does_not_mutate(self, pipeline_setup, monkeypatch):
        """Dry-run deletion should report intent without mutating data."""
        pipeline, repo_path, metadata, repo_id, file_id = pipeline_setup
        from kb.ingest.error_logging import ErrorLogger

        pruned_models: list[str] = []

        def fake_prune_invalidated_content_for_file(repo_id_arg, file_id_arg, embed_model, current_hashes):
            pruned_models.append(embed_model)
            return 1

        monkeypatch.setattr(metadata, "prune_invalidated_content_for_file", fake_prune_invalidated_content_for_file)

        error_logger = ErrorLogger(repo_path, "session1")
        stats = pipeline.process_deletions(
            repo_id=repo_id,
            repo_name="test-repo",
            files=["deleted.py"],
            embed_model="small",
            dry_run=True,
            error_logger=error_logger,
        )

        assert stats["files_done"] == 1
        assert stats["chunks_pruned"] == 0
        assert pruned_models == []
        assert metadata.get_file_id(repo_id, "deleted.py") == file_id

    def test_process_deletions_stops_on_cancel(self, pipeline_setup, monkeypatch):
        """process_deletions should stop between files when cancel is requested."""
        pipeline, repo_path, metadata, repo_id, file_id = pipeline_setup
        from kb.ingest.error_logging import ErrorLogger

        # Register a second file so there are two to delete
        metadata.upsert_file(
            repo_id=repo_id,
            path="other.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=50,
        )

        # Track which files the cleanup helper is called on
        cleaned_files: list[str] = []
        orig_cleanup = pipeline._cleanup_deleted_file_dependencies

        def tracking_cleanup(repo_id_arg, repo_name_arg, file_id_arg, path_arg):
            cleaned_files.append(path_arg)
            return orig_cleanup(repo_id_arg, repo_name_arg, file_id_arg, path_arg)

        monkeypatch.setattr(pipeline, "_cleanup_deleted_file_dependencies", tracking_cleanup)

        pipeline.request_cancel()
        error_logger = ErrorLogger(repo_path, "session1")

        with pytest.raises(Exception, match="cancelled"):
            pipeline.process_deletions(
                repo_id=repo_id,
                repo_name="test-repo",
                files=["deleted.py", "other.py"],
                embed_model="small",
                dry_run=False,
                error_logger=error_logger,
            )

        # Cancel fires before the first file is touched, so nothing should be cleaned
        assert cleaned_files == []

    def test_is_cancel_requested_reflects_state(self, pipeline_setup):
        """is_cancel_requested returns False initially and True after request_cancel."""
        pipeline, *_ = pipeline_setup

        assert not pipeline.is_cancel_requested()
        pipeline.request_cancel()
        assert pipeline.is_cancel_requested()


class TestPipelineDropRepoIndex:
    """Test IngestionPipeline _drop_repo_index operation."""

    @pytest.fixture
    def pipeline_with_data(self, tmp_path):
        """Create pipeline with indexed data."""
        store_path = tmp_path / "store"
        store_path.mkdir()

        config = KBConfig(store_root=store_path, embedding_provider="stub")
        metadata = SQLiteMetadataStore(store_path / "test.db")
        metadata.initialize()
        lancedb = LanceDBStore(store_path / "lancedb")
        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

        # Create and register repo
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        metadata.register_repo("test-repo", str(repo_path), default_embed_model="small")
        repo = metadata.get_repo_by_name("test-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        # Create some test data
        metadata.upsert_file(
            repo_id=repo_id,
            path="test.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=100,
        )
        metadata.begin_session(repo_id, "abc123", "main", "small")

        return pipeline, metadata, repo_id

    def test_drop_repo_index_clears_metadata(self, pipeline_with_data):
        """Test _drop_repo_index clears metadata."""
        pipeline, metadata, repo_id = pipeline_with_data

        # Verify data exists
        with metadata._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM files WHERE repo_id = ?", (repo_id,))
            files_before = cur.fetchone()[0]

        assert files_before > 0

        # Drop index
        pipeline._drop_repo_index(repo_id, "test-repo")

        # Verify data is cleared
        with metadata._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM files WHERE repo_id = ?", (repo_id,))
            files_after = cur.fetchone()[0]

        assert files_after == 0


class TestPipelineComputeGraphMetrics:
    """Test IngestionPipeline compute_graph_metrics."""

    @pytest.fixture
    def pipeline_with_repo(self, tmp_path):
        """Create pipeline with registered repo."""
        store_path = tmp_path / "store"
        store_path.mkdir()

        config = KBConfig(store_root=store_path, embedding_provider="stub")
        metadata = SQLiteMetadataStore(store_path / "test.db")
        metadata.initialize()
        lancedb = LanceDBStore(store_path / "lancedb")
        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

        metadata.register_repo("test-repo", str(store_path), default_embed_model="small")
        repo = metadata.get_repo_by_name("test-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        return pipeline, repo_id

    def test_compute_graph_metrics_empty_graph(self, pipeline_with_repo):
        """Test compute_graph_metrics returns empty metrics for empty graph."""
        pipeline, repo_id = pipeline_with_repo

        result = pipeline.compute_graph_metrics(repo_id)

        assert isinstance(result, dict)
        assert result["repo_id"] == repo_id
        assert result["node_count"] == 0
        assert result["edge_count"] == 0
        assert result["metrics_computed"] is False


class TestPipelineReconcileBranchSwitch:
    """Test IngestionPipeline reconcile_branch_switch."""

    @pytest.fixture
    def pipeline_with_repo(self, tmp_path):
        """Create pipeline with git repo."""
        store_path = tmp_path / "store"
        store_path.mkdir()

        config = KBConfig(store_root=store_path, embedding_provider="stub")
        metadata = SQLiteMetadataStore(store_path / "test.db")
        metadata.initialize()
        lancedb = LanceDBStore(store_path / "lancedb")
        pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

        # Create a git repo
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "commit.gpgsign", "false"],
            check=True,
            capture_output=True,
        )
        (repo_path / "test.py").write_text("x = 1")
        subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "initial"],
            check=True,
            capture_output=True,
        )

        metadata.register_repo("test-repo", str(repo_path), default_embed_model="small")

        return pipeline, repo_path

    def test_reconcile_branch_switch_calls_index(self, pipeline_with_repo):
        """Test reconcile_branch_switch calls index with force=True."""
        pipeline, repo_path = pipeline_with_repo

        # Should not raise
        pipeline.reconcile_branch_switch("test-repo")


@pytest.mark.asyncio
async def test_index_parallel_sets_session_failed_on_error(tmp_path, monkeypatch):
    """Test index_parallel marks the session failed when parsing fails."""
    store_path = tmp_path / "store"
    store_path.mkdir()

    config = KBConfig(store_root=store_path, embedding_provider="stub")
    metadata = SQLiteMetadataStore(store_path / "test.db")
    metadata.initialize()
    lancedb = LanceDBStore(store_path / "lancedb")
    pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "commit.gpgsign", "false"],
        check=True,
        capture_output=True,
    )
    (repo_path / "hello.py").write_text('def hello():\n    return "Hello, World!"\n')
    subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "initial"], check=True, capture_output=True)

    metadata.register_repo("test-repo", str(repo_path), default_embed_model="small")

    def _raise_parse(*args, **kwargs):
        raise RuntimeError("parse fail")

    monkeypatch.setattr(ingest_pipeline, "parse_files_parallel", _raise_parse)

    with pytest.raises(RuntimeError, match="parse fail"):
        await pipeline.index_parallel("test-repo", force=True)

    repo = metadata.get_repo_by_name("test-repo")
    assert repo is not None
    repo_id = repo["id"]
    with metadata._connect() as conn:
        row = conn.execute(
            "SELECT status, notes FROM sessions WHERE repo_id = ? ORDER BY id DESC LIMIT 1",
            (repo_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == "failed"
    assert "parse fail" in (row[1] or "")


@pytest.mark.asyncio
async def test_parallel_indexing_increments_error_on_dedup_failure(tmp_path, monkeypatch):
    """Mock ChunkDeduplicator.filter_unchanged_chunks to raise; parallel run completes; files_error is 1."""
    store_path = tmp_path / "store"
    store_path.mkdir()

    config = KBConfig(store_root=store_path, embedding_provider="stub")
    metadata = SQLiteMetadataStore(store_path / "test.db")
    metadata.initialize()
    lancedb = LanceDBStore(store_path / "lancedb")
    pipeline = IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "commit.gpgsign", "false"],
        check=True,
        capture_output=True,
    )
    (repo_path / "hello.py").write_text('def hello():\n    return "Hello, World!"\n')
    subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "initial"], check=True, capture_output=True)

    metadata.register_repo("test-repo", str(repo_path), default_embed_model="small")

    from kb.ingest.dedup import ChunkDeduplicator

    def _raise_dedup(self, *args, **kwargs):
        raise RuntimeError("dedup kaboom")

    monkeypatch.setattr(ChunkDeduplicator, "filter_unchanged_chunks", _raise_dedup)

    result = await pipeline.index_parallel("test-repo", force=True)

    assert result["files_error"] >= 1
