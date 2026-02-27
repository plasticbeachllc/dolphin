from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import UTC
from pathlib import Path
from typing import Any, TypedDict

from sqlalchemy import event
from sqlmodel import SQLModel, create_engine

from kb.migrations import LATEST_SCHEMA_VERSION, SCHEMA_MIGRATIONS
from kb.retrieval.bm25_stats import BM25StatisticsCollector
from kb.security import PathValidator
from kb.store.connection_pool import SQLiteConnectionPool, get_connection_pool


class ActiveSessionError(RuntimeError):
    """Raised when attempting to start an indexing session while another is active."""


class RepoRecord(TypedDict):
    """Type for repository record dictionaries."""

    id: int
    root_path: str
    default_embed_model: str


class FileRecord(TypedDict):
    """Type for file record dictionaries."""

    id: int
    repo_id: int
    path: str
    ext: str | None
    language: str | None
    is_binary: bool
    size_bytes: int | None
    latest_commit_sha: str | None
    created_at: str
    updated_at: str


class FileInfo(TypedDict):
    """Type for minimal file info dictionaries."""

    id: int
    path: str


class ChunkInfo(TypedDict):
    """Type for chunk info dictionaries."""

    text_hash: str
    text: str
    file_id: int
    chunk_index: int
    start_line: int
    end_line: int


class SnapshotRecord(TypedDict):
    """Type for file snapshot dictionaries."""

    file_id: int
    path: str
    mtime_ns: int
    size_bytes: int
    content_hash: str
    last_indexed_at: str


class PendingChangeRecord(TypedDict):
    """Type for pending change record dictionaries."""

    id: int
    repo_id: int
    file_path: str
    change_type: str
    old_path: str | None
    detected_at: str
    processed: bool
    processed_at: str | None


def generate_fts_content_id(repo_id: int, file_id: int, text_hash: str) -> str:
    """Generate deterministic FTS5 content_id independent of embed_model.

    This ensures that the same text content (identified by repo_id, file_id, text_hash)
    always gets the same FTS5 content_id, regardless of which embedding model(s)
    are used to index it. This prevents duplicate FTS5 entries for the same content.

    Args:
        repo_id: Repository ID
        file_id: File ID
        text_hash: SHA-256 hash of chunk text content

    Returns:
        Deterministic content_id for FTS5 table (32-character hex string)
    """
    # Create a stable, deterministic identifier
    composite = f"{repo_id}:{file_id}:{text_hash}"
    return hashlib.sha256(composite.encode()).hexdigest()[:32]


logger = logging.getLogger(__name__)

# Sentinel used to separate search-enrichment tokens from actual content in FTS5.
_FTS_ENRICHMENT_SENTINEL = "\n__FTS_META__\n"

# Regex for splitting CamelCase / PascalCase identifiers into sub-tokens.
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _split_camel_case(name: str) -> list[str]:
    """Split a CamelCase identifier into lowercase sub-tokens.

    >>> _split_camel_case("IngestionPipeline")
    ['ingestion', 'pipeline']
    >>> _split_camel_case("HTMLParser")
    ['html', 'parser']
    >>> _split_camel_case("simple")
    ['simple']
    """
    parts = _CAMEL_SPLIT_RE.split(name)
    return [p.lower() for p in parts if p]


def _path_tokens(path: str) -> list[str]:
    """Extract searchable tokens from a file path.

    Splits on '/' and '.', strips common noise like file extensions everyone knows,
    and lowercases everything.

    >>> _path_tokens("kb/ingest/pipeline.py")
    ['kb', 'ingest', 'pipeline']
    """
    # Strip the file extension first, then split on path separators.
    # This avoids confusing directory names (e.g. "c/") with extensions (e.g. ".c").
    stem = re.sub(r"\.[^/\\]+$", "", path)
    parts = re.split(r"[/\\]", stem)
    return [p.lower() for p in parts if p]


def enrich_fts_content(
    content: str,
    path: str,
    symbol_name: str | None = None,
    symbol_path: str | None = None,
) -> str:
    """Build FTS5 content enriched with path tokens and CamelCase-split symbols.

    The enrichment tokens are appended after a sentinel line so they can be
    stripped when retrieving content for display (see ``strip_fts_enrichment``).
    """
    extra_tokens: list[str] = []

    # Add path components as searchable tokens
    extra_tokens.extend(_path_tokens(path))

    # Split CamelCase symbol names into sub-tokens
    if symbol_name:
        extra_tokens.extend(_split_camel_case(symbol_name))
    if symbol_path:
        for segment in re.split(r"[./]", symbol_path):
            if segment:
                extra_tokens.extend(_split_camel_case(segment))

    if not extra_tokens:
        return content

    unique = list(dict.fromkeys(extra_tokens))
    return content + _FTS_ENRICHMENT_SENTINEL + " ".join(unique)


def strip_fts_enrichment(content: str) -> str:
    """Remove enrichment tokens appended by ``enrich_fts_content``."""
    idx = content.find(_FTS_ENRICHMENT_SENTINEL)
    if idx == -1:
        return content
    return content[:idx]


class SQLiteMetadataStore:
    """SQLite-backed metadata store using SQLModel for schema materialization."""

    def __init__(self, db_path: Path | str) -> None:
        path_obj = Path(db_path) if isinstance(db_path, str) else db_path
        self.db_path = path_obj.expanduser().absolute()
        self._init_lock = threading.Lock()
        self._initialized = False
        self._initializing = False
        self._bm25_stats_collector: BM25StatisticsCollector | None = None
        self._bm25_stats_path: Path | None = None
        self._connection_pool: SQLiteConnectionPool | None = None
        self._applied_startup_migrations: list[str] = []

    def _get_connection_pool(self) -> SQLiteConnectionPool:
        """Lazily create (or fetch) the connection pool for this store."""

        if self._connection_pool is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection_pool = get_connection_pool(self.db_path)
        return self._connection_pool

    @contextmanager
    def _connect(self):
        """Provide a pooled SQLite connection as a context manager."""

        pool = self._get_connection_pool()
        with pool.connection() as conn:
            yield conn

    def _engine(self):
        # Create SQLAlchemy engine for SQLModel and enforce foreign_keys pragma on connect.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{self.db_path}")

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            try:
                dbapi_connection.execute("PRAGMA foreign_keys=ON")
            except Exception as exc:
                logger.error(
                    "Failed to enable SQLite foreign key enforcement; referential integrity cannot be guaranteed: %s",
                    exc,
                    exc_info=True,
                )
                raise

        return engine

    def initialize(self) -> None:
        """Thread-safe enhanced initialization with proper validation and error handling."""
        logger.info("[SQLiteMeta] initialize() called")
        # Fast path: check if already initialized
        if self._initialized:
            logger.info("[SQLiteMeta] Already initialized, skipping")
            return

        # Use lock to prevent concurrent initialization
        with self._init_lock:
            # Double-check pattern: another thread might have initialized while we were waiting
            if self._initialized:
                logger.info("[SQLiteMeta] Already initialized (double-check), skipping")
                return

            try:
                logger.info("[SQLiteMeta] Starting initialization...")
                self._initializing = True

                engine = self._engine()

                # Import models at call time to register them with SQLModel.metadata
                from . import sql_models as _models  # noqa: F401

                # Create all tables if they don't exist (via SQLModel models)
                logger.info("[SQLiteMeta] Creating SQLModel tables...")
                SQLModel.metadata.create_all(engine)
                logger.info("[SQLiteMeta] SQLModel tables created")

                # Validate foreign key support and constraints
                with self._connect() as conn, closing(conn.cursor()) as cur:
                    # Enable and verify foreign key constraints
                    cur.execute("PRAGMA foreign_keys = ON")

                    # Apply pending schema migrations before integrity checks and
                    # table validation to ensure startup is always on a canonical schema.
                    applied_migrations = self._run_pending_schema_migrations(conn, cur)
                    self._applied_startup_migrations = applied_migrations
                    if applied_migrations:
                        logger.warning(
                            "[SQLiteMeta] Auto-applied startup migration(s) to canonical schema v%s: %s",
                            LATEST_SCHEMA_VERSION,
                            ", ".join(applied_migrations),
                        )

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
                        "chunk_locations": "Chunk locations",
                        "code_nodes": "Code graph nodes",
                        "code_edges": "Code graph edges",
                        "node_aliases": "Code graph aliases",
                        "cross_repo_references": "Cross-repo references",
                        "pending_changes": "File sync pending changes",
                        "file_snapshots": "File sync snapshots",
                        "schema_version": "Metadata schema version tracking",
                    }

                    for table, description in expected_tables.items():
                        cur.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                            (table,),
                        )
                        if cur.fetchone() is None:
                            raise RuntimeError(
                                f"Database initialization failed: '{table}' table missing ({description})."
                            )

                        # Validate table schema
                        self._validate_table_schema(cur, table)

                    # Ensure single-writer enforcement for indexing sessions
                    self._ensure_active_session_index(cur)

                    logger.info("[SQLiteMeta] Table validation complete, creating FTS5 tables...")

                    # Robust FTS5 creation with version checking
                    self._create_fts5_table_safe(cur)

                    # Create code graph FTS5 index for symbol search
                    self._create_code_graph_fts5_safe(cur)

                    logger.info("[SQLiteMeta] FTS5 tables created, committing...")
                    conn.commit()
                    logger.info("[SQLiteMeta] Changes committed")

                # Post-initialization validation
                logger.info("[SQLiteMeta] Validating database integrity...")
                self._validate_database_integrity()

                # Mark as successfully initialized
                self._initialized = True
                logger.info("[SQLiteMeta] ✅ Initialization complete")

            finally:
                self._initializing = False

    def configure_bm25_statistics(self, stats_path: Path | str | None, *, max_samples: int = 100_000) -> None:
        """Enable collection of BM25 scores for normalization telemetry."""
        if stats_path is None:
            self._bm25_stats_collector = None
            self._bm25_stats_path = None
            return
        resolved = Path(stats_path) if isinstance(stats_path, str) else stats_path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._bm25_stats_collector = BM25StatisticsCollector(max_samples=max_samples)
        self._bm25_stats_path = resolved
        logger.info("[SQLiteMeta] BM25 statistics collection enabled", extra={"path": str(resolved)})

    def flush_bm25_statistics(self) -> Path | None:
        """Persist collected BM25 stats if enough samples exist."""
        if not self._bm25_stats_collector or not self._bm25_stats_path:
            return None
        return self._bm25_stats_collector.flush_to(self._bm25_stats_path)

    def _record_bm25_score(self, score: float) -> None:
        if self._bm25_stats_collector:
            self._bm25_stats_collector.record(score)

    def _ensure_schema_version_table(self, cur) -> None:
        """Ensure schema version tracking table exists with a singleton row."""
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        cur.execute(
            """
            INSERT INTO schema_version (id, version, updated_at)
            VALUES (1, 0, datetime('now'))
            ON CONFLICT(id) DO NOTHING
            """
        )

    def _get_schema_version(self, cur) -> int:
        """Fetch current metadata schema version."""
        cur.execute("SELECT version FROM schema_version WHERE id = 1")
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("schema_version row missing after initialization")
        return int(row[0])

    def _set_schema_version(self, cur, version: int) -> None:
        """Persist current metadata schema version."""
        cur.execute(
            """
            UPDATE schema_version
            SET version = ?, updated_at = datetime('now')
            WHERE id = 1
            """,
            (int(version),),
        )

    def _run_pending_schema_migrations(self, conn, cur) -> list[str]:
        """Apply all pending schema migrations in order."""
        self._ensure_schema_version_table(cur)
        current_version = self._get_schema_version(cur)

        if current_version < 0:
            raise RuntimeError(f"Invalid database schema version {current_version}.")

        if current_version > LATEST_SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {current_version} is newer than supported "
                f"version {LATEST_SCHEMA_VERSION}. Upgrade pb-dolphin."
            )

        applied: list[str] = []
        for migration in SCHEMA_MIGRATIONS:
            if migration.version <= current_version:
                continue

            logger.info(
                "[SQLiteMeta] Applying schema migration v%s (%s)...",
                migration.version,
                migration.name,
            )
            note = migration.apply(conn)
            self._set_schema_version(cur, migration.version)

            label = f"v{migration.version}:{migration.name}"
            if note:
                label = f"{label} ({note})"
            applied.append(label)
            current_version = migration.version

        return applied

    def get_applied_startup_migrations(self) -> list[str]:
        """Return migrations applied during the latest initialize() call."""
        return list(self._applied_startup_migrations)

    def _validate_table_schema(self, cur, table_name: str) -> None:
        """Validate table schema integrity."""
        # S3 Fix: Whitelist table names to prevent SQL injection
        ALLOWED_TABLES = {
            "repos",
            "sessions",
            "files",
            "chunk_content",
            "chunk_locations",
            "code_nodes",
            "code_edges",
            "node_aliases",
            "cross_repo_references",
            "pending_changes",
            "file_snapshots",
            "schema_version",
            "graph_metrics",
            "graph_snapshots",
            "graph_cache_state",
        }
        if table_name not in ALLOWED_TABLES:
            raise ValueError(f"Invalid table name: {table_name}")

        # Get table schema
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = cur.fetchall()

        if not columns:
            raise RuntimeError(f"Table {table_name} exists but has no columns")

        # Validate expected columns based on table type
        if table_name == "repos":
            required_cols = {"id", "name", "root_path", "default_embed_model"}
        elif table_name == "sessions":
            required_cols = {
                "id",
                "repo_id",
                "commit_sha",
                "branch",
                "embed_model",
                "status",
            }
        elif table_name == "files":
            required_cols = {"id", "repo_id", "path", "ext", "language", "is_binary"}
        elif table_name == "chunk_content":
            required_cols = {"id", "repo_id", "file_id", "text_hash", "embed_model"}
        elif table_name == "chunk_locations":
            required_cols = {"id", "content_id", "start_line", "end_line"}
        elif table_name == "schema_version":
            required_cols = {"id", "version", "updated_at"}
        else:
            return  # Skip validation for unknown tables

        actual_cols = {col[1] for col in columns}  # col[1] is column name
        missing_cols = required_cols - actual_cols
        if missing_cols:
            raise RuntimeError(f"Table {table_name} missing required columns: {missing_cols}")

    def _ensure_active_session_index(self, cur) -> None:
        """Ensure the active-session unique index exists to enforce single-writer behavior."""
        try:
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_active_repo
                ON sessions(repo_id)
                WHERE status NOT IN ('succeeded', 'failed', 'aborted')
                """
            )
        except sqlite3.OperationalError as exc:
            logger.warning("[SQLiteMeta] Failed to create active-session index: %s", exc)

    def _create_fts5_table_safe(self, cur) -> None:
        """Safely create FTS5 table with version and feature detection."""
        import sqlite3

        logger.info("[FTS5 Migration] _create_fts5_table_safe() called")

        # Check SQLite version and FTS5 support
        cur.execute("SELECT sqlite_version()")
        sqlite_version = cur.fetchone()[0]
        logger.info(f"[FTS5 Migration] SQLite version: {sqlite_version}")

        # Check if FTS5 is available and handle schema migration
        try:
            # Check if table already exists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'")
            table_exists = cur.fetchone()
            logger.info(f"[FTS5 Migration] Table exists: {bool(table_exists)}")

            if table_exists:
                # Test if it has the text_hash column by trying to use it
                # PRAGMA table_info doesn't work reliably with FTS5 virtual tables
                logger.info("[FTS5 Migration] Testing for text_hash column...")
                try:
                    cur.execute("SELECT text_hash FROM chunks_fts LIMIT 0")
                    logger.info("[FTS5 Migration] text_hash column exists - schema is up to date")
                    return  # Already has correct schema
                except sqlite3.OperationalError as e:
                    logger.info(f"[FTS5 Migration] SELECT text_hash failed: {e}")
                    error_msg = str(e).lower()
                    if "text_hash" in error_msg and ("no column" in error_msg or "no such column" in error_msg):
                        # Old schema - drop and recreate
                        logger.warning(
                            "[FTS5 Migration] 🔄 Migrating FTS5 table to new schema (adding text_hash column)..."
                        )
                        cur.execute("DROP TABLE chunks_fts")
                        logger.info("[FTS5 Migration] Dropped old chunks_fts table")
                        # Fall through to creation below
                    else:
                        raise

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
        logger.info("[FTS5 Migration] Creating chunks_fts table with new schema...")
        try:
            cur.execute(
                """
                CREATE VIRTUAL TABLE chunks_fts USING fts5(
                    content_id UNINDEXED,
                    repo UNINDEXED,
                    path UNINDEXED,
                    text_hash UNINDEXED,
                    content,
                    symbol_name,
                    symbol_path,
                    tokenize='porter unicode61'
                )
            """
            )
            logger.info("[FTS5 Migration] ✅ chunks_fts table created successfully")
        except sqlite3.OperationalError as e:
            logger.error(f"[FTS5 Migration] ❌ Failed to create FTS5 table: {e}")
            raise RuntimeError(f"Failed to create FTS5 table: {e}")

    def _create_code_graph_fts5_safe(self, cur) -> None:
        """Safely create FTS5 table for code graph symbol search."""
        import sqlite3

        try:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='code_nodes_fts'")
            if cur.fetchone():
                return  # Already exists

            # Create FTS5 table for code node symbol search
            cur.execute(
                """
                CREATE VIRTUAL TABLE code_nodes_fts USING fts5(
                    node_id UNINDEXED,
                    qualified_name,
                    name,
                    signature,
                    docstring,
                    tokenize='porter unicode61'
                )
            """
            )
        except sqlite3.OperationalError as e:
            # FTS5 support already checked, so this is a different error
            raise RuntimeError(f"Failed to create code_nodes_fts table: {e}")

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
                (
                    "chunk_locations without content",
                    """
                    SELECT COUNT(*) FROM chunk_locations cl
                    LEFT JOIN chunk_content cc ON cl.content_id = cc.id
                    WHERE cc.id IS NULL
                """,
                ),
                (
                    "chunk_content without files",
                    """
                    SELECT COUNT(*) FROM chunk_content cc
                    LEFT JOIN files f ON cc.file_id = f.id
                    WHERE f.id IS NULL
                """,
                ),
                (
                    "files without repos",
                    """
                    SELECT COUNT(*) FROM files f
                    LEFT JOIN repos r ON f.repo_id = r.id
                    WHERE r.id IS NULL
                """,
                ),
                (
                    "sessions without repos",
                    """
                    SELECT COUNT(*) FROM sessions s
                    LEFT JOIN repos r ON s.repo_id = r.id
                    WHERE r.id IS NULL
                """,
                ),
            ]

            for check_name, sql in orphaned_checks:
                cur.execute(sql)
                count = cur.fetchone()[0]
                if count > 0:
                    # Log warning but don't fail initialization for existing databases
                    print(f"Warning: Found {count} orphaned records in {check_name}")

    def record_repo(self, name: str, path: Path | str, *, default_embed_model: str = "large") -> None:
        """Insert or update a repo registration.

        Uses raw sqlite3 for simplicity; models are already materialized.

        Note: Normalizes to an absolute path string without filesystem access.

        Args:
            name: Repository name
            path: Repository root path (Path object or string)
            default_embed_model: Default embedding model to use
        """
        # Convert string to Path if needed and normalize without touching filesystem.
        path_obj = Path(path) if isinstance(path, str) else path
        normalized_path = path_obj.expanduser().absolute()

        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                INSERT INTO repos (name, root_path, default_embed_model, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(name) DO UPDATE SET
                  root_path=excluded.root_path,
                  default_embed_model=excluded.default_embed_model,
                  created_at=COALESCE(repos.created_at, datetime('now')),
                  updated_at=datetime('now')
                """,
                (name, str(normalized_path), default_embed_model),
            )
            conn.commit()

    def register_repo(self, name: str, path: str | Path, *, default_embed_model: str = "large") -> None:
        """Alias for record_repo for backward compatibility.

        Args:
            name: Repository name
            path: Repository root path (str or Path)
            default_embed_model: Default embedding model to use
        """
        from pathlib import Path as PathType

        path_obj = PathType(path) if isinstance(path, str) else path
        self.record_repo(name, path_obj, default_embed_model=default_embed_model)

    def get_session(self, session_id: int) -> dict[str, Any] | None:
        """Return a session row as a dict or None if not found."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT id, repo_id, commit_sha, branch, embed_model, status,
                       files_indexed, chunks_indexed, vectors_written, chunks_skipped, chunks_pruned,
                       created_at, ended_at, notes
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
                "notes": row[13],
            }

    def summarize(self) -> dict[str, int]:
        """Return simple counts for key entities, 0 if tables missing."""
        counts: dict[str, int] = {"repos": 0, "files": 0, "chunks": 0}
        try:
            with self._connect() as conn, closing(conn.cursor()) as cur:
                for key, table in (
                    ("repos", "repos"),
                    ("files", "files"),
                    ("chunks", "chunk_content"),
                ):
                    cur.execute(f"SELECT COUNT(1) FROM {table}")
                    (value,) = cur.fetchone() or (0,)
                    counts[key] = int(value)
        except sqlite3.Error:
            # If initialization hasn't run, keep zeros.
            pass
        return counts

    def list_all_repos(self) -> list[dict[str, Any]]:
        """List all registered repositories with their metadata.

        Returns:
            List of repo dicts with id, name, root_path, default_embed_model
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT id, name, root_path, default_embed_model,
                       COALESCE(created_at, updated_at) as created_at,
                       updated_at
                FROM repos
                ORDER BY name
            """
            )
            rows = cur.fetchall() or []
            return [
                {
                    "id": int(row[0]),
                    "name": str(row[1]),
                    "root_path": str(row[2]),
                    "default_embed_model": str(row[3]),
                    "created_at": row[4],
                    "updated_at": row[5],
                }
                for row in rows
            ]

    def get_repo_counts(self, repo_id: int) -> dict[str, int]:
        """Get file and chunk counts for a repository.

        Returns:
            Dict with 'files' and 'chunks' integer counts.
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute("SELECT COUNT(*) FROM files WHERE repo_id = ?", (repo_id,))
            file_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM chunk_content WHERE repo_id = ?", (repo_id,))
            chunk_count = cur.fetchone()[0]
            return {"files": file_count, "chunks": chunk_count}

    def get_all_repo_counts(self) -> dict[int, dict[str, int]]:
        """Get file and chunk counts for all repositories in bulk.

        Returns:
            Dict mapping repo_id to {'files': int, 'chunks': int}.
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT repo_id, 'files' AS kind, COUNT(*) AS cnt FROM files GROUP BY repo_id
                UNION ALL
                SELECT repo_id, 'chunks' AS kind, COUNT(*) AS cnt FROM chunk_content GROUP BY repo_id
                """
            )
            result: dict[int, dict[str, int]] = {}
            for row in cur.fetchall():
                rid = int(row[0])
                if rid not in result:
                    result[rid] = {"files": 0, "chunks": 0}
                result[rid][str(row[1])] = int(row[2])
            return result

    def get_repo_by_name(self, name: str) -> RepoRecord | None:
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

    def get_repos_by_names(self, names: list[str]) -> dict[str, RepoRecord]:
        """Return repo records for the given names. Missing names are omitted."""
        if not names:
            return {}
        # Chunk into batches of 500 to stay within SQLite's SQLITE_LIMIT_VARIABLE_NUMBER (default 999).
        result: dict[str, RepoRecord] = {}
        batch_size = 500
        with self._connect() as conn, closing(conn.cursor()) as cur:
            for i in range(0, len(names), batch_size):
                batch = names[i : i + batch_size]
                placeholders = ",".join("?" * len(batch))
                cur.execute(
                    f"SELECT id, name, root_path, default_embed_model FROM repos WHERE name IN ({placeholders})",
                    batch,
                )
                for row in cur.fetchall():
                    result[str(row[1])] = {
                        "id": int(row[0]),
                        "root_path": str(row[2]),
                        "default_embed_model": str(row[3]),
                    }
        return result

    def begin_session(self, repo_id: int, commit_sha: str, branch: str, embed_model: str) -> int:
        """Create a new ingestion session and return its id."""
        from datetime import datetime

        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT id, status FROM sessions
                WHERE repo_id = ? AND status NOT IN ('succeeded', 'failed', 'aborted')
                LIMIT 1
                """,
                (repo_id,),
            )
            active = cur.fetchone()
            if active:
                raise ActiveSessionError(
                    f"Active indexing session already running for repo_id={repo_id} (session {active[0]})"
                )

            # Use ISO format timestamp for consistency with other timestamp fields
            created_at = datetime.now(UTC).isoformat()

            try:
                cur.execute(
                    """
                    INSERT INTO sessions (repo_id, commit_sha, branch, embed_model, status,
                                         files_indexed, chunks_indexed, vectors_written, chunks_skipped, chunks_pruned,
                                         created_at)
                    VALUES (?, ?, ?, ?, 'running', 0, 0, 0, 0, 0, ?)
                    """,
                    (repo_id, commit_sha, branch, embed_model, created_at),
                )
            except sqlite3.IntegrityError as exc:
                raise ActiveSessionError(f"Active indexing session already running for repo_id={repo_id}") from exc
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

    _ALLOWED_SESSION_COLUMNS = frozenset(
        {
            "files_indexed",
            "chunks_indexed",
            "vectors_written",
            "chunks_skipped",
            "chunks_pruned",
        }
    )

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
        column_values: dict[str, int] = {}
        if files_indexed is not None:
            column_values["files_indexed"] = int(files_indexed)
        if chunks_indexed is not None:
            column_values["chunks_indexed"] = int(chunks_indexed)
        if vectors_written is not None:
            column_values["vectors_written"] = int(vectors_written)
        if chunks_skipped is not None:
            column_values["chunks_skipped"] = int(chunks_skipped)
        if chunks_pruned is not None:
            column_values["chunks_pruned"] = int(chunks_pruned)
        if not column_values:
            return
        # Guard against accidental injection: only allow known column names.
        # All current callers pass literal keyword arguments, so this is a
        # programming-error check rather than a runtime-input guard.
        for col in column_values:
            assert col in self._ALLOWED_SESSION_COLUMNS, f"Disallowed session column: {col}"
        sets = [f"{col} = ?" for col in column_values]
        params: list[int] = list(column_values.values())
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
                (int(repo_id),),
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
                (int(repo_id), path),
            )
            row = cur.fetchone()
            return int(row[0]) if row else None

    def get_file_by_path(self, repo_id: int, path: str) -> FileRecord | None:
        """Get file metadata by repo_id and path.

        Returns file record dict or None if not found.
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """SELECT id, repo_id, path, ext, language, is_binary,
                          size_bytes, latest_commit_sha, created_at, updated_at
                   FROM files WHERE repo_id = ? AND path = ?""",
                (int(repo_id), path),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": int(row[0]),
                "repo_id": int(row[1]),
                "path": str(row[2]),
                "ext": row[3],
                "language": row[4],
                "is_binary": bool(row[5]),
                "size_bytes": row[6],
                "latest_commit_sha": row[7],
                "created_at": row[8],
                "updated_at": row[9],
            }

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
        """Insert or update a file row; return file id.

        Note: We always query for the id after upsert because SQLite's lastrowid
        is unreliable after ON CONFLICT DO UPDATE - it may return a stale value
        from a previous INSERT instead of the correct id.
        """
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
            # Always query for the id - don't rely on lastrowid which is unreliable
            # after ON CONFLICT DO UPDATE (it may return stale value from previous INSERT)
            cur.execute(
                "SELECT id FROM files WHERE repo_id = ? AND path = ?",
                (int(repo_id), path),
            )
            row = cur.fetchone()
            if not row:
                # This should never happen after a successful upsert
                raise RuntimeError(f"Failed to find file after upsert: repo_id={repo_id}, path={path}")
            file_id = int(row[0])
            conn.commit()
            return file_id

    def delete_file(self, repo_id: int, file_id: int) -> None:
        """Delete a file from the catalog."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                cur.execute("DELETE FROM files WHERE id = ? AND repo_id = ?", (int(file_id), int(repo_id)))
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                dependency_counts = self._collect_file_dependency_counts(cur, int(file_id))
                dependency_summary = (
                    ", ".join(f"{table}={count}" for table, count in dependency_counts.items())
                    if dependency_counts
                    else "none detected"
                )
                raise RuntimeError(
                    "Failed to delete file due to foreign key constraints "
                    f"(repo_id={int(repo_id)}, file_id={int(file_id)}, dependents={dependency_summary}). "
                    f"Ensure startup auto-migration to canonical schema v{LATEST_SCHEMA_VERSION} has run."
                ) from exc

    def _collect_file_dependency_counts(self, cur, file_id: int) -> dict[str, int]:
        """Collect remaining dependent rows for a file on FK deletion failure.

        Uses a single query with UNION ALL to avoid multiple round-trips.
        """
        # Build a single query checking all dependency tables at once.
        checks = [
            ("chunk_content", "SELECT 'chunk_content' AS tbl, COUNT(*) AS cnt FROM chunk_content WHERE file_id = ?"),
            ("code_nodes", "SELECT 'code_nodes', COUNT(*) FROM code_nodes WHERE file_id = ?"),
            ("node_aliases", "SELECT 'node_aliases', COUNT(*) FROM node_aliases WHERE file_id = ?"),
            (
                "graph_metrics",
                "SELECT 'graph_metrics', COUNT(*) FROM graph_metrics gm "
                "JOIN code_nodes cn ON gm.node_id = cn.id WHERE cn.file_id = ?",
            ),
            ("file_snapshots", "SELECT 'file_snapshots', COUNT(*) FROM file_snapshots WHERE file_id = ?"),
        ]

        # Filter to only tables that exist in the schema.
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cur.fetchall()}

        parts = []
        params: list[int] = []
        for table_name, sql in checks:
            if table_name not in existing_tables:
                continue
            parts.append(sql)
            params.append(int(file_id))

        if not parts:
            return {}

        combined_sql = " UNION ALL ".join(parts)
        cur.execute(combined_sql, tuple(params))
        counts: dict[str, int] = {}
        for row in cur.fetchall():
            tbl, cnt = str(row[0]), int(row[1])
            if cnt > 0:
                counts[tbl] = cnt
        return counts

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

    def upsert_chunk_content_row(
        self,
        repo_id: int,
        file_id: int,
        text_hash: str,
        embed_model: str,
        *,
        content_id: str | None = None,
    ) -> str:
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

    def sync_locations_for_content_row(
        self, content_id: str, desired_locations: list[dict[str, object]]
    ) -> dict[str, int]:
        """Reconcile locations for a single content_id to match desired.

        desired_locations: list of dicts with keys: start_line, end_line, symbol_kind, symbol_name, symbol_path
        Returns counts: {inserted, updated, deleted}
        """
        import uuid

        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                conn.execute("BEGIN IMMEDIATE")
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
                    start_raw = d.get("start_line")
                    end_raw = d.get("end_line")
                    if not isinstance(start_raw, (int, float, str, bytes, bytearray)) or not isinstance(
                        end_raw, (int, float, str, bytes, bytearray)
                    ):
                        continue
                    try:
                        start_line = int(start_raw)
                        end_line = int(end_raw)
                    except (TypeError, ValueError):
                        continue
                    desired_map[(start_line, end_line)] = (
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
                            (
                                new[0],
                                new[1],
                                new[2],
                                content_id,
                                int(pos[0]),
                                int(pos[1]),
                            ),
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
                conn.execute("BEGIN IMMEDIATE")
                # First, get the file path for FTS5 cleanup
                cur.execute("SELECT path FROM files WHERE id = ?", (int(file_id),))
                file_row = cur.fetchone()
                file_path = str(file_row[0]) if file_row else None

                if current_hashes:
                    placeholders = ",".join(["?"] * len(current_hashes))
                    params = (
                        int(repo_id),
                        int(file_id),
                        embed_model,
                        *list(current_hashes),
                    )
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
        Verifies file_id exists before INSERT to provide clear error handling.
        """
        import uuid

        mapping: dict[str, str] = {}
        if not hashes:
            return mapping
        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                conn.execute("BEGIN IMMEDIATE")
                # Pre-check: Verify the file exists in the files table
                # This provides a clearer error message than an FK constraint failure
                cur.execute("SELECT id, path FROM files WHERE id = ?", (int(file_id),))
                file_row = cur.fetchone()
                if not file_row:
                    # The file row doesn't exist - this shouldn't happen but can occur
                    # due to race conditions or incomplete cleanup. Log and raise.
                    logger.error(
                        f"File id {file_id} not found in files table. "
                        f"Cannot insert chunk_content rows. This indicates stale data or race condition."
                    )
                    raise ValueError(
                        f"File id {file_id} does not exist in files table. "
                        f"The file may have been deleted or not yet committed."
                    )

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
            except sqlite3.IntegrityError as e:
                conn.rollback()
                # Provide more context for FK constraint failures
                if "FOREIGN KEY constraint failed" in str(e):
                    logger.error(
                        f"FOREIGN KEY constraint failed inserting chunk_content. "
                        f"repo_id={repo_id}, file_id={file_id}, embed_model={embed_model}. "
                        f"This may indicate the file was deleted during processing."
                    )
                raise
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

        Returns stats: {"content_upserted": int, "locations_inserted": int,
                       "locations_updated": int, "locations_deleted": int, "content_pruned": int}
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

    def get_all_files_for_repo(self, repo_id: int) -> list[dict[str, Any]]:
        """Get all files for a repository.

        Returns list of dicts with keys: id, path
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                "SELECT id, path FROM files WHERE repo_id = ? ORDER BY path",
                (int(repo_id),),
            )
            rows = cur.fetchall() or []
            return [{"id": int(r[0]), "path": str(r[1])} for r in rows]

    def get_chunks_for_file(self, repo_id: int, path: str) -> list[dict[str, Any]] | None:
        """Get all chunks (content rows) for a file by repo_id and path.

        Args:
            repo_id: Repository ID
            path: File path relative to repo root

        Returns list of dicts or None if no chunks found.
        """
        # First get the file_id
        file_id = self.get_file_id(repo_id, path)
        if file_id is None:
            return None

        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute("SELECT id FROM chunk_content WHERE file_id = ?", (int(file_id),))
            rows = cur.fetchall() or []
            return [{"id": str(r[0])} for r in rows]

    @staticmethod
    def _prepare_fts5_query(query: str) -> str:
        """Convert a plain-text query to an FTS5 OR query for broader matching.

        FTS5 uses implicit AND by default, which is too restrictive for search:
        "ingestion indexer" requires BOTH terms in a chunk.  Converting to OR
        ensures partial matches surface while BM25 naturally ranks multi-term
        matches higher.

        Queries that already contain explicit FTS5 operators or quoted phrases
        are passed through unchanged.
        """
        tokens = query.split()
        if len(tokens) <= 1:
            return query

        # Preserve queries with explicit FTS5 operators or quoted phrases
        fts5_operators = {"AND", "OR", "NOT", "NEAR"}
        if any(t.upper() in fts5_operators for t in tokens):
            return query
        if '"' in query:
            return query

        return " OR ".join(tokens)

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
        if any(char in query for char in [";", "\\", "\x00"]):
            return []

        fts_query = self._prepare_fts5_query(query)

        try:
            with self._connect() as conn, closing(conn.cursor()) as cur:
                # Build FTS5 query with filters
                conditions = ["chunks_fts MATCH ?"]
                params = [fts_query]

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
                        text_hash,
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
                    score = float(row[4])
                    self._record_bm25_score(score)
                    results.append(
                        {
                            "chunk_id": str(row[0]),
                            "repo": str(row[1]),
                            "path": str(row[2]),
                            "text_hash": str(row[3]),  # Include text_hash for hydration
                            "score": score,  # Positive BM25 score
                            "rank": int(row[5]),
                        }
                    )

                return results
        except sqlite3.Error:
            # Return empty results on any FTS5 error
            return []

    def index_chunk_for_fts(
        self,
        content_id: str,
        repo: str,
        path: str,
        text_hash: str,
        content: str,
        symbol_name: str | None = None,
        symbol_path: str | None = None,
    ) -> None:
        """Index a chunk in the FTS5 table for BM25 search.

        Args:
            content_id: Deterministic chunk identifier (from generate_fts_content_id)
            repo: Repository name
            path: File path
            text_hash: SHA-256 hash of chunk content (for joining with chunk_content)
            content: Chunk text content (will be tokenized and stemmed)
            symbol_name: Optional symbol name for exact matching
            symbol_path: Optional fully qualified symbol path
        """

        enriched = enrich_fts_content(content, path, symbol_name, symbol_path)

        with self._connect() as conn, closing(conn.cursor()) as cur:
            # Upsert: replace if exists, insert if new
            cur.execute(
                """
                INSERT OR REPLACE INTO chunks_fts
                (content_id, repo, path, text_hash, content, symbol_name, symbol_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (content_id, repo, path, text_hash, enriched, symbol_name, symbol_path),
            )
            conn.commit()

    def bulk_index_chunks_for_fts(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        """Bulk index multiple chunks for better performance.

        Args:
            chunks: List of chunk dicts with keys:
                - content_id, repo, path, text_hash, content, symbol_name, symbol_path

        Returns:
            Number of chunks indexed
        """
        if not chunks:
            return 0

        with self._connect() as conn, closing(conn.cursor()) as cur:
            # Runtime schema migration check - ensure FTS5 table has text_hash column
            # This catches cases where initialize() was already called before the migration was added
            import sqlite3

            try:
                cur.execute("SELECT text_hash FROM chunks_fts LIMIT 0")
            except sqlite3.OperationalError as e:
                error_msg = str(e).lower()
                if "text_hash" in error_msg and ("no column" in error_msg or "no such column" in error_msg):
                    logger.warning(f"[FTS5 Migration] Runtime check: text_hash column missing ({e}), migrating now...")
                    cur.execute("DROP TABLE IF EXISTS chunks_fts")
                    cur.execute(
                        """
                        CREATE VIRTUAL TABLE chunks_fts USING fts5(
                            content_id UNINDEXED,
                            repo UNINDEXED,
                            path UNINDEXED,
                            text_hash UNINDEXED,
                            content,
                            symbol_name,
                            symbol_path,
                            tokenize='porter unicode61'
                        )
                    """
                    )
                    conn.commit()
                    logger.info("[FTS5 Migration] Runtime migration complete")
                else:
                    raise

            # Proceed with bulk insert (enrich content with path/symbol tokens)
            cur.executemany(
                """
                INSERT OR REPLACE INTO chunks_fts
                (content_id, repo, path, text_hash, content, symbol_name, symbol_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    (
                        c["content_id"],
                        c["repo"],
                        c["path"],
                        c["text_hash"],
                        enrich_fts_content(
                            c["content"],
                            c["path"],
                            c.get("symbol_name"),
                            c.get("symbol_path"),
                        ),
                        c.get("symbol_name"),
                        c.get("symbol_path"),
                    )
                    for c in chunks
                ],
            )
            conn.commit()
            return len(chunks)

    def rebuild_fts5_table(self) -> None:
        """Drop and recreate the FTS5 table with updated schema.

        This is useful when migrating to the new deterministic content_id format
        or when the FTS5 schema changes. After rebuilding, you'll need to
        re-index all chunks using bulk_index_chunks_for_fts().
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            # Python's default sqlite3 isolation mode auto-commits before DDL
            # statements, making DROP and CREATE run as separate autocommit ops.
            # Switch to isolation_level=None (autocommit) so we can issue an
            # explicit BEGIN and wrap both DDL ops in a single atomic transaction.
            saved_isolation = conn.isolation_level
            conn.isolation_level = None
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur.execute("DROP TABLE IF EXISTS chunks_fts")
                self._create_fts5_table_safe(cur)
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            finally:
                conn.isolation_level = saved_isolation

    def get_chunk_by_id(self, chunk_id: str) -> dict[str, Any] | None:
        """Get full chunk metadata by content_id.

        Returns:
            Dict with chunk metadata or None if not found.
            Includes 'repo_name' resolved via the repos table.
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
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
                    cl.symbol_path,
                    r.name
                FROM chunk_content cc
                JOIN files f ON cc.file_id = f.id
                JOIN repos r ON f.repo_id = r.id
                LEFT JOIN chunk_locations cl ON cc.id = cl.content_id
                WHERE cc.id = ?
            """,
                (chunk_id,),
            )

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
                "repo_name": str(row[12]),
            }

    def get_chunk_locations_by_identity(
        self,
        repo_id: int,
        file_id: int,
        text_hash: str,
        embed_model: str,
    ) -> list[dict[str, Any]]:
        """Get all locations for a chunk content identity."""

        with self._connect() as conn, closing(conn.cursor()) as cur:
            # We fetch all locations for the text_hash, regardless of embed_model,
            # so we can fall back to other models if the requested one is missing.
            cur.execute(
                """
                SELECT
                    cl.content_id,
                    cl.start_line,
                    cl.end_line,
                    cl.symbol_kind,
                    cl.symbol_name,
                    cl.symbol_path,
                    cc.embed_model
                FROM chunk_locations cl
                JOIN chunk_content cc ON cl.content_id = cc.id
                WHERE cc.repo_id = ? AND cc.file_id = ? AND cc.text_hash = ?
                ORDER BY cl.start_line ASC
                """,
                (repo_id, file_id, text_hash),
            )

            # Group locations by embed_model
            locations_by_model: dict[str, list[dict[str, Any]]] = {}
            for row in cur.fetchall():
                model = row[6]
                if model not in locations_by_model:
                    locations_by_model[model] = []

                locations_by_model[model].append(
                    {
                        "content_id": str(row[0]),
                        "start_line": int(row[1]) if row[1] is not None else None,
                        "end_line": int(row[2]) if row[2] is not None else None,
                        "symbol_kind": row[3],
                        "symbol_name": row[4],
                        "symbol_path": row[5],
                        "embed_model": model,
                    }
                )

            # Prefer the requested model, otherwise fall back to any available model
            if embed_model in locations_by_model:
                return locations_by_model[embed_model]

            # Fallback: return the first available model's locations
            # (sorting keys to be deterministic)
            sorted_models = sorted(locations_by_model.keys())
            if sorted_models:
                return locations_by_model[sorted_models[0]]

            return []

    def get_bm25_hydration_map(self, content_ids: list[str], embed_model: str) -> dict[str, dict[str, Any]]:
        """Bulk-hydrate BM25 hits keyed by deterministic FTS content_id.

        Args:
            content_ids: FTS content_ids returned by bm25_search
            embed_model: Preferred embedding model for location selection

        Returns:
            Mapping of content_id -> hydration payload:
                {
                    "repo_id": int,
                    "file_id": int,
                    "text_hash": str,
                    "embed_model": str,
                    "locations": list[dict[str, Any]],
                }
        """
        if not content_ids:
            return {}

        # Preserve caller order while removing duplicates.
        ordered_ids: list[str] = []
        seen: set[str] = set()
        for content_id in content_ids:
            if content_id in seen:
                continue
            seen.add(content_id)
            ordered_ids.append(content_id)

        placeholders = ",".join(["?"] * len(ordered_ids))
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                f"""
                SELECT
                    fts.content_id,
                    r.id AS repo_id,
                    f.id AS file_id,
                    fts.text_hash,
                    cc.embed_model,
                    cl.start_line,
                    cl.end_line,
                    cl.symbol_kind,
                    cl.symbol_name,
                    cl.symbol_path
                FROM chunks_fts fts
                JOIN repos r
                  ON r.name = fts.repo
                JOIN files f
                  ON f.repo_id = r.id AND f.path = fts.path
                JOIN chunk_content cc
                  ON cc.repo_id = r.id AND cc.file_id = f.id AND cc.text_hash = fts.text_hash
                LEFT JOIN chunk_locations cl
                  ON cl.content_id = cc.id
                WHERE fts.content_id IN ({placeholders})
                ORDER BY fts.content_id, cc.embed_model, cl.start_line ASC, cl.end_line ASC
                """,
                tuple(ordered_ids),
            )
            rows = cur.fetchall() or []

        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            content_id = str(row[0])
            repo_id = int(row[1])
            file_id = int(row[2])
            text_hash = str(row[3])
            model = str(row[4])
            start_line = int(row[5]) if row[5] is not None else None
            end_line = int(row[6]) if row[6] is not None else None
            symbol_kind = row[7]
            symbol_name = row[8]
            symbol_path = row[9]

            grouped_entry = grouped.setdefault(
                content_id,
                {
                    "repo_id": repo_id,
                    "file_id": file_id,
                    "text_hash": text_hash,
                    "models": {},
                },
            )

            model_locations = grouped_entry["models"].setdefault(model, [])
            if start_line is None or end_line is None:
                continue
            model_locations.append(
                {
                    "start_line": start_line,
                    "end_line": end_line,
                    "symbol_kind": symbol_kind,
                    "symbol_name": symbol_name,
                    "symbol_path": symbol_path,
                }
            )

        hydrated: dict[str, dict[str, Any]] = {}
        for content_id, entry in grouped.items():
            models: dict[str, list[dict[str, Any]]] = entry["models"]
            chosen_model: str | None = None

            preferred_locations = models.get(embed_model) or []
            if preferred_locations:
                chosen_model = embed_model
            else:
                available_models = sorted(model_name for model_name, locations in models.items() if locations)
                if available_models:
                    chosen_model = available_models[0]
                elif models:
                    # Keep deterministic behavior if we only have model identity but no locations.
                    chosen_model = sorted(models.keys())[0]

            if chosen_model is None:
                continue

            hydrated[content_id] = {
                "repo_id": entry["repo_id"],
                "file_id": entry["file_id"],
                "text_hash": entry["text_hash"],
                "embed_model": chosen_model,
                "locations": models.get(chosen_model, []),
            }

        return hydrated

    def get_chunk_by_content_identity(
        self,
        repo_id: int,
        file_id: int,
        text_hash: str,
    ) -> dict[str, Any] | None:
        """Get chunk metadata using deterministic FTS identity components."""

        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT
                    cc.id,
                    cc.text_hash,
                    cc.embed_model,
                    cc.first_indexed_at,
                    cc.last_indexed_at,
                    f.path,
                    f.language
                FROM chunk_content cc
                JOIN files f ON cc.file_id = f.id
                WHERE cc.repo_id = ? AND cc.file_id = ? AND cc.text_hash = ?
                ORDER BY
                    CASE WHEN cc.last_indexed_at IS NOT NULL THEN 0 ELSE 1 END,
                    cc.last_indexed_at DESC
                LIMIT 1
                """,
                (repo_id, file_id, text_hash),
            )

            row = cur.fetchone()
            if not row:
                return None

            content_id = str(row[0])
            metadata: dict[str, Any] = {
                "chunk_id": content_id,
                "text_hash": str(row[1]),
                "embed_model": str(row[2]),
                "first_indexed_at": row[3],
                "last_indexed_at": row[4],
                "path": str(row[5]),
                "language": row[6],
            }

            cur.execute(
                """
                SELECT
                    start_line,
                    end_line,
                    symbol_kind,
                    symbol_name,
                    symbol_path
                FROM chunk_locations
                WHERE content_id = ?
                ORDER BY
                    CASE WHEN last_seen_at IS NOT NULL THEN 0 ELSE 1 END,
                    last_seen_at DESC,
                    start_line ASC
                LIMIT 1
                """,
                (content_id,),
            )
            location = cur.fetchone()

            if location:
                metadata.update(
                    {
                        "start_line": (int(location[0]) if location[0] is not None else None),
                        "end_line": (int(location[1]) if location[1] is not None else None),
                        "symbol_kind": location[2],
                        "symbol_name": location[3],
                        "symbol_path": location[4],
                    }
                )

            return metadata

    def get_chunk_contents(self, chunk_ids: list[str]) -> dict[str, str]:
        """Get a mapping of chunk_id to its content.

        Tries to fetch content from FTS table first (preferred), but falls back
        to reconstructing content from files if FTS entries don't exist.

        Note: chunk_ids can be either:
        - Deterministic FTS content_ids (from generate_fts_content_id)
        - UUID-based chunk_content.id values (legacy)

        This method handles both by joining on text_hash.
        """
        if not chunk_ids:
            return {}

        placeholders = ",".join(["?"] * len(chunk_ids))

        # Try FTS table first (contains actual chunk content)
        # Join on text_hash since FTS5 now uses deterministic content_ids
        fts_query = f"""
            SELECT fts.content_id, fts.content
            FROM chunks_fts fts
            WHERE fts.content_id IN ({placeholders})
        """

        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(fts_query, chunk_ids)
            rows = cur.fetchall()
            result = {str(row[0]): strip_fts_enrichment(str(row[1])) for row in rows}

            # If all chunks found in FTS, return immediately
            if len(result) == len(chunk_ids):
                return result

            # For chunks not in FTS, try to get content from files
            missing_ids = [cid for cid in chunk_ids if cid not in result]
            if missing_ids:
                # Get file path and line ranges for missing chunks
                placeholders_missing = ",".join(["?"] * len(missing_ids))
                fallback_query = f"""
                    SELECT cc.id, f.path, r.root_path, cl.start_line, cl.end_line
                    FROM chunk_content cc
                    JOIN files f ON cc.file_id = f.id
                    JOIN repos r ON cc.repo_id = r.id
                    LEFT JOIN chunk_locations cl ON cc.id = cl.content_id
                    WHERE cc.id IN ({placeholders_missing})
                """
                cur.execute(fallback_query, missing_ids)
                fallback_rows = cur.fetchall()

                # Read content from files (best effort)

                for row in fallback_rows:
                    chunk_id, file_path, repo_root, start_line, end_line = row
                    if not all([file_path, repo_root, start_line, end_line]):
                        continue

                    try:
                        # Validate path to prevent directory traversal attacks
                        validator = PathValidator(base_dir=repo_root)
                        full_path = validator.validate(file_path)
                        if full_path.exists():
                            lines = full_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                            # Extract lines (1-indexed to 0-indexed)
                            chunk_lines = lines[start_line - 1 : end_line]
                            result[str(chunk_id)] = "\n".join(chunk_lines)
                    except Exception:
                        # If we can't read the file, skip this chunk
                        logger.debug("Could not read file for chunk_id=%s; skipping.", chunk_id, exc_info=True)

            return result

    # =====================
    # Enhanced Repository Removal (Phase 2)
    # =====================

    def get_active_sessions(self, repo_id: int) -> list:
        """Get all active (non-terminal) sessions for a repository."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT id, status, created_at FROM sessions
                WHERE repo_id = ? AND status NOT IN ('succeeded', 'failed', 'aborted')
                ORDER BY created_at DESC
            """,
                (repo_id,),
            )
            return cur.fetchall()

    def terminate_active_sessions(self, repo_id: int) -> int:
        """Terminate all active sessions for a repository."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                UPDATE sessions
                SET status = 'aborted', ended_at = datetime('now')
                WHERE repo_id = ? AND status NOT IN ('succeeded', 'failed', 'aborted')
            """,
                (repo_id,),
            )
            terminated = cur.rowcount
            conn.commit()
            return terminated

    def abort_stale_sessions(self, *, repo_id: int | None = None, reason: str) -> int:
        """Abort any active sessions (typically after crash recovery)."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            params: tuple[Any, ...]
            if repo_id is None:
                params = (reason, reason)
                cur.execute(
                    """
                    UPDATE sessions
                    SET status = 'aborted',
                        ended_at = datetime('now'),
                        notes = CASE
                            WHEN notes IS NULL OR notes = '' THEN ?
                            ELSE notes || ' | ' || ?
                        END
                    WHERE status NOT IN ('succeeded', 'failed', 'aborted')
                    """,
                    params,
                )
            else:
                params = (reason, reason, repo_id)
                cur.execute(
                    """
                    UPDATE sessions
                    SET status = 'aborted',
                        ended_at = datetime('now'),
                        notes = CASE
                            WHEN notes IS NULL OR notes = '' THEN ?
                            ELSE notes || ' | ' || ?
                        END
                    WHERE repo_id = ? AND status NOT IN ('succeeded', 'failed', 'aborted')
                    """,
                    params,
                )
            aborted = cur.rowcount
            conn.commit()
            return aborted

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
        cur.execute(
            """
            SELECT COUNT(*) FROM chunk_locations
            WHERE content_id IN (SELECT id FROM chunk_content WHERE repo_id = ?)
        """,
            (repo_id,),
        )
        counts["chunk_locations"] = cur.fetchone()[0]

        # Count FTS entries
        cur.execute("SELECT COUNT(*) FROM chunks_fts WHERE repo = ?", (repo_name,))
        counts["fts_entries"] = cur.fetchone()[0]

        # Count sessions
        cur.execute("SELECT COUNT(*) FROM sessions WHERE repo_id = ?", (repo_id,))
        counts["sessions"] = cur.fetchone()[0]

        if self._table_exists(cur, "file_snapshots"):
            cur.execute("SELECT COUNT(*) FROM file_snapshots WHERE repo_id = ?", (repo_id,))
            counts["file_snapshots"] = cur.fetchone()[0]

        if self._table_exists(cur, "pending_changes"):
            cur.execute("SELECT COUNT(*) FROM pending_changes WHERE repo_id = ?", (repo_id,))
            counts["pending_changes"] = cur.fetchone()[0]

        if self._table_exists(cur, "code_nodes"):
            cur.execute("SELECT COUNT(*) FROM code_nodes WHERE repo_id = ?", (repo_id,))
            counts["code_nodes"] = cur.fetchone()[0]

        if self._table_exists(cur, "code_edges"):
            cur.execute("SELECT COUNT(*) FROM code_edges WHERE repo_id = ?", (repo_id,))
            counts["code_edges"] = cur.fetchone()[0]

        if self._table_exists(cur, "node_aliases"):
            cur.execute(
                """
                SELECT COUNT(*) FROM node_aliases
                WHERE node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)
            """,
                (repo_id,),
            )
            counts["node_aliases"] = cur.fetchone()[0]

        if self._table_exists(cur, "code_nodes_fts"):
            cur.execute(
                """
                SELECT COUNT(*) FROM code_nodes_fts
                WHERE node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)
            """,
                (repo_id,),
            )
            counts["code_nodes_fts"] = cur.fetchone()[0]

        if self._table_exists(cur, "graph_metrics"):
            cur.execute(
                """
                SELECT COUNT(*) FROM graph_metrics
                WHERE node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)
            """,
                (repo_id,),
            )
            counts["graph_metrics"] = cur.fetchone()[0]

        if self._table_exists(cur, "cross_repo_references"):
            cur.execute("SELECT COUNT(*) FROM cross_repo_references WHERE source_repo_id = ?", (repo_id,))
            counts["cross_repo_references"] = cur.fetchone()[0]

        if self._table_exists(cur, "graph_snapshots"):
            cur.execute("SELECT COUNT(*) FROM graph_snapshots WHERE repo_id = ?", (repo_id,))
            counts["graph_snapshots"] = cur.fetchone()[0]

        if self._table_exists(cur, "graph_cache_state"):
            cur.execute("SELECT COUNT(*) FROM graph_cache_state WHERE repo_id = ?", (repo_id,))
            counts["graph_cache_state"] = cur.fetchone()[0]

        return counts

    def _table_exists(self, cur, table_name: str) -> bool:
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        )
        return cur.fetchone() is not None

    def _cleanup_fts_entries_comprehensive(self, cur, repo_id: int, repo_name: str) -> dict:
        """Comprehensive FTS5 cleanup with multiple strategies."""
        errors: list[str] = []
        stats = {"by_content_id": 0, "by_repo_name": 0, "orphaned": 0, "errors": errors}

        try:
            # Strategy 1: Delete by content_id (most precise)
            cur.execute(
                """
                DELETE FROM chunks_fts
                WHERE content_id IN (
                    SELECT cc.id FROM chunk_content cc
                    WHERE cc.repo_id = ?
                )
            """,
                (repo_id,),
            )
            stats["by_content_id"] = cur.rowcount

            # Strategy 2: Delete by repo name (fallback)
            cur.execute("DELETE FROM chunks_fts WHERE repo = ?", (repo_name,))
            stats["by_repo_name"] = cur.rowcount

            # Strategy 3: Delete orphaned entries (validation)
            cur.execute(
                """
                DELETE FROM chunks_fts
                WHERE content_id NOT IN (
                    SELECT id FROM chunk_content
                )
            """
            )
            stats["orphaned"] = cur.rowcount

        except Exception as e:
            logger.error("Failed to clean up FTS entries for repo %s", repo_name, exc_info=True)
            errors.append(str(e))

        return stats

    def _delete_chunk_locations_by_repo(self, cur, repo_id: int) -> int:
        """Delete all chunk locations for a repository."""
        cur.execute(
            """
            DELETE FROM chunk_locations
            WHERE content_id IN (
                SELECT id FROM chunk_content WHERE repo_id = ?
            )
        """,
            (repo_id,),
        )
        return cur.rowcount

    def _delete_chunk_content_by_repo(self, cur, repo_id: int) -> int:
        """Delete all chunk content for a repository."""
        cur.execute("DELETE FROM chunk_content WHERE repo_id = ?", (repo_id,))
        return cur.rowcount

    def _delete_files_by_repo(self, cur, repo_id: int) -> int:
        """Delete all files for a repository."""
        cur.execute("DELETE FROM files WHERE repo_id = ?", (repo_id,))
        return cur.rowcount

    def _delete_file_snapshots_by_repo(self, cur, repo_id: int) -> int:
        if not self._table_exists(cur, "file_snapshots"):
            return 0
        cur.execute("DELETE FROM file_snapshots WHERE repo_id = ?", (repo_id,))
        return cur.rowcount

    def _delete_pending_changes_by_repo(self, cur, repo_id: int) -> int:
        if not self._table_exists(cur, "pending_changes"):
            return 0
        cur.execute("DELETE FROM pending_changes WHERE repo_id = ?", (repo_id,))
        return cur.rowcount

    def _delete_code_edges_by_repo(self, cur, repo_id: int) -> int:
        if not self._table_exists(cur, "code_edges"):
            return 0
        cur.execute("DELETE FROM code_edges WHERE repo_id = ?", (repo_id,))
        return cur.rowcount

    def _delete_node_aliases_by_repo(self, cur, repo_id: int) -> int:
        if not self._table_exists(cur, "node_aliases"):
            return 0
        cur.execute(
            """
            DELETE FROM node_aliases
            WHERE node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)
        """,
            (repo_id,),
        )
        return cur.rowcount

    def _delete_graph_metrics_by_repo(self, cur, repo_id: int) -> int:
        if not self._table_exists(cur, "graph_metrics"):
            return 0
        cur.execute(
            """
            DELETE FROM graph_metrics
            WHERE node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)
        """,
            (repo_id,),
        )
        return cur.rowcount

    def _delete_cross_repo_references_by_repo(self, cur, repo_id: int) -> int:
        if not self._table_exists(cur, "cross_repo_references"):
            return 0
        cur.execute("DELETE FROM cross_repo_references WHERE source_repo_id = ?", (repo_id,))
        return cur.rowcount

    def _delete_code_nodes_fts_by_repo(self, cur, repo_id: int) -> int:
        if not self._table_exists(cur, "code_nodes_fts"):
            return 0
        cur.execute(
            """
            DELETE FROM code_nodes_fts
            WHERE node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)
        """,
            (repo_id,),
        )
        return cur.rowcount

    def _delete_code_nodes_by_repo(self, cur, repo_id: int) -> int:
        if not self._table_exists(cur, "code_nodes"):
            return 0
        cur.execute("DELETE FROM code_nodes WHERE repo_id = ?", (repo_id,))
        return cur.rowcount

    def _delete_graph_snapshots_by_repo(self, cur, repo_id: int) -> int:
        if not self._table_exists(cur, "graph_snapshots"):
            return 0
        cur.execute("DELETE FROM graph_snapshots WHERE repo_id = ?", (repo_id,))
        return cur.rowcount

    def _delete_graph_cache_state_by_repo(self, cur, repo_id: int) -> int:
        if not self._table_exists(cur, "graph_cache_state"):
            return 0
        cur.execute("DELETE FROM graph_cache_state WHERE repo_id = ?", (repo_id,))
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

                # 4. Code graph data (foreign keys to repos/files/nodes)
                code_edges_deleted = self._delete_code_edges_by_repo(cur, repo_id)
                node_aliases_deleted = self._delete_node_aliases_by_repo(cur, repo_id)
                graph_metrics_deleted = self._delete_graph_metrics_by_repo(cur, repo_id)
                cross_repo_refs_deleted = self._delete_cross_repo_references_by_repo(cur, repo_id)
                code_nodes_fts_deleted = self._delete_code_nodes_fts_by_repo(cur, repo_id)
                code_nodes_deleted = self._delete_code_nodes_by_repo(cur, repo_id)

                # 5. File sync data (foreign keys to files)
                file_snapshots_deleted = self._delete_file_snapshots_by_repo(cur, repo_id)
                pending_changes_deleted = self._delete_pending_changes_by_repo(cur, repo_id)

                # 6. Graph intelligence metadata (foreign key to repos)
                graph_snapshots_deleted = self._delete_graph_snapshots_by_repo(cur, repo_id)
                graph_cache_state_deleted = self._delete_graph_cache_state_by_repo(cur, repo_id)

                # 7. Files (foreign key to repos)
                files_deleted = self._delete_files_by_repo(cur, repo_id)

                # 8. Sessions (foreign key to repos)
                sessions_deleted = self._delete_sessions_by_repo(cur, repo_id)

                # 9. Repository registration
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
                "code_edges_deleted": code_edges_deleted,
                "node_aliases_deleted": node_aliases_deleted,
                "graph_metrics_deleted": graph_metrics_deleted,
                "cross_repo_refs_deleted": cross_repo_refs_deleted,
                "code_nodes_fts_deleted": code_nodes_fts_deleted,
                "code_nodes_deleted": code_nodes_deleted,
                "file_snapshots_deleted": file_snapshots_deleted,
                "pending_changes_deleted": pending_changes_deleted,
                "graph_snapshots_deleted": graph_snapshots_deleted,
                "graph_cache_state_deleted": graph_cache_state_deleted,
                "files_deleted": files_deleted,
                "sessions_deleted": sessions_deleted,
                "repo_deleted": repo_deleted,
            },
            "pre_cleanup_counts": pre_cleanup_counts,
            "post_cleanup_counts": post_cleanup_counts,
            "success": True,
        }

    def _cleanup_lancedb_comprehensive(self, lancedb_store, name: str) -> dict:
        """Comprehensive LanceDB cleanup with validation.

        Args:
            lancedb_store: LanceDBStore instance
            name: Repository name

        Returns:
            Statistics about cleanup: {small_deleted, large_deleted, errors}
        """
        errors: list[str] = []
        stats = {"small_deleted": 0, "large_deleted": 0, "errors": errors}

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
                    errors.append(f"{model} model: {post_count} vectors remain after deletion")

                stats[f"{model}_deleted"] = pre_count - post_count

            except Exception as e:
                logger.error("LanceDB %s model cleanup failed for repo %s", model, name, exc_info=True)
                errors.append(f"{model} model cleanup failed: {e}")

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
        issues: list[str] = []
        vector_counts: dict[str, int] = {}
        stats = {"consistent": True, "issues": issues, "vector_counts": vector_counts}

        try:
            # Count vectors in both models
            for model in ["small", "large"]:
                count = lancedb_store.count_repo_vectors(repo_name, model=model)
                vector_counts[model] = count

            # Could add more checks here, e.g., comparing metadata chunk counts
            # with vector counts

        except Exception as e:
            logger.error("LanceDB consistency check failed for repo %s", repo_name, exc_info=True)
            stats["consistent"] = False
            issues.append(f"LanceDB consistency check failed: {e}")

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
        issues: list[str] = []
        consistency_report = {
            "repo_id": repo_id,
            "repo_name": repo_name,
            "valid": True,
            "issues": issues,
            "statistics": {},
        }

        with self._connect() as conn, closing(conn.cursor()) as cur:
            # Get metadata statistics
            cur.execute("SELECT COUNT(*) FROM files WHERE repo_id = ?", (repo_id,))
            metadata_files = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM chunk_content WHERE repo_id = ?", (repo_id,))
            metadata_chunks = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM chunk_locations "
                "WHERE content_id IN (SELECT id FROM chunk_content WHERE repo_id = ?)",
                (repo_id,),
            )
            metadata_locations = cur.fetchone()[0]

            # Check for orphaned chunk_locations
            cur.execute(
                """
                SELECT COUNT(*) FROM chunk_locations cl
                LEFT JOIN chunk_content cc ON cl.content_id = cc.id
                WHERE cc.id IS NULL
            """
            )
            orphaned_locations = cur.fetchone()[0]

            if orphaned_locations > 0:
                consistency_report["valid"] = False
                issues.append(f"Found {orphaned_locations} orphaned chunk locations")

            # Check for orphaned FTS entries
            cur.execute(
                """
                SELECT COUNT(*) FROM chunks_fts
                WHERE content_id NOT IN (SELECT id FROM chunk_content)
            """
            )
            orphaned_fts = cur.fetchone()[0]

            if orphaned_fts > 0:
                consistency_report["valid"] = False
                issues.append(f"Found {orphaned_fts} orphaned FTS entries")

            # Check for chunk_content without files
            cur.execute(
                """
                SELECT COUNT(*) FROM chunk_content cc
                LEFT JOIN files f ON cc.file_id = f.id
                WHERE f.id IS NULL
            """
            )
            orphaned_content = cur.fetchone()[0]

            if orphaned_content > 0:
                consistency_report["valid"] = False
                issues.append(f"Found {orphaned_content} chunk_content rows without files")

            # Check for files without repos
            cur.execute(
                """
                SELECT COUNT(*) FROM files f
                LEFT JOIN repos r ON f.repo_id = r.id
                WHERE r.id IS NULL
            """
            )
            orphaned_files = cur.fetchone()[0]

            if orphaned_files > 0:
                consistency_report["valid"] = False
                issues.append(f"Found {orphaned_files} files without repos")

            consistency_report["statistics"] = {
                "metadata_files": metadata_files,
                "metadata_chunks": metadata_chunks,
                "metadata_locations": metadata_locations,
                "orphaned_locations": orphaned_locations,
                "orphaned_fts": orphaned_fts,
                "orphaned_content": orphaned_content,
                "orphaned_files": orphaned_files,
            }

        # Check LanceDB consistency
        lancedb_stats = self._check_lancedb_consistency(lancedb_store, repo_name)
        consistency_report["lancedb"] = lancedb_stats

        if not lancedb_stats["consistent"]:
            consistency_report["valid"] = False
            if isinstance(lancedb_stats["issues"], list):
                issues.extend(lancedb_stats["issues"])

        return consistency_report

    def repair_repository_consistency(self, repo_id: int, repo_name: str) -> dict:
        """Attempt to repair consistency issues in a repository.

        Args:
            repo_id: Repository ID
            repo_name: Repository name

        Returns:
            Repair report with actions taken and results
        """
        repairs_performed: list[str] = []
        errors: list[str] = []
        repair_report = {
            "repo_id": repo_id,
            "repo_name": repo_name,
            "repairs_performed": repairs_performed,
            "success": True,
            "errors": errors,
        }

        with self._connect() as conn, closing(conn.cursor()) as cur:
            try:
                # Repair orphaned chunk_locations
                cur.execute(
                    """
                    SELECT COUNT(*) FROM chunk_locations cl
                    LEFT JOIN chunk_content cc ON cl.content_id = cc.id
                    WHERE cc.id IS NULL
                """
                )
                orphaned_count = cur.fetchone()[0]

                if orphaned_count > 0:
                    cur.execute(
                        """
                        DELETE FROM chunk_locations
                        WHERE id IN (
                            SELECT cl.id FROM chunk_locations cl
                            LEFT JOIN chunk_content cc ON cl.content_id = cc.id
                            WHERE cc.id IS NULL
                        )
                    """
                    )
                    repairs_performed.append(f"Deleted {cur.rowcount} orphaned chunk locations")

                # Repair orphaned FTS entries
                cur.execute(
                    """
                    SELECT COUNT(*) FROM chunks_fts
                    WHERE content_id NOT IN (SELECT id FROM chunk_content)
                """
                )
                orphaned_fts_count = cur.fetchone()[0]

                if orphaned_fts_count > 0:
                    cur.execute(
                        """
                        DELETE FROM chunks_fts
                        WHERE content_id NOT IN (SELECT id FROM chunk_content)
                    """
                    )
                    repairs_performed.append(f"Deleted {cur.rowcount} orphaned FTS entries")

                # Repair orphaned chunk_content (without files)
                cur.execute(
                    """
                    SELECT COUNT(*) FROM chunk_content cc
                    LEFT JOIN files f ON cc.file_id = f.id
                    WHERE f.id IS NULL
                """
                )
                orphaned_content_count = cur.fetchone()[0]

                if orphaned_content_count > 0:
                    # First delete FTS entries for this content
                    cur.execute(
                        """
                        DELETE FROM chunks_fts
                        WHERE content_id IN (
                            SELECT cc.id FROM chunk_content cc
                            LEFT JOIN files f ON cc.file_id = f.id
                            WHERE f.id IS NULL
                        )
                    """
                    )

                    # Then delete locations
                    cur.execute(
                        """
                        DELETE FROM chunk_locations
                        WHERE content_id IN (
                            SELECT cc.id FROM chunk_content cc
                            LEFT JOIN files f ON cc.file_id = f.id
                            WHERE f.id IS NULL
                        )
                    """
                    )

                    # Finally delete content
                    cur.execute(
                        """
                        DELETE FROM chunk_content
                        WHERE id IN (
                            SELECT cc.id FROM chunk_content cc
                            LEFT JOIN files f ON cc.file_id = f.id
                            WHERE f.id IS NULL
                        )
                    """
                    )
                    repairs_performed.append(f"Deleted {cur.rowcount} orphaned chunk_content rows")

                # Repair orphaned files (without repos)
                cur.execute(
                    """
                    SELECT COUNT(*) FROM files f
                    LEFT JOIN repos r ON f.repo_id = r.id
                    WHERE r.id IS NULL
                """
                )
                orphaned_files_count = cur.fetchone()[0]

                if orphaned_files_count > 0:
                    # Cascade delete: FTS -> locations -> content -> files
                    cur.execute(
                        """
                        DELETE FROM chunks_fts
                        WHERE content_id IN (
                            SELECT cc.id FROM chunk_content cc
                            WHERE cc.file_id IN (
                                SELECT f.id FROM files f
                                LEFT JOIN repos r ON f.repo_id = r.id
                                WHERE r.id IS NULL
                            )
                        )
                    """
                    )

                    cur.execute(
                        """
                        DELETE FROM chunk_locations
                        WHERE content_id IN (
                            SELECT cc.id FROM chunk_content cc
                            WHERE cc.file_id IN (
                                SELECT f.id FROM files f
                                LEFT JOIN repos r ON f.repo_id = r.id
                                WHERE r.id IS NULL
                            )
                        )
                    """
                    )

                    cur.execute(
                        """
                        DELETE FROM chunk_content
                        WHERE file_id IN (
                            SELECT f.id FROM files f
                            LEFT JOIN repos r ON f.repo_id = r.id
                            WHERE r.id IS NULL
                        )
                    """
                    )

                    cur.execute(
                        """
                        DELETE FROM files
                        WHERE id IN (
                            SELECT f.id FROM files f
                            LEFT JOIN repos r ON f.repo_id = r.id
                            WHERE r.id IS NULL
                        )
                    """
                    )
                    repairs_performed.append(f"Deleted {cur.rowcount} orphaned files")

                conn.commit()

            except Exception as e:
                logger.error("Database integrity repair failed", exc_info=True)
                conn.rollback()
                repair_report["success"] = False
                errors.append(f"Repair failed: {e}")

        return repair_report

    # =====================
    # File Sync Methods (Phase 1)
    # =====================

    def record_pending_change(
        self,
        repo_id: int,
        file_path: str,
        change_type: str,
        old_path: str | None = None,
    ) -> int:
        """Record a file change in the pending queue."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                INSERT INTO pending_changes
                (repo_id, file_path, change_type, old_path, detected_at, processed)
                VALUES (?, ?, ?, ?, datetime('now'), 0)
            """,
                (repo_id, file_path, change_type, old_path),
            )
            change_id = cur.lastrowid
            conn.commit()
            # Type narrowing: lastrowid should always be set after INSERT, but handle None case
            if change_id is None:
                raise RuntimeError("Failed to get change_id from INSERT")
            return int(change_id)

    def get_pending_changes(self, repo_id: int | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        """Get unprocessed pending changes."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            if repo_id:
                cur.execute(
                    """
                    SELECT id, repo_id, file_path, change_type, old_path, detected_at
                    FROM pending_changes
                    WHERE repo_id = ? AND processed = 0
                    ORDER BY detected_at ASC
                    LIMIT ?
                """,
                    (repo_id, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, repo_id, file_path, change_type, old_path, detected_at
                    FROM pending_changes
                    WHERE processed = 0
                    ORDER BY detected_at ASC
                    LIMIT ?
                """,
                    (limit,),
                )

            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "repo_id": row[1],
                    "file_path": row[2],
                    "change_type": row[3],
                    "old_path": row[4],
                    "detected_at": row[5],
                }
                for row in rows
            ]

    def mark_changes_processed(self, change_ids: list[int]) -> int:
        """Mark pending changes as processed."""
        if not change_ids:
            return 0

        placeholders = ",".join(["?"] * len(change_ids))
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                f"""
                UPDATE pending_changes
                SET processed = 1, processed_at = datetime('now')
                WHERE id IN ({placeholders})
            """,
                tuple(change_ids),
            )
            updated = cur.rowcount
            conn.commit()
            return updated

    def mark_changes_for_file_processed(self, repo_id: int, file_path: str) -> int:
        """Mark all pending changes for a specific file as processed.

        Called automatically by the indexing pipeline after successfully indexing a file.

        Args:
            repo_id: Repository ID
            file_path: Relative file path within repository

        Returns:
            Number of changes marked as processed
        """
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                UPDATE pending_changes
                SET processed = 1, processed_at = datetime('now')
                WHERE repo_id = ?
                AND file_path = ?
                AND processed = 0
            """,
                (repo_id, file_path),
            )
            updated = cur.rowcount
            conn.commit()
            return updated

    def cleanup_old_changes(self, days: int = 7) -> int:
        """Delete processed changes older than specified days."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                DELETE FROM pending_changes
                WHERE processed = 1
                AND processed_at < datetime('now', ?)
            """,
                (f"-{days} days",),
            )
            deleted = cur.rowcount
            conn.commit()
            return deleted

    def upsert_file_snapshot(
        self,
        file_id: int,
        repo_id: int,
        path: str,
        mtime_ns: int,
        size_bytes: int,
        content_hash: str,
    ) -> None:
        """Record file state after successful indexing."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                INSERT INTO file_snapshots
                (file_id, repo_id, path, mtime_ns, size_bytes, content_hash, last_indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(file_id) DO UPDATE SET
                    mtime_ns = excluded.mtime_ns,
                    size_bytes = excluded.size_bytes,
                    content_hash = excluded.content_hash,
                    last_indexed_at = excluded.last_indexed_at
            """,
                (file_id, repo_id, path, mtime_ns, size_bytes, content_hash),
            )
            conn.commit()

    def get_file_snapshot(self, file_id: int) -> SnapshotRecord | None:
        """Get snapshot for a file."""
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT file_id, path, mtime_ns, size_bytes, content_hash, last_indexed_at
                FROM file_snapshots
                WHERE file_id = ?
            """,
                (file_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "file_id": row[0],
                "path": row[1],
                "mtime_ns": row[2],
                "size_bytes": row[3],
                "content_hash": row[4],
                "last_indexed_at": row[5],
            }

    def detect_drift(self, repo_id: int) -> list[dict]:
        """Detect files that changed since last snapshot."""
        import hashlib
        from pathlib import Path

        # Get repo info
        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute("SELECT name, root_path FROM repos WHERE id = ?", (repo_id,))
            repo_row = cur.fetchone()
            if not repo_row:
                return []

            repo_row[0]
            root = Path(repo_row[1])

        drift_events = []

        with self._connect() as conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT fs.file_id, fs.path, fs.mtime_ns, fs.size_bytes, fs.content_hash
                FROM file_snapshots fs
                WHERE fs.repo_id = ?
            """,
                (repo_id,),
            )

            for row in cur.fetchall():
                file_id, path, snapshot_mtime, snapshot_size, snapshot_hash = row
                file_path = root / path

                if not file_path.exists():
                    drift_events.append({"file_id": file_id, "path": path, "drift_type": "deleted"})
                    continue

                stat = file_path.stat()
                if stat.st_mtime_ns != snapshot_mtime or stat.st_size != snapshot_size:
                    current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
                    if current_hash != snapshot_hash:
                        drift_events.append({"file_id": file_id, "path": path, "drift_type": "modified"})

        return drift_events
