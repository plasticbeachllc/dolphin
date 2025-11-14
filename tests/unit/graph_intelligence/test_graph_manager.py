"""Tests for GraphManager."""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import networkx as nx
import pytest

from kb.graph_intelligence.graph_manager import GraphManager


@pytest.fixture
def mock_db():
    """Create a mock database."""
    return Mock()


@pytest.fixture
def manager(mock_db):
    """Create a GraphManager instance."""
    return GraphManager(
        db=mock_db, repo_id=1, edge_change_threshold=5, cache_ttl_minutes=10
    )


class TestLazyLoading:
    """Test lazy loading behavior."""

    def test_first_access_triggers_rebuild(self, manager):
        """Test that first graph access triggers rebuild."""
        # Mock validator to return False (cache invalid)
        with patch.object(manager.validator, "is_cache_valid", return_value=False):
            with patch.object(manager, "_rebuild_graph") as mock_rebuild:
                # First access should trigger rebuild
                manager.get_graph()
                assert mock_rebuild.called

    def test_cached_graph_reused(self, manager):
        """Test that cached graph is reused when valid."""
        # Set up a cached graph
        manager._graph = nx.DiGraph()
        manager._graph.add_edge("node1", "node2")

        # Mock validator to return True (cache valid)
        with patch.object(manager.validator, "is_cache_valid", return_value=True):
            with patch.object(manager, "_rebuild_graph") as mock_rebuild:
                # Should return cached graph without rebuild
                graph = manager.get_graph()
                assert not mock_rebuild.called
                assert graph == manager._graph

    def test_force_rebuild_ignores_cache(self, manager):
        """Test that force_rebuild bypasses cache."""
        # Set up a cached graph
        manager._graph = nx.DiGraph()

        # Mock validator to return True (cache valid)
        with patch.object(manager.validator, "is_cache_valid", return_value=True):
            with patch.object(manager, "_rebuild_graph") as mock_rebuild:
                # Force rebuild should ignore cache
                manager.get_graph(force_rebuild=True)
                assert mock_rebuild.called


class TestGraphRebuild:
    """Test graph rebuild from database."""

    def test_rebuild_creates_graph(self, manager):
        """Test that rebuild creates NetworkX graph from edges."""
        # Mock database edges
        mock_edges = [
            {
                "source_node_id": "func1",
                "target_node_id": "func2",
                "edge_type": "calls",
                "commit_sha": "abc123",
                "line_number": 10,
                "is_direct": True,
                "relationship_metadata": None,
            },
            {
                "source_node_id": "func2",
                "target_node_id": "func3",
                "edge_type": "calls",
                "commit_sha": "abc123",
                "line_number": 20,
                "is_direct": True,
                "relationship_metadata": None,
            },
        ]

        with patch.object(manager, "_fetch_nodes_from_db", return_value=[]):
            with patch.object(manager, "_fetch_edges_from_db", return_value=mock_edges):
                with patch.object(
                    manager.validator, "_get_current_commit_sha", return_value="abc123"
                ):
                    with patch.object(
                        manager.validator, "update_cache_state"
                    ) as mock_update:
                        manager._rebuild_graph()

                        # Verify graph was created
                        assert manager._graph is not None
                        assert manager._graph.number_of_nodes() == 3
                        assert manager._graph.number_of_edges() == 2

                        # Verify edges exist
                        assert manager._graph.has_edge("func1", "func2")
                        assert manager._graph.has_edge("func2", "func3")

                        # Verify cache state was updated
                        assert mock_update.called

    def test_rebuild_with_empty_database(self, manager):
        """Test rebuild with no edges in database."""
        with patch.object(manager, "_fetch_nodes_from_db", return_value=[]):
            with patch.object(manager, "_fetch_edges_from_db", return_value=[]):
                with patch.object(
                    manager.validator, "_get_current_commit_sha", return_value="abc123"
                ):
                    with patch.object(manager.validator, "update_cache_state"):
                        manager._rebuild_graph()

                        # Should create empty graph
                        assert manager._graph is not None
                        assert manager._graph.number_of_nodes() == 0
                        assert manager._graph.number_of_edges() == 0


class TestEdgeChangeTracking:
    """Test edge change tracking."""

    def test_on_edges_changed_increments_counter(self, manager):
        """Test that edge changes are tracked."""
        with patch.object(
            manager.validator, "increment_edge_changes"
        ) as mock_increment:
            manager.on_edges_changed(5)
            mock_increment.assert_called_once_with(5)

    def test_multiple_edge_changes_accumulate(self, manager):
        """Test that multiple edge changes accumulate."""
        with patch.object(
            manager.validator, "increment_edge_changes"
        ) as mock_increment:
            manager.on_edges_changed(3)
            manager.on_edges_changed(7)
            manager.on_edges_changed(2)

            # Verify all calls were made
            assert mock_increment.call_count == 3


class TestCacheInvalidation:
    """Test cache invalidation."""

    def test_invalidate_cache_clears_graph(self, manager):
        """Test that invalidate_cache clears the in-memory graph."""
        # Set up cached graph
        manager._graph = nx.DiGraph()
        manager._graph.add_edge("node1", "node2")
        manager._last_rebuild = datetime.now()

        # Invalidate
        manager.invalidate_cache()

        # Verify cleared
        assert manager._graph is None
        assert manager._last_rebuild is None


class TestCacheStats:
    """Test cache statistics."""

    def test_get_cache_stats_with_loaded_graph(self, manager):
        """Test cache stats when graph is loaded."""
        # Set up cached graph
        manager._graph = nx.DiGraph()
        manager._graph.add_edge("node1", "node2")
        manager._last_rebuild = datetime.now()

        mock_cache_state = {
            "commit_sha": "abc123",
            "last_rebuild_at": datetime.now().isoformat(),
            "node_count": 2,
            "edge_count": 1,
            "edge_changes_since_rebuild": 0,
        }

        with patch.object(
            manager.validator, "_get_cache_state", return_value=mock_cache_state
        ):
            with patch.object(manager.validator, "is_cache_valid", return_value=True):
                stats = manager.get_cache_stats()

                assert stats["repo_id"] == 1
                assert stats["is_loaded"] is True
                assert stats["is_valid"] is True
                assert stats["node_count"] == 2
                assert stats["edge_count"] == 1

    def test_get_cache_stats_without_graph(self, manager):
        """Test cache stats when graph is not loaded."""
        with patch.object(manager.validator, "_get_cache_state", return_value=None):
            stats = manager.get_cache_stats()

            assert stats["repo_id"] == 1
            assert stats["is_loaded"] is False
            assert stats["is_valid"] is False
            assert stats["node_count"] == 0
            assert stats["edge_count"] == 0


class TestMetricsComputation:
    """Test graph metrics computation."""

    def test_compute_metrics_on_simple_graph(self, manager):
        """Test metrics computation on a simple graph."""
        # Create a simple graph
        manager._graph = nx.DiGraph()
        manager._graph.add_edge("A", "B")
        manager._graph.add_edge("B", "C")
        manager._graph.add_edge("A", "C")

        metrics = manager.compute_metrics()

        # Verify PageRank was computed
        assert "pagerank" in metrics
        assert len(metrics["pagerank"]) == 3
        assert all(0 <= v <= 1 for v in metrics["pagerank"].values())

        # Verify degree metrics
        assert "in_degree" in metrics
        assert "out_degree" in metrics
        assert metrics["out_degree"]["A"] == 2
        assert metrics["in_degree"]["C"] == 2

    def test_compute_metrics_on_empty_graph(self, manager):
        """Test metrics computation on empty graph."""
        manager._graph = nx.DiGraph()

        metrics = manager.compute_metrics()

        # Should return empty dict
        assert metrics == {}

    def test_compute_metrics_with_community_detection(self, manager):
        """Test community detection if python-louvain available."""
        # Create a graph with clear communities
        manager._graph = nx.DiGraph()

        # Community 1
        manager._graph.add_edge("A1", "A2")
        manager._graph.add_edge("A2", "A3")

        # Community 2
        manager._graph.add_edge("B1", "B2")
        manager._graph.add_edge("B2", "B3")

        # Sparse connection between communities
        manager._graph.add_edge("A3", "B1")

        try:
            import importlib.util

            if importlib.util.find_spec("community") is not None:
                metrics = manager.compute_metrics()

                # Verify community detection ran
                assert "community" in metrics
                assert len(metrics["community"]) > 0
            else:
                # Skip if python-louvain not available
                pytest.skip("python-louvain not installed")
        except ImportError:
            # Skip if python-louvain not available
            pytest.skip("python-louvain not installed")


class TestMetricsStorage:
    """Test storing metrics in database."""

    def test_store_metrics_creates_records(self, manager):
        """Test that store_metrics creates database records."""
        mock_metrics = {
            "pagerank": {"node1": 0.5, "node2": 0.3, "node3": 0.2},
            "betweenness_centrality": {"node1": 0.6, "node2": 0.3, "node3": 0.1},
            "in_degree": {"node1": 2, "node2": 1, "node3": 0},
            "out_degree": {"node1": 0, "node2": 1, "node3": 2},
            "community": {"node1": 0, "node2": 0, "node3": 1},
        }

        with patch("kb.graph_intelligence.graph_manager.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # No existing metrics
            mock_session_inst.exec.return_value.first.return_value = None

            manager.store_metrics(mock_metrics)

            # Verify records were added
            assert mock_session_inst.add.call_count == 3  # 3 nodes

    def test_store_metrics_updates_existing(self, manager):
        """Test that store_metrics updates existing records."""
        mock_metrics = {
            "pagerank": {"node1": 0.7},
            "in_degree": {"node1": 5},
            "out_degree": {"node1": 3},
        }

        with patch("kb.graph_intelligence.graph_manager.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # Mock existing metrics
            existing = Mock()
            existing.pagerank = 0.5
            existing.in_degree = 3
            existing.out_degree = 2
            mock_session_inst.exec.return_value.first.return_value = existing

            manager.store_metrics(mock_metrics)

            # Verify existing was updated
            assert existing.pagerank == 0.7
            assert existing.in_degree == 5
            assert existing.out_degree == 3


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_full_workflow(self, manager):
        """Test complete workflow: load -> compute metrics -> store."""
        # Mock database edges
        mock_edges = [
            {
                "source_node_id": "func1",
                "target_node_id": "func2",
                "edge_type": "calls",
                "commit_sha": "abc123",
                "line_number": 10,
                "is_direct": True,
                "relationship_metadata": None,
            },
        ]

        with patch.object(manager, "_fetch_nodes_from_db", return_value=[]):
            with patch.object(manager, "_fetch_edges_from_db", return_value=mock_edges):
                with patch.object(
                    manager.validator, "_get_current_commit_sha", return_value="abc123"
                ):
                    with patch.object(manager.validator, "update_cache_state"):
                        with patch(
                            "kb.graph_intelligence.graph_manager.Session"
                        ) as mock_session:
                            mock_session_inst = MagicMock()
                            mock_session.return_value.__enter__.return_value = (
                                mock_session_inst
                            )
                            mock_session_inst.exec.return_value.first.return_value = (
                                None
                            )

                            # Get graph (triggers rebuild)
                            graph = manager.get_graph()
                            assert graph.number_of_nodes() == 2

                            # Compute metrics
                            metrics = manager.compute_metrics()
                            assert "pagerank" in metrics

                            # Store metrics
                            manager.store_metrics(metrics)
                            assert mock_session_inst.add.called
