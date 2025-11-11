"""Tests for Python call graph extraction."""

import pytest
from kb.graph_intelligence.extractors.python_call_graph import PythonCallGraphExtractor
from kb.graph_intelligence.models import NodeType, EdgeType


@pytest.fixture
def extractor():
    """Create a PythonCallGraphExtractor instance."""
    return PythonCallGraphExtractor()


def test_extract_simple_function(extractor):
    """Test extraction of simple function definition."""
    code = '''
def hello():
    """Say hello."""
    print("Hello")
'''
    nodes, edges = extractor.extract("test.py", code, repo_id=1, file_id=1,
                                     commit_sha="abc123", branch="main")

    assert len(nodes) == 1
    assert nodes[0].name == "hello"
    assert nodes[0].node_type == NodeType.FUNCTION
    assert nodes[0].docstring == "Say hello."
    assert nodes[0].language == "python"


def test_extract_function_call(extractor):
    """Test extraction of function call edge."""
    code = '''
def caller():
    callee()

def callee():
    pass
'''
    nodes, edges = extractor.extract("test.py", code, repo_id=1, file_id=1,
                                     commit_sha="abc123", branch="main")

    assert len(nodes) == 2
    assert len(edges) == 1
    assert edges[0].edge_type == EdgeType.CALLS
    assert edges[0].attributes["call_type"] == "direct"


def test_extract_class_and_methods(extractor):
    """Test extraction of class with methods."""
    code = '''
class Calculator:
    """A simple calculator."""

    def add(self, a, b):
        """Add two numbers."""
        return a + b

    def multiply(self, a, b):
        """Multiply two numbers."""
        return self.add(a, 0) * b
'''
    nodes, edges = extractor.extract("test.py", code, repo_id=1, file_id=1,
                                     commit_sha="abc123", branch="main")

    # Should have: Calculator class, add method, multiply method
    assert len(nodes) == 3

    class_node = next(n for n in nodes if n.node_type == NodeType.CLASS)
    assert class_node.name == "Calculator"
    assert class_node.docstring == "A simple calculator."

    method_nodes = [n for n in nodes if n.node_type == NodeType.METHOD]
    assert len(method_nodes) == 2
    assert set(n.name for n in method_nodes) == {"add", "multiply"}

    # multiply calls add
    call_edges = [e for e in edges if e.edge_type == EdgeType.CALLS]
    assert len(call_edges) >= 1


def test_async_function_detection(extractor):
    """Test detection of async functions."""
    code = '''
async def fetch_data():
    """Async function."""
    await some_api_call()

async def some_api_call():
    pass
'''
    nodes, edges = extractor.extract("test.py", code, repo_id=1, file_id=1,
                                     commit_sha="abc123", branch="main")

    assert len(nodes) == 2
    fetch_node = next(n for n in nodes if n.name == "fetch_data")
    assert "async" in fetch_node.signature


def test_nested_function_calls(extractor):
    """Test extraction of nested function calls."""
    code = '''
def outer():
    def inner():
        helper()
    inner()

def helper():
    pass
'''
    nodes, edges = extractor.extract("test.py", code, repo_id=1, file_id=1,
                                     commit_sha="abc123", branch="main")

    # Should detect: outer, inner, helper
    assert len(nodes) == 3

    # Should have edges
    assert len(edges) >= 1


def test_method_call_in_class(extractor):
    """Test method calls within a class."""
    code = '''
class MyClass:
    def method_a(self):
        self.method_b()

    def method_b(self):
        pass
'''
    nodes, edges = extractor.extract("test.py", code, repo_id=1, file_id=1,
                                     commit_sha="abc123", branch="main")

    # Should have class + 2 methods
    assert len(nodes) == 3

    # Should have call edge from method_a to method_b
    call_edges = [e for e in edges if e.edge_type == EdgeType.CALLS]
    assert len(call_edges) >= 1


def test_qualified_names(extractor):
    """Test that qualified names are generated correctly."""
    code = '''
class Outer:
    def method(self):
        pass

def standalone():
    pass
'''
    nodes, edges = extractor.extract("path/to/module.py", code, repo_id=1, file_id=1,
                                     commit_sha="abc123", branch="main")

    class_node = next(n for n in nodes if n.node_type == NodeType.CLASS)
    assert class_node.qualified_name == "path.to.module.Outer"

    method_node = next(n for n in nodes if n.node_type == NodeType.METHOD)
    assert method_node.qualified_name == "path.to.module.Outer.method"

    func_node = next(n for n in nodes if n.name == "standalone")
    assert func_node.qualified_name == "path.to.module.standalone"


def test_empty_file(extractor):
    """Test extraction from empty file."""
    code = ""
    nodes, edges = extractor.extract("test.py", code, repo_id=1, file_id=1,
                                     commit_sha="abc123", branch="main")

    assert len(nodes) == 0
    assert len(edges) == 0


def test_multiple_classes(extractor):
    """Test extraction of multiple classes."""
    code = '''
class ClassA:
    def method_a(self):
        pass

class ClassB:
    def method_b(self):
        pass
'''
    nodes, edges = extractor.extract("test.py", code, repo_id=1, file_id=1,
                                     commit_sha="abc123", branch="main")

    # Should have 2 classes and 2 methods
    assert len(nodes) == 4

    classes = [n for n in nodes if n.node_type == NodeType.CLASS]
    assert len(classes) == 2
    assert set(c.name for c in classes) == {"ClassA", "ClassB"}
