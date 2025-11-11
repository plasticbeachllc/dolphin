"""Helper functions for extracting and storing code graph data during indexing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kb.chunkers.graph_types import GraphNode, GraphEdge
from kb.chunkers.types import Chunk
from kb.store.graph_store import GraphStore


def extract_graph_from_file(
    file_path: Path,
    language: str,
    text: str,
    repo_config: dict[str, Any] | None = None,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Extract graph nodes and edges from a file.
    
    This calls the appropriate chunker module's extract_graph_data() function.
    
    Args:
        file_path: Absolute path to the file
        language: Programming language
        text: File content
        repo_config: Optional repository-specific configuration
        
    Returns:
        Tuple of (nodes, edges)
    """
    # Import chunker modules that have extract_graph_data functions
    import kb.chunkers.py_chunker as py_chunker
    import kb.chunkers.ts_chunker as ts_chunker
    import kb.chunkers.sql_chunker as sql_chunker
    import kb.chunkers.svelte_chunker as svelte_chunker
    
    # Map languages to chunker modules that support graph extraction
    chunker_map = {
        "python": py_chunker,
        "typescript": ts_chunker,
        "typescriptreact": ts_chunker,
        "javascript": ts_chunker,
        "javascriptreact": ts_chunker,
        "sql": sql_chunker,
        "svelte": svelte_chunker,
    }
    
    lang_key = language.lower() if language else ""
    chunker_module = chunker_map.get(lang_key)
    
    if not chunker_module or not hasattr(chunker_module, 'extract_graph_data'):
        # Language doesn't support graph extraction
        return [], []
    
    # Call the module's extract_graph_data function
    try:
        nodes, edges = chunker_module.extract_graph_data(text)
        return nodes, edges
    except Exception as e:
        # Log but don't fail - graph extraction is optional
        print(f"  Warning: Graph extraction failed for {file_path}: {e}")
        return [], []


def store_graph_data(
    graph_store: GraphStore,
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    *,
    repo_id: int,
    file_id: int,
    language: str,
    commit_sha: str,
    branch: str,
) -> dict[str, int]:
    """Store extracted graph nodes and edges.
    
    Args:
        graph_store: Graph store instance
        nodes: List of extracted nodes
        edges: List of extracted edges
        repo_id: Repository ID
        file_id: File ID
        language: Programming language
        commit_sha: Git commit SHA
        branch: Git branch name
        
    Returns:
        Statistics dict with counts of nodes and edges created
    """
    # Track created entities
    node_ids_map: dict[str, str] = {}  # qualified_name -> node_id
    nodes_created = 0
    edges_created = 0
    
    # Store nodes
    for node in nodes:
        try:
            node_id = graph_store.upsert_node(
                node_type=node.node_type,
                name=node.name,
                qualified_name=node.qualified_name,
                repo_id=repo_id,
                file_id=file_id,
                start_line=node.start_line,
                end_line=node.end_line,
                language=language,
                commit_sha=commit_sha,
                branch=branch,
            )
            node_ids_map[node.qualified_name] = node_id
            nodes_created += 1
        except Exception as e:
            print(f"  Warning: Failed to store node {node.qualified_name}: {e}")
    
    # Store edges
    for edge in edges:
        try:
            # Resolve source and target node IDs
            source_id = node_ids_map.get(edge.source_name)
            target_id = node_ids_map.get(edge.target_name)
            
            # Skip edge if we couldn't resolve both endpoints
            # (This can happen for external references or incomplete extraction)
            if not source_id:
                # Try to find existing node
                source_node = graph_store.find_node_by_qualified_name(
                    edge.source_name, repo_id=repo_id
                )
                if source_node:
                    source_id = source_node["id"]
            
            if not target_id:
                # Try to find existing node
                target_node = graph_store.find_node_by_qualified_name(
                    edge.target_name, repo_id=repo_id
                )
                if target_node:
                    target_id = target_node["id"]
            
            if source_id and target_id:
                graph_store.upsert_edge(
                    source_node_id=source_id,
                    target_node_id=target_id,
                    edge_type=edge.edge_type,
                    line_number=edge.line_number,
                    commit_sha=commit_sha,
                )
                edges_created += 1
        except Exception as e:
            print(f"  Warning: Failed to store edge {edge.source_name} -> {edge.target_name}: {e}")
    
    return {
        "nodes_created": nodes_created,
        "edges_created": edges_created,
    }


def cleanup_graph_for_file(graph_store: GraphStore, file_id: int) -> int:
    """Clean up graph data for a deleted or ignored file.
    
    Args:
        graph_store: Graph store instance
        file_id: File ID
        
    Returns:
        Number of nodes deleted (edges cascade automatically)
    """
    try:
        return graph_store.delete_nodes_for_file(file_id)
    except Exception as e:
        print(f"  Warning: Failed to clean up graph data for file {file_id}: {e}")
        return 0


def cleanup_graph_for_repo(graph_store: GraphStore, repo_id: int) -> int:
    """Clean up all graph data for a repository.
    
    Args:
        graph_store: Graph store instance
        repo_id: Repository ID
        
    Returns:
        Number of nodes deleted (edges cascade automatically)
    """
    try:
        return graph_store.delete_nodes_for_repo(repo_id)
    except Exception as e:
        print(f"  Warning: Failed to clean up graph data for repo {repo_id}: {e}")
        return 0