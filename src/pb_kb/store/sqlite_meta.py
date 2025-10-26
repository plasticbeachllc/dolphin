from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


_SCHEMA_SQL = """
-- Enable FK enforcement
PRAGMA foreign_keys = ON;

-- Logical repositories registered for indexing/retrieval
CREATE TABLE IF NOT EXISTS repos (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  root_path TEXT NOT NULL,
  default_embed_model TEXT NOT NULL DEFAULT 'small',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Ingestion sessions are budget/accounting units and capture the HEAD commit
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  commit_sha TEXT NOT NULL CHECK (length(commit_sha) = 40),
  branch TEXT NOT NULL,
  embed_model TEXT NOT NULL DEFAULT 'small',
  files_indexed INTEGER NOT NULL DEFAULT 0,
  chunks_indexed INTEGER NOT NULL DEFAULT 0,
  vectors_written INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running', -- running | succeeded | failed | aborted
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  ended_at TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_repo_commit ON sessions(repo_id, commit_sha);

-- Files deduplicated by (repo, path); keep lightweight attributes
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  path TEXT NOT NULL, -- POSIX-style relative path from repo root
  ext TEXT,           -- e.g., '.py', '.md'
  language TEXT,      -- coarse tag: 'python' | 'typescript' | 'markdown' | 'text' | ...
  is_binary INTEGER NOT NULL DEFAULT 0,
  size_bytes INTEGER,
  latest_commit_sha TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (repo_id, path)
);
CREATE INDEX IF NOT EXISTS idx_files_repo_path ON files(repo_id, path);

-- Deduplicated chunk text stored once per content hash
CREATE TABLE IF NOT EXISTS chunk_texts (
  text_hash TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chunk_texts_created_at ON chunk_texts(created_at);

-- Chunk metadata per occurrence (per commit); vectors live in LanceDB
CREATE TABLE IF NOT EXISTS chunks_meta (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  commit_sha TEXT NOT NULL,
  -- location and structure
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  symbol_kind TEXT,     -- e.g., 'function' | 'class' | 'module' | null
  symbol_name TEXT,
  symbol_path TEXT,     -- hierarchical name (e.g., 'pkg.mod:Class.method')
  -- markdown headings (not embedded)
  h1 TEXT,
  h2 TEXT,
  h3 TEXT,
  -- content identity & accounting
  text_hash TEXT NOT NULL REFERENCES chunk_texts(text_hash) ON DELETE RESTRICT, -- sha256(canonicalize_text(chunk_text))
  token_count INTEGER NOT NULL,    -- tokens in chunk_text used for embedding
  embed_model TEXT NOT NULL,       -- 'small' | 'large'
  vector_dim INTEGER NOT NULL,     -- 1536 | 3072
  vector_collection TEXT NOT NULL, -- 'chunks_small' | 'chunks_large'
  vector_id TEXT NOT NULL,         -- primary key of the LanceDB record (chunk_uid)
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  -- idempotency: do not duplicate this exact chunk occurrence
  UNIQUE (repo_id, file_id, commit_sha, start_line, end_line, text_hash, embed_model)
);
CREATE INDEX IF NOT EXISTS idx_chunks_repo_file_commit ON chunks_meta(repo_id, file_id, commit_sha);
CREATE INDEX IF NOT EXISTS idx_chunks_text_hash ON chunks_meta(text_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_vector ON chunks_meta(vector_collection, vector_id);
"""


class SQLiteMetadataStore:
    """SQLite-backed metadata store adhering to the Sprint 1 schema."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        # Return rows as dict-like objects if needed in the future
        conn.row_factory = sqlite3.Row
        with closing(conn.cursor()) as cur:
            cur.execute("PRAGMA foreign_keys = ON;")
        return conn

    def initialize(self) -> None:
        """Ensure the database exists and the schema is applied idempotently."""
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)
            conn.commit()

    def record_repo(self, name: str, path: Path, *, default_embed_model: str = "small") -> None:
        """Insert or update a repo registration.

        This provides a minimal implementation used after initialization.
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
