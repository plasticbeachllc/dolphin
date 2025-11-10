"""Graph database store for code relationships and navigation.

This module provides CRUD operations for the code graph database,
which tracks code entities (nodes), their relationships (edges),
and cross-repository references.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from kb.chunkers.graph_types import GraphNode, GraphEdge


class GraphStore:
    """Graph database store for code entities and relationships."""

    def __init__(self, db_path: Path) -> None:
        """Initialize graph store with database path.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        """Create a database connection with proper configuration."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        with closing(conn.cursor()) as cur:
            cur.execute("PRAGMA foreign_keys = ON;")
        return conn

    # =====================
    # Node Operations
    # =====================

    def upsert_node(
        self,
        *,
        node_id: str | None = None,
        node_type: str,
        name: str,
        qualified_name: str,
        repo_id: int,
        file_id: int,
        start_line: int,
        end_line: int,
        language: str,
        commit_sha: str,
        branch: str,
        signature: str | None = None,
        docstring: str | None = None,
        visibility: str | None = None,
        is_async: bool = False,
        is_generator: bool = False,
    ) -> str:
        """Insert or update a code node.
        
        Args:
            node_id: Optional node ID (UUID). If None, a new one is generated.
            node_type: Type of node (function, class, method, etc.)
            name: Simple name of the entity
            qualified_name: Fully qualified name
            repo_id: Repository ID
            file_id: File ID
            start_line: Starting line number
            end_line: Ending line number
            language: Programming language
            commit_sha: Git commit SHA
            branch: Git branch name
            signature: Optional function signature or type definition
            docstring: Optional documentation
            visibility: Optional visibility (public, private, etc.)
            is_async: Whether the entity is async
            is_generator: Whether the entity is a generator
            
        Returns:
            The node ID (UUID string)
        """
        if node_id is None:
            node_id = str(uuid.uuid4())

        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO code_nodes (
                        id, node_type, name, qualified_name, repo_id, file_id,
                        start_line, end_line, language, signature, docstring,
                        visibility, is_async, is_generator, commit_sha, branch,
                        first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    ON CONFLICT(repo_id, file_id, qualified_name, start_line)
                    DO UPDATE SET
                        node_type = excluded.node_type,
                        name = excluded.name,
                        end_line = excluded.end_line,
                        signature = excluded.signature,
                        docstring = excluded.docstring,
                        visibility = excluded.visibility,
                        is_async = excluded.is_async,
                        is_generator = excluded.is_generator,
                        commit_sha = excluded.commit_sha,
                        branch = excluded.branch,
                        last_seen_at = datetime('now')
                    RETURNING id
                    """,
                    (
                        node_id, node_type, name, qualified_name, repo_id, file_id,
                        start_line, end_line, language, signature, docstring,
                        visibility, is_async, is_generator, commit_sha, branch
                    ),
                )
                row = cur.fetchone()
                if row:
                    node_id = str(row[0])
                
                # Update FTS5 index
                cur.execute(
                    """
                    INSERT OR REPLACE INTO code_nodes_fts
                    (node_id, qualified_name, name, signature, docstring)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (node_id, qualified_name, name, signature, docstring)
                )
                
                conn.commit()
                return node_id
            except Exception:
                conn.rollback()
                raise

    def get_node_by_id(self, node_id: str) -> dict[str, Any] | None:
        """Get a node by its ID.
        
        Args:
            node_id: Node UUID
            
        Returns:
            Node data as dict or None if not found
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT id, node_type, name, qualified_name, repo_id, file_id,
                       start_line, end_line, language, signature, docstring,
                       visibility, is_async, is_generator, commit_sha, branch,
                       first_seen_at, last_seen_at
                FROM code_nodes WHERE id = ?
                """,
                (node_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            
            return {
                "id": str(row[0]),
                "node_type": str(row[1]),
                "name": str(row[2]),
                "qualified_name": str(row[3]),
                "repo_id": int(row[4]),
                "file_id": int(row[5]),
                "start_line": int(row[6]),
                "end_line": int(row[7]),
                "language": str(row[8]),
                "signature": row[9],
                "docstring": row[10],
                "visibility": row[11],
                "is_async": bool(row[12]),
                "is_generator": bool(row[13]),
                "commit_sha": str(row[14]),
                "branch": str(row[15]),
                "first_seen_at": row[16],
                "last_seen_at": row[17],
            }

    def find_node_by_qualified_name(
        self, qualified_name: str, repo_id: int | None = None
    ) -> dict[str, Any] | None:
        """Find a node by its qualified name.
        
        Args:
            qualified_name: Fully qualified name
            repo_id: Optional repository filter
            
        Returns:
            Node data as dict or None if not found
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            if repo_id is not None:
                cur.execute(
                    """
                    SELECT id, node_type, name, qualified_name, repo_id, file_id,
                           start_line, end_line, language, signature, docstring,
                           visibility, is_async, is_generator, commit_sha, branch,
                           first_seen_at, last_seen_at
                    FROM code_nodes
                    WHERE qualified_name = ? AND repo_id = ?
                    ORDER BY last_seen_at DESC
                    LIMIT 1
                    """,
                    (qualified_name, repo_id)
                )
            else:
                cur.execute(
                    """
                    SELECT id, node_type, name, qualified_name, repo_id, file_id,
                           start_line, end_line, language, signature, docstring,
                           visibility, is_async, is_generator, commit_sha, branch,
                           first_seen_at, last_seen_at
                    FROM code_nodes
                    WHERE qualified_name = ?
                    ORDER BY last_seen_at DESC
                    LIMIT 1
                    """,
                    (qualified_name,)
                )
            
            row = cur.fetchone()
            if not row:
                return None
            
            return {
                "id": str(row[0]),
                "node_type": str(row[1]),
                "name": str(row[2]),
                "qualified_name": str(row[3]),
                "repo_id": int(row[4]),
                "file_id": int(row[5]),
                "start_line": int(row[6]),
                "end_line": int(row[7]),
                "language": str(row[8]),
                "signature": row[9],
                "docstring": row[10],
                "visibility": row[11],
                "is_async": bool(row[12]),
                "is_generator": bool(row[13]),
                "commit_sha": str(row[14]),
                "branch": str(row[15]),
                "first_seen_at": row[16],
                "last_seen_at": row[17],
            }

    def get_nodes_for_file(self, file_id: int) -> list[dict[str, Any]]:
        """Get all nodes for a file.
        
        Args:
            file_id: File ID
            
        Returns:
            List of node dicts
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT id, node_type, name, qualified_name, repo_id, file_id,
                       start_line, end_line, language, signature, docstring,
                       visibility, is_async, is_generator, commit_sha, branch,
                       first_seen_at, last_seen_at
                FROM code_nodes
                WHERE file_id = ?
                ORDER BY start_line
                """,
                (file_id,)
            )
            rows = cur.fetchall() or []
            
            return [
                {
                    "id": str(row[0]),
                    "node_type": str(row[1]),
                    "name": str(row[2]),
                    "qualified_name": str(row[3]),
                    "repo_id": int(row[4]),
                    "file_id": int(row[5]),
                    "start_line": int(row[6]),
                    "end_line": int(row[7]),
                    "language": str(row[8]),
                    "signature": row[9],
                    "docstring": row[10],
                    "visibility": row[11],
                    "is_async": bool(row[12]),
                    "is_generator": bool(row[13]),
                    "commit_sha": str(row[14]),
                    "branch": str(row[15]),
                    "first_seen_at": row[16],
                    "last_seen_at": row[17],
                }
                for row in rows
            ]

    # =====================
    # Edge Operations
    # =====================

    def upsert_edge(
        self,
        *,
        edge_id: str | None = None,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        line_number: int | None = None,
        is_direct: bool = True,
        relationship_metadata: str | None = None,
        commit_sha: str,
    ) -> str:
        """Insert or update a code edge.
        
        Args:
            edge_id: Optional edge ID (UUID). If None, a new one is generated.
            source_node_id: Source node UUID
            target_node_id: Target node UUID
            edge_type: Type of relationship
            line_number: Optional line number where relationship occurs
            is_direct: Whether this is a direct relationship
            relationship_metadata: Optional JSON metadata
            commit_sha: Git commit SHA
            
        Returns:
            The edge ID (UUID string)
        """
        if edge_id is None:
            edge_id = str(uuid.uuid4())

        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO code_edges (
                        id, source_node_id, target_node_id, edge_type,
                        line_number, is_direct, relationship_metadata,
                        commit_sha, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    ON CONFLICT(source_node_id, target_node_id, edge_type, line_number)
                    DO UPDATE SET
                        is_direct = excluded.is_direct,
                        relationship_metadata = excluded.relationship_metadata,
                        commit_sha = excluded.commit_sha,
                        last_seen_at = datetime('now')
                    RETURNING id
                    """,
                    (
                        edge_id, source_node_id, target_node_id, edge_type,
                        line_number, is_direct, relationship_metadata, commit_sha
                    ),
                )
                row = cur.fetchone()
                if row:
                    edge_id = str(row[0])
                
                conn.commit()
                return edge_id
            except Exception:
                conn.rollback()
                raise

    def get_outgoing_edges(
        self, node_id: str, edge_type: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get outgoing edges from a node.
        
        Args:
            node_id: Source node UUID
            edge_type: Optional filter by edge type
            limit: Maximum number of edges to return
            
        Returns:
            List of edge dicts
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            if edge_type:
                cur.execute(
                    """
                    SELECT id, source_node_id, target_node_id, edge_type,
                           line_number, is_direct, relationship_metadata,
                           commit_sha, first_seen_at, last_seen_at
                    FROM code_edges
                    WHERE source_node_id = ? AND edge_type = ?
                    ORDER BY line_number
                    LIMIT ?
                    """,
                    (node_id, edge_type, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT id, source_node_id, target_node_id, edge_type,
                           line_number, is_direct, relationship_metadata,
                           commit_sha, first_seen_at, last_seen_at
                    FROM code_edges
                    WHERE source_node_id = ?
                    ORDER BY edge_type, line_number
                    LIMIT ?
                    """,
                    (node_id, limit)
                )
            
            rows = cur.fetchall() or []
            
            return [
                {
                    "id": str(row[0]),
                    "source_node_id": str(row[1]),
                    "target_node_id": str(row[2]),
                    "edge_type": str(row[3]),
                    "line_number": row[4],
                    "is_direct": bool(row[5]),
                    "relationship_metadata": row[6],
                    "commit_sha": str(row[7]),
                    "first_seen_at": row[8],
                    "last_seen_at": row[9],
                }
                for row in rows
            ]

    def get_incoming_edges(
        self, node_id: str, edge_type: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get incoming edges to a node.
        
        Args:
            node_id: Target node UUID
            edge_type: Optional filter by edge type
            limit: Maximum number of edges to return
            
        Returns:
            List of edge dicts
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            if edge_type:
                cur.execute(
                    """
                    SELECT id, source_node_id, target_node_id, edge_type,
                           line_number, is_direct, relationship_metadata,
                           commit_sha, first_seen_at, last_seen_at
                    FROM code_edges
                    WHERE target_node_id = ? AND edge_type = ?
                    ORDER BY line_number
                    LIMIT ?
                    """,
                    (node_id, edge_type, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT id, source_node_id, target_node_id, edge_type,
                           line_number, is_direct, relationship_metadata,
                           commit_sha, first_seen_at, last_seen_at
                    FROM code_edges
                    WHERE target_node_id = ?
                    ORDER BY edge_type, line_number
                    LIMIT ?
                    """,
                    (node_id, limit)
                )
            
            rows = cur.fetchall() or []
            
            return [
                {
                    "id": str(row[0]),
                    "source_node_id": str(row[1]),
                    "target_node_id": str(row[2]),
                    "edge_type": str(row[3]),
                    "line_number": row[4],
                    "is_direct": bool(row[5]),
                    "relationship_metadata": row[6],
                    "commit_sha": str(row[7]),
                    "first_seen_at": row[8],
                    "last_seen_at": row[9],
                }
                for row in rows
            ]

    # =====================
    # Cleanup Operations
    # =====================

    def delete_nodes_for_file(self, file_id: int) -> int:
        """Delete all nodes for a file.

        This will cascade delete edges and FTS entries.
        Edges are deleted both via CASCADE (if schema has it) and manually for compatibility.

        Args:
            file_id: File ID

        Returns:
            Number of nodes deleted
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                # Determine if there are nodes to clean up
                cur.execute(
                    "SELECT COUNT(*) FROM code_nodes WHERE file_id = ?",
                    (file_id,)
                )
                node_count = int(cur.fetchone()[0])

                if node_count == 0:
                    return 0

                # Delete edges (for backward compatibility with databases without CASCADE)
                # This also handles edges where the target is being deleted
                cur.execute(
                    (
                        "DELETE FROM code_edges "
                        "WHERE source_node_id IN (SELECT id FROM code_nodes WHERE file_id = ?) "
                        "   OR target_node_id IN (SELECT id FROM code_nodes WHERE file_id = ?)"
                    ),
                    (file_id, file_id)
                )

                # Delete from FTS5
                cur.execute(
                    (
                        "DELETE FROM code_nodes_fts "
                        "WHERE node_id IN (SELECT id FROM code_nodes WHERE file_id = ?)"
                    ),
                    (file_id,)
                )

                # Delete nodes
                cur.execute(
                    "DELETE FROM code_nodes WHERE file_id = ?",
                    (file_id,)
                )
                deleted = cur.rowcount

                conn.commit()
                return deleted
            except Exception:
                conn.rollback()
                raise

    def delete_nodes_for_repo(self, repo_id: int) -> int:
        """Delete all nodes for a repository.

        This will cascade delete edges and FTS entries.
        Edges are deleted both via CASCADE (if schema has it) and manually for compatibility.

        Args:
            repo_id: Repository ID

        Returns:
            Number of nodes deleted
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                # Determine if there are nodes to clean up
                cur.execute(
                    "SELECT COUNT(*) FROM code_nodes WHERE repo_id = ?",
                    (repo_id,)
                )
                node_count = int(cur.fetchone()[0])

                if node_count == 0:
                    return 0

                # Delete edges (for backward compatibility with databases without CASCADE)
                # This also handles edges where the target is being deleted
                cur.execute(
                    (
                        "DELETE FROM code_edges "
                        "WHERE source_node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?) "
                        "   OR target_node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)"
                    ),
                    (repo_id, repo_id)
                )

                # Delete from FTS5
                cur.execute(
                    (
                        "DELETE FROM code_nodes_fts "
                        "WHERE node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)"
                    ),
                    (repo_id,)
                )

                # Delete nodes
                cur.execute(
                    "DELETE FROM code_nodes WHERE repo_id = ?",
                    (repo_id,)
                )
                deleted = cur.rowcount

                conn.commit()
                return deleted
            except Exception:
                conn.rollback()
                raise

    # =====================
    # Statistics
    # =====================

    def get_node_count(self, repo_id: int | None = None) -> int:
        """Get count of nodes, optionally filtered by repo.
        
        Args:
            repo_id: Optional repository filter
            
        Returns:
            Number of nodes
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            if repo_id is not None:
                cur.execute(
                    "SELECT COUNT(*) FROM code_nodes WHERE repo_id = ?",
                    (repo_id,)
                )
            else:
                cur.execute("SELECT COUNT(*) FROM code_nodes")
            
            return int(cur.fetchone()[0])

    def get_edge_count(self, repo_id: int | None = None) -> int:
        """Get count of edges, optionally filtered by repo.
        
        Args:
            repo_id: Optional repository filter
            
        Returns:
            Number of edges
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            if repo_id is not None:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM code_edges
                    WHERE source_node_id IN (
                        SELECT id FROM code_nodes WHERE repo_id = ?
                    )
                    """,
                    (repo_id,)
                )
            else:
                cur.execute("SELECT COUNT(*) FROM code_edges")
            
            return int(cur.fetchone()[0])