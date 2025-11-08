from __future__ import annotations

from typing import Optional

from sqlalchemy import UniqueConstraint, Index
from sqlmodel import Field, SQLModel


# =====================
# Core Metadata Tables
# =====================


class Repo(SQLModel, table=True):
    __tablename__ = "repos"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    root_path: str
    default_embed_model: str = Field(default="large")

    # Timestamps (managed by DML in store methods)
    created_at: Optional[str] = Field(default=None)
    updated_at: Optional[str] = Field(default=None)


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: int = Field(foreign_key="repos.id")

    commit_sha: str
    branch: str
    embed_model: str
    status: str = Field(default="running")

    # Metrics/counters
    files_indexed: int = Field(default=0)
    chunks_indexed: int = Field(default=0)
    vectors_written: int = Field(default=0)
    chunks_skipped: int = Field(default=0)
    chunks_pruned: int = Field(default=0)  # Added for Phase 6: tracks chunks removed from deleted files

    # Notes and lifecycle
    notes: Optional[str] = Field(default=None)
    ended_at: Optional[str] = Field(default=None)

    created_at: Optional[str] = Field(default=None)


class File(SQLModel, table=True):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("repo_id", "path", name="uq_files_repo_path"),
        Index("ix_files_repo_id", "repo_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: int = Field(foreign_key="repos.id")

    path: str
    ext: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None)
    is_binary: bool = Field(default=False)
    size_bytes: Optional[int] = Field(default=None)

    latest_commit_sha: Optional[str] = Field(default=None)

    created_at: Optional[str] = Field(default=None)
    updated_at: Optional[str] = Field(default=None)


class ChunkContent(SQLModel, table=True):
    __tablename__ = "chunk_content"
    __table_args__ = (
        UniqueConstraint(
            "repo_id",
            "file_id",
            "text_hash",
            "embed_model",
            name="uq_chunk_content_identity",
        ),
        Index("ix_chunk_content_repo_file", "repo_id", "file_id"),
    )

    # Stable id for content (UUID string)
    id: str = Field(primary_key=True)

    repo_id: int = Field(foreign_key="repos.id")
    file_id: int = Field(foreign_key="files.id")

    text_hash: str
    embed_model: str

    first_indexed_at: Optional[str] = Field(default=None)
    last_indexed_at: Optional[str] = Field(default=None)


class ChunkLocation(SQLModel, table=True):
    __tablename__ = "chunk_locations"
    __table_args__ = (
        UniqueConstraint(
            "content_id",
            "start_line",
            "end_line",
            name="uq_chunk_location_unique",
        ),
        Index("ix_chunk_locations_content", "content_id"),
    )

    id: str = Field(primary_key=True)

    content_id: str = Field(foreign_key="chunk_content.id")

    start_line: int
    end_line: int

    symbol_kind: Optional[str] = Field(default=None)
    symbol_name: Optional[str] = Field(default=None)
    symbol_path: Optional[str] = Field(default=None)

    last_seen_at: Optional[str] = Field(default=None)


# =====================
# Code Graph Tables
# =====================


class CodeNode(SQLModel, table=True):
    """Represents a code entity in the code graph (function, class, table, component, etc.)."""
    __tablename__ = "code_nodes"
    __table_args__ = (
        UniqueConstraint("repo_id", "file_id", "qualified_name", "start_line", name="uq_code_node_identity"),
        Index("ix_code_nodes_qualified_name", "qualified_name"),
        Index("ix_code_nodes_name", "name"),
        Index("ix_code_nodes_type", "node_type"),
        Index("ix_code_nodes_file", "file_id"),
        Index("ix_code_nodes_repo", "repo_id"),
        Index("ix_code_nodes_location", "repo_id", "file_id", "start_line"),
    )

    # Identity
    id: str = Field(primary_key=True)  # UUID

    # Type and naming
    node_type: str  # 'function', 'class', 'method', 'table', 'view', 'component', 'interface', 'type', 'enum'
    name: str  # Simple name (e.g., "calculate_total")
    qualified_name: str  # Full path (e.g., "myapp.utils.math.calculate_total")

    # Location
    repo_id: int = Field(foreign_key="repos.id")
    file_id: int = Field(foreign_key="files.id")
    start_line: int
    end_line: int

    # Language context
    language: str  # 'python', 'typescript', 'sql', 'svelte'

    # Optional metadata (language-specific)
    signature: Optional[str] = Field(default=None)  # Function signature or type definition
    docstring: Optional[str] = Field(default=None)  # Documentation/comments
    visibility: Optional[str] = Field(default=None)  # 'public', 'private', 'protected', 'exported'
    is_async: bool = Field(default=False)
    is_generator: bool = Field(default=False)

    # Lifecycle tracking
    commit_sha: str
    branch: str
    first_seen_at: str
    last_seen_at: str


class CodeEdge(SQLModel, table=True):
    """Represents a relationship between code entities in the code graph."""
    __tablename__ = "code_edges"
    __table_args__ = (
        UniqueConstraint("source_node_id", "target_node_id", "edge_type", "line_number", name="uq_code_edge_identity"),
        Index("ix_code_edges_source", "source_node_id", "edge_type"),
        Index("ix_code_edges_target", "target_node_id", "edge_type"),
        Index("ix_code_edges_type", "edge_type"),
        Index("ix_code_edges_bidirectional", "source_node_id", "target_node_id"),
        Index("ix_code_edges_source_type_target", "source_node_id", "edge_type", "target_node_id"),
        Index("ix_code_edges_target_type_source", "target_node_id", "edge_type", "source_node_id"),
    )

    # Identity
    id: str = Field(primary_key=True)  # UUID

    # Relationship
    source_node_id: str = Field(foreign_key="code_nodes.id")
    target_node_id: str = Field(foreign_key="code_nodes.id")
    edge_type: str  # 'calls', 'imports', 'inherits', 'implements', 'depends_on_table', etc.

    # Context
    line_number: Optional[int] = Field(default=None)  # Where this relationship occurs in source
    is_direct: bool = Field(default=True)  # Direct vs. transitive relationship

    # Optional metadata
    relationship_metadata: Optional[str] = Field(default=None)  # JSON for language-specific details

    # Lifecycle
    commit_sha: str
    first_seen_at: str
    last_seen_at: str


class NodeAlias(SQLModel, table=True):
    """Tracks multiple names for the same entity (imports, renames, etc.)."""
    __tablename__ = "node_aliases"
    __table_args__ = (
        UniqueConstraint("node_id", "file_id", "alias_qualified_name", name="uq_node_alias_identity"),
        Index("ix_node_aliases_name", "alias_name"),
        Index("ix_node_aliases_qualified", "alias_qualified_name"),
        Index("ix_node_aliases_node", "node_id"),
    )

    # Identity
    id: str = Field(primary_key=True)  # UUID

    # References
    node_id: str = Field(foreign_key="code_nodes.id")
    file_id: int = Field(foreign_key="files.id")

    # Alias information
    alias_name: str  # Imported/aliased name
    alias_qualified_name: str  # Full alias path
    line_number: Optional[int] = Field(default=None)


class CrossRepoReference(SQLModel, table=True):
    """Tracks relationships across repository boundaries (external dependencies)."""
    __tablename__ = "cross_repo_references"
    __table_args__ = (
        Index("ix_cross_repo_source", "source_node_id"),
        Index("ix_cross_repo_package", "target_package", "target_module"),
    )

    # Identity
    id: str = Field(primary_key=True)  # UUID

    # Source (current repo)
    source_node_id: str = Field(foreign_key="code_nodes.id")
    source_repo_id: int = Field(foreign_key="repos.id")

    # Target (external reference)
    target_package: str  # npm package, pip package, etc.
    target_module: Optional[str] = Field(default=None)
    target_symbol: Optional[str] = Field(default=None)
    reference_type: str  # 'import', 'call', 'type_reference'

    # Location
    file_id: int = Field(foreign_key="files.id")
    line_number: Optional[int] = Field(default=None)

    # Lifecycle
    first_seen_at: str
    last_seen_at: str
