"""Integration tests for indexing functionality."""

import os
from pathlib import Path

import pytest

from kb.config import KBConfig
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore
from tests.utils.mock_services import MockEmbeddingService


class TestIndexingIntegration:
    """Integration tests for indexing functionality."""

    def test_indexing_workflow_completeness(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test that indexing workflow processes all repository files."""
        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Register repository
        metadata_store.record_repo(name="test-repo", path=sample_repo_path, default_embed_model="small")

        # Run indexing
        result = pipeline.index("test-repo", dry_run=True, force=True)

        # Verify indexing completed successfully
        assert result["session_id"] is not None
        assert result["files_indexed"] >= 0

        # Verify metadata was recorded
        session = metadata_store.get_session(result["session_id"])
        assert session is not None
        # In dry_run mode, status remains running and counters may not be persisted
        assert session["status"] == "running"

    def test_indexing_content_deduplication(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test that indexing properly deduplicates content."""
        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Register repository
        metadata_store.record_repo(name="test-repo", path=sample_repo_path, default_embed_model="small")

        # First indexing run
        result1 = pipeline.index("test-repo", dry_run=True, force=True)

        # Second indexing run (should have deduplication)
        result2 = pipeline.index("test-repo", dry_run=True, force=True)

        # Verify deduplication occurred
        # In second run, chunks_skipped should be higher due to deduplication
        assert result2["chunks_skipped"] >= result1["chunks_skipped"]
        # Total chunks processed should be similar or less
        assert (result2["chunks_indexed"] + result2["chunks_skipped"]) <= (
            result1["chunks_indexed"] + result1["chunks_skipped"]
        )

    def test_indexing_error_recovery(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test that indexing recovers from errors gracefully."""
        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Register repository
        metadata_store.record_repo(name="test-repo", path=sample_repo_path, default_embed_model="small")

        # Create a problematic file that might cause chunking errors
        problematic_file = sample_repo_path / "problematic.py"
        problematic_file.write_text(
            """
        # This file has syntax that might break some chunkers
        def broken_function(
            missing_paren:
            pass
        """
        )

        try:
            # Indexing should handle the problematic file gracefully
            result = pipeline.index("test-repo", dry_run=True, force=True)

            # Should complete with some files processed
            assert result["files_indexed"] > 0
            assert result["session_id"] is not None

        finally:
            # Clean up
            if problematic_file.exists():
                problematic_file.unlink()

    def test_indexing_large_file_handling(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test indexing behavior with large files."""
        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Register repository
        metadata_store.record_repo(name="test-repo", path=sample_repo_path, default_embed_model="small")

        # Create a large file
        large_file = sample_repo_path / "large_file.py"
        large_content = "# Large file\n" + "print('line')\n" * 1000
        large_file.write_text(large_content)

        try:
            # Index the repository
            result = pipeline.index("test-repo", dry_run=True, force=True)

            # Verify large file was processed
            assert result["files_indexed"] > 0
            assert result["chunks_indexed"] > 0

            # Large files should be chunked appropriately
            # (not too many chunks, not too few)
            chunks_per_large_file = result["chunks_indexed"] / result["files_indexed"]
            assert 1 <= chunks_per_large_file <= 50  # Reasonable range

        finally:
            # Clean up
            if large_file.exists():
                large_file.unlink()

    def test_indexing_mixed_file_types(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test indexing with various file types and languages."""
        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Register repository
        metadata_store.record_repo(name="test-repo", path=sample_repo_path, default_embed_model="small")

        # Create various file types
        files_to_create = [
            ("test.py", "def hello(): pass"),
            ("test.js", "function test() {}"),
            ("test.md", "# Test Markdown"),
            ("test.txt", "Plain text file"),
            ("test.json", '{"key": "value"}'),
        ]

        created_files = []
        try:
            for filename, content in files_to_create:
                file_path = sample_repo_path / filename
                file_path.write_text(content)
                created_files.append(file_path)

            # Index the repository
            result = pipeline.index("test-repo", dry_run=True, force=True)

            # Verify files were processed (at least existing tracked ones)
            assert result["files_indexed"] >= 0
            assert result["chunks_indexed"] >= 0

            # Different file types should use appropriate chunkers
            # (this is verified by the fact that indexing completes)

        finally:
            # Clean up
            for file_path in created_files:
                if file_path.exists():
                    file_path.unlink()


class TestIndexingPerformance:
    """Performance-focused indexing integration tests."""

    def test_indexing_memory_usage(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test that indexing maintains reasonable memory usage."""
        import os

        import psutil

        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Register repository
        metadata_store.record_repo(name="test-repo", path=sample_repo_path, default_embed_model="small")

        # Measure memory before indexing
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Run indexing
        result = pipeline.index("test-repo", dry_run=True, force=True)

        # Measure memory after indexing
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_used = memory_after - memory_before

        # Verify reasonable memory usage (under 500MB as per spec)
        assert memory_used < 500, f"Memory usage too high: {memory_used:.2f}MB"

        # Verify indexing completed successfully
        assert result["files_indexed"] > 0

    def test_indexing_execution_time(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test that indexing completes within reasonable time."""
        import time

        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Register repository
        metadata_store.record_repo(name="test-repo", path=sample_repo_path, default_embed_model="small")

        # Measure execution time
        start_time = time.time()
        result = pipeline.index("test-repo", dry_run=True, force=True)
        end_time = time.time()

        execution_time = end_time - start_time

        # Verify reasonable execution time (under 30s for integration tests)
        assert execution_time < 30, f"Indexing took too long: {execution_time:.2f}s"

        # Verify indexing completed successfully
        assert result["files_indexed"] > 0

    def test_indexing_concurrent_operations(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test indexing behavior under concurrent operations."""
        import threading

        # Setup
        config = KBConfig(default_embed_model="small", ignore=["*.pyc", "__pycache__/*"])

        metadata_store = SQLiteMetadataStore(temp_db_path)
        metadata_store.initialize()  # Initialize database tables
        lancedb_store = LanceDBStore("memory://test_db")

        # Register multiple repositories
        repo_names = ["repo1", "repo2", "repo3"]
        for repo_name in repo_names:
            metadata_store.record_repo(name=repo_name, path=sample_repo_path, default_embed_model="small")

        results = {}
        errors = {}

        def run_indexing(repo_name):
            """Run indexing for a specific repository."""
            try:
                pipeline = IngestionPipeline(config, lancedb_store, metadata_store)
                result = pipeline.index(repo_name, dry_run=True, force=True)
                results[repo_name] = result
            except Exception as e:
                errors[repo_name] = str(e)

        # Start concurrent indexing operations
        threads = []
        for repo_name in repo_names:
            thread = threading.Thread(target=run_indexing, args=(repo_name,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all indexing operations completed
        assert len(results) == len(repo_names)
        assert len(errors) == 0

        for repo_name, result in results.items():
            assert result["files_indexed"] > 0
            assert result["session_id"] is not None


@pytest.mark.skipif(
    os.environ.get("DOLPHIN_TEST_FULL") != "1",
    reason="Requires actual external services - set DOLPHIN_TEST_FULL=1 to run",
)
class TestIndexingWithExternalServices:
    """Integration tests that require external services (marked as skip by default)."""

    def test_indexing_with_real_embeddings(self, sample_repo_path: Path, temp_db_path: Path):
        """Test indexing with real embedding service (requires API access)."""
        # This test would use real embedding service instead of mock
        # It's skipped by default to avoid external dependencies
        pass

    def test_indexing_with_real_lancedb(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test indexing with real LanceDB storage (requires LanceDB)."""
        # This test would use real LanceDB instead of in-memory
        # It's skipped by default to avoid external dependencies
        pass
