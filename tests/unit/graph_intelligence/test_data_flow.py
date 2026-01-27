"""Unit tests for data flow analysis."""

import unittest

from kb.graph_intelligence.data_flow import DataFlowAnalyzer
from kb.graph_intelligence.models import EdgeType, GraphNode, NodeType


class MockNode:
    """Mock tree-sitter Node."""

    def __init__(self, type_name, text=None, start_point=(0, 0), end_point=(0, 0), children=None):
        self.type = type_name
        self.text = text.encode("utf8") if text else None
        self.start_point = start_point
        self.end_point = end_point
        self.children = children or []
        self.parent = None

        for child in self.children:
            child.parent = self

        self.id = id(self)

    def child_by_field_name(self, name):
        # Simplification: we store children with field names in a dict if needed
        # For this test, we'll just check children manually or rely on structure
        if name == "left" and self.children:
            return self.children[0]
        if name == "right" and len(self.children) > 1:
            return self.children[1]
        return None


class TestDataFlowAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = DataFlowAnalyzer()

    def test_extract_data_flow_python_simple(self):
        """Test simple data flow in Python."""
        # Code structure:
        # def foo():  (lines 0-3)
        #     x = 1   (line 1)
        #     y = x   (line 2)

        # Function definition node (for context)
        foo_def = GraphNode(
            id="func-foo",
            node_type=NodeType.FUNCTION,
            name="foo",
            qualified_name="foo",
            start_line=0,
            end_line=3,
            repo_id=1,
            file_path="foo.py",
            language="python",
        )

        # Tree structure
        # assignment (x = 1)
        x_assign = MockNode(
            "assignment",
            start_point=(1, 0),
            children=[
                MockNode("identifier", "x", start_point=(1, 0)),  # left
                MockNode("integer", "1", start_point=(1, 4)),  # right
            ],
        )

        # assignment (y = x)
        y_assign = MockNode(
            "assignment",
            start_point=(2, 0),
            children=[
                MockNode("identifier", "y", start_point=(2, 0)),  # left
                MockNode("identifier", "x", start_point=(2, 4)),  # right (use)
            ],
        )

        # Function body
        foo_body = MockNode("block", start_point=(0, 10), end_point=(3, 0), children=[x_assign, y_assign])

        # Function definition (root)
        root = MockNode(
            "function_definition",
            start_point=(0, 0),
            end_point=(3, 0),
            children=[MockNode("identifier", "foo"), foo_body],
        )

        edges = self.analyzer.extract_data_flow_python(root, [foo_def], repo_id=1)  # type: ignore

        # Expect one USES edge: x is defined and used within the same function
        self.assertEqual(len(edges), 1)
        edge = edges[0]
        self.assertEqual(edge.source_id, "func-foo")
        self.assertEqual(edge.target_id, "func-foo")
        self.assertEqual(edge.edge_type, EdgeType.USES)
        self.assertEqual(edge.attributes["variable"], "x")

    def test_extract_data_flow_python_cross_function(self):
        """Test data flow across functions (global/outer scope)."""
        # Code structure:
        # def producer(): (lines 0-2)
        #     x = 1       (line 1)
        #
        # def consumer(): (lines 4-6)
        #     y = x       (line 5)
        #
        # The analyzer matches variable names across functions.

        producer_def = GraphNode(
            id="func-producer",
            node_type=NodeType.FUNCTION,
            name="producer",
            qualified_name="producer",
            start_line=0,
            end_line=2,
            repo_id=1,
            file_path="module.py",
            language="python",
        )

        consumer_def = GraphNode(
            id="func-consumer",
            node_type=NodeType.FUNCTION,
            name="consumer",
            qualified_name="consumer",
            start_line=4,
            end_line=6,
            repo_id=1,
            file_path="module.py",
            language="python",
        )

        # Tree
        x_assign = MockNode(
            "assignment",
            start_point=(1, 0),
            children=[MockNode("identifier", "x", start_point=(1, 0)), MockNode("integer", "1")],
        )
        producer_body = MockNode("block", start_point=(0, 10), end_point=(2, 0), children=[x_assign])
        producer_node = MockNode(
            "function_definition",
            start_point=(0, 0),
            end_point=(2, 0),
            children=[MockNode("identifier", "producer"), producer_body],
        )

        y_assign = MockNode(
            "assignment",
            start_point=(5, 0),
            children=[
                MockNode("identifier", "y", start_point=(5, 0)),
                MockNode("identifier", "x", start_point=(5, 4)),  # Usage of x
            ],
        )
        consumer_body = MockNode("block", start_point=(4, 10), end_point=(6, 0), children=[y_assign])
        consumer_node = MockNode(
            "function_definition",
            start_point=(4, 0),
            end_point=(6, 0),
            children=[MockNode("identifier", "consumer"), consumer_body],
        )

        root = MockNode("module", children=[producer_node, consumer_node])

        edges = self.analyzer.extract_data_flow_python(root, [producer_def, consumer_def], repo_id=1)  # type: ignore

        self.assertEqual(len(edges), 1)
        edge = edges[0]
        self.assertEqual(edge.source_id, "func-consumer")  # Consumer uses
        self.assertEqual(edge.target_id, "func-producer")  # Producer defines
        self.assertEqual(edge.edge_type, EdgeType.USES)
        self.assertEqual(edge.attributes["variable"], "x")

    def test_find_python_variable_references(self):
        """Test finding variable references."""
        # Wrap in a function so uses are detected (uses outside functions are ignored)
        func_def = GraphNode(
            id="func-1",
            node_type=NodeType.FUNCTION,
            name="func",
            qualified_name="func",
            start_line=0,
            end_line=5,
            repo_id=1,
            file_path="test.py",
            language="python",
        )

        # x = 1
        x_assign = MockNode(
            "assignment",
            start_point=(1, 0),
            children=[MockNode("identifier", "x", start_point=(1, 0)), MockNode("integer", "1")],
        )

        # y = x
        y_assign = MockNode(
            "assignment",
            start_point=(2, 0),
            children=[MockNode("identifier", "y", start_point=(2, 0)), MockNode("identifier", "x", start_point=(2, 4))],
        )

        # Function body
        body = MockNode("block", start_point=(0, 10), end_point=(5, 0), children=[x_assign, y_assign])

        # Function def
        root = MockNode(
            "function_definition", start_point=(0, 0), end_point=(5, 0), children=[MockNode("identifier", "func"), body]
        )

        refs = self.analyzer._find_python_variable_references(root, [func_def])  # type: ignore

        # Expected: x definition, y definition, x usage, and func name (counted as inside func)
        self.assertEqual(len(refs), 4)

        # x definition
        ref_x_def = next(r for r in refs if r.var_name == "x" and r.is_definition)
        self.assertEqual(ref_x_def.line, 1)
        self.assertEqual(ref_x_def.func_id, "func-1")

        # y definition
        ref_y_def = next(r for r in refs if r.var_name == "y" and r.is_definition)
        self.assertEqual(ref_y_def.line, 2)

        # x usage
        ref_x_use = next(r for r in refs if r.var_name == "x" and not r.is_definition)
        self.assertEqual(ref_x_use.line, 2)
        self.assertEqual(ref_x_use.func_id, "func-1")
