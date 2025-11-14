"""Integration tests for code graph extraction during indexing."""

from __future__ import annotations

import pytest

from kb.config import KBConfig
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore
from kb.store.graph_store import GraphStore


@pytest.fixture
def temp_test_repo(tmp_path):
    """Create a temporary test repository with Python and TypeScript files."""
    import subprocess

    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repository
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True
    )

    # Create Python file with functions and classes
    py_file = repo_path / "example.py"
    py_file.write_text(
        """
import os
from typing import List

def helper_function(x: int) -> int:
    \"\"\"Helper function.\"\"\"
    return x * 2

class DataProcessor:
    \"\"\"Data processor class.\"\"\"
    
    def __init__(self, name: str):
        self.name = name
    
    def process(self, data: List[int]) -> List[int]:
        \"\"\"Process data using helper.\"\"\"
        return [helper_function(x) for x in data]
    
    def validate(self) -> bool:
        \"\"\"Validate processor state.\"\"\"
        return len(self.name) > 0

def main():
    \"\"\"Main entry point.\"\"\"
    processor = DataProcessor("test")
    result = processor.process([1, 2, 3])
    print(result)
"""
    )

    # Create TypeScript file with functions and interfaces
    ts_file = repo_path / "example.ts"
    ts_file.write_text(
        """
interface User {
    id: number;
    name: string;
}

interface UserRepository {
    getUser(id: number): Promise<User>;
    saveUser(user: User): Promise<void>;
}

function validateUser(user: User): boolean {
    return user.name.length > 0;
}

class UserService implements UserRepository {
    async getUser(id: number): Promise<User> {
        // Implementation
        return { id, name: "test" };
    }
    
    async saveUser(user: User): Promise<void> {
        if (!validateUser(user)) {
            throw new Error("Invalid user");
        }
        // Save logic
    }
}

export { User, UserRepository, UserService, validateUser };
"""
    )

    # Add and commit files
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    return repo_path


class TestGraphExtraction:
    """Integration tests for code graph extraction."""

    def test_graph_extraction_from_python(self, temp_test_repo, tmp_path):
        """Test that graph extraction works for Python files during indexing."""
        # Setup
        config = KBConfig()
        db_path = tmp_path / "test.db"
        lance_path = tmp_path / "lance"

        metadata = SQLiteMetadataStore(db_path)
        metadata.initialize()  # Initialize database tables
        lancedb = LanceDBStore(lance_path)
        graph_store = GraphStore(db_path)

        pipeline = IngestionPipeline(
            config=config,
            lancedb=lancedb,
            metadata=metadata,
            graph_store=graph_store,
        )

        # Index the repository (need to register it first)
        repo_name = "test_repo"
        metadata.record_repo(
            name=repo_name, path=str(temp_test_repo), default_embed_model="small"
        )

        result = pipeline.index(
            repo_name,
            force=True,
            dry_run=False,
        )

        # Verify indexing completed
        assert result["files_indexed"] == 2
        assert result["chunks_indexed"] > 0

        # Verify graph data was extracted
        assert result.get("graph_nodes_created", 0) > 0
        assert result.get("graph_edges_created", 0) > 0

        # Get repo_id and file_id
        repo_id = result["repo_id"]
        file_id = metadata.get_file_id(repo_id, "example.py")
        assert file_id is not None

        # Verify Python nodes were created
        python_nodes = graph_store.get_nodes_for_file(file_id)

        # Should have nodes for:
        # - helper_function
        # - DataProcessor class
        # - DataProcessor.__init__
        # - DataProcessor.process
        # - DataProcessor.validate
        # - main function
        assert len(python_nodes) >= 6

        # Verify we have different node types
        node_types = {node["node_type"] for node in python_nodes}
        assert "function" in node_types
        assert "class" in node_types

        # Find specific nodes
        helper_node = next(
            (n for n in python_nodes if n["name"] == "helper_function"), None
        )
        assert helper_node is not None
        assert helper_node["node_type"] == "function"
        assert "helper_function" in helper_node["qualified_name"]

        main_node = next((n for n in python_nodes if n["name"] == "main"), None)
        assert main_node is not None

        # Verify edges (main calls DataProcessor and helper_function)
        main_edges = graph_store.get_outgoing_edges(main_node["id"])
        assert len(main_edges) > 0

        # Check for calls edge type
        call_edges = [e for e in main_edges if e["edge_type"] == "calls"]
        assert len(call_edges) > 0

    def test_graph_extraction_from_typescript(self, temp_test_repo, tmp_path):
        """Test that graph extraction works for TypeScript files during indexing."""
        # Setup
        config = KBConfig()
        db_path = tmp_path / "test.db"
        lance_path = tmp_path / "lance"

        metadata = SQLiteMetadataStore(db_path)
        metadata.initialize()  # Initialize database tables
        lancedb = LanceDBStore(lance_path)
        graph_store = GraphStore(db_path)

        pipeline = IngestionPipeline(
            config=config,
            lancedb=lancedb,
            metadata=metadata,
            graph_store=graph_store,
        )

        # Index the repository (need to register it first)
        repo_name = "test_repo"
        metadata.record_repo(
            name=repo_name, path=str(temp_test_repo), default_embed_model="small"
        )

        result = pipeline.index(
            repo_name,
            force=True,
            dry_run=False,
        )

        # Get repo_id and file_id
        repo_id = result["repo_id"]
        file_id = metadata.get_file_id(repo_id, "example.ts")
        assert file_id is not None

        # Verify TypeScript nodes were created
        ts_nodes = graph_store.get_nodes_for_file(file_id)

        # Should have nodes for:
        # - validateUser function
        # - UserService class
        # - UserService.getUser method
        # - UserService.saveUser method
        # Note: TypeScript interfaces are not currently extracted as graph nodes
        assert len(ts_nodes) >= 4, "TypeScript graph extraction should create nodes"

        # Verify we have different node types
        node_types = {node["node_type"] for node in ts_nodes}
        # Note: Interfaces are not currently extracted by TypeScript parser
        assert "function" in node_types
        assert "class" in node_types

        # Find specific nodes
        # Note: Interfaces are extracted, look for User interface
        user_interface = next(
            (
                n
                for n in ts_nodes
                if n["name"] == "User" and n["node_type"] == "interface"
            ),
            None,
        )
        # If interface extraction is working, this should pass
        # If not, we may need to check if interfaces are being stored correctly
        if user_interface is None:
            # Debug: print all nodes to see what was actually extracted
            print(
                f"DEBUG: All TS nodes: {[(n['name'], n['node_type']) for n in ts_nodes]}"
            )
        assert user_interface is not None, (
            f"User interface not found in nodes: {[(n['name'], n['node_type']) for n in ts_nodes]}"
        )
        assert user_interface["node_type"] == "interface"

        user_service = next((n for n in ts_nodes if n["name"] == "UserService"), None)
        assert user_service is not None
        assert user_service["node_type"] == "class"

        # Verify UserService implements UserRepository
        service_edges = graph_store.get_outgoing_edges(user_service["id"])
        implements_edges = [e for e in service_edges if e["edge_type"] == "implements"]
        assert len(implements_edges) > 0

    def test_graph_cleanup_on_file_deletion(self, temp_test_repo, tmp_path):
        """Test that graph data is cleaned up when files are deleted."""
        import subprocess

        # Setup
        config = KBConfig()
        db_path = tmp_path / "test.db"
        lance_path = tmp_path / "lance"

        metadata = SQLiteMetadataStore(db_path)
        metadata.initialize()  # Initialize database tables
        lancedb = LanceDBStore(lance_path)
        graph_store = GraphStore(db_path)

        pipeline = IngestionPipeline(
            config=config,
            lancedb=lancedb,
            metadata=metadata,
            graph_store=graph_store,
        )

        # Initial indexing (need to register it first)
        repo_name = "test_repo"
        metadata.record_repo(
            name=repo_name, path=str(temp_test_repo), default_embed_model="small"
        )

        result1 = pipeline.index(
            repo_name,
            force=True,
            dry_run=False,
        )

        repo_id = result1["repo_id"]
        initial_node_count = graph_store.get_node_count()
        initial_edge_count = graph_store.get_edge_count()

        assert initial_node_count > 0
        assert initial_edge_count > 0

        # Delete one file and commit the deletion (so git tracks it)
        (temp_test_repo / "example.py").unlink()
        subprocess.run(
            ["git", "add", "-A"], cwd=temp_test_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Delete example.py"],
            cwd=temp_test_repo,
            check=True,
            capture_output=True,
        )

        # Re-index (incremental mode will detect the deletion via git diff)
        pipeline.index(
            repo_name,
            force=True,
            dry_run=False,
        )

        # Verify nodes were pruned
        final_node_count = graph_store.get_node_count()
        final_edge_count = graph_store.get_edge_count()

        # Should have fewer nodes and edges after deletion
        assert final_node_count < initial_node_count, (
            "Graph nodes should be pruned when files are deleted"
        )
        assert final_edge_count < initial_edge_count, (
            "Graph edges should be pruned when files are deleted"
        )

        # Verify no nodes remain for deleted file
        py_file_id = metadata.get_file_id(repo_id, "example.py")
        if py_file_id:
            py_nodes = graph_store.get_nodes_for_file(py_file_id)
            assert len(py_nodes) == 0

    def test_graph_statistics_in_result(self, temp_test_repo, tmp_path):
        """Test that indexing result includes graph statistics."""
        # Setup
        config = KBConfig()
        db_path = tmp_path / "test.db"
        lance_path = tmp_path / "lance"

        metadata = SQLiteMetadataStore(db_path)
        metadata.initialize()  # Initialize database tables
        lancedb = LanceDBStore(lance_path)
        graph_store = GraphStore(db_path)

        pipeline = IngestionPipeline(
            config=config,
            lancedb=lancedb,
            metadata=metadata,
            graph_store=graph_store,
        )

        # Index the repository (need to register it first)
        repo_name = "test_repo"
        metadata.record_repo(
            name=repo_name, path=str(temp_test_repo), default_embed_model="small"
        )

        result = pipeline.index(
            repo_name,
            force=True,
            dry_run=False,
        )

        # Verify graph statistics are included in result
        assert "graph_nodes_created" in result
        assert "graph_edges_created" in result
        assert result["graph_nodes_created"] > 0
        assert result["graph_edges_created"] > 0
