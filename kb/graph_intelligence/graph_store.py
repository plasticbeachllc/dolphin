"""Graph store wrapper for graph intelligence operations."""

import sqlite3
from contextlib import closing
from datetime import datetime
from typing import List, Optional

from kb.store.graph_store import GraphStore as BaseGraphStore

from .models import GraphEdge, GraphMetrics, GraphNode


class GraphStore:
    """Wrapper for graph store with intelligence-specific operations."""

    def __init__(self, base_store: BaseGraphStore):
        """Initialize with existing graph store.

        Args:
            base_store: The base GraphStore instance
        """
        self.base_store = base_store

    def upsert_nodes(self, nodes: List[GraphNode]) -> List[str]:
        """Batch insert or update graph nodes.

        Args:
            nodes: List of GraphNode objects to upsert

        Returns:
            List of node IDs
        """
        node_ids = []
        for node in nodes:
            # Extract metadata fields
            metadata = node.metadata or {}
            file_id = metadata.get("file_id", 0)
            commit_sha = metadata.get("commit_sha", "")
            branch = metadata.get("branch", "main")
            is_async = metadata.get("is_async", False)

            node_id = self.base_store.upsert_node(
                node_id=node.id,
                node_type=node.node_type.value,
                name=node.name,
                qualified_name=node.qualified_name or node.name,
                repo_id=node.repo_id,
                file_id=file_id,
                start_line=node.start_line or 0,
                end_line=node.end_line or 0,
                language=node.language,
                commit_sha=commit_sha,
                branch=branch,
                signature=node.signature,
                docstring=node.docstring,
                is_async=is_async,
            )
            node_ids.append(node_id)

        return node_ids

    def upsert_edges(self, edges: List[GraphEdge]) -> List[str]:
        """Batch insert or update graph edges.

        Args:
            edges: List of GraphEdge objects to upsert

        Returns:
            List of edge IDs
        """
        edge_ids = []
        for edge in edges:
            # Extract metadata
            attributes = edge.attributes or {}
            commit_sha = attributes.get("commit_sha", "")
            line_number = attributes.get("call_line") or attributes.get("import_line")

            edge_id = self.base_store.upsert_edge(
                source_node_id=edge.source_id,
                target_node_id=edge.target_id,
                edge_type=edge.edge_type.value,
                commit_sha=commit_sha,
                line_number=line_number,
                is_direct=True,
                relationship_metadata=str(attributes) if attributes else None,
            )
            edge_ids.append(edge_id)

        return edge_ids

    def upsert_metrics(self, metrics: GraphMetrics) -> None:
        """Insert or update graph metrics for a node.

        Args:
            metrics: GraphMetrics object
        """
        with self.base_store._connect() as conn, closing(conn.cursor()) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO graph_metrics (
                        node_id, pagerank, betweenness_centrality, in_degree,
                        out_degree, cyclomatic_complexity, community_id, computed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(node_id)
                    DO UPDATE SET
                        pagerank = excluded.pagerank,
                        betweenness_centrality = excluded.betweenness_centrality,
                        in_degree = excluded.in_degree,
                        out_degree = excluded.out_degree,
                        cyclomatic_complexity = excluded.cyclomatic_complexity,
                        community_id = excluded.community_id,
                        computed_at = datetime('now')
                    """,
                    (
                        metrics.node_id,
                        metrics.pagerank,
                        metrics.betweenness_centrality,
                        metrics.in_degree,
                        metrics.out_degree,
                        metrics.cyclomatic_complexity,
                        metrics.community_id,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_metrics(self, node_id: str) -> Optional[GraphMetrics]:
        """Get metrics for a node.

        Args:
            node_id: Node UUID

        Returns:
            GraphMetrics or None if not found
        """
        with self.base_store._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT node_id, pagerank, betweenness_centrality, in_degree,
                       out_degree, cyclomatic_complexity, community_id
                FROM graph_metrics WHERE node_id = ?
                """,
                (node_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return GraphMetrics(
                node_id=str(row[0]),
                pagerank=row[1],
                betweenness_centrality=row[2],
                in_degree=int(row[3]) if row[3] is not None else 0,
                out_degree=int(row[4]) if row[4] is not None else 0,
                cyclomatic_complexity=int(row[5]) if row[5] is not None else None,
                community_id=int(row[6]) if row[6] is not None else None,
            )

    def get_nodes_by_file(self, file_path: str, repo_id: int) -> List[GraphNode]:
        """Get all nodes in a file.

        Args:
            file_path: Path to the file
            repo_id: Repository ID

        Returns:
            List of GraphNode objects
        """
        # Use the base store's method to get nodes
        nodes = self.base_store.get_nodes_by_file_path(file_path, repo_id)

        # Convert to GraphNode objects
        from .models import NodeType

        result = []
        for node_data in nodes:
            try:
                result.append(
                    GraphNode(
                        id=node_data["id"],
                        repo_id=node_data["repo_id"],
                        node_type=NodeType(node_data["node_type"]),
                        name=node_data["name"],
                        qualified_name=node_data["qualified_name"],
                        file_path=file_path,
                        start_line=node_data["start_line"],
                        end_line=node_data["end_line"],
                        language=node_data["language"],
                        signature=node_data.get("signature"),
                        docstring=node_data.get("docstring"),
                        metadata={
                            "file_id": node_data["file_id"],
                            "commit_sha": node_data["commit_sha"],
                            "branch": node_data["branch"],
                        },
                    )
                )
            except (KeyError, ValueError):
                # Skip malformed nodes
                continue

        return result

    def get_edges_by_source(self, source_node_id: str) -> List[GraphEdge]:
        """Get all edges originating from a node.

        Args:
            source_node_id: Source node UUID

        Returns:
            List of GraphEdge objects
        """
        edges_data = self.base_store.get_edges_by_source(source_node_id)

        # Convert to GraphEdge objects
        from .models import EdgeType

        result = []
        for edge_data in edges_data:
            try:
                result.append(
                    GraphEdge(
                        source_id=edge_data["source_node_id"],
                        target_id=edge_data["target_node_id"],
                        edge_type=EdgeType(edge_data["edge_type"]),
                        weight=1.0,
                        attributes={
                            "line_number": edge_data.get("line_number"),
                            "is_direct": edge_data.get("is_direct"),
                        },
                    )
                )
            except (KeyError, ValueError):
                # Skip malformed edges
                continue

        return result

    def delete_nodes_by_file(self, file_path: str, repo_id: int) -> int:
        """Delete all nodes for a file (for re-indexing).

        Args:
            file_path: Path to the file
            repo_id: Repository ID

        Returns:
            Number of nodes deleted
        """
        # Get the file_id first
        with self.base_store._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                "SELECT id FROM files WHERE path = ? AND repo_id = ?",
                (file_path, repo_id),
            )
            row = cur.fetchone()
            if not row:
                return 0

            file_id = row[0]

            try:
                # Delete nodes (edges will be cascaded)
                cur.execute(
                    "DELETE FROM code_nodes WHERE file_id = ? AND repo_id = ?",
                    (file_id, repo_id),
                )
                deleted_count = cur.rowcount
                conn.commit()
                return deleted_count
            except Exception:
                conn.rollback()
                raise
