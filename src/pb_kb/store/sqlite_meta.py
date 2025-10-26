from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlmodel import SQLModel, create_engine


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
        # Import models at call time to register them with SQLModel.metadata
        from . import sql_models as _models  # noqa: F401
        # Create all tables if they don't exist (via SQLModel models)
        SQLModel.metadata.create_all(engine)
        # Sanity check: ensure tables exist without hardcoded DDL
        with self._connect() as conn, closing(conn.cursor()) as cur:
            for table in ("repos", "sessions", "files"):
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                if cur.fetchone() is None:
                    raise RuntimeError(f"Database initialization failed: '{table}' table missing.")

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

    def get_repo_by_name(self, name: str) -> dict[str, str | int] | None:
        """Return repo record by name or None if not found."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                "SELECT id, root_path, default_embed_model FROM repos WHERE name = ?",
                (name,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": int(row[0]),
                "root_path": str(row[1]),
                "default_embed_model": str(row[2]),
            }

    def begin_session(self, repo_id: int, commit_sha: str, branch: str, embed_model: str) -> int:
        """Create a new ingestion session and return its id."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                INSERT INTO sessions (repo_id, commit_sha, branch, embed_model, status)
                VALUES (?, ?, ?, ?, 'running')
                """,
                (repo_id, commit_sha, branch, embed_model),
            )
            conn.commit()
            return int(cur.lastrowid)

    def set_session_status(self, session_id: int, status: str, notes: str | None = None) -> None:
        """Update a session status; set ended_at when terminal."""
        terminal = {"succeeded", "failed", "aborted"}
        with self._connect() as conn, closing(conn.cursor()) as cur:
            if status in terminal:
                cur.execute(
                    """
                    UPDATE sessions
                    SET status = ?, ended_at = datetime('now'), notes = COALESCE(?, notes)
                    WHERE id = ?
                    """,
                    (status, notes, session_id),
                )
            else:
                cur.execute(
                    "UPDATE sessions SET status = ?, notes = COALESCE(?, notes) WHERE id = ?",
                    (status, notes, session_id),
                )
            conn.commit()

    def bump_session_counters(
        self,
        session_id: int,
        *,
        files_indexed: int | None = None,
        chunks_indexed: int | None = None,
        vectors_written: int | None = None,
    ) -> None:
        """Set session counters to the provided values (no-op if all None)."""
        sets: list[str] = []
        params: list[int] = []
        if files_indexed is not None:
            sets.append("files_indexed = ?")
            params.append(int(files_indexed))
        if chunks_indexed is not None:
            sets.append("chunks_indexed = ?")
            params.append(int(chunks_indexed))
        if vectors_written is not None:
            sets.append("vectors_written = ?")
            params.append(int(vectors_written))
        if not sets:
            return
        sql = f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?"
        params.append(int(session_id))
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(sql, tuple(params))
            conn.commit()

    def upsert_file(
        self,
        repo_id: int,
        *,
        path: str,
        ext: str | None,
        language: str | None,
        is_binary: bool,
        size_bytes: int | None,
    ) -> int:
        """Insert or update a file row; return file id."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                INSERT INTO files (repo_id, path, ext, language, is_binary, size_bytes)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo_id, path) DO UPDATE SET
                  ext=excluded.ext,
                  language=excluded.language,
                  is_binary=excluded.is_binary,
                  size_bytes=excluded.size_bytes,
                  updated_at=datetime('now')
                """,
                (
                    int(repo_id),
                    path,
                    ext,
                    language,
                    1 if is_binary else 0,
                    size_bytes,
                ),
            )
            file_id = int(cur.lastrowid)
            if file_id == 0:
                cur.execute(
                    "SELECT id FROM files WHERE repo_id = ? AND path = ?",
                    (int(repo_id), path),
                )
                row = cur.fetchone()
                file_id = int(row[0]) if row else 0
            conn.commit()
            return file_id

    def set_file_latest_commit(self, repo_id: int, path: str, commit_sha: str) -> None:
        """Update latest_commit_sha for a file."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                UPDATE files
                SET latest_commit_sha = ?, updated_at = datetime('now')
                WHERE repo_id = ? AND path = ?
                """,
                (commit_sha, int(repo_id), path),
            )
            conn.commit()
