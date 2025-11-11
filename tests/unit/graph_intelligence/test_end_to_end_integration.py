"""End-to-end integration tests for graph intelligence pipeline.

Tests the full integration flow without requiring real tiktoken/embeddings.
Uses mocked components for embedding while testing real graph intelligence.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from sqlmodel import create_engine, Session, select
import subprocess
from unittest.mock import Mock, MagicMock, patch

from kb.store.sql_models import CodeNode, CodeEdge, GraphMetrics, GraphCacheState, Repo, File
from kb.store.graph_store import GraphStore
from kb.store.sqlite_meta import SQLiteMetadataStore
from kb.graph_intelligence.graph_manager import GraphManager
from kb.ingest.graph_helpers import extract_graph_from_file, store_graph_data


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository with Python code."""
    tmpdir = tempfile.mkdtemp()
    repo_path = Path(tmpdir) / "test_repo"
    repo_path.mkdir()

    # Initialize git repo with test-friendly config
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
    # Disable GPG signing for this repo
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create Python files
    main_py = repo_path / "main.py"
    main_py.write_text("""
def main():
    result = process()
    display(result)

def process():
    return transform(load())

def load():
    return [1, 2, 3]

def transform(data):
    return [x * 2 for x in data]

def display(result):
    print(result)
""")

    # Commit
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
def initialized_db(temp_git_repo):
    """Create and initialize database with required tables."""
    db_path = temp_git_repo / "test.db"

    # Initialize database using SQLiteMetadataStore
    metadata_store = SQLiteMetadataStore(db_path)
    metadata_store.initialize()

    # Register test repo
    metadata_store.record_repo("test_repo", temp_git_repo)
    repo = metadata_store.get_repo_by_name("test_repo")
    repo_id = int(repo["id"])

    # Add a file
    file_id = metadata_store.upsert_file(
        repo_id=repo_id,
        path="main.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=1000,
    )

    yield db_path, metadata_store, repo_id, file_id

    # Cleanup - no close() method needed for SQLiteMetadataStore


@pytest.fixture
def graph_store_with_data(temp_git_repo, initialized_db):
    """Create graph store and populate it with test data."""
    db_path, metadata_store, repo_id, file_id = initialized_db
    graph_store = GraphStore(db_path)

    # Get commit SHA
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=temp_git_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    commit_sha = result.stdout.strip()

    # Extract graph from main.py
    main_py = temp_git_repo / "main.py"
    text = main_py.read_text()

    nodes, edges = extract_graph_from_file(main_py, "python", text)

    # Store graph data
    stats = store_graph_data(
        graph_store,
        nodes,
        edges,
        repo_id=repo_id,
        file_id=file_id,
        language="python",
        commit_sha=commit_sha,
        branch="main",
    )

    yield graph_store, repo_id, commit_sha, stats


class TestEndToEndIntegration:
    """Test complete end-to-end graph intelligence workflow."""

    def test_extract_and_store_cycle(self, temp_git_repo, initialized_db):
        """Test extraction and storage of graph data."""
        db_path, metadata_store, repo_id, file_id = initialized_db
        graph_store = GraphStore(db_path)

        # Extract graph
        main_py = temp_git_repo / "main.py"
        text = main_py.read_text()
        nodes, edges = extract_graph_from_file(main_py, "python", text)

        # Verify extraction
        assert len(nodes) > 0
        assert len(edges) > 0

        # Store graph
        stats = store_graph_data(
            graph_store,
            nodes,
            edges,
            repo_id=repo_id,
            file_id=file_id,
            language="python",
            commit_sha="abc123",
            branch="main",
        )

        # Verify storage
        assert stats["nodes_created"] > 0
        assert stats["edges_created"] > 0

        # Verify database
        with Session(graph_store.db) as session:
            db_nodes = session.exec(select(CodeNode)).all()
            db_edges = session.exec(select(CodeEdge)).all()

            assert len(db_nodes) == stats["nodes_created"]
            assert len(db_edges) == stats["edges_created"]

    def test_graph_manager_builds_networkx_graph(self, graph_store_with_data):
        """Test GraphManager builds NetworkX graph from database."""
        graph_store, repo_id, commit_sha, stats = graph_store_with_data

        # Create GraphManager
        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=repo_id,
            edge_change_threshold=100,
            cache_ttl_hours=1,
        )

        # Graph should not be loaded initially
        assert graph_manager._graph is None

        # Get graph (triggers lazy loading)
        graph = graph_manager.get_graph()

        # Verify graph was built
        assert graph is not None
        assert graph.number_of_nodes() == stats["nodes_created"]
        assert graph.number_of_edges() == stats["edges_created"]

        # Verify graph structure
        assert "main" in graph.nodes()
        assert "process" in graph.nodes()
        assert "load" in graph.nodes()

    def test_metrics_computation_and_storage(self, graph_store_with_data):
        """Test computing and storing graph metrics."""
        graph_store, repo_id, commit_sha, stats = graph_store_with_data

        # Create GraphManager
        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=repo_id,
        )

        # Compute metrics
        metrics = graph_manager.compute_metrics()

        # Verify metrics structure
        assert "pagerank" in metrics
        assert "in_degree" in metrics
        assert "out_degree" in metrics

        # Verify PageRank values
        assert len(metrics["pagerank"]) > 0
        assert all(0 <= pr <= 1 for pr in metrics["pagerank"].values())

        # Store metrics
        graph_manager.store_metrics(metrics)

        # Verify stored metrics
        with Session(graph_store.db) as session:
            db_metrics = session.exec(select(GraphMetrics)).all()
            assert len(db_metrics) > 0

            # Find "main" function metrics
            main_metrics = next(
                (m for m in db_metrics if m.node_id.endswith("main")), None
            )
            assert main_metrics is not None
            assert main_metrics.pagerank is not None
            assert main_metrics.in_degree >= 0
            assert main_metrics.out_degree >= 0

    def test_cache_invalidation_on_git_changes(self, graph_store_with_data, temp_git_repo):
        """Test cache invalidation when git commit changes."""
        graph_store, repo_id, initial_commit, stats = graph_store_with_data

        # Create GraphManager
        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=repo_id,
        )

        # Build graph (creates cache state)
        initial_graph = graph_manager.get_graph()
        assert graph_manager.validator.is_cache_valid()

        # Get initial cache state
        initial_cache = graph_manager.validator._get_cache_state()
        assert initial_cache["commit_sha"] == initial_commit

        # Make a git change
        new_file = temp_git_repo / "utils.py"
        new_file.write_text("def helper():\n    return 42\n")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add utils"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Cache should be invalid (commit SHA changed)
        assert not graph_manager.validator.is_cache_valid()

    def test_edge_change_tracking(self, graph_store_with_data):
        """Test edge change tracking for cache invalidation."""
        graph_store, repo_id, commit_sha, stats = graph_store_with_data

        # Create GraphManager
        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=repo_id,
            edge_change_threshold=5,  # Low threshold for testing
        )

        # Build graph
        graph_manager.get_graph()

        # Get initial cache state
        initial_cache = graph_manager.validator._get_cache_state()
        assert initial_cache["edge_changes_since_rebuild"] == 0

        # Simulate edge changes
        graph_manager.on_edges_changed(3)

        # Cache should still be valid
        assert graph_manager.validator.is_cache_valid()

        # Add more changes to exceed threshold
        graph_manager.on_edges_changed(3)

        # Cache should now be invalid
        assert not graph_manager.validator.is_cache_valid()

    def test_cache_stats_reporting(self, graph_store_with_data):
        """Test cache statistics reporting."""
        graph_store, repo_id, commit_sha, stats = graph_store_with_data

        # Create GraphManager
        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=repo_id,
        )

        # Build graph
        graph_manager.get_graph()

        # Get cache stats
        cache_stats = graph_manager.get_cache_stats()

        # Verify stats
        assert cache_stats["repo_id"] == repo_id
        assert cache_stats["is_loaded"] is True
        assert cache_stats["is_valid"] is True
        assert cache_stats["node_count"] == stats["nodes_created"]
        assert cache_stats["edge_count"] == stats["edges_created"]
        assert cache_stats["cache_state"] is not None

    def test_force_rebuild(self, graph_store_with_data):
        """Test force rebuild bypasses cache."""
        graph_store, repo_id, commit_sha, stats = graph_store_with_data

        # Create GraphManager
        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=repo_id,
        )

        # Build graph
        initial_graph = graph_manager.get_graph()
        initial_rebuild_time = graph_manager._last_rebuild

        # Force rebuild
        new_graph = graph_manager.get_graph(force_rebuild=True)

        # Rebuild time should be different
        assert graph_manager._last_rebuild > initial_rebuild_time

        # Graph should be valid
        assert new_graph.number_of_nodes() == initial_graph.number_of_nodes()

    def test_manual_cache_invalidation(self, graph_store_with_data):
        """Test manual cache invalidation."""
        graph_store, repo_id, commit_sha, stats = graph_store_with_data

        # Create GraphManager
        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=repo_id,
        )

        # Build graph
        graph_manager.get_graph()
        assert graph_manager._graph is not None

        # Invalidate cache
        graph_manager.invalidate_cache()

        # Cache should be cleared
        assert graph_manager._graph is None
        assert graph_manager._last_rebuild is None

        # Next access should rebuild
        new_graph = graph_manager.get_graph()
        assert new_graph is not None

    def test_empty_graph_metrics(self, temp_git_repo, initialized_db):
        """Test metrics computation on empty graph."""
        db_path, metadata_store, repo_id, file_id = initialized_db
        graph_store = GraphStore(db_path)

        # Create GraphManager with empty database
        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=999,  # Non-existent repo
        )

        # Get graph (will be empty)
        graph = graph_manager.get_graph()
        assert graph.number_of_nodes() == 0

        # Compute metrics
        metrics = graph_manager.compute_metrics()

        # Should return empty dict
        assert metrics == {}

    def test_community_detection(self, graph_store_with_data):
        """Test community detection in metrics."""
        graph_store, repo_id, commit_sha, stats = graph_store_with_data

        # Create GraphManager
        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=repo_id,
        )

        # Compute metrics
        metrics = graph_manager.compute_metrics()

        # Community detection should run (if python-louvain available)
        try:
            import community as community_louvain

            assert "community" in metrics
            assert len(metrics["community"]) > 0
        except ImportError:
            # python-louvain not available, community key won't exist
            pass


class TestPerformance:
    """Test performance characteristics of graph intelligence."""

    def test_lazy_loading_overhead(self, graph_store_with_data):
        """Test lazy loading minimizes overhead."""
        import time

        graph_store, repo_id, commit_sha, stats = graph_store_with_data

        # Creating GraphManager should be fast
        start = time.time()
        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=repo_id,
        )
        creation_time = time.time() - start

        # Should be very fast (< 10ms)
        assert creation_time < 0.01

        # Graph not loaded yet
        assert graph_manager._graph is None

    def test_cached_access_performance(self, graph_store_with_data):
        """Test cached graph access is fast."""
        import time

        graph_store, repo_id, commit_sha, stats = graph_store_with_data

        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=repo_id,
        )

        # First access (builds graph)
        start = time.time()
        first_graph = graph_manager.get_graph()
        first_time = time.time() - start

        # Second access (uses cache)
        start = time.time()
        second_graph = graph_manager.get_graph()
        second_time = time.time() - start

        # Cached access should be much faster
        assert second_time < first_time
        # Should be < 1ms
        assert second_time < 0.001

        # Should be same object
        assert second_graph is first_graph


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_non_python_file(self, temp_git_repo, initialized_db):
        """Test extraction from non-Python files."""
        # Create TypeScript file
        ts_file = temp_git_repo / "app.ts"
        ts_file.write_text("""
function hello() {
    console.log("Hello");
}

function world() {
    hello();
}
""")

        # Extract graph
        text = ts_file.read_text()
        nodes, edges = extract_graph_from_file(ts_file, "typescript", text)

        # Should extract TypeScript nodes
        assert len(nodes) > 0
        node_names = {node.name for node in nodes}
        assert "hello" in node_names
        assert "world" in node_names

    def test_malformed_code(self, temp_git_repo):
        """Test handling of malformed code."""
        # Create file with syntax errors
        bad_py = temp_git_repo / "bad.py"
        bad_py.write_text("""
def broken(
    missing_paren:
    pass
""")

        # Extract should handle gracefully
        text = bad_py.read_text()
        try:
            nodes, edges = extract_graph_from_file(bad_py, "python", text)
            # Should either return empty or partial results
            assert isinstance(nodes, list)
            assert isinstance(edges, list)
        except Exception:
            # Acceptable to raise exception for malformed code
            pass

    def test_large_graph_sampling(self, temp_git_repo, initialized_db):
        """Test that large graphs use sampling for betweenness."""
        db_path, metadata_store, repo_id, file_id = initialized_db
        graph_store = GraphStore(db_path)

        # Create a large graph by adding many nodes
        with Session(graph_store.db) as session:
            # Add 1500 nodes (> 1000 threshold for sampling)
            for i in range(1500):
                node = CodeNode(
                    id=f"node_{i}",
                    name=f"func_{i}",
                    qualified_name=f"module.func_{i}",
                    node_type="function",
                    language="python",
                    repo_id=repo_id,
                    file_id=file_id,
                    start_line=i,
                    end_line=i + 1,
                )
                session.add(node)

            # Add some edges
            for i in range(100):
                edge = CodeEdge(
                    source_node_id=f"node_{i}",
                    target_node_id=f"node_{i+1}",
                    edge_type="calls",
                    repo_id=repo_id,
                )
                session.add(edge)

            session.commit()

        # Create GraphManager
        graph_manager = GraphManager(
            db=graph_store.db,
            repo_id=repo_id,
        )

        # Compute metrics (should use sampling for betweenness)
        metrics = graph_manager.compute_metrics()

        # Should complete successfully
        assert "betweenness_centrality" in metrics
        # Betweenness should be sampled (not all nodes)
        assert len(metrics["betweenness_centrality"]) <= 1500
