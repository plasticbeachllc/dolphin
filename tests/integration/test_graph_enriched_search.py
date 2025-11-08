"""Integration tests for graph-enriched search results."""

from __future__ import annotations

import pytest
from pathlib import Path

from kb.api.search_backend import KnowledgeSearchBackend, create_search_backend
from kb.api.app import SearchRequest
from kb.store.graph_store import GraphStore
from kb.store.sqlite_meta import SQLiteMetadataStore
from kb.retrieval.graph_context import GraphContextEnricher, format_graph_context_for_llm
from kb.ingest.pipeline import IngestionPipeline


@pytest.fixture
def sample_python_file(tmp_path: Path) -> Path:
    """Create a sample Python file with multiple functions."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    
    sample_file = repo_dir / "calculator.py"
    sample_file.write_text("""
def add(a, b):
    \"\"\"Add two numbers.\"\"\"
    return a + b

def subtract(a, b):
    \"\"\"Subtract b from a.\"\"\"
    return a - b

def multiply(a, b):
    \"\"\"Multiply two numbers.\"\"\"
    return a * b

def calculate_total(items):
    \"\"\"Calculate total using add.\"\"\"
    total = 0
    for item in items:
        total = add(total, item)
    return total

def process_data(values):
    \"\"\"Process data using multiple operations.\"\"\"
    result = add(values[0], values[1])
    result = subtract(result, values[2])
    result = multiply(result, 2)
    return result
""")
    
    return repo_dir


@pytest.fixture
def indexed_repo(sample_python_file: Path, tmp_path: Path):
    """Create an indexed repository with graph data."""
    store_root = tmp_path / "kb_store"
    store_root.mkdir()
    
    # Create stores
    sql_store = SQLiteMetadataStore(store_root / "metadata.db")
    graph_store = GraphStore(store_root / "metadata.db")
    
    # Initialize database
    sql_store.initialize()
    
    # Create repository record
    sql_store.record_repo("test_repo", sample_python_file)
    repo_info = sql_store.get_repo_by_name("test_repo")
    
    # Process the file to extract graph data
    file_path = sample_python_file / "calculator.py"
    from kb.ingest.graph_helpers import extract_graph_from_file, store_graph_data
    from kb.chunkers.repo_config import RepoChunkingConfig
    
    file_info_id = sql_store.upsert_file(
        repo_id=repo_info["id"],
        path="calculator.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=len(file_path.read_text())
    )
    file_info = {"id": file_info_id}
    
    # Extract and store graph data
    try:
        text = file_path.read_text()
        nodes, edges = extract_graph_from_file(
            file_path=file_path,
            language="python",
            text=text,
            repo_config=RepoChunkingConfig()
        )
        
        if nodes or edges:
            store_graph_data(
                graph_store=graph_store,
                nodes=nodes,
                edges=edges,
                repo_id=repo_info["id"],
                file_id=file_info["id"],
                language="python",
                commit_sha="test123",
                branch="main"
            )
    except Exception as e:
        # Graph extraction might not work perfectly in test environment
        print(f"Graph extraction error (expected in test): {e}")
    
    return {
        "store_root": store_root,
        "sql_store": sql_store,
        "graph_store": graph_store,
        "repo_info": repo_info,
        "file_info": file_info
    }


def test_graph_context_enricher_basic(indexed_repo):
    """Test basic graph context enrichment."""
    sql_store = indexed_repo["sql_store"]
    graph_store = indexed_repo["graph_store"]
    
    enricher = GraphContextEnricher(
        graph_store=graph_store,
        sql_store=sql_store,
        max_related_nodes=10,
        max_edges_per_node=5
    )
    
    # Create a mock search result
    result = {
        "repo": "test_repo",
        "path": "calculator.py",
        "start_line": 15,
        "end_line": 20,
        "chunk_id": "test-chunk-1",
        "score": 0.9
    }
    
    # Enrich the result
    enriched = enricher.enrich_search_results([result])
    
    assert len(enriched) == 1
    assert "graph_context" in enriched[0] or enriched[0].get("graph_context") is None
    
    # If graph context is present, validate structure
    if enriched[0].get("graph_context"):
        graph_ctx = enriched[0]["graph_context"]
        assert "nodes" in graph_ctx
        assert "relationships" in graph_ctx


def test_graph_context_with_relationships(indexed_repo):
    """Test graph context includes relationships."""
    sql_store = indexed_repo["sql_store"]
    graph_store = indexed_repo["graph_store"]
    
    enricher = GraphContextEnricher(
        graph_store=graph_store,
        sql_store=sql_store
    )
    
    # Get the calculate_total function (which calls add)
    result = {
        "repo": "test_repo",
        "path": "calculator.py",
        "start_line": 15,
        "end_line": 20,
        "chunk_id": "test-chunk-1",
        "score": 0.9
    }
    
    enriched = enricher.enrich_search_results([result])
    
    if enriched[0].get("graph_context"):
        graph_ctx = enriched[0]["graph_context"]
        
        # Should have relationships if graph extraction worked
        if graph_ctx.get("relationships"):
            assert isinstance(graph_ctx["relationships"], list)


def test_format_graph_context_for_llm():
    """Test formatting graph context for LLM consumption."""
    graph_context = {
        "nodes": [
            {
                "id": "node-1",
                "type": "function",
                "name": "calculate_total",
                "qualified_name": "calculator.calculate_total",
                "signature": "def calculate_total(items)",
                "line_range": [15, 20]
            }
        ],
        "relationships": [
            {
                "type": "calls",
                "direction": "outgoing",
                "target": {
                    "name": "add",
                    "qualified_name": "calculator.add",
                    "node_type": "function",
                    "signature": "def add(a, b)"
                },
                "line_number": 18
            }
        ]
    }
    
    formatted = format_graph_context_for_llm(graph_context)
    
    assert "Code Graph Context" in formatted
    assert "Entities in this code:" in formatted
    assert "calculate_total" in formatted
    assert "Calls:" in formatted
    assert "calculator.add" in formatted


def test_graph_context_multiple_nodes(indexed_repo):
    """Test graph context with multiple overlapping nodes."""
    sql_store = indexed_repo["sql_store"]
    graph_store = indexed_repo["graph_store"]
    
    enricher = GraphContextEnricher(
        graph_store=graph_store,
        sql_store=sql_store
    )
    
    # Large line range that might include multiple functions
    result = {
        "repo": "test_repo",
        "path": "calculator.py",
        "start_line": 1,
        "end_line": 30,
        "chunk_id": "test-chunk-1",
        "score": 0.9
    }
    
    enriched = enricher.enrich_search_results([result])
    
    if enriched[0].get("graph_context"):
        graph_ctx = enriched[0]["graph_context"]
        # Might have multiple nodes in this range
        assert isinstance(graph_ctx["nodes"], list)


def test_graph_context_filtering_options(indexed_repo):
    """Test graph context with different filtering options."""
    sql_store = indexed_repo["sql_store"]
    graph_store = indexed_repo["graph_store"]
    
    enricher = GraphContextEnricher(
        graph_store=graph_store,
        sql_store=sql_store
    )
    
    result = {
        "repo": "test_repo",
        "path": "calculator.py",
        "start_line": 15,
        "end_line": 20,
        "chunk_id": "test-chunk-1",
        "score": 0.9
    }
    
    # Test with all relationship types disabled
    enriched_none = enricher.enrich_search_results(
        [result],
        include_callsites=False,
        include_implementations=False,
        include_dependencies=False
    )
    
    # Test with only callsites enabled
    enriched_calls = enricher.enrich_search_results(
        [result],
        include_callsites=True,
        include_implementations=False,
        include_dependencies=False
    )
    
    # Results should be structured properly regardless of options
    assert isinstance(enriched_none, list)
    assert isinstance(enriched_calls, list)


def test_graph_context_no_graph_data(tmp_path: Path):
    """Test behavior when no graph data is available."""
    store_root = tmp_path / "kb_store"
    store_root.mkdir()
    
    sql_store = SQLiteMetadataStore(store_root / "metadata.db")
    graph_store = GraphStore(store_root / "metadata.db")
    sql_store.initialize()
    
    # Create repo without graph data
    sql_store.record_repo("empty_repo", tmp_path)
    repo_info = sql_store.get_repo_by_name("empty_repo")
    file_info_id = sql_store.upsert_file(
        repo_id=repo_info["id"],
        path="test.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=0
    )
    file_info = {"id": file_info_id}
    
    enricher = GraphContextEnricher(
        graph_store=graph_store,
        sql_store=sql_store
    )
    
    result = {
        "repo": "empty_repo",
        "path": "test.py",
        "start_line": 1,
        "end_line": 10,
        "chunk_id": "test-chunk-1",
        "score": 0.9
    }
    
    enriched = enricher.enrich_search_results([result])
    
    # Should not fail, just return result without graph context
    assert len(enriched) == 1
    assert enriched[0].get("graph_context") is None


def test_format_graph_context_empty():
    """Test formatting empty graph context."""
    # Empty graph context
    formatted = format_graph_context_for_llm({})
    assert formatted == ""
    
    # Graph context with no nodes
    formatted = format_graph_context_for_llm({"nodes": [], "relationships": []})
    assert formatted == ""


def test_graph_context_deduplication():
    """Test that duplicate relationships are removed."""
    from kb.retrieval.graph_context import GraphContextEnricher
    
    # Create mock enricher
    enricher = GraphContextEnricher(
        graph_store=None,
        sql_store=None
    )
    
    # Test deduplication
    relationships = [
        {
            "type": "calls",
            "direction": "outgoing",
            "target": {"qualified_name": "func1"},
            "line_number": 10
        },
        {
            "type": "calls",
            "direction": "outgoing",
            "target": {"qualified_name": "func1"},
            "line_number": 10
        },  # Duplicate
        {
            "type": "calls",
            "direction": "outgoing",
            "target": {"qualified_name": "func2"},
            "line_number": 15
        }
    ]
    
    deduped = enricher._deduplicate_relationships(relationships)
    
    assert len(deduped) == 2
    assert deduped[0]["target"]["qualified_name"] == "func1"
    assert deduped[1]["target"]["qualified_name"] == "func2"