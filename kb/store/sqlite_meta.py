from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlmodel import SQLModel, create_engine
class SQLiteMetadataStore:
    """SQLite-backed metadata store using SQLModel for schema materialization."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_lock = threading.Lock()
        self._initialized = False
        self._initializing = False

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
        """Thread-safe enhanced initialization with proper validation and error handling."""
        # Fast path: check if already initialized
        if self._initialized:
            return
        
        # Use lock to prevent concurrent initialization
        with self._init_lock:
            # Double-check pattern: another thread might have initialized while we were waiting
            if self._initialized:
                return
            
            try:
                self._initializing = True
                
                engine = self._engine()
                
                # Import models at call time to register them with SQLModel.metadata
                from . import sql_models as _models  # noqa: F401
                
                # Create all tables if they don't exist (via SQLModel models)
                SQLModel.metadata.create_all(engine)
                
                # Validate foreign key support and constraints
                with self._connect() as conn, closing(conn.cursor()) as cur:
                    # Enable and verify foreign key constraints
                    cur.execute("PRAGMA foreign_keys = ON")
                    cur.execute("PRAGMA foreign_key_check")
                    foreign_key_errors = cur.fetchall()
                    if foreign_key_errors:
                        raise RuntimeError(f"Foreign key constraint violations: {foreign_key_errors}")
                    
                    # Enhanced table validation with schema verification
                    expected_tables = {
                        "repos": "Repository metadata",
                        "sessions": "Indexing sessions",
                        "files": "File catalog",
                        "chunk_content": "Chunk content",
                        "chunk_locations": "Chunk locations"
                    }
                    
                    for table, description in expected_tables.items():
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                        if cur.fetchone() is None:
                            raise RuntimeError(f"Database initialization failed: '{table}' table missing ({description}).")
                        
                        # Validate table schema
                        self._validate_table_schema(cur, table)
                    
                    # Robust FTS5 creation with version checking
                    self._create_fts5_table_safe(cur)
                    
                    conn.commit()
                
                # Post-initialization validation
                self._validate_database_integrity()
                
                # Mark as successfully initialized
                self._initialized = True
                
            finally:
                self._initializing = False
    
    def _validate_table_schema(self, cur, table_name: str) -> None:
        """Validate table schema integrity."""
        # Get table schema
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = cur.fetchall()
        
        if not columns:
            raise RuntimeError(f"Table {table_name} exists but has no columns")
        
        # Validate expected columns based on table type
        if table_name == "repos":
            required_cols = {"id", "name", "root_path", "default_embed_model"}
        elif table_name == "sessions":
            required_cols = {"id", "repo_id", "commit_sha", "branch", "embed_model", "status"}
        elif table_name == "files":
            required_cols = {"id", "repo_id", "path", "ext", "language", "is_binary"}
        elif table_name == "chunk_content":
            required_cols = {"id", "repo_id", "file_id", "text_hash", "embed_model"}
        elif table_name == "chunk_locations":
            required_cols = {"id", "content_id", "start_line", "end_line"}
        else:
            return  # Skip validation for unknown tables
        
        actual_cols = {col[1] for col in columns}  # col[1] is column name
        missing_cols = required_cols - actual_cols
        if missing_cols:
            raise RuntimeError(f"Table {table_name} missing required columns: {missing_cols}")
    
    def _create_fts5_table_safe(self, cur) -> None:
        """Safely create FTS5 table with version and feature detection."""
        import sqlite3
        
        # Check SQLite version and FTS5 support
        cur.execute("SELECT sqlite_version()")
        sqlite_version = cur.fetchone()[0]
        
        # Check if FTS5 is available
        try:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'")
            if cur.fetchone():
                return  # Already exists
            
            # Test FTS5 support
            cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_test USING fts5(x)")
            cur.execute("DROP TABLE _fts5_test")
            
        except sqlite3.OperationalError as e:
            if "fts5" in str(e).lower():
                raise RuntimeError(
                    f"FTS5 not available in SQLite version {sqlite_version}. "
                    "FTS5 is required for full-text search functionality."
                )
            else:
                raise RuntimeError(f"FTS5 test failed: {e}")
        
        # Create FTS5 table with proper schema
        try:
            cur.execute("""
                CREATE VIRTUAL TABLE chunks_fts USING fts5(
                    content_id UNINDEXED,
                    repo UNINDEXED,
                    path UNINDEXED,
                    content,
                    symbol_name,
                    symbol_path,
                    tokenize='porter unicode61'
                )
            """)
        except sqlite3.OperationalError as e:
            raise RuntimeError(f"Failed to create FTS5 table: {e}")
    
    def _validate_database_integrity(self) -> None:
        """Perform comprehensive database integrity validation."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            # Check database integrity
            cur.execute("PRAGMA integrity_check")
            integrity_result = cur.fetchone()
            if integrity_result and integrity_result[0] != "ok":
                raise RuntimeError(f"Database integrity check failed: {integrity_result[0]}")
            
            # Check for orphaned records
            orphaned_checks = [
                ("chunk_locations without content", """
                    SELECT COUNT(*) FROM chunk_locations cl
                    LEFT JOIN chunk_content cc ON cl.content_id = cc.id
                    WHERE cc.id IS NULL
                """),
                ("chunk_content without files", """
                    SELECT COUNT(*) FROM chunk_content cc
                    LEFT JOIN files f ON cc.file_id = f.id
                    WHERE f.id IS NULL
                """),
                ("files without repos", """
                    SELECT COUNT(*) FROM files f
                    LEFT JOIN repos r ON f.repo_id = r.id
                    WHERE r.id IS NULL
                """),
                ("sessions without repos", """
                    SELECT COUNT(*) FROM sessions s
                    LEFT JOIN repos r ON s.repo_id = r.id
                    WHERE r.id IS NULL
                """)
            ]
            
            for check_name, sql in orphaned_checks:
                cur.execute(sql)
                count = cur.fetchone()[0]
                if count > 0:
                    # Log warning but don't fail initialization for existing databases
                    print(f"Warning: Found {count} orphaned records in {check_name}")

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

    def get_session(self, session_id: int) -> dict[str, Any] | None:
        """Return a session row as a dict or None if not found."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT id, repo_id, commit_sha, branch, embed_model, status,
                       files_indexed, chunks_indexed, vectors_written, chunks_skipped, chunks_pruned,
                       created_at, ended_at
                FROM sessions WHERE id = ?
                """,
                (int(session_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": int(row[0]),
                "repo_id": int(row[1]),
                "commit_sha": str(row[2]),
                "branch": str(row[3]),
                "embed_model": str(row[4]),
                "status": str(row[5]),
                "files_indexed": int(row[6]),
                "chunks_indexed": int(row[7]),
                "vectors_written": int(row[8]),
                "chunks_skipped": int(row[9]),
                "chunks_pruned": int(row[10]),
                "created_at": row[11],
                "ended_at": row[12],
            }

    def summarize(self) -> dict[str, int]:
        """Return simple counts for key entities, 0 if tables missing."""
        counts: dict[str, int] = {"repos": 0, "files": 0, "chunks": 0}
        try:
            with self._connect() as conn, closing(conn.cursor()) as cur:
                for key, table in ("repos", "repos"), ("files", "files"), ("chunks", "chunk_content"):
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
                INSERT INTO sessions (repo_id, commit_sha, branch, embed_model, status, 
                                     files_indexed, chunks_indexed, vectors_written, chunks_skipped, chunks_pruned)
                VALUES (?, ?, ?, ?, 'running', 0, 0, 0, 0, 0)
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
        chunks_skipped: int | None = None,
        chunks_pruned: int | None = None,
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
        if chunks_skipped is not None:
            sets.append("chunks_skipped = ?")
            params.append(int(chunks_skipped))
        if chunks_pruned is not None:
            sets.append("chunks_pruned = ?")
            params.append(int(chunks_pruned))
        if not sets:
            return
        sql = f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?"
        params.append(int(session_id))
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(sql, tuple(params))
            conn.commit()

    def get_last_successful_commit(self, repo_id: int) -> str | None:
        """Get the commit SHA of the last successful session for a repo.
        
        Returns None if no successful sessions exist.
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT commit_sha FROM sessions 
                WHERE repo_id = ? AND status = 'succeeded' 
                ORDER BY id DESC LIMIT 1
                """,
                (int(repo_id),)
            )
            row = cur.fetchone()
            return str(row[0]) if row else None

    def get_file_id(self, repo_id: int, path: str) -> int | None:
        """Get the file_id for a given repo_id and path.
        
        Returns None if the file doesn't exist in the catalog.
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                "SELECT id FROM files WHERE repo_id = ? AND path = ?",
                (int(repo_id), path)
            )
            row = cur.fetchone()
            return int(row[0]) if row else None

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

    # =====================
    # Chunk content and location APIs
    # =====================

    def get_existing_content_hashes_for_file(self, repo_id: int, file_id: int, embed_model: str) -> set[str]:
        """Return the set of distinct text_hash values for a file and model."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT DISTINCT text_hash
                FROM chunk_content
                WHERE repo_id = ? AND file_id = ? AND embed_model = ?
                """,
                (int(repo_id), int(file_id), embed_model),
            )
            rows = cur.fetchall() or []
            return {str(r[0]) for r in rows}

    def get_existing_content_map_for_file(self, repo_id: int, file_id: int, embed_model: str) -> dict[str, str]:
        """Return mapping text_hash -> content_id for a file and model."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT text_hash, id
                FROM chunk_content
                WHERE repo_id = ? AND file_id = ? AND embed_model = ?
                """,
                (int(repo_id), int(file_id), embed_model),
            )
            rows = cur.fetchall() or []
            return {str(r[0]): str(r[1]) for r in rows}

    def upsert_chunk_content_row(self, repo_id: int, file_id: int, text_hash: str, embed_model: str, *, content_id: str | None = None) -> str:
        """Insert or update a chunk_content row and return its id atomically.

        Uses SQLite's RETURNING clause to fetch the id in a single statement.
        """
        import uuid

        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                if content_id is None:
                    content_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO chunk_content (
                        id, repo_id, file_id, text_hash, embed_model, first_indexed_at, last_indexed_at
                    ) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    ON CONFLICT(repo_id, file_id, text_hash, embed_model)
                    DO UPDATE SET last_indexed_at = excluded.last_indexed_at
                    RETURNING id
                    """,
                    (content_id, int(repo_id), int(file_id), text_hash, embed_model),
                )
                row = cur.fetchone()
                if row:
                    content_id = str(row[0])
                conn.commit()
                return content_id
            except Exception:
                conn.rollback()
                raise

    def get_existing_locations_for_content_ids(self, content_ids: list[str]) -> dict[str, list[dict[str, object]]]:
        """Return existing locations for a set of content_ids.

        Returns dict: content_id -> list of {start_line, end_line, symbol_kind, symbol_name, symbol_path}
        """
        if not content_ids:
            return {}
        placeholders = ",".join(["?"] * len(content_ids))
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                f"""
                SELECT content_id, start_line, end_line, symbol_kind, symbol_name, symbol_path
                FROM chunk_locations
                WHERE content_id IN ({placeholders})
                """,
                tuple(content_ids),
            )
            rows = cur.fetchall() or []
        out: dict[str, list[dict[str, object]]] = {}
        for r in rows:
            cid = str(r[0])
            out.setdefault(cid, []).append(
                {
                    "start_line": int(r[1]),
                    "end_line": int(r[2]),
                    "symbol_kind": r[3],
                    "symbol_name": r[4],
                    "symbol_path": r[5],
                }
            )
        return out

    def sync_locations_for_content_row(self, content_id: str, desired_locations: list[dict[str, object]]) -> dict[str, int]:
        """Reconcile locations for a single content_id to match desired.

        desired_locations: list of dicts with keys: start_line, end_line, symbol_kind, symbol_name, symbol_path
        Returns counts: {inserted, updated, deleted}
        """
        import uuid

        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                # Load existing
                cur.execute(
                    """
                    SELECT start_line, end_line, symbol_kind, symbol_name, symbol_path
                    FROM chunk_locations
                    WHERE content_id = ?
                    """,
                    (content_id,),
                )
                rows = cur.fetchall() or []
                existing: dict[tuple[int, int], tuple[Any, Any, Any]] = {
                    (int(r[0]), int(r[1])): (r[2], r[3], r[4]) for r in rows
                }

                desired_map: dict[tuple[int, int], tuple[Any, Any, Any]] = {}
                for d in desired_locations:
                    desired_map[(int(d["start_line"]), int(d["end_line"]))] = (
                        d.get("symbol_kind"),
                        d.get("symbol_name"),
                        d.get("symbol_path"),
                    )

                desired_positions = set(desired_map.keys())
                existing_positions = set(existing.keys())

                to_insert = desired_positions - existing_positions
                to_delete = existing_positions - desired_positions
                to_consider_update = desired_positions & existing_positions

                inserted = updated = deleted = 0

                # Inserts
                for pos in to_insert:
                    sk, sn, sp = desired_map[pos]
                    loc_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO chunk_locations (
                            id, content_id, start_line, end_line, symbol_kind, symbol_name, symbol_path, last_seen_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                        """,
                        (loc_id, content_id, int(pos[0]), int(pos[1]), sk, sn, sp),
                    )
                    inserted += 1

                # Updates or touch last_seen_at
                for pos in to_consider_update:
                    old = existing[pos]
                    new = desired_map[pos]
                    if old != new:
                        cur.execute(
                            """
                            UPDATE chunk_locations
                            SET symbol_kind = ?, symbol_name = ?, symbol_path = ?, last_seen_at = datetime('now')
                            WHERE content_id = ? AND start_line = ? AND end_line = ?
                            """,
                            (new[0], new[1], new[2], content_id, int(pos[0]), int(pos[1])),
                        )
                        updated += 1
                    else:
                        cur.execute(
                            """
                            UPDATE chunk_locations
                            SET last_seen_at = datetime('now')
                            WHERE content_id = ? AND start_line = ? AND end_line = ?
                            """,
                            (content_id, int(pos[0]), int(pos[1])),
                        )

                # Deletes
                for pos in to_delete:
                    cur.execute(
                        """
                        DELETE FROM chunk_locations
                        WHERE content_id = ? AND start_line = ? AND end_line = ?
                        """,
                        (content_id, int(pos[0]), int(pos[1])),
                    )
                    deleted += 1

                conn.commit()
                return {"inserted": inserted, "updated": updated, "deleted": deleted}
            except Exception:
                conn.rollback()
                raise

    def prune_invalidated_content_for_file(
        self, repo_id: int, file_id: int, embed_model: str, current_hashes: set[str]
    ) -> int:
        """Delete content (and locations) not present in current_hashes. Returns count deleted."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                # First, get the file path for FTS5 cleanup
                cur.execute("SELECT path FROM files WHERE id = ?", (int(file_id),))
                file_row = cur.fetchone()
                file_path = str(file_row[0]) if file_row else None
                
                if current_hashes:
                    placeholders = ",".join(["?"] * len(current_hashes))
                    params = (int(repo_id), int(file_id), embed_model, *list(current_hashes))
                    cur.execute(
                        f"""
                        SELECT id FROM chunk_content
                        WHERE repo_id = ? AND file_id = ? AND embed_model = ? AND text_hash NOT IN ({placeholders})
                        """,
                        params,
                    )
                else:
                    # If no current hashes, all content for this file+model is invalidated
                    cur.execute(
                        """
                        SELECT id FROM chunk_content
                        WHERE repo_id = ? AND file_id = ? AND embed_model = ?
                        """,
                        (int(repo_id), int(file_id), embed_model),
                    )
                rows = cur.fetchall() or []
                to_delete_ids = [str(r[0]) for r in rows]
                if not to_delete_ids:
                    return 0
                placeholders = ",".join(["?"] * len(to_delete_ids))
                # Delete from FTS5 index first (by content_id and also by file path as fallback)
                cur.execute(
                    f"DELETE FROM chunks_fts WHERE content_id IN ({placeholders})",
                    tuple(to_delete_ids),
                )
                # Also delete any orphaned FTS5 entries for this file
                if file_path:
                    cur.execute("DELETE FROM chunks_fts WHERE path = ?", (file_path,))
                # Delete locations (FK cascade may do this, but be explicit)
                cur.execute(
                    f"DELETE FROM chunk_locations WHERE content_id IN ({placeholders})",
                    tuple(to_delete_ids),
                )
                # Delete content rows
                cur.execute(
                    f"DELETE FROM chunk_content WHERE id IN ({placeholders})",
                    tuple(to_delete_ids),
                )
                conn.commit()
                return len(to_delete_ids)
            except Exception:
                conn.rollback()
                raise

    # =====================
    # Minimal utilities for per-file sync planning & application
    # =====================

    def plan_content_upserts_for_file(
        self, repo_id: int, file_id: int, embed_model: str, desired_hashes: set[str]
    ) -> tuple[set[str], dict[str, str]]:
        """Plan per-file content upserts.

        Returns (new_hashes, existing_map) where:
        - new_hashes: set of hashes not yet present for this file+model
        - existing_map: dict mapping existing hash -> content_id
        """
        existing_map = self.get_existing_content_map_for_file(repo_id, file_id, embed_model)
        new_hashes = set(desired_hashes) - set(existing_map.keys())
        return new_hashes, existing_map

    def ensure_content_rows_for_file(
        self, repo_id: int, file_id: int, embed_model: str, hashes: list[str]
    ) -> dict[str, str]:
        """Ensure chunk_content rows exist for all hashes; return hash -> content_id mapping.

        Uses a single connection for efficiency and returns ids atomically via RETURNING.
        """
        import uuid

        mapping: dict[str, str] = {}
        if not hashes:
            return mapping
        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                for h in hashes:
                    cid = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO chunk_content (
                            id, repo_id, file_id, text_hash, embed_model, first_indexed_at, last_indexed_at
                        ) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                        ON CONFLICT(repo_id, file_id, text_hash, embed_model)
                        DO UPDATE SET last_indexed_at = excluded.last_indexed_at
                        RETURNING id
                        """,
                        (cid, int(repo_id), int(file_id), h, embed_model),
                    )
                    row = cur.fetchone()
                    if row:
                        cid = str(row[0])
                    mapping[h] = cid
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return mapping

    def sync_file_state(
        self,
        repo_id: int,
        file_id: int,
        embed_model: str,
        desired: dict[str, list[dict[str, object]]],
    ) -> dict[str, int]:
        """Idempotently apply desired file state to content and locations.

        desired: mapping text_hash -> list of occurrence dicts
                 each occurrence dict should include start_line, end_line, and optional symbol metadata

        Returns stats: {"content_upserted": int, "locations_inserted": int, "locations_updated": int, "locations_deleted": int, "content_pruned": int}
        """
        desired_hashes = set(desired.keys())
        # Ensure content rows for all desired hashes
        mapping = self.ensure_content_rows_for_file(repo_id, file_id, embed_model, list(desired_hashes))

        # Sync locations for each content
        inserted = updated = deleted = 0
        for h, occs in desired.items():
            cid = mapping.get(h)
            if not cid:
                # Should not happen; guard and continue
                continue
            stats = self.sync_locations_for_content_row(cid, occs)
            inserted += stats.get("inserted", 0)
            updated += stats.get("updated", 0)
            deleted += stats.get("deleted", 0)

        # Prune invalidated content for this file
        pruned = self.prune_invalidated_content_for_file(repo_id, file_id, embed_model, desired_hashes)

        return {
            "content_upserted": len(desired_hashes),
            "locations_inserted": inserted,
            "locations_updated": updated,
            "locations_deleted": deleted,
            "content_pruned": pruned,
        }

    def get_all_files_for_repo(self, repo_id: int) -> list[dict[str, object]]:
        """Get all files for a repository.
        
        Returns list of dicts with keys: id, path
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                "SELECT id, path FROM files WHERE repo_id = ? ORDER BY path",
                (int(repo_id),)
            )
            rows = cur.fetchall() or []
            return [
                {"id": int(r[0]), "path": str(r[1])}
                for r in rows
            ]

    def get_chunks_for_file(self, file_id: int) -> list[dict[str, object]] | None:
        """Get all chunks (content rows) for a file.
        
        Returns list of dicts or None if no chunks found.
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                "SELECT id FROM chunk_content WHERE file_id = ?",
                (int(file_id),)
            )
            rows = cur.fetchall() or []
            return [{"id": str(r[0])} for r in rows] if rows else None

    def bm25_search(
        self,
        query: str,
        *,
        repo: str | None = None,
        path_prefix: list[str] | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Execute BM25 full-text search on indexed chunks.
        
        Args:
            query: Search query (plain text, not SQL)
            repo: Optional repository filter
            path_prefix: Optional path prefix filters
            top_k: Number of results to return
        
        Returns:
            List of results with BM25 scores
        
        FTS5 Query Syntax:
            - Simple: "authentication login"
            - Phrase: '"user controller"'
            - Boolean: "auth AND login NOT test"
            - Near: "NEAR(user controller, 5)"
        """
        # Input validation
        if not query or not query.strip():
            return []
        
        # Basic FTS5 safety: escape potentially dangerous characters
        # FTS5 uses MATCH syntax, so we need to be careful about quotes and operators
        if any(char in query for char in [';', '\\', '\x00']):
            return []
        
        try:
            with self._connect() as conn, closing(conn.cursor()) as cur:
                # Build FTS5 query with filters
                conditions = ["chunks_fts MATCH ?"]
                params = [query]
                
                if repo:
                    conditions.append("repo = ?")
                    params.append(repo)
                
                if path_prefix:
                    # Add path prefix filters
                    path_conditions = []
                    for prefix in path_prefix:
                        path_conditions.append("path LIKE ?")
                        params.append(f"{prefix}%")
                    conditions.append(f"({' OR '.join(path_conditions)})")
                
                where_clause = " AND ".join(conditions)
                
                # FTS5 BM25 scoring:
                # - bm25(chunks_fts): Overall BM25 score (lower is better!)
                # - rank: Pre-computed relevance rank (also lower is better!)
                #
                # Note: FTS5 returns negative BM25 scores, where more negative = more relevant
                # We negate to get positive scores for easier interpretation
                
                sql = f"""
                    SELECT
                        content_id,
                        repo,
                        path,
                        -bm25(chunks_fts) as bm25_score,
                        rank
                    FROM chunks_fts
                    WHERE {where_clause}
                    ORDER BY rank
                    LIMIT ?
                """
                params.append(top_k)
                
                cur.execute(sql, tuple(params))
                rows = cur.fetchall() or []
                
                # Convert to list of dicts
                results = []
                for row in rows:
                    results.append({
                        "chunk_id": str(row[0]),
                        "repo": str(row[1]),
                        "path": str(row[2]),
                        "score": float(row[3]),  # Positive BM25 score
                        "rank": int(row[4]),
                    })
                
                return results
        except sqlite3.Error:
            # Return empty results on any FTS5 error
            return []

    def index_chunk_for_fts(
        self,
        content_id: str,
        repo: str,
        path: str,
        content: str,
        symbol_name: str | None = None,
        symbol_path: str | None = None,
    ) -> None:
        """Index a chunk in the FTS5 table for BM25 search.
        
        Args:
            content_id: Unique chunk identifier
            repo: Repository name
            path: File path
            content: Chunk text content (will be tokenized and stemmed)
            symbol_name: Optional symbol name for exact matching
            symbol_path: Optional fully qualified symbol path
        """
        
        with self._connect() as conn, closing(conn.cursor()) as cur:
            # Upsert: replace if exists, insert if new
            cur.execute("""
                INSERT OR REPLACE INTO chunks_fts
                (content_id, repo, path, content, symbol_name, symbol_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (content_id, repo, path, content, symbol_name, symbol_path))
            conn.commit()

    def bulk_index_chunks_for_fts(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        """Bulk index multiple chunks for better performance.
        
        Args:
            chunks: List of chunk dicts with keys:
                - content_id, repo, path, content, symbol_name, symbol_path
        
        Returns:
            Number of chunks indexed
        """
        if not chunks:
            return 0
        
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.executemany("""
                INSERT OR REPLACE INTO chunks_fts
                (content_id, repo, path, content, symbol_name, symbol_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                (c["content_id"], c["repo"], c["path"],
                 c["content"], c.get("symbol_name"), c.get("symbol_path"))
                for c in chunks
            ])
            conn.commit()
            return len(chunks)

    def get_chunk_by_id(self, chunk_id: str) -> dict[str, Any] | None:
        """Get full chunk metadata by content_id.
        
        Returns:
            Dict with chunk metadata or None if not found
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute("""
                SELECT
                    cc.id,
                    cc.text_hash,
                    cc.embed_model,
                    cc.first_indexed_at,
                    cc.last_indexed_at,
                    f.path,
                    f.language,
                    cl.start_line,
                    cl.end_line,
                    cl.symbol_kind,
                    cl.symbol_name,
                    cl.symbol_path
                FROM chunk_content cc
                JOIN files f ON cc.file_id = f.id
                LEFT JOIN chunk_locations cl ON cc.id = cl.content_id
                WHERE cc.id = ?
            """, (chunk_id,))
            
            row = cur.fetchone()
            if not row:
                return None
            
            return {
                "chunk_id": str(row[0]),
                "text_hash": str(row[1]),
                "embed_model": str(row[2]),
                "first_indexed_at": row[3],
                "last_indexed_at": row[4],
                "path": str(row[5]),
                "language": row[6],
                "start_line": int(row[7]) if row[7] else None,
                "end_line": int(row[8]) if row[8] else None,
                "symbol_kind": row[9],
                "symbol_name": row[10],
                "symbol_path": row[11],
            }

    def get_chunk_contents(self, chunk_ids: list[str]) -> dict[str, str]:
        """Get a mapping of chunk_id to its content."""
        if not chunk_ids:
            return {}
        
        placeholders = ",".join(["?"] * len(chunk_ids))
        query = f"""
            SELECT c.id, fts.content
            FROM chunk_content c
            JOIN chunks_fts fts ON c.id = fts.content_id
            WHERE c.id IN ({placeholders})
        """
        
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(query, chunk_ids)
            rows = cur.fetchall()
            return {str(row[0]): str(row[1]) for row in rows}


    # =====================
    # Enhanced Repository Removal (Phase 2)
    # =====================

    def get_active_sessions(self, repo_id: int) -> list:
        """Get all active (non-terminal) sessions for a repository."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute("""
                SELECT id, status, created_at FROM sessions 
                WHERE repo_id = ? AND status NOT IN ('succeeded', 'failed', 'aborted')
                ORDER BY created_at DESC
            """, (repo_id,))
            return cur.fetchall()

    def terminate_active_sessions(self, repo_id: int) -> int:
        """Terminate all active sessions for a repository."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute("""
                UPDATE sessions 
                SET status = 'aborted', ended_at = datetime('now')
                WHERE repo_id = ? AND status NOT IN ('succeeded', 'failed', 'aborted')
            """, (repo_id,))
            terminated = cur.rowcount
            conn.commit()
            return terminated

    def _get_repo_data_counts(self, cur, repo_id: int, repo_name: str) -> dict:
        """Collect counts of all data that will be deleted for validation."""
        counts = {}
        
        # Count files
        cur.execute("SELECT COUNT(*) FROM files WHERE repo_id = ?", (repo_id,))
        counts["files"] = cur.fetchone()[0]
        
        # Count chunk content
        cur.execute("SELECT COUNT(*) FROM chunk_content WHERE repo_id = ?", (repo_id,))
        counts["chunk_content"] = cur.fetchone()[0]
        
        # Count chunk locations
        cur.execute("""
            SELECT COUNT(*) FROM chunk_locations 
            WHERE content_id IN (SELECT id FROM chunk_content WHERE repo_id = ?)
        """, (repo_id,))
        counts["chunk_locations"] = cur.fetchone()[0]
        
        # Count FTS entries
        cur.execute("SELECT COUNT(*) FROM chunks_fts WHERE repo = ?", (repo_name,))
        counts["fts_entries"] = cur.fetchone()[0]
        
        # Count sessions
        cur.execute("SELECT COUNT(*) FROM sessions WHERE repo_id = ?", (repo_id,))
        counts["sessions"] = cur.fetchone()[0]
        
        return counts

    def _cleanup_fts_entries_comprehensive(self, cur, repo_id: int, repo_name: str) -> dict:
        """Comprehensive FTS5 cleanup with multiple strategies."""
        stats = {"by_content_id": 0, "by_repo_name": 0, "orphaned": 0, "errors": []}
        
        try:
            # Strategy 1: Delete by content_id (most precise)
            cur.execute("""
                DELETE FROM chunks_fts 
                WHERE content_id IN (
                    SELECT cc.id FROM chunk_content cc 
                    WHERE cc.repo_id = ?
                )
            """, (repo_id,))
            stats["by_content_id"] = cur.rowcount
            
            # Strategy 2: Delete by repo name (fallback)
            cur.execute("DELETE FROM chunks_fts WHERE repo = ?", (repo_name,))
            stats["by_repo_name"] = cur.rowcount
            
            # Strategy 3: Delete orphaned entries (validation)
            cur.execute("""
                DELETE FROM chunks_fts 
                WHERE content_id NOT IN (
                    SELECT id FROM chunk_content
                )
            """)
            stats["orphaned"] = cur.rowcount
            
        except Exception as e:
            stats["errors"].append(str(e))
            
        return stats

    def _delete_chunk_locations_by_repo(self, cur, repo_id: int) -> int:
        """Delete all chunk locations for a repository."""
        cur.execute("""
            DELETE FROM chunk_locations
            WHERE content_id IN (
                SELECT id FROM chunk_content WHERE repo_id = ?
            )
        """, (repo_id,))
        return cur.rowcount

    def _delete_chunk_content_by_repo(self, cur, repo_id: int) -> int:
        """Delete all chunk content for a repository."""
        cur.execute("DELETE FROM chunk_content WHERE repo_id = ?", (repo_id,))
        return cur.rowcount

    def _delete_files_by_repo(self, cur, repo_id: int) -> int:
        """Delete all files for a repository."""
        cur.execute("DELETE FROM files WHERE repo_id = ?", (repo_id,))
        return cur.rowcount

    def _delete_sessions_by_repo(self, cur, repo_id: int) -> int:
        """Delete all sessions for a repository."""
        cur.execute("DELETE FROM sessions WHERE repo_id = ?", (repo_id,))
        return cur.rowcount

    def _delete_repo_registration(self, cur, repo_id: int) -> int:
        """Delete repository registration."""
        cur.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
        return cur.rowcount

    def _validate_cleanup_success(self, pre_counts: dict, post_counts: dict) -> bool:
        """Validate that cleanup was successful by comparing counts."""
        for key in pre_counts:
            if post_counts.get(key, 0) > 0:
                return False
        return True

    def rm_repo_enhanced(self, name: str, force: bool = False) -> dict:
        """Enhanced repository removal with comprehensive cleanup validation.
        
        This implements Phase 2 Fix 2.1 from the remediation plan:
        - Checks for active sessions before deletion
        - Deletes in proper foreign key order
        - Validates cleanup was comprehensive
        - Provides detailed statistics
        """
        repo = self.get_repo_by_name(name)
        if not repo:
            raise ValueError(f"Repository '{name}' not found")
        
        repo_id = int(repo["id"])
        
        # Check for active sessions first
        active_sessions = self.get_active_sessions(repo_id)
        if active_sessions and not force:
            raise RuntimeError(
                f"Cannot remove repository '{name}': {len(active_sessions)} active indexing sessions found. "
                "Use --force to override."
            )
        
        # Pre-cleanup validation and data collection
        with self._connect() as conn:
            cur = conn.cursor()
            
            # Collect all data that will be deleted for validation
            pre_cleanup_counts = self._get_repo_data_counts(cur, repo_id, name)
            
            # Delete in proper foreign key order with validation
            try:
                # 1. FTS5 entries (clean by content_id first, then by repo name)
                fts_cleanup_stats = self._cleanup_fts_entries_comprehensive(cur, repo_id, name)
                
                # 2. Chunk locations (foreign key to chunk_content)
                locations_deleted = self._delete_chunk_locations_by_repo(cur, repo_id)
                
                # 3. Chunk content (foreign key to files)
                content_deleted = self._delete_chunk_content_by_repo(cur, repo_id)
                
                # 4. Files (foreign key to repos)
                files_deleted = self._delete_files_by_repo(cur, repo_id)
                
                # 5. Sessions (foreign key to repos)  
                sessions_deleted = self._delete_sessions_by_repo(cur, repo_id)
                
                # 6. Repository registration
                repo_deleted = self._delete_repo_registration(cur, repo_id)
                
                # Validate cleanup was comprehensive
                post_cleanup_counts = self._get_repo_data_counts(cur, repo_id, name)
                cleanup_success = self._validate_cleanup_success(pre_cleanup_counts, post_cleanup_counts)
                
                if not cleanup_success and not force:
                    raise RuntimeError(f"Cleanup validation failed: {post_cleanup_counts}")
                
                conn.commit()
                
            except Exception as e:
                conn.rollback()
                raise RuntimeError(f"Repository removal failed: {e}")
        
        # Return detailed stats
        return {
            "repository": name,
            "cleanup_stats": {
                "fts5_entries": fts_cleanup_stats,
                "locations_deleted": locations_deleted,
                "content_deleted": content_deleted, 
                "files_deleted": files_deleted,
                "sessions_deleted": sessions_deleted,
                "repo_deleted": repo_deleted
            },
            "pre_cleanup_counts": pre_cleanup_counts,
            "post_cleanup_counts": post_cleanup_counts,
            "success": True
        }

    def _cleanup_lancedb_comprehensive(self, lancedb_store, name: str) -> dict:
        """Comprehensive LanceDB cleanup with validation.
        
        Args:
            lancedb_store: LanceDBStore instance
            name: Repository name
            
        Returns:
            Statistics about cleanup: {small_deleted, large_deleted, errors}
        """
        stats = {"small_deleted": 0, "large_deleted": 0, "errors": []}
        
        for model in ["small", "large"]:
            try:
                # Count vectors before deletion
                pre_count = lancedb_store.count_repo_vectors(name, model=model)
                
                # Delete vectors
                lancedb_store.delete_repo(name, model=model)
                
                # Count vectors after deletion
                post_count = lancedb_store.count_repo_vectors(name, model=model)
                
                # Verify deletion was successful
                if post_count > 0:
                    stats["errors"].append(
                        f"{model} model: {post_count} vectors remain after deletion"
                    )
                
                stats[f"{model}_deleted"] = pre_count - post_count
                
            except Exception as e:
                stats["errors"].append(f"{model} model cleanup failed: {e}")
        
        return stats

    def rm_repo_with_lancedb(self, lancedb_store, name: str, force: bool = False) -> dict:
        """Enhanced repository removal with LanceDB cleanup validation.
        
        This implements Phase 2 Fix 2.1 from the remediation plan:
        - Checks for active sessions before deletion
        - Deletes in proper foreign key order
        - Validates SQLite cleanup was comprehensive
        - Validates LanceDB cleanup was comprehensive
        - Provides detailed statistics
        
        Args:
            lancedb_store: LanceDBStore instance
            name: Repository name
            force: Skip active session check if True
            
        Returns:
            Dict with cleanup statistics and success status
        """
        # First perform SQLite cleanup
        sqlite_result = self.rm_repo_enhanced(name, force=force)
        
        # Then cleanup LanceDB with validation
        lancedb_stats = self._cleanup_lancedb_comprehensive(lancedb_store, name)
        
        # Add LanceDB stats to result
        sqlite_result["cleanup_stats"]["lancedb_vectors"] = lancedb_stats
        
        # Check if there were any LanceDB errors
        if lancedb_stats["errors"]:
            sqlite_result["lancedb_warnings"] = lancedb_stats["errors"]
            if not force:
                sqlite_result["success"] = False
        
        return sqlite_result

    def _check_lancedb_consistency(self, lancedb_store, repo_name: str) -> dict:
        """Check consistency between metadata and LanceDB vector stores.
        
        Args:
            lancedb_store: LanceDBStore instance
            repo_name: Repository name
            
        Returns:
            Consistency report with statistics and issues
        """
        stats = {
            "consistent": True,
            "issues": [],
            "vector_counts": {}
        }
        
        try:
            # Count vectors in both models
            for model in ["small", "large"]:
                count = lancedb_store.count_repo_vectors(repo_name, model=model)
                stats["vector_counts"][model] = count
            
            # Could add more checks here, e.g., comparing metadata chunk counts
            # with vector counts
            
        except Exception as e:
            stats["consistent"] = False
            stats["issues"].append(f"LanceDB consistency check failed: {e}")
        
        return stats

    def validate_repo_consistency(self, lancedb_store, repo_id: int, repo_name: str) -> dict:
        """Comprehensive consistency validation between metadata and vector stores.
        
        Args:
            lancedb_store: LanceDBStore instance
            repo_id: Repository ID
            repo_name: Repository name
            
        Returns:
            Comprehensive consistency report
        """
        consistency_report = {
            "repo_id": repo_id,
            "repo_name": repo_name,
            "valid": True,
            "issues": [],
            "statistics": {}
        }
        
        with self._connect() as conn, closing(conn.cursor()) as cur:
            # Get metadata statistics
            cur.execute("SELECT COUNT(*) FROM files WHERE repo_id = ?", (repo_id,))
            metadata_files = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM chunk_content WHERE repo_id = ?", (repo_id,))
            metadata_chunks = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM chunk_locations WHERE content_id IN (SELECT id FROM chunk_content WHERE repo_id = ?)", (repo_id,))
            metadata_locations = cur.fetchone()[0]
            
            # Check for orphaned chunk_locations
            cur.execute("""
                SELECT COUNT(*) FROM chunk_locations cl
                LEFT JOIN chunk_content cc ON cl.content_id = cc.id
                WHERE cc.id IS NULL
            """)
            orphaned_locations = cur.fetchone()[0]
            
            if orphaned_locations > 0:
                consistency_report["valid"] = False
                consistency_report["issues"].append(f"Found {orphaned_locations} orphaned chunk locations")
            
            # Check for orphaned FTS entries
            cur.execute("""
                SELECT COUNT(*) FROM chunks_fts
                WHERE content_id NOT IN (SELECT id FROM chunk_content)
            """)
            orphaned_fts = cur.fetchone()[0]
            
            if orphaned_fts > 0:
                consistency_report["valid"] = False
                consistency_report["issues"].append(f"Found {orphaned_fts} orphaned FTS entries")
            
            # Check for chunk_content without files
            cur.execute("""
                SELECT COUNT(*) FROM chunk_content cc
                LEFT JOIN files f ON cc.file_id = f.id
                WHERE f.id IS NULL
            """)
            orphaned_content = cur.fetchone()[0]
            
            if orphaned_content > 0:
                consistency_report["valid"] = False
                consistency_report["issues"].append(f"Found {orphaned_content} chunk_content rows without files")
            
            # Check for files without repos
            cur.execute("""
                SELECT COUNT(*) FROM files f
                LEFT JOIN repos r ON f.repo_id = r.id
                WHERE r.id IS NULL
            """)
            orphaned_files = cur.fetchone()[0]
            
            if orphaned_files > 0:
                consistency_report["valid"] = False
                consistency_report["issues"].append(f"Found {orphaned_files} files without repos")
            
            consistency_report["statistics"] = {
                "metadata_files": metadata_files,
                "metadata_chunks": metadata_chunks,
                "metadata_locations": metadata_locations,
                "orphaned_locations": orphaned_locations,
                "orphaned_fts": orphaned_fts,
                "orphaned_content": orphaned_content,
                "orphaned_files": orphaned_files
            }
        
        # Check LanceDB consistency
        lancedb_stats = self._check_lancedb_consistency(lancedb_store, repo_name)
        consistency_report["lancedb"] = lancedb_stats
        
        if not lancedb_stats["consistent"]:
            consistency_report["valid"] = False
            consistency_report["issues"].extend(lancedb_stats["issues"])
        
        return consistency_report

    def repair_repository_consistency(self, repo_id: int, repo_name: str) -> dict:
        """Attempt to repair consistency issues in a repository.
        
        Args:
            repo_id: Repository ID
            repo_name: Repository name
            
        Returns:
            Repair report with actions taken and results
        """
        repair_report = {
            "repo_id": repo_id,
            "repo_name": repo_name,
            "repairs_performed": [],
            "success": True,
            "errors": []
        }
        
        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                # Repair orphaned chunk_locations
                cur.execute("""
                    SELECT COUNT(*) FROM chunk_locations cl
                    LEFT JOIN chunk_content cc ON cl.content_id = cc.id
                    WHERE cc.id IS NULL
                """)
                orphaned_count = cur.fetchone()[0]
                
                if orphaned_count > 0:
                    cur.execute("""
                        DELETE FROM chunk_locations
                        WHERE id IN (
                            SELECT cl.id FROM chunk_locations cl
                            LEFT JOIN chunk_content cc ON cl.content_id = cc.id
                            WHERE cc.id IS NULL
                        )
                    """)
                    repair_report["repairs_performed"].append(
                        f"Deleted {cur.rowcount} orphaned chunk locations"
                    )
                
                # Repair orphaned FTS entries
                cur.execute("""
                    SELECT COUNT(*) FROM chunks_fts
                    WHERE content_id NOT IN (SELECT id FROM chunk_content)
                """)
                orphaned_fts_count = cur.fetchone()[0]
                
                if orphaned_fts_count > 0:
                    cur.execute("""
                        DELETE FROM chunks_fts
                        WHERE content_id NOT IN (SELECT id FROM chunk_content)
                    """)
                    repair_report["repairs_performed"].append(
                        f"Deleted {cur.rowcount} orphaned FTS entries"
                    )
                
                # Repair orphaned chunk_content (without files)
                cur.execute("""
                    SELECT COUNT(*) FROM chunk_content cc
                    LEFT JOIN files f ON cc.file_id = f.id
                    WHERE f.id IS NULL
                """)
                orphaned_content_count = cur.fetchone()[0]
                
                if orphaned_content_count > 0:
                    # First delete FTS entries for this content
                    cur.execute("""
                        DELETE FROM chunks_fts
                        WHERE content_id IN (
                            SELECT cc.id FROM chunk_content cc
                            LEFT JOIN files f ON cc.file_id = f.id
                            WHERE f.id IS NULL
                        )
                    """)
                    
                    # Then delete locations
                    cur.execute("""
                        DELETE FROM chunk_locations
                        WHERE content_id IN (
                            SELECT cc.id FROM chunk_content cc
                            LEFT JOIN files f ON cc.file_id = f.id
                            WHERE f.id IS NULL
                        )
                    """)
                    
                    # Finally delete content
                    cur.execute("""
                        DELETE FROM chunk_content
                        WHERE id IN (
                            SELECT cc.id FROM chunk_content cc
                            LEFT JOIN files f ON cc.file_id = f.id
                            WHERE f.id IS NULL
                        )
                    """)
                    repair_report["repairs_performed"].append(
                        f"Deleted {cur.rowcount} orphaned chunk_content rows"
                    )
                
                # Repair orphaned files (without repos)
                cur.execute("""
                    SELECT COUNT(*) FROM files f
                    LEFT JOIN repos r ON f.repo_id = r.id
                    WHERE r.id IS NULL
                """)
                orphaned_files_count = cur.fetchone()[0]
                
                if orphaned_files_count > 0:
                    # Cascade delete: FTS -> locations -> content -> files
                    cur.execute("""
                        DELETE FROM chunks_fts
                        WHERE content_id IN (
                            SELECT cc.id FROM chunk_content cc
                            WHERE cc.file_id IN (
                                SELECT f.id FROM files f
                                LEFT JOIN repos r ON f.repo_id = r.id
                                WHERE r.id IS NULL
                            )
                        )
                    """)
                    
                    cur.execute("""
                        DELETE FROM chunk_locations
                        WHERE content_id IN (
                            SELECT cc.id FROM chunk_content cc
                            WHERE cc.file_id IN (
                                SELECT f.id FROM files f
                                LEFT JOIN repos r ON f.repo_id = r.id
                                WHERE r.id IS NULL
                            )
                        )
                    """)
                    
                    cur.execute("""
                        DELETE FROM chunk_content
                        WHERE file_id IN (
                            SELECT f.id FROM files f
                            LEFT JOIN repos r ON f.repo_id = r.id
                            WHERE r.id IS NULL
                        )
                    """)
                    
                    cur.execute("""
                        DELETE FROM files
                        WHERE id IN (
                            SELECT f.id FROM files f
                            LEFT JOIN repos r ON f.repo_id = r.id
                            WHERE r.id IS NULL
                        )
                    """)
                    repair_report["repairs_performed"].append(
                        f"Deleted {cur.rowcount} orphaned files"
                    )
                
                conn.commit()
                
            except Exception as e:
                conn.rollback()
                repair_report["success"] = False
                repair_report["errors"].append(f"Repair failed: {e}")
        
        return repair_report