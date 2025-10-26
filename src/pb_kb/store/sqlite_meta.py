from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlmodel import SQLModel, create_engine

# Fallback DDL if models fail to register (debug/edge cases)
_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS repos (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  root_path TEXT NOT NULL,
  default_embed_model TEXT NOT NULL DEFAULT 'small',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  commit_sha TEXT NOT NULL,
  branch TEXT NOT NULL,
  embed_model TEXT NOT NULL DEFAULT 'small',
  files_indexed INTEGER NOT NULL DEFAULT 0,
  chunks_indexed INTEGER NOT NULL DEFAULT 0,
  vectors_written INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running',
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  ended_at TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_repo_commit ON sessions(repo_id, commit_sha);

CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  ext TEXT,
  language TEXT,
  is_binary INTEGER NOT NULL DEFAULT 0,
  size_bytes INTEGER,
  latest_commit_sha TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (repo_id, path)
);
CREATE INDEX IF NOT EXISTS idx_files_repo_path ON files(repo_id, path);

CREATE TABLE IF NOT EXISTS chunk_texts (
  text_hash TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chunk_texts_created_at ON chunk_texts(created_at);

CREATE TABLE IF NOT EXISTS chunks_meta (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  commit_sha TEXT NOT NULL,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  symbol_kind TEXT,
  symbol_name TEXT,
  symbol_path TEXT,
  h1 TEXT,
  h2 TEXT,
  h3 TEXT,
  text_hash TEXT NOT NULL REFERENCES chunk_texts(text_hash) ON DELETE RESTRICT,
  token_count INTEGER NOT NULL,
  embed_model TEXT NOT NULL,
  vector_dim INTEGER NOT NULL,
  vector_collection TEXT NOT NULL,
  vector_id TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (repo_id, file_id, commit_sha, start_line, end_line, text_hash, embed_model)
);
CREATE INDEX IF NOT EXISTS idx_chunks_repo_file_commit ON chunks_meta(repo_id, file_id, commit_sha);
CREATE INDEX IF NOT EXISTS idx_chunks_text_hash ON chunks_meta(text_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_vector ON chunks_meta(vector_collection, vector_id);
"""


class SQLiteMetadataStore:
    """SQLite-backed metadata store using SQLModel for schema materialization."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        with closing(conn.cursor()) as cur:
            cur.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _engine(self):
        # Create SQLAlchemy engine for SQLModel and enforce foreign_keys pragma on connect.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{self.db_path}")
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-redef]
            try:
                dbapi_connection.execute("PRAGMA foreign_keys=ON")
            except Exception:
                pass
        return engine

    def initialize(self) -> None:
        """Ensure the database exists and the schema is applied idempotently via SQLModel."""
        engine = self._engine()
        try:
            # Import models at call time to register them with SQLModel.metadata
            from . import sql_models as _models  # noqa: F401
            # If no tables registered (edge case), raise to fallback to DDL
            if not SQLModel.metadata.tables:
                raise RuntimeError("SQLModel metadata empty; falling back to DDL")
            SQLModel.metadata.create_all(engine)
        except Exception:
            # Fallback to raw DDL (keeps Sprint 1 unblocked)
            with self._connect() as conn:
                conn.executescript(_SCHEMA_SQL)
                conn.commit()

    def record_repo(self, name: str, path: Path, *, default_embed_model: str = "small") -> None:
        """Insert or update a repo registration.

        Uses raw sqlite3 for simplicity; models are already materialized.
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                INSERT INTO repos (name, root_path, default_embed_model)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                  root_path=excluded.root_path,
                  default_embed_model=excluded.default_embed_model,
                  updated_at=datetime('now')
                """,
                (name, str(path), default_embed_model),
            )
            conn.commit()

    def summarize(self) -> dict[str, int]:
        """Return simple counts for key entities, 0 if tables missing."""
        counts: dict[str, int] = {"repos": 0, "files": 0, "chunks": 0}
        try:
            with self._connect() as conn, closing(conn.cursor()) as cur:
                for key, table in ("repos", "repos"), ("files", "files"), ("chunks", "chunks_meta"):
                    cur.execute(f"SELECT COUNT(1) FROM {table}")
                    (value,) = cur.fetchone() or (0,)
                    counts[key] = int(value)
        except sqlite3.Error:
            # If initialization hasn't run, keep zeros.
            pass
        return counts
