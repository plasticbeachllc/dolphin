"""Unit tests for graph context enrichment."""

import unittest
from unittest.mock import MagicMock, patch

from kb.retrieval.graph_context import GraphContextEnricher, format_graph_context_for_llm
from kb.store.graph_store import GraphStore
from kb.store.sqlite_meta import SQLiteMetadataStore


class TestGraphContextEnricher(unittest.TestCase):
    def setUp(self):
        self.graph_store = MagicMock(spec=GraphStore)
        self.sql_store = MagicMock(spec=SQLiteMetadataStore)
        self.enricher = GraphContextEnricher(
            graph_store=self.graph_store,
            sql_store=self.sql_store,
            max_related_nodes=5,
            max_edges_per_node=2,
        )

    def test_enrich_search_results_basic(self):
        """Test basic enrichment of search results."""
        # Setup mocks
        self.sql_store.get_repo_by_name.return_value = {"id": 1, "root_path": "/tmp/repo"}
        self.sql_store.get_file_id.return_value = 100

        # Mock nodes overlapping with result
        mock_node = {
            "id": "node-1",
            "node_type": "function",
            "name": "process_data",
            "qualified_name": "module.process_data",
            "signature": "def process_data(data)",
            "start_line": 10,
            "end_line": 20,
        }
        self.graph_store.get_nodes_for_file.return_value = [mock_node]

        # Mock relationships
        self.graph_store.get_outgoing_edges.return_value = []
        self.graph_store.get_incoming_edges.return_value = []

        results = [
            {
                "repo": "test-repo",
                "path": "src/module.py",
                "start_line": 12,
                "end_line": 15,
                "text": "code snippet",
            }
        ]

        enriched = self.enricher.enrich_search_results(results)

        self.assertEqual(len(enriched), 1)
        self.assertIn("graph_context", enriched[0])
        context = enriched[0]["graph_context"]

        self.assertEqual(len(context["nodes"]), 1)
        self.assertEqual(context["nodes"][0]["name"], "process_data")
        self.assertEqual(context["nodes"][0]["type"], "function")

    def test_enrich_search_results_filtering(self):
        """Test filtering nodes by line range."""
        self.sql_store.get_repo_by_name.return_value = {"id": 1}
        self.sql_store.get_file_id.return_value = 100

        # Node completely outside result range
        node_outside = {
            "id": "node-1",
            "start_line": 0,
            "end_line": 5,
            "node_type": "function",
            "name": "setup",
            "qualified_name": "module.setup",
            "signature": "def setup()",
        }
        # Node overlapping result range
        node_inside = {
            "id": "node-2",
            "start_line": 10,
            "end_line": 20,
            "node_type": "function",
            "name": "process",
            "qualified_name": "module.process",
            "signature": "def process()",
        }

        self.graph_store.get_nodes_for_file.return_value = [node_outside, node_inside]
        self.graph_store.get_outgoing_edges.return_value = []
        self.graph_store.get_incoming_edges.return_value = []

        results = [
            {
                "repo": "test-repo",
                "path": "src/module.py",
                "start_line": 12,
                "end_line": 15,
            }
        ]

        enriched = self.enricher.enrich_search_results(results)
        context = enriched[0]["graph_context"]

        self.assertEqual(len(context["nodes"]), 1)
        self.assertEqual(context["nodes"][0]["name"], "process")

    def test_enrich_relationships(self):
        """Test inclusion of relationships."""
        self.sql_store.get_repo_by_name.return_value = {"id": 1}
        self.sql_store.get_file_id.return_value = 100

        mock_node = {
            "id": "node-1",
            "start_line": 10,
            "end_line": 20,
            "node_type": "function",
            "name": "process",
            "qualified_name": "module.process",
            "signature": "def process()",
        }
        self.graph_store.get_nodes_for_file.return_value = [mock_node]

        # Outgoing edge (calls)
        outgoing_edge = {
            "edge_type": "calls",
            "target_node_id": "node-2",
            "line_number": 15,
        }
        self.graph_store.get_outgoing_edges.return_value = [outgoing_edge]

        # Target node details
        target_node = {
            "name": "helper",
            "qualified_name": "utils.helper",
            "node_type": "function",
            "signature": "def helper()",
        }
        self.graph_store.get_node_by_id.side_effect = lambda nid: target_node if nid == "node-2" else None

        results = [{"repo": "r", "path": "p", "start_line": 10, "end_line": 20}]
        enriched = self.enricher.enrich_search_results(results)

        rels = enriched[0]["graph_context"]["relationships"]
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["type"], "calls")
        self.assertEqual(rels[0]["direction"], "outgoing")
        self.assertEqual(rels[0]["target"]["name"], "helper")

    def test_deduplicate_relationships(self):
        """Test that duplicate relationships are removed."""
        # Setup minimal mocks to reach _deduplicate_relationships
        rels = [
            {
                "type": "calls",
                "direction": "outgoing",
                "target": {"qualified_name": "foo"},
                "line_number": 10
            },
            {
                "type": "calls",
                "direction": "outgoing",
                "target": {"qualified_name": "foo"},
                "line_number": 10
            },
            {
                "type": "calls",
                "direction": "outgoing",
                "target": {"qualified_name": "bar"},
                "line_number": 12
            }
        ]

        deduped = self.enricher._deduplicate_relationships(rels)
        self.assertEqual(len(deduped), 2)
        targets = sorted([r["target"]["qualified_name"] for r in deduped])
        self.assertEqual(targets, ["bar", "foo"])

    def test_format_graph_context_for_llm(self):
        """Test formatting of graph context into string."""
        context = {
            "nodes": [
                {
                    "type": "function",
                    "qualified_name": "module.process",
                    "signature": "def process()",
                    "line_range": [10, 20]
                }
            ],
            "relationships": [
                {
                    "type": "calls",
                    "direction": "outgoing",
                    "target": {"qualified_name": "utils.helper"},
                    "line_number": 15
                }
            ]
        }

        formatted = format_graph_context_for_llm(context)

        self.assertIn("## Code Graph Context", formatted)
        self.assertIn("- **function** `module.process`", formatted)
        self.assertIn("### Calls:", formatted)
        self.assertIn("- → `utils.helper` (line 15)", formatted)
