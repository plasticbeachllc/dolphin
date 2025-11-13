"""Unit tests for graph context enrichment."""

from unittest.mock import MagicMock, Mock

import pytest

from kb.retrieval.graph_context import (
    GraphContextEnricher,
    format_graph_context_for_llm,
)


class TestGraphContextEnricher:
    """Test graph context enrichment logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_graph_store = Mock()
        self.mock_sql_store = Mock()
        self.enricher = GraphContextEnricher(
            self.mock_graph_store,
            self.mock_sql_store,
            max_related_nodes=10,
            max_edges_per_node=5,
        )

    def test_initialization(self):
        """Test enricher initialization."""
        assert self.enricher.graph_store == self.mock_graph_store
        assert self.enricher.sql_store == self.mock_sql_store
        assert self.enricher.max_related_nodes == 10
        assert self.enricher.max_edges_per_node == 5

    def test_initialization_with_custom_limits(self):
        """Test initialization with custom limits."""
        enricher = GraphContextEnricher(
            self.mock_graph_store,
            self.mock_sql_store,
            max_related_nodes=20,
            max_edges_per_node=10,
        )

        assert enricher.max_related_nodes == 20
        assert enricher.max_edges_per_node == 10

    def test_enrich_with_no_graph_data(self):
        """Test enrichment when no graph data exists."""
        # Setup: No repo found
        self.mock_sql_store.get_repo_by_name.return_value = None

        results = [
            {
                "repo": "test-repo",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "content": "def test(): pass",
                "score": 0.9,
            }
        ]

        enriched = self.enricher.enrich_search_results(results)

        # Should return original results without graph_context
        assert len(enriched) == 1
        assert "graph_context" not in enriched[0]
        assert enriched[0]["content"] == results[0]["content"]

    def test_enrich_adds_graph_context(self):
        """Test that graph context is added when available."""
        # Setup: Mock the entire chain
        self.mock_sql_store.get_repo_by_name.return_value = {
            "id": 1,
            "name": "test-repo",
        }
        self.mock_sql_store.get_file_id.return_value = 100

        # Mock overlapping nodes
        self.mock_graph_store.get_nodes_for_file.return_value = [
            {
                "id": "node-1",
                "node_type": "function",
                "name": "test_func",
                "qualified_name": "module.test_func",
                "signature": "def test_func()",
                "start_line": 1,
                "end_line": 10,
            }
        ]

        # Mock edges (empty for simplicity)
        self.mock_graph_store.get_outgoing_edges.return_value = []
        self.mock_graph_store.get_incoming_edges.return_value = []

        results = [
            {
                "repo": "test-repo",
                "path": "src/test.py",
                "start_line": 1,
                "end_line": 10,
                "content": "def test_func(): pass",
                "score": 0.9,
            }
        ]

        enriched = self.enricher.enrich_search_results(results)

        # Should have graph_context
        assert len(enriched) == 1
        assert "graph_context" in enriched[0]

        context = enriched[0]["graph_context"]
        assert "nodes" in context
        assert len(context["nodes"]) == 1
        assert context["nodes"][0]["name"] == "test_func"

    def test_enrich_respects_max_related_nodes_limit(self):
        """Test that max_related_nodes limit is respected."""
        enricher = GraphContextEnricher(
            self.mock_graph_store,
            self.mock_sql_store,
            max_related_nodes=2,
            max_edges_per_node=5,
        )

        # Setup
        self.mock_sql_store.get_repo_by_name.return_value = {"id": 1}
        self.mock_sql_store.get_file_id.return_value = 100

        # Return 5 nodes
        self.mock_graph_store.get_nodes_for_file.return_value = [
            {
                "id": f"node-{i}",
                "node_type": "function",
                "name": f"func{i}",
                "qualified_name": f"module.func{i}",
                "signature": f"def func{i}()",
                "start_line": i * 10,
                "end_line": i * 10 + 9,
            }
            for i in range(5)
        ]

        self.mock_graph_store.get_outgoing_edges.return_value = []
        self.mock_graph_store.get_incoming_edges.return_value = []

        results = [
            {
                "repo": "test-repo",
                "path": "test.py",
                "start_line": 1,
                "end_line": 50,
                "score": 0.9,
            }
        ]

        enriched = enricher.enrich_search_results(results)

        # Should only include 2 nodes (the limit)
        context = enriched[0]["graph_context"]
        assert len(context["nodes"]) == 2

    def test_enrich_filters_non_overlapping_nodes(self):
        """Test that nodes outside the result's line range are filtered."""
        self.mock_sql_store.get_repo_by_name.return_value = {"id": 1}
        self.mock_sql_store.get_file_id.return_value = 100

        # Return nodes, but only one overlaps with result (lines 10-20)
        self.mock_graph_store.get_nodes_for_file.return_value = [
            {
                "id": "node-1",
                "node_type": "function",
                "name": "func1",
                "qualified_name": "module.func1",
                "signature": "def func1()",
                "start_line": 1,
                "end_line": 5,  # Does NOT overlap with 10-20
            },
            {
                "id": "node-2",
                "node_type": "function",
                "name": "func2",
                "qualified_name": "module.func2",
                "signature": "def func2()",
                "start_line": 15,
                "end_line": 25,  # OVERLAPS with 10-20
            },
        ]

        self.mock_graph_store.get_outgoing_edges.return_value = []
        self.mock_graph_store.get_incoming_edges.return_value = []

        results = [
            {
                "repo": "test-repo",
                "path": "test.py",
                "start_line": 10,
                "end_line": 20,
                "score": 0.9,
            }
        ]

        enriched = self.enricher.enrich_search_results(results)

        # Should only include func2 (the overlapping node)
        context = enriched[0]["graph_context"]
        assert len(context["nodes"]) == 1
        assert context["nodes"][0]["name"] == "func2"

    def test_enrich_handles_missing_result_fields(self):
        """Test handling of results with missing required fields."""
        results = [
            {"repo": "test-repo", "path": "test.py"},  # Missing line numbers
            {"repo": "test-repo", "start_line": 1, "end_line": 10},  # Missing path
            {"path": "test.py", "start_line": 1, "end_line": 10},  # Missing repo
            {},  # Missing everything
        ]

        enriched = self.enricher.enrich_search_results(results)

        # None should have graph_context
        assert all("graph_context" not in result for result in enriched)

    def test_enrich_includes_outgoing_call_relationships(self):
        """Test that outgoing call relationships are included."""
        self.mock_sql_store.get_repo_by_name.return_value = {"id": 1}
        self.mock_sql_store.get_file_id.return_value = 100

        self.mock_graph_store.get_nodes_for_file.return_value = [
            {
                "id": "node-1",
                "node_type": "function",
                "name": "caller",
                "qualified_name": "module.caller",
                "signature": "def caller()",
                "start_line": 1,
                "end_line": 10,
            }
        ]

        # Mock outgoing call edge
        self.mock_graph_store.get_outgoing_edges.return_value = [
            {"edge_type": "calls", "target_node_id": "node-2", "line_number": 5}
        ]

        # Mock target node
        self.mock_graph_store.get_node_by_id.return_value = {
            "id": "node-2",
            "node_type": "function",
            "name": "callee",
            "qualified_name": "module.callee",
            "signature": "def callee()",
        }

        self.mock_graph_store.get_incoming_edges.return_value = []

        results = [
            {
                "repo": "test-repo",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "score": 0.9,
            }
        ]

        enriched = self.enricher.enrich_search_results(results, include_callsites=True)

        context = enriched[0]["graph_context"]
        assert len(context["relationships"]) >= 1

        # Find the call relationship
        call_rels = [r for r in context["relationships"] if r["type"] == "calls"]
        assert len(call_rels) == 1
        assert call_rels[0]["direction"] == "outgoing"
        assert call_rels[0]["target"]["name"] == "callee"
        assert call_rels[0]["line_number"] == 5

    def test_enrich_includes_incoming_call_relationships(self):
        """Test that incoming call relationships (callsites) are included."""
        self.mock_sql_store.get_repo_by_name.return_value = {"id": 1}
        self.mock_sql_store.get_file_id.return_value = 100

        self.mock_graph_store.get_nodes_for_file.return_value = [
            {
                "id": "node-1",
                "node_type": "function",
                "name": "callee",
                "qualified_name": "module.callee",
                "signature": "def callee()",
                "start_line": 1,
                "end_line": 10,
            }
        ]

        self.mock_graph_store.get_outgoing_edges.return_value = []

        # Mock incoming call edge
        self.mock_graph_store.get_incoming_edges.return_value = [
            {"edge_type": "calls", "source_node_id": "node-2", "line_number": 5}
        ]

        # Mock source node
        self.mock_graph_store.get_node_by_id.return_value = {
            "id": "node-2",
            "node_type": "function",
            "name": "caller",
            "qualified_name": "module.caller",
            "signature": "def caller()",
        }

        results = [
            {
                "repo": "test-repo",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "score": 0.9,
            }
        ]

        enriched = self.enricher.enrich_search_results(results, include_callsites=True)

        context = enriched[0]["graph_context"]

        # Find incoming call relationships
        incoming_calls = [
            r
            for r in context["relationships"]
            if r["type"] == "calls" and r["direction"] == "incoming"
        ]
        assert len(incoming_calls) >= 1
        assert incoming_calls[0]["source"]["name"] == "caller"

    def test_enrich_filters_relationships_by_flags(self):
        """Test that relationship inclusion flags are respected."""
        self.mock_sql_store.get_repo_by_name.return_value = {"id": 1}
        self.mock_sql_store.get_file_id.return_value = 100

        self.mock_graph_store.get_nodes_for_file.return_value = [
            {
                "id": "node-1",
                "node_type": "function",
                "name": "func",
                "qualified_name": "module.func",
                "signature": "def func()",
                "start_line": 1,
                "end_line": 10,
            }
        ]

        # Mock different edge types
        self.mock_graph_store.get_outgoing_edges.return_value = [
            {"edge_type": "calls", "target_node_id": "node-2", "line_number": 5},
            {"edge_type": "imports", "target_node_id": "node-3", "line_number": 1},
        ]

        self.mock_graph_store.get_incoming_edges.return_value = []

        # Mock node lookup
        def mock_get_node(node_id):
            return {
                "id": node_id,
                "node_type": "function",
                "name": f"target_{node_id}",
                "qualified_name": f"module.target_{node_id}",
                "signature": "def target()",
            }

        self.mock_graph_store.get_node_by_id.side_effect = mock_get_node

        results = [
            {
                "repo": "test-repo",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "score": 0.9,
            }
        ]

        # Test with callsites disabled
        enriched = self.enricher.enrich_search_results(
            results, include_callsites=False, include_dependencies=True
        )

        context = enriched[0]["graph_context"]
        # Should not have any incoming calls
        # But the function can call outgoing (not filtered by include_callsites)

        # Test with dependencies disabled
        enriched = self.enricher.enrich_search_results(
            results, include_callsites=True, include_dependencies=False
        )

        context = enriched[0]["graph_context"]
        # Should not have imports/depends_on edges
        import_rels = [r for r in context["relationships"] if r["type"] == "imports"]
        assert len(import_rels) == 0

    def test_enrich_handles_graph_store_errors(self):
        """Test that graph store errors don't crash enrichment."""
        self.mock_sql_store.get_repo_by_name.side_effect = Exception("DB error")

        results = [
            {
                "repo": "test-repo",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "score": 0.9,
            }
        ]

        # Should not crash
        enriched = self.enricher.enrich_search_results(results)
        assert len(enriched) == 1
        assert "graph_context" not in enriched[0]

    def test_enrich_deduplicates_relationships(self):
        """Test that duplicate relationships are removed."""
        self.mock_sql_store.get_repo_by_name.return_value = {"id": 1}
        self.mock_sql_store.get_file_id.return_value = 100

        # Return 2 nodes that both call the same target
        self.mock_graph_store.get_nodes_for_file.return_value = [
            {
                "id": "node-1",
                "node_type": "function",
                "name": "func1",
                "qualified_name": "module.func1",
                "signature": "def func1()",
                "start_line": 1,
                "end_line": 10,
            },
            {
                "id": "node-2",
                "node_type": "function",
                "name": "func2",
                "qualified_name": "module.func2",
                "signature": "def func2()",
                "start_line": 11,
                "end_line": 20,
            },
        ]

        # Both nodes call the same target
        self.mock_graph_store.get_outgoing_edges.return_value = [
            {"edge_type": "calls", "target_node_id": "target", "line_number": 5}
        ]

        self.mock_graph_store.get_incoming_edges.return_value = []

        self.mock_graph_store.get_node_by_id.return_value = {
            "id": "target",
            "node_type": "function",
            "name": "target_func",
            "qualified_name": "module.target_func",
            "signature": "def target_func()",
        }

        results = [
            {
                "repo": "test-repo",
                "path": "test.py",
                "start_line": 1,
                "end_line": 20,
                "score": 0.9,
            }
        ]

        enriched = self.enricher.enrich_search_results(results)

        context = enriched[0]["graph_context"]

        # Count unique relationships
        call_rels = [r for r in context["relationships"] if r["type"] == "calls"]

        # Should deduplicate based on (type, direction, target, line_number)
        # Since both have same line_number and target, should be 1
        assert len(call_rels) == 1

    def test_ranges_overlap(self):
        """Test the line range overlap logic."""
        # Test overlapping ranges
        assert self.enricher._ranges_overlap(1, 10, 5, 15) is True
        assert self.enricher._ranges_overlap(5, 15, 1, 10) is True
        assert self.enricher._ranges_overlap(1, 10, 1, 10) is True  # Exact match
        assert self.enricher._ranges_overlap(1, 10, 10, 20) is True  # Touch at boundary

        # Test non-overlapping ranges
        assert self.enricher._ranges_overlap(1, 10, 11, 20) is False
        assert self.enricher._ranges_overlap(11, 20, 1, 10) is False

        # Test containing ranges
        assert self.enricher._ranges_overlap(1, 20, 5, 10) is True  # Contains
        assert self.enricher._ranges_overlap(5, 10, 1, 20) is True  # Contained

    def test_enrich_multiple_results(self):
        """Test enriching multiple results in one call."""
        self.mock_sql_store.get_repo_by_name.return_value = {"id": 1}
        self.mock_sql_store.get_file_id.side_effect = [100, 101]

        self.mock_graph_store.get_nodes_for_file.side_effect = [
            [  # First result has nodes
                {
                    "id": "node-1",
                    "node_type": "function",
                    "name": "func1",
                    "qualified_name": "module.func1",
                    "signature": "def func1()",
                    "start_line": 1,
                    "end_line": 10,
                }
            ],
            [],  # Second result has no nodes
        ]

        self.mock_graph_store.get_outgoing_edges.return_value = []
        self.mock_graph_store.get_incoming_edges.return_value = []

        results = [
            {
                "repo": "test-repo",
                "path": "file1.py",
                "start_line": 1,
                "end_line": 10,
                "score": 0.9,
            },
            {
                "repo": "test-repo",
                "path": "file2.py",
                "start_line": 1,
                "end_line": 10,
                "score": 0.8,
            },
        ]

        enriched = self.enricher.enrich_search_results(results)

        assert len(enriched) == 2
        assert "graph_context" in enriched[0]  # First has context
        assert "graph_context" not in enriched[1]  # Second doesn't


class TestFormatGraphContextForLLM:
    """Test LLM formatting of graph context."""

    def test_format_empty_context(self):
        """Test formatting empty context."""
        result = format_graph_context_for_llm({})
        assert result == ""

        result = format_graph_context_for_llm({"nodes": [], "relationships": []})
        assert result == ""

    def test_format_nodes_only(self):
        """Test formatting context with only nodes."""
        context = {
            "nodes": [
                {
                    "type": "function",
                    "name": "test_func",
                    "qualified_name": "module.test_func",
                    "signature": "def test_func(x: int) -> str",
                    "line_range": [10, 20],
                }
            ],
            "relationships": [],
        }

        result = format_graph_context_for_llm(context)

        assert "## Code Graph Context" in result
        assert "### Entities in this code:" in result
        assert "**function**" in result
        assert "`module.test_func`" in result
        assert "def test_func(x: int) -> str" in result
        assert "(lines 10-20)" in result

    def test_format_with_outgoing_calls(self):
        """Test formatting context with outgoing calls."""
        context = {
            "nodes": [
                {
                    "type": "function",
                    "name": "caller",
                    "qualified_name": "module.caller",
                    "signature": "def caller()",
                    "line_range": [1, 10],
                }
            ],
            "relationships": [
                {
                    "type": "calls",
                    "direction": "outgoing",
                    "target": {
                        "name": "callee",
                        "qualified_name": "module.callee",
                        "node_type": "function",
                        "signature": "def callee()",
                    },
                    "line_number": 5,
                }
            ],
        }

        result = format_graph_context_for_llm(context)

        assert "### Calls:" in result
        assert "→ `module.callee`" in result
        assert "(line 5)" in result

    def test_format_with_incoming_calls(self):
        """Test formatting context with incoming calls."""
        context = {
            "nodes": [
                {
                    "type": "function",
                    "name": "callee",
                    "qualified_name": "module.callee",
                    "signature": "def callee()",
                    "line_range": [1, 10],
                }
            ],
            "relationships": [
                {
                    "type": "calls",
                    "direction": "incoming",
                    "source": {
                        "name": "caller",
                        "qualified_name": "module.caller",
                        "node_type": "function",
                        "signature": "def caller()",
                    },
                    "line_number": 5,
                }
            ],
        }

        result = format_graph_context_for_llm(context)

        assert "### Called by:" in result
        assert "← `module.caller`" in result
        assert "(line 5)" in result

    def test_format_with_inheritance(self):
        """Test formatting context with inheritance relationships."""
        context = {
            "nodes": [
                {
                    "type": "class",
                    "name": "ChildClass",
                    "qualified_name": "module.ChildClass",
                    "signature": "class ChildClass",
                    "line_range": [10, 50],
                }
            ],
            "relationships": [
                {
                    "type": "inherits",
                    "direction": "outgoing",
                    "target": {
                        "name": "BaseClass",
                        "qualified_name": "module.BaseClass",
                        "node_type": "class",
                        "signature": "class BaseClass",
                    },
                    "line_number": 10,
                }
            ],
        }

        result = format_graph_context_for_llm(context)

        assert "### Inherits from:" in result
        assert "`module.BaseClass`" in result

    def test_format_with_implementations(self):
        """Test formatting context with interface implementations."""
        context = {
            "nodes": [
                {
                    "type": "class",
                    "name": "ConcreteClass",
                    "qualified_name": "module.ConcreteClass",
                    "signature": "class ConcreteClass",
                    "line_range": [10, 50],
                }
            ],
            "relationships": [
                {
                    "type": "implements",
                    "direction": "outgoing",
                    "target": {
                        "name": "IInterface",
                        "qualified_name": "module.IInterface",
                        "node_type": "interface",
                        "signature": "interface IInterface",
                    },
                    "line_number": 10,
                },
                {
                    "type": "implements",
                    "direction": "incoming",
                    "source": {
                        "name": "AnotherImpl",
                        "qualified_name": "module.AnotherImpl",
                        "node_type": "class",
                        "signature": "class AnotherImpl",
                    },
                    "line_number": 50,
                },
            ],
        }

        result = format_graph_context_for_llm(context)

        assert "### Implementations:" in result
        assert "Implements `module.IInterface`" in result
        assert "Implemented by `module.AnotherImpl`" in result

    def test_format_with_dependencies(self):
        """Test formatting context with dependencies/imports."""
        context = {
            "nodes": [
                {
                    "type": "module",
                    "name": "main",
                    "qualified_name": "main",
                    "signature": "",
                    "line_range": [1, 100],
                }
            ],
            "relationships": [
                {
                    "type": "imports",
                    "direction": "outgoing",
                    "target": {
                        "name": "utils",
                        "qualified_name": "utils",
                        "node_type": "module",
                        "signature": "",
                    },
                    "line_number": 1,
                }
            ],
        }

        result = format_graph_context_for_llm(context)

        assert "### Dependencies:" in result
        assert "`utils`" in result

    def test_format_limits_relationship_count(self):
        """Test that formatting limits the number of relationships shown."""
        # Create 10 outgoing calls
        context = {
            "nodes": [
                {
                    "type": "function",
                    "name": "func",
                    "qualified_name": "module.func",
                    "signature": "def func()",
                    "line_range": [1, 100],
                }
            ],
            "relationships": [
                {
                    "type": "calls",
                    "direction": "outgoing",
                    "target": {
                        "name": f"target{i}",
                        "qualified_name": f"module.target{i}",
                        "node_type": "function",
                        "signature": f"def target{i}()",
                    },
                    "line_number": i,
                }
                for i in range(10)
            ],
        }

        result = format_graph_context_for_llm(context)

        # Should limit to 5 calls (top 5)
        assert result.count("→ `module.target") == 5

    def test_format_handles_missing_signature(self):
        """Test formatting when node signature is missing."""
        context = {
            "nodes": [
                {
                    "type": "function",
                    "name": "test_func",
                    "qualified_name": "module.test_func",
                    "signature": None,  # Missing signature
                    "line_range": [10, 20],
                }
            ],
            "relationships": [],
        }

        result = format_graph_context_for_llm(context)

        assert "**function**" in result
        assert "`module.test_func`" in result
        # Should not crash, just omit signature

    def test_format_handles_missing_line_number(self):
        """Test formatting when relationship line number is missing."""
        context = {
            "nodes": [
                {
                    "type": "function",
                    "name": "caller",
                    "qualified_name": "module.caller",
                    "signature": "def caller()",
                    "line_range": [1, 10],
                }
            ],
            "relationships": [
                {
                    "type": "calls",
                    "direction": "outgoing",
                    "target": {
                        "name": "callee",
                        "qualified_name": "module.callee",
                        "node_type": "function",
                        "signature": "def callee()",
                    },
                    # No line_number field
                }
            ],
        }

        result = format_graph_context_for_llm(context)

        # Should not crash, just omit line number
        assert "→ `module.callee`" in result
        # Should not have "(line" when line number is missing
