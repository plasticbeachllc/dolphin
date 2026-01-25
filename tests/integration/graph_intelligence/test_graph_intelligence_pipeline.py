"""Integration tests for graph intelligence pipeline.

Tests the full end-to-end flow:
1. Index code files
2. Extract and store graph data
3. Build NetworkX graph via GraphManager
4. Compute and store metrics
5. Cache invalidation scenarios
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from sqlmodel import Session

from kb.config import KBConfig
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore
from kb.store.graph_store import GraphStore


@pytest.fixture
def temp_repo():
    """Create a temporary git repository with Python code."""
    tmpdir = tempfile.mkdtemp()
    repo_path = Path(tmpdir) / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create Python files with functions and calls
    main_py = repo_path / "main.py"
    main_py.write_text(
        """
def main():
    '''Main entry point.'''
    result = process_data()
    display_result(result)
    return result

def process_data():
    '''Process the data.'''
    data = load_data()
    return transform(data)

def load_data():
    '''Load data from source.'''
    return [1, 2, 3, 4, 5]

def transform(data):
    '''Transform the data.'''
    return [x * 2 for x in data]

def display_result(result):
    '''Display the result.'''
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
"""
    )

    utils_py = repo_path / "utils.py"
    utils_py.write_text(
        """
class DataProcessor:
    '''Utility class for data processing.'''

    def __init__(self):
        self.cache = {}

    def process(self, data):
        '''Process data with caching.'''
        key = self._compute_key(data)
        if key not in self.cache:
            self.cache[key] = self._transform(data)
        return self.cache[key]

    def _compute_key(self, data):
        '''Compute cache key.'''
        return hash(tuple(data))

    def _transform(self, data):
        '''Transform data.'''
        return [x ** 2 for x in data]
"""
    )

    # Commit files
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    yield repo_path

    # Cleanup
    shutil.rmtree(tmpdir)


@pytest.fixture
def db_and_stores(temp_repo):
    """Create database and stores for testing."""
    db_path = temp_repo / ".kb" / "metadata.db"
    db_path.parent.mkdir(exist_ok=True)

    # Create stores
    metadata = SQLiteMetadataStore(str(db_path))
    metadata.initialize()  # Initialize database tables before registering repo
    lancedb_path = temp_repo / ".kb" / "lancedb"
    lancedb = LanceDBStore(str(lancedb_path))
    graph_store = GraphStore(str(db_path))

    # Register repo
    metadata.register_repo("test_repo", str(temp_repo))

    yield metadata, lancedb, graph_store

    # Cleanup - SQLite connections are automatically closed


@pytest.fixture
def pipeline(db_and_stores):
    """Create ingestion pipeline."""
    metadata, lancedb, graph_store = db_and_stores
    config = KBConfig()
    return IngestionPipeline(
        config=config,
        lancedb=lancedb,
        metadata=metadata,
        graph_store=graph_store,
    )


class TestEndToEndFlow:
    """Test complete end-to-end workflow."""

    def test_index_and_extract_graph(self, pipeline, temp_repo):
        """Test that indexing extracts graph data."""
        # Index the repository
        result = pipeline.index("test_repo", force=True)

        # Verify graph data was extracted
        assert result["graph_nodes_created"] > 0
        assert result["graph_edges_created"] > 0

        # Verify specific nodes exist
        with Session(pipeline.graph_store.db) as session:
            from sqlmodel import select

            from kb.store.sql_models import CodeNode

            nodes = session.exec(select(CodeNode)).all()
            node_names = {node.name for node in nodes}

            # Should have extracted functions
            assert "main" in node_names
            assert "process_data" in node_names
            assert "load_data" in node_names
            assert "DataProcessor" in node_names

    def test_graph_manager_lazy_loading(self, pipeline, temp_repo):
        """Test GraphManager lazy loading after indexing."""
        # Index first
        result = pipeline.index("test_repo", force=True)
        repo_id = result["repo_id"]

        # Get GraphManager
        graph_manager = pipeline.get_graph_manager(repo_id)

        # After indexing, graph is now automatically loaded (via force_rebuild)
        # This ensures cache state is accurate
        assert graph_manager._graph is not None

        # Access graph (should return cached graph)
        graph = graph_manager.get_graph()

        # Verify graph was built
        assert graph is not None
        assert graph.number_of_nodes() > 0
        assert graph.number_of_edges() > 0

        # Verify specific edges exist (function calls)
        # main() calls process_data(), display_result()
        # process_data() calls load_data(), transform()
        edges = list(graph.edges())
        assert len(edges) > 0

        # Test that invalidating cache works
        graph_manager.invalidate_cache()
        assert graph_manager._graph is None

        # Re-accessing rebuilds
        graph2 = graph_manager.get_graph()
        assert graph2 is not None
        assert graph2.number_of_nodes() == graph.number_of_nodes()

    def test_metrics_computation(self, pipeline, temp_repo):
        """Test graph metrics computation."""
        # Index repository
        result = pipeline.index("test_repo", force=True)
        repo_id = result["repo_id"]

        # Compute metrics
        metrics_result = pipeline.compute_graph_metrics(repo_id)

        # Verify metrics were computed
        assert metrics_result["metrics_computed"] is True
        assert metrics_result["node_count"] > 0
        assert metrics_result["pagerank_nodes"] > 0

        # Verify metrics are stored in database
        with Session(pipeline.graph_store.db) as session:
            from sqlmodel import select

            from kb.store.sql_models import GraphMetrics

            metrics = session.exec(select(GraphMetrics)).all()
            assert len(metrics) > 0

            # Verify PageRank values
            pagerank_values = [m.pagerank for m in metrics if m.pagerank]
            assert len(pagerank_values) > 0
            assert all(0 <= pr <= 1 for pr in pagerank_values)

    def test_cache_invalidation_on_commit_change(self, pipeline, temp_repo):
        """Test cache invalidation when git commit changes."""
        # Index repository
        result = pipeline.index("test_repo", force=True)
        repo_id = result["repo_id"]

        # Get graph manager and build graph
        graph_manager = pipeline.get_graph_manager(repo_id)
        initial_graph = graph_manager.get_graph()
        initial_node_count = initial_graph.number_of_nodes()

        # Verify cache is valid
        assert graph_manager.validator.is_cache_valid()

        # Make a change and commit
        new_file = temp_repo / "new_module.py"
        new_file.write_text(
            """
def new_function():
    '''A new function.'''
    return 42
"""
        )
        subprocess.run(
            ["git", "add", "new_module.py"],
            cwd=temp_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add new function"],
            cwd=temp_repo,
            check=True,
            capture_output=True,
        )

        # Cache should now be invalid (commit SHA changed)
        assert not graph_manager.validator.is_cache_valid()

        # Re-index with new commit
        result = pipeline.index("test_repo", force=True)

        # Graph should rebuild automatically
        new_graph = graph_manager.get_graph()
        assert new_graph.number_of_nodes() > initial_node_count

    def test_edge_change_tracking(self, pipeline, temp_repo):
        """Test that edge changes are tracked during indexing."""
        # Index repository
        result = pipeline.index("test_repo", force=True)
        repo_id = result["repo_id"]
        result["graph_edges_created"]

        # Get cache state
        graph_manager = pipeline.get_graph_manager(repo_id)
        cache_state = graph_manager.validator._get_cache_state()

        # Edge changes should have been tracked
        assert cache_state is not None
        # After a rebuild, edge changes should be reset to 0
        assert cache_state["edge_changes_since_rebuild"] == 0

    def test_incremental_indexing_tracks_changes(self, pipeline, temp_repo):
        """Test incremental indexing tracks edge changes."""
        # Initial index
        result1 = pipeline.index("test_repo", force=True)
        repo_id = result1["repo_id"]

        # Get initial cache state
        graph_manager = pipeline.get_graph_manager(repo_id)
        graph_manager.get_graph()  # Build graph
        initial_cache = graph_manager.validator._get_cache_state()

        # Add a new file with function calls
        new_file = temp_repo / "service.py"
        new_file.write_text(
            """
def service_function():
    '''Service function that calls helpers.'''
    helper_a()
    helper_b()

def helper_a():
    '''Helper A.'''
    pass

def helper_b():
    '''Helper B.'''
    pass
"""
        )
        subprocess.run(["git", "add", "service.py"], cwd=temp_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add service"],
            cwd=temp_repo,
            check=True,
            capture_output=True,
        )

        # Incremental index
        result2 = pipeline.index("test_repo", force=True)

        # Edge changes should have been tracked
        assert result2["graph_edges_created"] > 0

        # Force graph rebuild to update cache with new commit
        graph_manager.get_graph(force_rebuild=True)

        # Get new cache state
        new_cache = graph_manager.validator._get_cache_state()

        # Commit SHA should have changed, cache should be invalid
        assert new_cache["commit_sha"] != initial_cache["commit_sha"]


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_empty_repository(self, pipeline):
        """Test handling of empty repository."""
        # Create empty repo
        tmpdir = tempfile.mkdtemp()
        empty_repo = Path(tmpdir) / "empty"
        empty_repo.mkdir()

        subprocess.run(["git", "init"], cwd=empty_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=empty_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=empty_repo,
            check=True,
            capture_output=True,
        )

        # Create initial commit
        readme = empty_repo / "README.md"
        readme.write_text("# Empty Repo")
        subprocess.run(["git", "add", "."], cwd=empty_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=empty_repo,
            check=True,
            capture_output=True,
        )

        # Register and index
        pipeline.metadata.register_repo("empty_repo", str(empty_repo))

        try:
            result = pipeline.index("empty_repo", force=True)

            # Should handle gracefully
            assert result["graph_nodes_created"] == 0
            assert result["graph_edges_created"] == 0

            # Metrics computation should handle empty graph
            repo = pipeline.metadata.get_repo_by_name("empty_repo")
            metrics_result = pipeline.compute_graph_metrics(int(repo["id"]))
            assert metrics_result["metrics_computed"] is False
        finally:
            shutil.rmtree(tmpdir)

    def test_deleted_file_cleanup(self, pipeline, temp_repo):
        """Test graph cleanup when files are deleted."""
        # Index repository
        result1 = pipeline.index("test_repo", force=True)
        repo_id = result1["repo_id"]

        # Get initial graph
        graph_manager = pipeline.get_graph_manager(repo_id)
        initial_graph = graph_manager.get_graph()
        initial_nodes = initial_graph.number_of_nodes()

        # Delete a file
        utils_file = temp_repo / "utils.py"
        utils_file.unlink()
        subprocess.run(["git", "add", "-u"], cwd=temp_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Delete utils"],
            cwd=temp_repo,
            check=True,
            capture_output=True,
        )

        # Re-index
        pipeline.index("test_repo", force=True)

        # Graph should have fewer nodes
        new_graph = graph_manager.get_graph(force_rebuild=True)
        assert new_graph.number_of_nodes() < initial_nodes

    def test_cache_stats(self, pipeline, temp_repo):
        """Test cache statistics reporting."""
        # Index repository
        result = pipeline.index("test_repo", force=True)
        repo_id = result["repo_id"]

        # Get graph manager and build graph
        graph_manager = pipeline.get_graph_manager(repo_id)
        graph_manager.get_graph()

        # Get cache stats
        stats = graph_manager.get_cache_stats()

        # Verify stats structure
        assert "repo_id" in stats
        assert "is_loaded" in stats
        assert "is_valid" in stats
        assert "node_count" in stats
        assert "edge_count" in stats

        assert stats["repo_id"] == repo_id
        assert stats["is_loaded"] is True
        assert stats["is_valid"] is True
        assert stats["node_count"] > 0
        assert stats["edge_count"] >= 0


class TestPerformance:
    """Test performance characteristics."""

    def test_lazy_loading_performance(self, pipeline, temp_repo):
        """Test that cached graph access is fast."""
        import time

        # Index repository (which now also builds the graph)
        result = pipeline.index("test_repo", force=True)
        repo_id = result["repo_id"]

        # Get GraphManager
        graph_manager = pipeline.get_graph_manager(repo_id)

        # Graph is already loaded from indexing, so first access uses cache
        start = time.perf_counter()
        graph_manager.get_graph()
        first_access_time = time.perf_counter() - start

        # Second access should also use cache
        start = time.perf_counter()
        graph_manager.get_graph()
        second_access_time = time.perf_counter() - start

        # Both cached accesses should be fast (< 50ms to account for CI/test overhead)
        assert first_access_time < 0.05
        assert second_access_time < 0.05

        # Test invalidation and rebuild
        graph_manager.invalidate_cache()
        start = time.perf_counter()
        graph_manager.get_graph()
        rebuild_time = time.perf_counter() - start

        # Rebuild might be slower but still reasonable for small graph
        assert rebuild_time < 0.5  # 500ms should be plenty for a small graph

        # After rebuild, cache should work again
        start = time.perf_counter()
        graph_manager.get_graph()
        cached_again_time = time.perf_counter() - start
        assert cached_again_time < 0.05  # Relaxed to avoid timing flakiness in CI

    def test_metrics_computation_performance(self, pipeline, temp_repo):
        """Test metrics computation performance."""
        import time

        # Index repository
        result = pipeline.index("test_repo", force=True)
        repo_id = result["repo_id"]

        # Compute metrics
        start = time.time()
        metrics_result = pipeline.compute_graph_metrics(repo_id)
        computation_time = time.time() - start

        # Should complete in reasonable time (< 5 seconds for small graph)
        assert computation_time < 5.0

        # Verify metrics were computed
        assert metrics_result["metrics_computed"] is True
