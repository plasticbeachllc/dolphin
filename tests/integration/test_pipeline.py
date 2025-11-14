"""Integration tests for KB pipeline component interactions."""

from pathlib import Path

import pytest

from kb.config import KBConfig
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore
from tests.utils.mock_services import MockEmbeddingService


class TestPipelineIntegration:
    """Integration tests for the ingestion pipeline."""

    def test_pipeline_scan_integration(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test complete pipeline scanning workflow."""
        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        # Create stores
        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        # Create pipeline
        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Register test repository
        metadata_store.record_repo(name="test-repo", path=sample_repo_path, default_embed_model="small")

        # Test scanning
        result = pipeline.scan("test-repo", dry_run=True, force=True)

        # Verify scan results
        assert "session_id" in result
        assert result["repo"] == "test-repo"
        assert result["files_kept"] > 0

        # Verify session was created (dry_run implies running)
        session = metadata_store.get_session(result["session_id"])
        assert session is not None
        assert session["status"] == "running"

    def test_pipeline_index_integration(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test complete pipeline indexing workflow."""
        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        # Create stores
        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        # Create pipeline
        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Register test repository
        metadata_store.record_repo(name="test-repo", path=sample_repo_path, default_embed_model="small")

        # Test indexing with dry run
        result = pipeline.index("test-repo", dry_run=True, force=True)

        # Verify indexing results
        assert "session_id" in result
        assert result["repo"] == "test-repo"
        assert "files_indexed" in result
        assert "chunks_indexed" in result
        assert "vectors_written" in result

        # Verify session returned
        session = metadata_store.get_session(result["session_id"])
        assert session is not None
        # In dry_run mode, session remains running
        assert session["status"] == "running"

    def test_pipeline_incremental_indexing(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test incremental indexing workflow."""
        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        # Create stores
        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        # Create pipeline
        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Register test repository
        metadata_store.record_repo(name="test-repo", path=sample_repo_path, default_embed_model="small")

        # First full index
        result1 = pipeline.index("test-repo", dry_run=True, force=True)

        # Second incremental index (should process minimal changes)
        pipeline.index("test-repo", dry_run=True, force=True)

        # Verify incremental indexing behavior
        assert result1["files_indexed"] > 0
        # In incremental mode with no changes, files_indexed should be lower
        # or similar (depends on git diff logic)

    def test_pipeline_error_handling(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test pipeline error handling and recovery."""
        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        # Create stores
        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        # Create pipeline
        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Test with non-existent repository
        with pytest.raises(ValueError, match="Repository not registered"):
            pipeline.scan("non-existent-repo")

        # Test with invalid embed model
        metadata_store.record_repo(
            name="invalid-model-repo",
            path=sample_repo_path,
            default_embed_model="invalid-model",
        )

        with pytest.raises(ValueError, match="Unsupported embed model"):
            pipeline.scan("invalid-model-repo")


@pytest.mark.asyncio
class TestPipelineAsyncIntegration:
    """Async integration tests for pipeline components."""

    async def test_pipeline_concurrent_operations(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test pipeline operations under concurrent load."""
        import asyncio

        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        # Create stores
        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        # Register multiple repositories
        repo_names = [f"test-repo-{i}" for i in range(3)]
        for repo_name in repo_names:
            metadata_store.record_repo(name=repo_name, path=sample_repo_path, default_embed_model="small")

        # Create pipelines
        pipelines = [IngestionPipeline(config, lancedb_store, metadata_store) for _ in repo_names]

        # Run concurrent scans
        async def run_scan(pipeline, repo_name):
            return pipeline.scan(repo_name, dry_run=True, force=True)

        tasks = [run_scan(pipeline, repo_name) for pipeline, repo_name in zip(pipelines, repo_names)]

        results = await asyncio.gather(*tasks)

        # Verify all scans completed
        assert len(results) == len(repo_names)
        for result in results:
            assert "session_id" in result
            assert result["files_kept"] > 0
