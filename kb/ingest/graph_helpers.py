"""Helper functions for extracting and storing code graph data during indexing."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from kb.chunkers.graph_types import GraphEdge as ChunkerGraphEdge, GraphNode as ChunkerGraphNode
from kb.store.graph_store import GraphStore


def extract_graph_from_file(
    file_path: Path,
    language: str,
    text: str,
    repo_config: dict[str, Any] | None = None,
) -> tuple[list[ChunkerGraphNode], list[ChunkerGraphEdge]]:
    """Extract graph nodes and edges from a file.

    This calls the appropriate chunker module's extract_graph_data() function
    or uses the enhanced graph intelligence extractors for Python and TypeScript.

    Args:
        file_path: Absolute path to the file
        language: Programming language
        text: File content
        repo_config: Optional repository-specific configuration

    Returns:
        Tuple of (nodes, edges)
    """
    lang_key = language.lower() if language else ""

    # Try to use enhanced graph intelligence extractors for Python and TypeScript
    if lang_key in (
        "python",
        "typescript",
        "typescriptreact",
        "javascript",
        "javascriptreact",
    ):
        try:
            return _extract_with_intelligence(file_path, lang_key, text)
        except Exception as e:
            print(
                f"  Warning: Enhanced graph extraction failed for {file_path}, falling back to basic: {e}"
            )

    # Fall back to basic chunker extraction
    import kb.chunkers.py_chunker as py_chunker
    import kb.chunkers.sql_chunker as sql_chunker
    import kb.chunkers.svelte_chunker as svelte_chunker
    import kb.chunkers.ts_chunker as ts_chunker

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

    chunker_module = chunker_map.get(lang_key)

    if not chunker_module or not hasattr(chunker_module, "extract_graph_data"):
        # Language doesn't support graph extraction
        return [], []

    # Call the module's extract_graph_data function
    try:
        # Type narrowing: we've checked hasattr for extract_graph_data
        extract_fn = getattr(chunker_module, "extract_graph_data")
        nodes, edges = extract_fn(text)
        return nodes, edges
    except Exception as e:
        # Log but don't fail - graph extraction is optional
        print(f"  Warning: Graph extraction failed for {file_path}: {e}")
        return [], []


def _extract_with_intelligence(
    file_path: Path,
    language: str,
    text: str,
) -> tuple[list[ChunkerGraphNode], list[ChunkerGraphEdge]]:
    """Extract graph data using enhanced graph intelligence extractors.

    Args:
        file_path: Path to the file
        language: Programming language
        text: File content

    Returns:
        Tuple of (nodes, edges) in chunker format
    """
    from kb.graph_intelligence.extractors import (
        PythonCallGraphExtractor,
        TypeScriptCallGraphExtractor,
    )

    # Use appropriate extractor
    if language == "python":
        extractor = PythonCallGraphExtractor()
    else:  # TypeScript/JavaScript
        extractor = TypeScriptCallGraphExtractor()

    # Extract nodes and edges
    # Note: We pass dummy IDs since we don't have repo_id/file_id at this stage
    # The store_graph_data function will handle the actual IDs
    nodes, edges = extractor.extract(
        str(file_path),
        text,
        repo_id=0,  # Placeholder
        file_id=0,  # Placeholder
        commit_sha="",  # Placeholder
        branch="",  # Placeholder
    )

    # Convert to chunker format
    chunker_nodes = []
    for node in nodes:
        chunker_nodes.append(
            ChunkerGraphNode(
                node_type=node.node_type.value,
                name=node.name,
                qualified_name=node.qualified_name or node.name,
                start_line=node.start_line or 0,
                end_line=node.end_line or 0,
            )
        )

    chunker_edges = []
    for edge in edges:
        # Find the qualified names for source and target
        source_node = next((n for n in nodes if n.id == edge.source_id), None)
        target_node = next((n for n in nodes if n.id == edge.target_id), None)

        if source_node and target_node:
            chunker_edges.append(
                ChunkerGraphEdge(
                    source_name=source_node.qualified_name or source_node.name,
                    target_name=target_node.qualified_name or target_node.name,
                    edge_type=edge.edge_type.value,
                    line_number=int(edge.attributes.get("call_line") or edge.attributes.get("import_line") or 0),
                )
            )

    return chunker_nodes, chunker_edges


def store_graph_data(
    graph_store: GraphStore,
    nodes: list[ChunkerGraphNode],
    edges: list[ChunkerGraphEdge],
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
                source_node = graph_store.find_node_by_qualified_name(edge.source_name, repo_id=repo_id)
                if source_node:
                    source_id = source_node["id"]

            if not target_id:
                # Try to find existing node
                target_node = graph_store.find_node_by_qualified_name(edge.target_name, repo_id=repo_id)
                if target_node:
                    target_id = target_node["id"]

            if source_id and target_id:
                graph_store.upsert_edge(
                    source_node_id=source_id,
                    target_node_id=target_id,
                    edge_type=edge.edge_type,
                    repo_id=repo_id,
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


def cleanup_graph_for_file(graph_store: GraphStore, file_id: int) -> tuple[int, int]:
    """Clean up graph data for a deleted or ignored file.

    Args:
        graph_store: Graph store instance
        file_id: File ID

    Returns:
        Tuple of (nodes_deleted, edges_deleted)
    """

    edges_deleted = 0

    try:
        with graph_store._connect() as conn, closing(conn.cursor()) as cur:  # type: ignore[attr-defined]
            cur.execute(
                (
                    "WITH nodes AS (SELECT id FROM code_nodes WHERE file_id = ?) "
                    "SELECT COUNT(*) FROM code_edges "
                    "WHERE source_node_id IN (SELECT id FROM nodes) "
                    "   OR target_node_id IN (SELECT id FROM nodes)"
                ),
                (file_id,),
            )
            row = cur.fetchone()
            if row is not None:
                edges_deleted = int(row[0])
    except Exception as e:
        print(f"  Warning: Failed to calculate graph edge cleanup for file {file_id}: {e}")

    try:
        nodes_deleted = graph_store.delete_nodes_for_file(file_id)
        return nodes_deleted, edges_deleted
    except Exception as e:
        print(f"  Warning: Failed to clean up graph data for file {file_id}: {e}")
        return 0, 0


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
