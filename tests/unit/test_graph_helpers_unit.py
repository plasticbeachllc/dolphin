"""Unit tests for graph extraction helpers."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from kb.chunkers.graph_types import GraphEdge, GraphNode
from kb.ingest.graph_helpers import (cleanup_graph_for_file,
                                     cleanup_graph_for_repo,
                                     extract_graph_from_file, store_graph_data)


class TestExtractGraphFromFile:
    """Test graph extraction from individual files."""

    @patch("kb.ingest.graph_helpers.py_chunker")
    def test_extract_graph_from_python_file(self, mock_py_chunker):
        """Test graph extraction from Python file."""
        # Setup mock chunker
        mock_py_chunker.extract_graph_data.return_value = (
            [
                GraphNode(
                    node_type="function",
                    name="test_func",
                    qualified_name="module.test_func",
                    start_line=1,
                    end_line=10,
                )
            ],
            [
                GraphEdge(
                    source_name="module.test_func",
                    target_name="module.TestClass",
                    edge_type="member_of",
                    line_number=2,
                )
            ],
        )

        # Execute
        nodes, edges = extract_graph_from_file(
            Path("/repo/test.py"), "python", "def test_func():\n    pass"
        )

        # Verify
        assert len(nodes) == 1
        assert nodes[0].name == "test_func"
        assert nodes[0].node_type == "function"
        assert len(edges) == 1
        assert edges[0].source_name == "module.test_func"
        assert edges[0].target_name == "module.TestClass"

        mock_py_chunker.extract_graph_data.assert_called_once_with(
            "def test_func():\n    pass"
        )

    @patch("kb.ingest.graph_helpers.ts_chunker")
    def test_extract_graph_from_typescript_file(self, mock_ts_chunker):
        """Test graph extraction from TypeScript file."""
        mock_ts_chunker.extract_graph_data.return_value = (
            [
                GraphNode(
                    node_type="class",
                    name="TestClass",
                    qualified_name="TestClass",
                    start_line=1,
                    end_line=20,
                )
            ],
            [],
        )

        nodes, edges = extract_graph_from_file(
            Path("/repo/test.ts"), "typescript", "class TestClass { }"
        )

        assert len(nodes) == 1
        assert nodes[0].name == "TestClass"
        assert nodes[0].node_type == "class"
        assert len(edges) == 0

    @patch("kb.ingest.graph_helpers.ts_chunker")
    def test_extract_graph_from_javascript_file(self, mock_ts_chunker):
        """Test graph extraction from JavaScript file uses TypeScript chunker."""
        mock_ts_chunker.extract_graph_data.return_value = ([], [])

        nodes, edges = extract_graph_from_file(
            Path("/repo/app.js"), "javascript", "function app() {}"
        )

        assert nodes == []
        assert edges == []
        mock_ts_chunker.extract_graph_data.assert_called_once()

    @patch("kb.ingest.graph_helpers.ts_chunker")
    def test_extract_graph_from_jsx_file(self, mock_ts_chunker):
        """Test graph extraction from JSX file uses TypeScript chunker."""
        mock_ts_chunker.extract_graph_data.return_value = ([], [])

        nodes, edges = extract_graph_from_file(
            Path("/repo/Component.jsx"),
            "javascriptreact",
            "export const Component = () => <div />",
        )

        assert nodes == []
        assert edges == []
        mock_ts_chunker.extract_graph_data.assert_called_once()

    @patch("kb.ingest.graph_helpers.sql_chunker")
    def test_extract_graph_from_sql_file(self, mock_sql_chunker):
        """Test graph extraction from SQL file."""
        mock_sql_chunker.extract_graph_data.return_value = (
            [
                GraphNode(
                    node_type="table",
                    name="users",
                    qualified_name="public.users",
                    start_line=1,
                    end_line=5,
                )
            ],
            [],
        )

        nodes, edges = extract_graph_from_file(
            Path("/repo/schema.sql"), "sql", "CREATE TABLE users (id INT);"
        )

        assert len(nodes) == 1
        assert nodes[0].name == "users"
        assert nodes[0].node_type == "table"

    @patch("kb.ingest.graph_helpers.svelte_chunker")
    def test_extract_graph_from_svelte_file(self, mock_svelte_chunker):
        """Test graph extraction from Svelte file."""
        mock_svelte_chunker.extract_graph_data.return_value = ([], [])

        nodes, edges = extract_graph_from_file(
            Path("/repo/App.svelte"), "svelte", "<script>let count = 0;</script>"
        )

        assert nodes == []
        assert edges == []
        mock_svelte_chunker.extract_graph_data.assert_called_once()

    def test_extract_graph_from_unsupported_language(self):
        """Test graph extraction from unsupported language returns empty."""
        nodes, edges = extract_graph_from_file(
            Path("/repo/file.txt"), "text", "plain text content"
        )

        assert nodes == []
        assert edges == []

    def test_extract_graph_from_markdown_file(self):
        """Test that markdown files don't support graph extraction."""
        nodes, edges = extract_graph_from_file(
            Path("/repo/README.md"), "markdown", "# Title\n\nContent"
        )

        assert nodes == []
        assert edges == []

    @patch("kb.ingest.graph_helpers.py_chunker")
    def test_extract_graph_handles_chunker_errors(self, mock_py_chunker, capsys):
        """Test that extraction errors are handled gracefully."""
        mock_py_chunker.extract_graph_data.side_effect = Exception("Parse error")

        nodes, edges = extract_graph_from_file(
            Path("/repo/broken.py"), "python", "invalid syntax {"
        )

        # Should return empty rather than crash
        assert nodes == []
        assert edges == []

        # Should log warning
        captured = capsys.readouterr()
        assert "Warning: Graph extraction failed" in captured.out
        assert "broken.py" in captured.out

    @patch("kb.ingest.graph_helpers.py_chunker")
    def test_extract_graph_handles_missing_extract_function(self, mock_py_chunker):
        """Test handling when chunker doesn't have extract_graph_data."""
        # Remove the extract_graph_data attribute
        del mock_py_chunker.extract_graph_data

        nodes, edges = extract_graph_from_file(
            Path("/repo/test.py"), "python", "def test(): pass"
        )

        # Should return empty when function doesn't exist
        assert nodes == []
        assert edges == []

    def test_extract_graph_with_empty_language(self):
        """Test extraction with empty language string."""
        nodes, edges = extract_graph_from_file(Path("/repo/file"), "", "content")

        assert nodes == []
        assert edges == []

    def test_extract_graph_with_none_language(self):
        """Test extraction with None language."""
        nodes, edges = extract_graph_from_file(Path("/repo/file"), None, "content")

        assert nodes == []
        assert edges == []

    @patch("kb.ingest.graph_helpers.py_chunker")
    def test_extract_graph_case_insensitive_language(self, mock_py_chunker):
        """Test that language matching is case-insensitive."""
        mock_py_chunker.extract_graph_data.return_value = ([], [])

        # Test with uppercase
        nodes, edges = extract_graph_from_file(
            Path("/repo/test.py"), "PYTHON", "def test(): pass"
        )

        assert mock_py_chunker.extract_graph_data.called
        assert nodes == []
        assert edges == []

    @patch("kb.ingest.graph_helpers.py_chunker")
    def test_extract_graph_with_repo_config(self, mock_py_chunker):
        """Test that repo_config parameter is accepted (for future use)."""
        mock_py_chunker.extract_graph_data.return_value = ([], [])

        # Repo config is accepted but not currently used
        repo_config = {"some_option": True}
        nodes, edges = extract_graph_from_file(
            Path("/repo/test.py"), "python", "def test(): pass", repo_config=repo_config
        )

        assert nodes == []
        assert edges == []


class TestStoreGraphData:
    """Test storing graph data in the graph store."""

    def test_store_nodes_and_edges(self):
        """Test storing nodes and edges."""
        mock_store = Mock()
        mock_store.upsert_node.side_effect = ["node1-id", "node2-id"]

        nodes = [
            GraphNode(
                node_type="function",
                name="func1",
                qualified_name="module.func1",
                start_line=1,
                end_line=10,
            ),
            GraphNode(
                node_type="class",
                name="Class1",
                qualified_name="module.Class1",
                start_line=11,
                end_line=20,
            ),
        ]
        edges = [
            GraphEdge(
                source_name="module.func1",
                target_name="module.Class1",
                edge_type="member_of",
                line_number=2,
            )
        ]

        stats = store_graph_data(
            mock_store,
            nodes,
            edges,
            repo_id=1,
            file_id=100,
            language="python",
            commit_sha="abc123",
            branch="main",
        )

        # Verify nodes were stored
        assert mock_store.upsert_node.call_count == 2

        # Check first node call
        call1 = mock_store.upsert_node.call_args_list[0]
        assert call1[1]["node_type"] == "function"
        assert call1[1]["name"] == "func1"
        assert call1[1]["qualified_name"] == "module.func1"
        assert call1[1]["repo_id"] == 1
        assert call1[1]["file_id"] == 100
        assert call1[1]["language"] == "python"
        assert call1[1]["commit_sha"] == "abc123"
        assert call1[1]["branch"] == "main"

        # Verify edges were stored
        assert mock_store.upsert_edge.call_count == 1
        edge_call = mock_store.upsert_edge.call_args[1]
        assert edge_call["source_node_id"] == "node1-id"
        assert edge_call["target_node_id"] == "node2-id"
        assert edge_call["edge_type"] == "member_of"
        assert edge_call["line_number"] == 2
        assert edge_call["commit_sha"] == "abc123"

        # Verify stats
        assert stats["nodes_created"] == 2
        assert stats["edges_created"] == 1

    def test_store_empty_graph(self):
        """Test storing empty graph doesn't crash."""
        mock_store = Mock()

        stats = store_graph_data(
            mock_store,
            [],
            [],
            repo_id=1,
            file_id=100,
            language="python",
            commit_sha="abc123",
            branch="main",
        )

        # Should not call store methods
        assert mock_store.upsert_node.call_count == 0
        assert mock_store.upsert_edge.call_count == 0

        assert stats["nodes_created"] == 0
        assert stats["edges_created"] == 0

    def test_store_nodes_only_no_edges(self):
        """Test storing nodes without edges."""
        mock_store = Mock()
        mock_store.upsert_node.return_value = "node1-id"

        nodes = [
            GraphNode(
                node_type="function",
                name="func1",
                qualified_name="module.func1",
                start_line=1,
                end_line=10,
            )
        ]

        stats = store_graph_data(
            mock_store,
            nodes,
            [],
            repo_id=1,
            file_id=100,
            language="python",
            commit_sha="abc123",
            branch="main",
        )

        assert mock_store.upsert_node.call_count == 1
        assert mock_store.upsert_edge.call_count == 0
        assert stats["nodes_created"] == 1
        assert stats["edges_created"] == 0

    def test_store_handles_node_creation_error(self, capsys):
        """Test that node creation errors are handled gracefully."""
        mock_store = Mock()
        mock_store.upsert_node.side_effect = Exception("Database error")

        nodes = [
            GraphNode(
                node_type="function",
                name="func",
                qualified_name="module.func",
                start_line=1,
                end_line=10,
            )
        ]

        stats = store_graph_data(
            mock_store,
            nodes,
            [],
            repo_id=1,
            file_id=100,
            language="python",
            commit_sha="abc123",
            branch="main",
        )

        # Should log warning but not crash
        captured = capsys.readouterr()
        assert "Warning: Failed to store node" in captured.out
        assert "module.func" in captured.out

        # No nodes should be created
        assert stats["nodes_created"] == 0

    def test_store_edge_resolves_existing_nodes(self):
        """Test that edges can reference existing nodes from store."""
        mock_store = Mock()

        # First node doesn't exist in map (target node)
        mock_store.find_node_by_qualified_name.return_value = {"id": "existing-node-id"}
        mock_store.upsert_node.return_value = "new-node-id"

        nodes = [
            GraphNode(
                node_type="function",
                name="func1",
                qualified_name="module.func1",
                start_line=1,
                end_line=10,
            )
        ]

        edges = [
            GraphEdge(
                source_name="module.func1",
                target_name="external.Class",  # External reference
                edge_type="uses",
                line_number=5,
            )
        ]

        stats = store_graph_data(
            mock_store,
            nodes,
            edges,
            repo_id=1,
            file_id=100,
            language="python",
            commit_sha="abc123",
            branch="main",
        )

        # Should have looked up the target node
        assert mock_store.find_node_by_qualified_name.called

        # Should have created edge with resolved IDs
        assert mock_store.upsert_edge.call_count == 1
        edge_call = mock_store.upsert_edge.call_args[1]
        assert edge_call["source_node_id"] == "new-node-id"
        assert edge_call["target_node_id"] == "existing-node-id"

    def test_store_skips_edge_when_source_not_found(self, capsys):
        """Test that edges are skipped when source node can't be resolved."""
        mock_store = Mock()
        mock_store.find_node_by_qualified_name.return_value = None

        edges = [
            GraphEdge(
                source_name="unknown.source",
                target_name="unknown.target",
                edge_type="uses",
                line_number=1,
            )
        ]

        stats = store_graph_data(
            mock_store,
            [],
            edges,
            repo_id=1,
            file_id=100,
            language="python",
            commit_sha="abc123",
            branch="main",
        )

        # Should not create edge
        assert mock_store.upsert_edge.call_count == 0
        assert stats["edges_created"] == 0

    def test_store_handles_edge_creation_error(self, capsys):
        """Test that edge creation errors are handled gracefully."""
        mock_store = Mock()
        mock_store.upsert_node.side_effect = ["node1-id", "node2-id"]
        mock_store.upsert_edge.side_effect = Exception("Edge constraint violation")

        nodes = [
            GraphNode(
                node_type="function",
                name="func1",
                qualified_name="module.func1",
                start_line=1,
                end_line=10,
            ),
            GraphNode(
                node_type="class",
                name="Class1",
                qualified_name="module.Class1",
                start_line=11,
                end_line=20,
            ),
        ]

        edges = [
            GraphEdge(
                source_name="module.func1",
                target_name="module.Class1",
                edge_type="member_of",
                line_number=2,
            )
        ]

        stats = store_graph_data(
            mock_store,
            nodes,
            edges,
            repo_id=1,
            file_id=100,
            language="python",
            commit_sha="abc123",
            branch="main",
        )

        # Nodes should be created
        assert stats["nodes_created"] == 2

        # Edge should fail but not crash
        captured = capsys.readouterr()
        assert "Warning: Failed to store edge" in captured.out
        assert stats["edges_created"] == 0

    def test_store_multiple_edges_between_same_nodes(self):
        """Test storing multiple edges between the same node pair."""
        mock_store = Mock()
        mock_store.upsert_node.side_effect = ["node1-id", "node2-id"]

        nodes = [
            GraphNode(
                node_type="function",
                name="func1",
                qualified_name="module.func1",
                start_line=1,
                end_line=10,
            ),
            GraphNode(
                node_type="class",
                name="Class1",
                qualified_name="module.Class1",
                start_line=11,
                end_line=20,
            ),
        ]

        edges = [
            GraphEdge(
                source_name="module.func1",
                target_name="module.Class1",
                edge_type="member_of",
                line_number=2,
            ),
            GraphEdge(
                source_name="module.func1",
                target_name="module.Class1",
                edge_type="calls",
                line_number=5,
            ),
        ]

        stats = store_graph_data(
            mock_store,
            nodes,
            edges,
            repo_id=1,
            file_id=100,
            language="python",
            commit_sha="abc123",
            branch="main",
        )

        # Both edges should be created
        assert mock_store.upsert_edge.call_count == 2
        assert stats["edges_created"] == 2


class TestCleanupGraphForFile:
    """Test cleaning up graph data for a file."""

    def test_cleanup_removes_all_file_data(self):
        """Test that cleanup removes all nodes/edges for a file."""
        mock_store = Mock()
        mock_store.delete_nodes_for_file.return_value = 5

        deleted_count = cleanup_graph_for_file(mock_store, file_id=100)

        # Verify cleanup method called
        mock_store.delete_nodes_for_file.assert_called_once_with(100)
        assert deleted_count == 5

    def test_cleanup_with_no_data(self):
        """Test cleanup when file has no graph data."""
        mock_store = Mock()
        mock_store.delete_nodes_for_file.return_value = 0

        deleted_count = cleanup_graph_for_file(mock_store, file_id=100)

        assert deleted_count == 0

    def test_cleanup_handles_errors_gracefully(self, capsys):
        """Test that cleanup errors are handled gracefully."""
        mock_store = Mock()
        mock_store.delete_nodes_for_file.side_effect = Exception("Database error")

        deleted_count = cleanup_graph_for_file(mock_store, file_id=100)

        # Should log warning but not crash
        captured = capsys.readouterr()
        assert "Warning: Failed to clean up graph data" in captured.out
        assert "file 100" in captured.out

        # Should return 0 on error
        assert deleted_count == 0


class TestCleanupGraphForRepo:
    """Test cleaning up entire repository graph."""

    def test_cleanup_removes_all_repo_data(self):
        """Test that cleanup removes all nodes/edges for a repo."""
        mock_store = Mock()
        mock_store.delete_nodes_for_repo.return_value = 150

        deleted_count = cleanup_graph_for_repo(mock_store, repo_id=1)

        mock_store.delete_nodes_for_repo.assert_called_once_with(1)
        assert deleted_count == 150

    def test_cleanup_with_no_data(self):
        """Test cleanup when repo has no graph data."""
        mock_store = Mock()
        mock_store.delete_nodes_for_repo.return_value = 0

        deleted_count = cleanup_graph_for_repo(mock_store, repo_id=1)

        assert deleted_count == 0

    def test_cleanup_handles_errors_gracefully(self, capsys):
        """Test that cleanup errors are handled gracefully."""
        mock_store = Mock()
        mock_store.delete_nodes_for_repo.side_effect = Exception("Constraint violation")

        deleted_count = cleanup_graph_for_repo(mock_store, repo_id=1)

        # Should log warning but not crash
        captured = capsys.readouterr()
        assert "Warning: Failed to clean up graph data" in captured.out
        assert "repo 1" in captured.out

        # Should return 0 on error
        assert deleted_count == 0

    def test_cleanup_multiple_repos(self):
        """Test cleanup can be called for multiple repos."""
        mock_store = Mock()
        mock_store.delete_nodes_for_repo.side_effect = [100, 50, 200]

        count1 = cleanup_graph_for_repo(mock_store, repo_id=1)
        count2 = cleanup_graph_for_repo(mock_store, repo_id=2)
        count3 = cleanup_graph_for_repo(mock_store, repo_id=3)

        assert count1 == 100
        assert count2 == 50
        assert count3 == 200
        assert mock_store.delete_nodes_for_repo.call_count == 3
