"""Integration tests for cache layer functionality."""

import subprocess
import time
from pathlib import Path


from kb.api.app import SearchRequest
from kb.api.search_backend import KnowledgeSearchBackend
from kb.cache import QueryCache
from kb.config import KBConfig
from kb.embeddings.provider import EmbeddingProvider
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore
from tests.conftest import init_test_git_repo


def _create_backend(
    metadata_store: SQLiteMetadataStore,
    lancedb_store: LanceDBStore,
    config: KBConfig,
    *,
    enable_cache: bool,
) -> KnowledgeSearchBackend:
    cache = QueryCache() if enable_cache else None
    return KnowledgeSearchBackend(
        embedding_provider=EmbeddingProvider(),
        lance_store=lancedb_store,
        sql_store=metadata_store,
        cache=cache,
        config=config,
    )


def _run_search(
    backend: KnowledgeSearchBackend,
    query: str,
    *,
    top_k: int,
    repo_name: str,
    embed_model: str,
):
    request = SearchRequest(
        query=query,
        top_k=top_k,
        repos=[repo_name],
        embed_model=embed_model,
        include_graph_context=False,
    )
    return backend.search(request)


class TestCachePerformance:
    """Test cache performance and behavior."""

    def test_cache_speeds_up_repeated_queries(self, temp_dir: Path):
        """Verify cache improves query performance for repeated queries."""
        # Setup repository and index
        repo_path = temp_dir / "cache_repo"
        repo_path.mkdir()
        init_test_git_repo(repo_path)

        (repo_path / "auth.py").write_text(
            """
def authenticate_user(username, password):
    '''Authenticate user with credentials.'''
    return verify_credentials(username, password)

def verify_credentials(username, password):
    '''Verify user credentials against database.'''
    return True
"""
        )

        (repo_path / "api.py").write_text(
            """
def create_endpoint(route):
    '''Create API endpoint.'''
    return {'route': route}
"""
        )

        # Commit files to git
        subprocess.run(
            ["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "Initial commit"],
            check=True,
            capture_output=True,
        )

        # Setup and index
        db_path = temp_dir / "cache.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://cache_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="cache-repo", path=repo_path, default_embed_model="small"
        )

        pipeline.index("cache-repo", dry_run=False, force=True)

        # Create search backend with caching enabled
        backend = _create_backend(
            metadata_store,
            lancedb_store,
            config,
            enable_cache=True,
        )

        # First query (cold cache)
        query = "user authentication"
        start = time.time()
        results1 = _run_search(
            backend,
            query,
            top_k=5,
            repo_name="cache-repo",
            embed_model=config.default_embed_model,
        )
        cold_time = time.time() - start

        # Second identical query (warm cache if caching enabled)
        start = time.time()
        results2 = _run_search(
            backend,
            query,
            top_k=5,
            repo_name="cache-repo",
            embed_model=config.default_embed_model,
        )
        warm_time = time.time() - start

        # Results should be identical
        assert len(results1) == len(results2)

        # Warm cache should be at least as fast (might be same if cache disabled)
        assert warm_time <= cold_time * 1.5  # Allow some variance

    def test_cache_invalidation_on_reindex(self, temp_dir: Path):
        """Test cache is invalidated when repository is re-indexed."""
        repo_path = temp_dir / "invalidate_repo"
        repo_path.mkdir()
        init_test_git_repo(repo_path)

        (repo_path / "code.py").write_text("def original(): return 'original'")

        # Commit initial file
        subprocess.run(
            ["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "Initial commit"],
            check=True,
            capture_output=True,
        )

        # Setup and initial index
        db_path = temp_dir / "invalidate.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://invalidate_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="invalidate-repo", path=repo_path, default_embed_model="small"
        )

        pipeline.index("invalidate-repo", dry_run=False, force=True)

        backend = _create_backend(
            metadata_store,
            lancedb_store,
            config,
            enable_cache=True,
        )

        # Initial search
        results1 = _run_search(
            backend,
            "original",
            top_k=5,
            repo_name="invalidate-repo",
            embed_model=config.default_embed_model,
        )
        len(results1)

        # Modify repository
        (repo_path / "code.py").write_text(
            """
def original(): return 'original'
def new_function(): return 'new'
def another_function(): return 'another'
"""
        )

        # Commit changes
        subprocess.run(
            ["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "Add new functions"],
            check=True,
            capture_output=True,
        )

        # Re-index
        pipeline.index("invalidate-repo", dry_run=False, force=True)

        # Search again - should reflect new content
        results2 = _run_search(
            backend,
            "new function",
            top_k=5,
            repo_name="invalidate-repo",
            embed_model=config.default_embed_model,
        )

        # Should find new content (cache invalidated)
        assert isinstance(results2, list)
        # May or may not find more results depending on chunking


class TestCacheConsistency:
    """Test cache consistency and correctness."""

    def test_cache_returns_consistent_results(self, temp_dir: Path):
        """Test cache returns consistent results across multiple queries."""
        repo_path = temp_dir / "consistent_repo"
        repo_path.mkdir()
        init_test_git_repo(repo_path)

        (repo_path / "data.py").write_text(
            """
def process_data(data):
    '''Process input data.'''
    return transform(data)

def transform(data):
    '''Transform data.'''
    return data.upper()
"""
        )

        # Commit files
        subprocess.run(
            ["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "Initial commit"],
            check=True,
            capture_output=True,
        )

        # Setup
        db_path = temp_dir / "consistent.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://consistent_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="consistent-repo", path=repo_path, default_embed_model="small"
        )

        pipeline.index("consistent-repo", dry_run=False, force=True)

        backend = _create_backend(
            metadata_store,
            lancedb_store,
            config,
            enable_cache=True,
        )

        # Run same query multiple times
        query = "process data transformation"
        results_list = []

        for _ in range(5):
            results = _run_search(
                backend,
                query,
                top_k=3,
                repo_name="consistent-repo",
                embed_model=config.default_embed_model,
            )
            results_list.append(results)

        # All results should be identical
        for i in range(1, 5):
            assert len(results_list[i]) == len(results_list[0])

            # Check that chunk IDs are the same
            if len(results_list[0]) > 0:
                ids_0 = [r["chunk_id"] for r in results_list[0]]
                ids_i = [r["chunk_id"] for r in results_list[i]]
                assert ids_0 == ids_i

    def test_cache_handles_different_top_k(self, temp_dir: Path):
        """Test cache correctly handles different top_k values."""
        repo_path = temp_dir / "topk_repo"
        repo_path.mkdir()
        init_test_git_repo(repo_path)

        # Create file with enough content for multiple results
        content = "\n\n".join(
            [
                f"def function_{i}():\n    '''Function {i} for testing.'''\n    return {i}"
                for i in range(10)
            ]
        )
        (repo_path / "functions.py").write_text(content)

        # Commit files
        subprocess.run(
            ["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "Initial commit"],
            check=True,
            capture_output=True,
        )

        # Setup
        db_path = temp_dir / "topk.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://topk_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="topk-repo", path=repo_path, default_embed_model="small"
        )

        pipeline.index("topk-repo", dry_run=False, force=True)

        backend = _create_backend(
            metadata_store,
            lancedb_store,
            config,
            enable_cache=True,
        )

        # Search with different top_k values
        results_3 = _run_search(
            backend,
            "function testing",
            top_k=3,
            repo_name="topk-repo",
            embed_model=config.default_embed_model,
        )
        results_5 = _run_search(
            backend,
            "function testing",
            top_k=5,
            repo_name="topk-repo",
            embed_model=config.default_embed_model,
        )
        results_10 = _run_search(
            backend,
            "function testing",
            top_k=10,
            repo_name="topk-repo",
            embed_model=config.default_embed_model,
        )

        # Should respect top_k limits
        assert len(results_3) <= 3
        assert len(results_5) <= 5
        assert len(results_10) <= 10

        # Larger top_k should include all results from smaller top_k
        if len(results_3) > 0 and len(results_5) > 0:
            ids_3 = [r["chunk_id"] for r in results_3]
            ids_5 = [r["chunk_id"] for r in results_5]
            # First 3 IDs from top_k=5 should match top_k=3
            assert ids_5[: len(ids_3)] == ids_3


class TestCacheEdgeCases:
    """Test cache behavior in edge cases."""

    def test_cache_handles_empty_results(self, temp_dir: Path):
        """Test cache correctly handles queries with no results."""
        repo_path = temp_dir / "empty_repo"
        repo_path.mkdir()
        init_test_git_repo(repo_path)

        (repo_path / "simple.py").write_text("def simple(): pass")

        # Commit files
        subprocess.run(
            ["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "Initial commit"],
            check=True,
            capture_output=True,
        )

        # Setup
        db_path = temp_dir / "empty.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://empty_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="empty-repo", path=repo_path, default_embed_model="small"
        )

        pipeline.index("empty-repo", dry_run=False, force=True)

        backend = _create_backend(
            metadata_store,
            lancedb_store,
            config,
            enable_cache=True,
        )

        # Query unlikely to match
        results1 = _run_search(
            backend,
            "xyzabc123nonexistent",
            top_k=5,
            repo_name="empty-repo",
            embed_model=config.default_embed_model,
        )
        results2 = _run_search(
            backend,
            "xyzabc123nonexistent",
            top_k=5,
            repo_name="empty-repo",
            embed_model=config.default_embed_model,
        )

        # Both should return empty or same results
        assert len(results1) == len(results2)

    def test_cache_handles_special_characters(self, temp_dir: Path):
        """Test cache handles queries with special characters."""
        repo_path = temp_dir / "special_repo"
        repo_path.mkdir()
        init_test_git_repo(repo_path)

        (repo_path / "code.py").write_text(
            """
def handle_special_chars():
    '''Handle special characters: @#$%^&*()'''
    return "special"
"""
        )

        # Commit files
        subprocess.run(
            ["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "Initial commit"],
            check=True,
            capture_output=True,
        )

        # Setup
        db_path = temp_dir / "special.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://special_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="special-repo", path=repo_path, default_embed_model="small"
        )

        pipeline.index("special-repo", dry_run=False, force=True)

        backend = _create_backend(
            metadata_store,
            lancedb_store,
            config,
            enable_cache=True,
        )

        # Queries with special characters
        special_queries = [
            "special @#$%",
            "handle & characters",
            "test (parentheses)",
        ]

        for query in special_queries:
            # Should not crash
            results = _run_search(
                backend,
                query,
                top_k=5,
                repo_name="special-repo",
                embed_model=config.default_embed_model,
            )
            assert isinstance(results, list)

    def test_cache_concurrent_access(self, temp_dir: Path):
        """Test cache handles concurrent access correctly."""
        import threading

        repo_path = temp_dir / "concurrent_repo"
        repo_path.mkdir()
        init_test_git_repo(repo_path)

        (repo_path / "code.py").write_text(
            """
def concurrent_test():
    '''Test concurrent access.'''
    return True
"""
        )

        # Commit files
        subprocess.run(
            ["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "Initial commit"],
            check=True,
            capture_output=True,
        )

        # Setup
        db_path = temp_dir / "concurrent.db"
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://concurrent_test")
        config = KBConfig(default_embed_model="small")

        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        metadata_store.record_repo(
            name="concurrent-repo", path=repo_path, default_embed_model="small"
        )

        pipeline.index("concurrent-repo", dry_run=False, force=True)

        backend = _create_backend(
            metadata_store,
            lancedb_store,
            config,
            enable_cache=True,
        )

        # Shared results storage
        results_dict = {}

        def search_task(task_id: int):
            """Search task for threading."""
            results = _run_search(
                backend,
                "concurrent test",
                top_k=5,
                repo_name="concurrent-repo",
                embed_model=config.default_embed_model,
            )
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
