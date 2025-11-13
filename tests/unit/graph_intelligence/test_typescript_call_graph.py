"""Tests for TypeScript call graph extraction."""

import pytest

from kb.graph_intelligence.extractors.typescript_call_graph import \
    TypeScriptCallGraphExtractor
from kb.graph_intelligence.models import EdgeType, NodeType


@pytest.fixture
def extractor():
    """Create a TypeScriptCallGraphExtractor instance."""
    return TypeScriptCallGraphExtractor()


def test_extract_simple_function(extractor):
    """Test extraction of simple function declaration."""
    code = """
function hello() {
    console.log("Hello");
}
"""
    nodes, edges = extractor.extract(
        "test.ts", code, repo_id=1, file_id=1, commit_sha="abc123", branch="main"
    )

    assert len(nodes) == 1
    assert nodes[0].name == "hello"
    assert nodes[0].node_type == NodeType.FUNCTION
    assert nodes[0].language == "typescript"


def test_extract_arrow_function(extractor):
    """Test extraction of arrow function."""
    code = """
const greet = (name: string) => {
    console.log(`Hello, ${name}`);
};
"""
    nodes, edges = extractor.extract(
        "test.ts", code, repo_id=1, file_id=1, commit_sha="abc123", branch="main"
    )

    assert len(nodes) == 1
    assert nodes[0].name == "greet"
    assert nodes[0].node_type == NodeType.FUNCTION
    assert "greet" in nodes[0].signature


def test_extract_class_and_methods(extractor):
    """Test extraction of class with methods."""
    code = """
class Calculator {
    add(a: number, b: number): number {
        return a + b;
    }

    multiply(a: number, b: number): number {
        return this.add(a, 0) * b;
    }
}
"""
    nodes, edges = extractor.extract(
        "test.ts", code, repo_id=1, file_id=1, commit_sha="abc123", branch="main"
    )

    # Should have: Calculator class, add method, multiply method
    assert len(nodes) == 3

    class_node = next(n for n in nodes if n.node_type == NodeType.CLASS)
    assert class_node.name == "Calculator"

    method_nodes = [n for n in nodes if n.node_type == NodeType.METHOD]
    assert len(method_nodes) == 2
    assert set(n.name for n in method_nodes) == {"add", "multiply"}


def test_async_function_detection(extractor):
    """Test detection of async functions."""
    code = """
async function fetchData() {
    await someApiCall();
}

async function someApiCall() {
    return Promise.resolve();
}
"""
    nodes, edges = extractor.extract(
        "test.ts", code, repo_id=1, file_id=1, commit_sha="abc123", branch="main"
    )

    assert len(nodes) == 2
    fetch_node = next(n for n in nodes if n.name == "fetchData")
    assert "async" in fetch_node.signature


def test_function_call(extractor):
    """Test extraction of function call edge."""
    code = """
function caller() {
    callee();
}

function callee() {
    // do nothing
}
"""
    nodes, edges = extractor.extract(
        "test.ts", code, repo_id=1, file_id=1, commit_sha="abc123", branch="main"
    )

    assert len(nodes) == 2
    assert len(edges) == 1
    assert edges[0].edge_type == EdgeType.CALLS


def test_qualified_names(extractor):
    """Test that qualified names are generated correctly."""
    code = """
class Outer {
    method() {
        // do nothing
    }
}

function standalone() {
    // do nothing
}
"""
    nodes, edges = extractor.extract(
        "path/to/module.ts",
        code,
        repo_id=1,
        file_id=1,
        commit_sha="abc123",
        branch="main",
    )

    class_node = next(n for n in nodes if n.node_type == NodeType.CLASS)
    assert class_node.qualified_name == "path.to.module.Outer"

    method_node = next(n for n in nodes if n.node_type == NodeType.METHOD)
    assert method_node.qualified_name == "path.to.module.Outer.method"

    func_node = next(n for n in nodes if n.name == "standalone")
    assert func_node.qualified_name == "path.to.module.standalone"


def test_empty_file(extractor):
    """Test extraction from empty file."""
    code = ""
    nodes, edges = extractor.extract(
        "test.ts", code, repo_id=1, file_id=1, commit_sha="abc123", branch="main"
    )

    assert len(nodes) == 0
    assert len(edges) == 0


def test_async_arrow_function(extractor):
    """Test async arrow function."""
    code = """
const fetchUser = async (id: string) => {
    return await api.getUser(id);
};
"""
    nodes, edges = extractor.extract(
        "test.ts", code, repo_id=1, file_id=1, commit_sha="abc123", branch="main"
    )

    assert len(nodes) == 1
    assert nodes[0].name == "fetchUser"
    assert "async" in nodes[0].signature
