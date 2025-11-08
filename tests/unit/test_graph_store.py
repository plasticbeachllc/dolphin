"""Unit tests for graph store operations."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kb.store.graph_store import GraphStore
from kb.store.sqlite_meta import SQLiteMetadataStore


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        
        # Initialize database with schema
        meta_store = SQLiteMetadataStore(db_path)
        meta_store.initialize()
        
        yield db_path


@pytest.fixture
def graph_store(temp_db):
    """Create a graph store instance."""
    return GraphStore(temp_db)


@pytest.fixture
def sample_repo_and_file(temp_db):
    """Create sample repo and file for testing."""
    meta_store = SQLiteMetadataStore(temp_db)
    
    # Create repo
    meta_store.record_repo("test-repo", Path("/tmp/test-repo"))
    repo = meta_store.get_repo_by_name("test-repo")
    repo_id = repo["id"]
    
    # Create file
    file_id = meta_store.upsert_file(
        repo_id,
        path="src/main.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=1024,
    )
    
    return repo_id, file_id


class TestNodeOperations:
    """Test node CRUD operations."""
    
    def test_upsert_node_creates_new(self, graph_store, sample_repo_and_file):
        """Test creating a new node."""
        repo_id, file_id = sample_repo_and_file
        
        node_id = graph_store.upsert_node(
            node_type="function",
            name="calculate_total",
            qualified_name="myapp.utils.calculate_total",
            repo_id=repo_id,
            file_id=file_id,
            start_line=10,
            end_line=20,
            language="python",
            commit_sha="abc123",
            branch="main",
            signature="def calculate_total(items: list) -> float",
            docstring="Calculate total with tax",
            visibility="public",
        )
        
        assert node_id is not None
        
        # Verify node was created
        node = graph_store.get_node_by_id(node_id)
        assert node is not None
        assert node["node_type"] == "function"
        assert node["name"] == "calculate_total"
        assert node["qualified_name"] == "myapp.utils.calculate_total"
        assert node["start_line"] == 10
        assert node["end_line"] == 20
        assert node["signature"] == "def calculate_total(items: list) -> float"
    
    def test_upsert_node_updates_existing(self, graph_store, sample_repo_and_file):
        """Test updating an existing node."""
        repo_id, file_id = sample_repo_and_file
        
        # Create initial node
        node_id1 = graph_store.upsert_node(
            node_type="function",
            name="calculate_total",
            qualified_name="myapp.utils.calculate_total",
            repo_id=repo_id,
            file_id=file_id,
            start_line=10,
            end_line=20,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        # Update same node (same repo, file, qualified_name, start_line)
        node_id2 = graph_store.upsert_node(
            node_type="function",
            name="calculate_total",
            qualified_name="myapp.utils.calculate_total",
            repo_id=repo_id,
            file_id=file_id,
            start_line=10,
            end_line=25,  # Changed end line
            language="python",
            commit_sha="def456",
            branch="main",
            signature="def calculate_total(items: list, tax: float) -> float",  # Added signature
        )
        
        # Should return same ID
        assert node_id1 == node_id2
        
        # Verify updates were applied
        node = graph_store.get_node_by_id(node_id2)
        assert node["end_line"] == 25
        assert node["signature"] == "def calculate_total(items: list, tax: float) -> float"
        assert node["commit_sha"] == "def456"
    
    def test_get_node_by_id_not_found(self, graph_store):
        """Test getting non-existent node."""
        node = graph_store.get_node_by_id("nonexistent-id")
        assert node is None
    
    def test_find_node_by_qualified_name(self, graph_store, sample_repo_and_file):
        """Test finding node by qualified name."""
        repo_id, file_id = sample_repo_and_file
        
        # Create node
        node_id = graph_store.upsert_node(
            node_type="class",
            name="Calculator",
            qualified_name="myapp.utils.Calculator",
            repo_id=repo_id,
            file_id=file_id,
            start_line=1,
            end_line=50,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        # Find by qualified name
        node = graph_store.find_node_by_qualified_name("myapp.utils.Calculator")
        assert node is not None
        assert node["id"] == node_id
        assert node["node_type"] == "class"
    
    def test_find_node_by_qualified_name_with_repo_filter(self, graph_store, sample_repo_and_file):
        """Test finding node by qualified name with repo filter."""
        repo_id, file_id = sample_repo_and_file
        
        # Create node
        graph_store.upsert_node(
            node_type="function",
            name="helper",
            qualified_name="myapp.helpers.helper",
            repo_id=repo_id,
            file_id=file_id,
            start_line=1,
            end_line=10,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        # Find with correct repo
        node = graph_store.find_node_by_qualified_name("myapp.helpers.helper", repo_id=repo_id)
        assert node is not None
        
        # Try with wrong repo
        node = graph_store.find_node_by_qualified_name("myapp.helpers.helper", repo_id=9999)
        assert node is None
    
    def test_get_nodes_for_file(self, graph_store, sample_repo_and_file):
        """Test getting all nodes for a file."""
        repo_id, file_id = sample_repo_and_file
        
        # Create multiple nodes
        graph_store.upsert_node(
            node_type="function",
            name="func1",
            qualified_name="myapp.func1",
            repo_id=repo_id,
            file_id=file_id,
            start_line=1,
            end_line=10,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        graph_store.upsert_node(
            node_type="function",
            name="func2",
            qualified_name="myapp.func2",
            repo_id=repo_id,
            file_id=file_id,
            start_line=15,
            end_line=25,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        # Get all nodes for file
        nodes = graph_store.get_nodes_for_file(file_id)
        assert len(nodes) == 2
        
        # Verify sorted by start_line
        assert nodes[0]["start_line"] == 1
        assert nodes[1]["start_line"] == 15


class TestEdgeOperations:
    """Test edge CRUD operations."""
    
    def test_upsert_edge_creates_new(self, graph_store, sample_repo_and_file):
        """Test creating a new edge."""
        repo_id, file_id = sample_repo_and_file
        
        # Create two nodes
        source_id = graph_store.upsert_node(
            node_type="function",
            name="caller",
            qualified_name="myapp.caller",
            repo_id=repo_id,
            file_id=file_id,
            start_line=1,
            end_line=10,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        target_id = graph_store.upsert_node(
            node_type="function",
            name="callee",
            qualified_name="myapp.callee",
            repo_id=repo_id,
            file_id=file_id,
            start_line=20,
            end_line=30,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        # Create edge
        edge_id = graph_store.upsert_edge(
            source_node_id=source_id,
            target_node_id=target_id,
            edge_type="calls",
            line_number=5,
            commit_sha="abc123",
        )
        
        assert edge_id is not None
        
        # Verify edge
        edges = graph_store.get_outgoing_edges(source_id)
        assert len(edges) == 1
        assert edges[0]["target_node_id"] == target_id
        assert edges[0]["edge_type"] == "calls"
        assert edges[0]["line_number"] == 5
    
    def test_get_outgoing_edges_filtered(self, graph_store, sample_repo_and_file):
        """Test getting outgoing edges with type filter."""
        repo_id, file_id = sample_repo_and_file
        
        # Create nodes
        source_id = graph_store.upsert_node(
            node_type="function",
            name="source",
            qualified_name="myapp.source",
            repo_id=repo_id,
            file_id=file_id,
            start_line=1,
            end_line=10,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        target1_id = graph_store.upsert_node(
            node_type="function",
            name="target1",
            qualified_name="myapp.target1",
            repo_id=repo_id,
            file_id=file_id,
            start_line=20,
            end_line=30,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        target2_id = graph_store.upsert_node(
            node_type="module",
            name="target2",
            qualified_name="myapp.target2",
            repo_id=repo_id,
            file_id=file_id,
            start_line=40,
            end_line=50,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        # Create edges with different types
        graph_store.upsert_edge(
            source_node_id=source_id,
            target_node_id=target1_id,
            edge_type="calls",
            line_number=5,
            commit_sha="abc123",
        )
        
        graph_store.upsert_edge(
            source_node_id=source_id,
            target_node_id=target2_id,
            edge_type="imports",
            line_number=1,
            commit_sha="abc123",
        )
        
        # Get all edges
        all_edges = graph_store.get_outgoing_edges(source_id)
        assert len(all_edges) == 2
        
        # Get filtered edges
        call_edges = graph_store.get_outgoing_edges(source_id, edge_type="calls")
        assert len(call_edges) == 1
        assert call_edges[0]["edge_type"] == "calls"
    
    def test_get_incoming_edges(self, graph_store, sample_repo_and_file):
        """Test getting incoming edges (who calls this?)."""
        repo_id, file_id = sample_repo_and_file
        
        # Create nodes
        caller1_id = graph_store.upsert_node(
            node_type="function",
            name="caller1",
            qualified_name="myapp.caller1",
            repo_id=repo_id,
            file_id=file_id,
            start_line=1,
            end_line=10,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        caller2_id = graph_store.upsert_node(
            node_type="function",
            name="caller2",
            qualified_name="myapp.caller2",
            repo_id=repo_id,
            file_id=file_id,
            start_line=15,
            end_line=25,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        target_id = graph_store.upsert_node(
            node_type="function",
            name="target",
            qualified_name="myapp.target",
            repo_id=repo_id,
            file_id=file_id,
            start_line=30,
            end_line=40,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        # Create edges
        graph_store.upsert_edge(
            source_node_id=caller1_id,
            target_node_id=target_id,
            edge_type="calls",
            line_number=5,
            commit_sha="abc123",
        )
        
        graph_store.upsert_edge(
            source_node_id=caller2_id,
            target_node_id=target_id,
            edge_type="calls",
            line_number=20,
            commit_sha="abc123",
        )
        
        # Get incoming edges (callsites)
        incoming = graph_store.get_incoming_edges(target_id, edge_type="calls")
        assert len(incoming) == 2
        
        source_ids = {e["source_node_id"] for e in incoming}
        assert caller1_id in source_ids
        assert caller2_id in source_ids


class TestCleanupOperations:
    """Test cleanup operations."""
    
    def test_delete_nodes_for_file(self, graph_store, sample_repo_and_file):
        """Test deleting all nodes for a file."""
        repo_id, file_id = sample_repo_and_file
        
        # Create nodes
        graph_store.upsert_node(
            node_type="function",
            name="func1",
            qualified_name="myapp.func1",
            repo_id=repo_id,
            file_id=file_id,
            start_line=1,
            end_line=10,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        graph_store.upsert_node(
            node_type="function",
            name="func2",
            qualified_name="myapp.func2",
            repo_id=repo_id,
            file_id=file_id,
            start_line=15,
            end_line=25,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        # Verify nodes exist
        nodes = graph_store.get_nodes_for_file(file_id)
        assert len(nodes) == 2
        
        # Delete all nodes for file
        deleted = graph_store.delete_nodes_for_file(file_id)
        assert deleted == 2
        
        # Verify nodes are gone
        nodes = graph_store.get_nodes_for_file(file_id)
        assert len(nodes) == 0
    
    def test_delete_nodes_for_repo(self, graph_store, sample_repo_and_file):
        """Test deleting all nodes for a repository."""
        repo_id, file_id = sample_repo_and_file
        
        # Create nodes
        graph_store.upsert_node(
            node_type="function",
            name="func1",
            qualified_name="myapp.func1",
            repo_id=repo_id,
            file_id=file_id,
            start_line=1,
            end_line=10,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        # Delete all nodes for repo
        deleted = graph_store.delete_nodes_for_repo(repo_id)
        assert deleted == 1
        
        # Verify count
        count = graph_store.get_node_count(repo_id=repo_id)
        assert count == 0


class TestStatistics:
    """Test statistics operations."""
    
    def test_get_node_count(self, graph_store, sample_repo_and_file):
        """Test getting node count."""
        repo_id, file_id = sample_repo_and_file
        
        # Initially empty
        assert graph_store.get_node_count() == 0
        assert graph_store.get_node_count(repo_id=repo_id) == 0
        
        # Add nodes
        graph_store.upsert_node(
            node_type="function",
            name="func1",
            qualified_name="myapp.func1",
            repo_id=repo_id,
            file_id=file_id,
            start_line=1,
            end_line=10,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        assert graph_store.get_node_count() == 1
        assert graph_store.get_node_count(repo_id=repo_id) == 1
    
    def test_get_edge_count(self, graph_store, sample_repo_and_file):
        """Test getting edge count."""
        repo_id, file_id = sample_repo_and_file
        
        # Create nodes
        source_id = graph_store.upsert_node(
            node_type="function",
            name="source",
            qualified_name="myapp.source",
            repo_id=repo_id,
            file_id=file_id,
            start_line=1,
            end_line=10,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        target_id = graph_store.upsert_node(
            node_type="function",
            name="target",
            qualified_name="myapp.target",
            repo_id=repo_id,
            file_id=file_id,
            start_line=20,
            end_line=30,
            language="python",
            commit_sha="abc123",
            branch="main",
        )
        
        # Initially no edges
        assert graph_store.get_edge_count() == 0
        assert graph_store.get_edge_count(repo_id=repo_id) == 0
        
        # Add edge
        graph_store.upsert_edge(
            source_node_id=source_id,
            target_node_id=target_id,
            edge_type="calls",
            line_number=5,
            commit_sha="abc123",
        )
        
        assert graph_store.get_edge_count() == 1
        assert graph_store.get_edge_count(repo_id=repo_id) == 1