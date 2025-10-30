from __future__ import annotations

from typing import Optional

from sqlalchemy import UniqueConstraint, Index
from sqlmodel import Field, SQLModel


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
