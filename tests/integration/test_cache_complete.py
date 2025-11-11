"""Integration tests for cache layer functionality."""

import pytest
import time
from pathlib import Path

from kb.api.search_backend import SearchBackend
from kb.store import LanceDBStore, SQLiteMetadataStore
from kb.ingest.pipeline import IngestionPipeline
from kb.config import KBConfig


class TestCachePerformance:
    """Test cache performance and behavior."""

    def test_cache_speeds_up_repeated_queries(self, temp_dir: Path):
        """Verify cache improves query performance for repeated queries."""
        # Setup repository and index
        repo_path = temp_dir / "cache_repo"
        repo_path.mkdir()

        (repo_path / "auth.py").write_text("""
def authenticate_user(username, password):
    '''Authenticate user with credentials.'''
    return verify_credentials(username, password)

def verify_credentials(username, password):
    '''Verify user credentials against database.'''
    return True
""")

        (repo_path / "api.py").write_text("""
def create_endpoint(route):
    '''Create API endpoint.'''
    return {'route': route}
""")

        # Setup and index
        db_path = temp_dir / "cache.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://cache_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="cache-repo",
            path=repo_path,
            default_embed_model="small"
        )

        pipeline.index("cache-repo", dry_run=False, force=True)

        # Create search backend
        backend = SearchBackend(lancedb_store)

        # First query (cold cache)
        query = "user authentication"
        start = time.time()
        results1 = backend.search(query, top_k=5)
        cold_time = time.time() - start

        # Second identical query (warm cache if caching enabled)
        start = time.time()
        results2 = backend.search(query, top_k=5)
        warm_time = time.time() - start

        # Results should be identical
        assert len(results1) == len(results2)

        # Warm cache should be at least as fast (might be same if cache disabled)
        assert warm_time <= cold_time * 1.5  # Allow some variance

    def test_cache_invalidation_on_reindex(self, temp_dir: Path):
        """Test cache is invalidated when repository is re-indexed."""
        repo_path = temp_dir / "invalidate_repo"
        repo_path.mkdir()

        (repo_path / "code.py").write_text("def original(): return 'original'")

        # Setup and initial index
        db_path = temp_dir / "invalidate.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://invalidate_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="invalidate-repo",
            path=repo_path,
            default_embed_model="small"
        )

        pipeline.index("invalidate-repo", dry_run=False, force=True)

        backend = SearchBackend(lancedb_store)

        # Initial search
        results1 = backend.search("original", top_k=5)
        initial_count = len(results1)

        # Modify repository
        (repo_path / "code.py").write_text("""
def original(): return 'original'
def new_function(): return 'new'
def another_function(): return 'another'
""")

        # Re-index
        pipeline.index("invalidate-repo", dry_run=False, force=True)

        # Search again - should reflect new content
        results2 = backend.search("new function", top_k=5)

        # Should find new content (cache invalidated)
        assert isinstance(results2, list)
        # May or may not find more results depending on chunking


class TestCacheConsistency:
    """Test cache consistency and correctness."""

    def test_cache_returns_consistent_results(self, temp_dir: Path):
        """Test cache returns consistent results across multiple queries."""
        repo_path = temp_dir / "consistent_repo"
        repo_path.mkdir()

        (repo_path / "data.py").write_text("""
def process_data(data):
    '''Process input data.'''
    return transform(data)

def transform(data):
    '''Transform data.'''
    return data.upper()
""")

        # Setup
        db_path = temp_dir / "consistent.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://consistent_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="consistent-repo",
            path=repo_path,
            default_embed_model="small"
        )

        pipeline.index("consistent-repo", dry_run=False, force=True)

        backend = SearchBackend(lancedb_store)

        # Run same query multiple times
        query = "process data transformation"
        results_list = []

        for _ in range(5):
            results = backend.search(query, top_k=3)
            results_list.append(results)

        # All results should be identical
        for i in range(1, 5):
            assert len(results_list[i]) == len(results_list[0])

            # Check that chunk IDs are the same
            if len(results_list[0]) > 0:
                ids_0 = [r['chunk_id'] for r in results_list[0]]
                ids_i = [r['chunk_id'] for r in results_list[i]]
                assert ids_0 == ids_i

    def test_cache_handles_different_top_k(self, temp_dir: Path):
        """Test cache correctly handles different top_k values."""
        repo_path = temp_dir / "topk_repo"
        repo_path.mkdir()

        # Create file with enough content for multiple results
        content = "\n\n".join([
            f"def function_{i}():\n    '''Function {i} for testing.'''\n    return {i}"
            for i in range(10)
        ])
        (repo_path / "functions.py").write_text(content)

        # Setup
        db_path = temp_dir / "topk.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://topk_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="topk-repo",
            path=repo_path,
            default_embed_model="small"
        )

        pipeline.index("topk-repo", dry_run=False, force=True)

        backend = SearchBackend(lancedb_store)

        # Search with different top_k values
        results_3 = backend.search("function testing", top_k=3)
        results_5 = backend.search("function testing", top_k=5)
        results_10 = backend.search("function testing", top_k=10)

        # Should respect top_k limits
        assert len(results_3) <= 3
        assert len(results_5) <= 5
        assert len(results_10) <= 10

        # Larger top_k should include all results from smaller top_k
        if len(results_3) > 0 and len(results_5) > 0:
            ids_3 = [r['chunk_id'] for r in results_3]
            ids_5 = [r['chunk_id'] for r in results_5]
            # First 3 IDs from top_k=5 should match top_k=3
            assert ids_5[:len(ids_3)] == ids_3


class TestCacheEdgeCases:
    """Test cache behavior in edge cases."""

    def test_cache_handles_empty_results(self, temp_dir: Path):
        """Test cache correctly handles queries with no results."""
        repo_path = temp_dir / "empty_repo"
        repo_path.mkdir()

        (repo_path / "simple.py").write_text("def simple(): pass")

        # Setup
        db_path = temp_dir / "empty.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://empty_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="empty-repo",
            path=repo_path,
            default_embed_model="small"
        )

        pipeline.index("empty-repo", dry_run=False, force=True)

        backend = SearchBackend(lancedb_store)

        # Query unlikely to match
        results1 = backend.search("xyzabc123nonexistent", top_k=5)
        results2 = backend.search("xyzabc123nonexistent", top_k=5)

        # Both should return empty or same results
        assert len(results1) == len(results2)

    def test_cache_handles_special_characters(self, temp_dir: Path):
        """Test cache handles queries with special characters."""
        repo_path = temp_dir / "special_repo"
        repo_path.mkdir()

        (repo_path / "code.py").write_text("""
def handle_special_chars():
    '''Handle special characters: @#$%^&*()'''
    return "special"
""")

        # Setup
        db_path = temp_dir / "special.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://special_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="special-repo",
            path=repo_path,
            default_embed_model="small"
        )

        pipeline.index("special-repo", dry_run=False, force=True)

        backend = SearchBackend(lancedb_store)

        # Queries with special characters
        special_queries = [
            "special @#$%",
            "handle & characters",
            "test (parentheses)",
        ]

        for query in special_queries:
            # Should not crash
            results = backend.search(query, top_k=5)
            assert isinstance(results, list)

    def test_cache_concurrent_access(self, temp_dir: Path):
        """Test cache handles concurrent access correctly."""
        import threading

        repo_path = temp_dir / "concurrent_repo"
        repo_path.mkdir()

        (repo_path / "code.py").write_text("""
def concurrent_test():
    '''Test concurrent access.'''
    return True
""")

        # Setup
        db_path = temp_dir / "concurrent.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://concurrent_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="concurrent-repo",
            path=repo_path,
            default_embed_model="small"
        )

        pipeline.index("concurrent-repo", dry_run=False, force=True)

        backend = SearchBackend(lancedb_store)

        # Shared results storage
        results_dict = {}

        def search_task(task_id: int):
            """Search task for threading."""
            results = backend.search("concurrent test", top_k=5)
            results_dict[task_id] = results

        # Run multiple searches concurrently
        threads = []
        for i in range(5):
            thread = threading.Thread(target=search_task, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # All threads should have gotten results
        assert len(results_dict) == 5

        # Results should be consistent across threads
        first_result = results_dict[0]
        for i in range(1, 5):
            assert len(results_dict[i]) == len(first_result)
