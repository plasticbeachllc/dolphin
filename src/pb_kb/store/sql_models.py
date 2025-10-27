from __future__ import annotations

from typing import Optional

from sqlalchemy import UniqueConstraint, Index
from sqlmodel import Field, SQLModel


class Repo(SQLModel, table=True):
    __tablename__ = "repos"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    root_path: str
    default_embed_model: str = Field(default="small")

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


class ChunkMeta(SQLModel, table=True):
    __tablename__ = "chunks_meta"
    __table_args__ = (
        UniqueConstraint(
            "repo_id",
            "file_id",
            "start_line",
            "end_line",
            "text_hash",
            name="uq_chunk_meta_location_hash",
        ),
        Index("ix_chunks_meta_repo_file", "repo_id", "file_id"),
    )

    # Stable id for chunk (UUID string)
    id: str = Field(primary_key=True)

    repo_id: int = Field(foreign_key="repos.id")
    file_id: int = Field(foreign_key="files.id")

    text_hash: str
    start_line: int
    end_line: int

    symbol_kind: Optional[str] = Field(default=None)
    symbol_name: Optional[str] = Field(default=None)
    symbol_path: Optional[str] = Field(default=None)

    embed_model: str
    indexed_at: str  # ISO timestamp string
