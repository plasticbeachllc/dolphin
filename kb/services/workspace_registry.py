"""Durable explicit-worktree registrations for the 0.3.0 repository lifecycle."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal, cast

from kb.cleanup_authority import is_valid_cleanup_receipt
from kb.lifecycle_limits import (
    ENTITY_ID_MAX_LENGTH,
    HEAD_COMMIT_MAX_LENGTH,
    ISO_TIMESTAMP_MAX_LENGTH,
    OPERATION_ID_MAX_LENGTH,
    REPO_LIST_CURSOR_MAX_LENGTH,
    REPO_LIST_PAGE_SIZE,
)
from kb.runtime.storage import StorageLayout, StorageLayoutError
from kb.services.worktree import (
    GitWorktree,
    WorktreeDiscoveryError,
    git_directory_identity,
    validate_git_worktree_snapshot,
)


class WorkspaceRegistryError(RuntimeError):
    """The local workspace registry cannot complete a safe transaction."""


class RepoListCursorInvalid(ValueError):
    """The repository-list cursor is malformed or belongs to another store."""


class RepoListCursorExpired(ValueError):
    """The repository-list cursor names an obsolete actionable-list revision."""


_SCHEMA_VERSION = 4
_REPO_LIST_CURSOR_PREFIX = "dolphin-repo-list-v1_"
_OPERATION_STATUS_RETENTION = timedelta(days=30)
_REGISTRATION_LOCK_DEADLINE_SECONDS = 15.0
_REGISTRATION_LOCK_INITIAL_BACKOFF_SECONDS = 0.05
_REGISTRATION_LOCK_MAX_BACKOFF_SECONDS = 0.5

type OperationKind = Literal["initial_index", "sync", "recovery"]
type WorkspaceEffectiveState = Literal["registered", "indexing", "ready", "failed"]


class OperationState(StrEnum):
    """Durable lifecycle states for correctness-preserving indexing work."""

    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED_OPERATION_TRANSITIONS: dict[OperationState, frozenset[OperationState]] = {
    OperationState.QUEUED: frozenset({OperationState.RUNNING, OperationState.CANCELLED}),
    OperationState.RUNNING: frozenset(
        {
            OperationState.AWAITING_APPROVAL,
            OperationState.PAUSED,
            OperationState.SUCCEEDED,
            OperationState.FAILED,
            OperationState.CANCELLED,
        }
    ),
    OperationState.AWAITING_APPROVAL: frozenset({OperationState.RUNNING, OperationState.CANCELLED}),
    OperationState.PAUSED: frozenset({OperationState.RUNNING, OperationState.CANCELLED}),
    OperationState.SUCCEEDED: frozenset(),
    OperationState.FAILED: frozenset(),
    OperationState.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class WorkspaceRegistration:
    """The bounded durable result of one explicit worktree enrollment attempt."""

    workspace_id: str
    repository_id: str
    root: str
    branch: str | None
    head_commit: str
    created: bool
    cleanup_receipt: str | None


@dataclass(frozen=True, slots=True)
class WorkspaceOperation:
    """A bounded durable snapshot of one workspace operation."""

    operation_id: str
    workspace_id: str
    kind: OperationKind
    state: OperationState
    target_head_commit: str
    attempt: int
    created: bool


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    """One actionable workspace projection for bounded read APIs."""

    workspace_id: str
    repository_id: str
    repository_display_name: str
    workspace_display_name: str
    root: str
    branch: str | None
    head_commit: str
    state: WorkspaceEffectiveState


@dataclass(frozen=True, slots=True)
class WorkspaceReadSnapshot:
    """One consistent registry status projection."""

    registered: int
    indexing: int
    ready: int
    failed: int
    current_workspace: WorkspaceSnapshot | None


@dataclass(frozen=True, slots=True)
class WorkspaceListPage:
    """One revision-consistent page of actionable workspaces."""

    items: tuple[WorkspaceSnapshot, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class OperationSnapshot:
    """One immediate durable operation projection for agent inspection."""

    operation_id: str
    workspace_id: str | None
    kind: OperationKind
    state: OperationState
    target_head_commit: str
    attempt: int
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None


class WorkspaceRegistry:
    """SQLite-backed registration authority, independent of MCP transport and indexing."""

    def __init__(self, layout: StorageLayout) -> None:
        self._layout = layout
        self._initialized = False
        self._initialization_lock = threading.Lock()

    def database_exists(self) -> bool:
        """Check for registry state without creating directories or files."""
        try:
            return self._layout.metadata_database_exists()
        except StorageLayoutError as exc:
            raise WorkspaceRegistryError("Dolphin metadata storage is unavailable") from exc

    def schema_is_current(self) -> bool:
        """Inspect schema compatibility without migrating or creating registry state."""
        if not self.database_exists():
            return True
        try:
            connection = sqlite3.connect(
                self._layout.metadata_db.as_uri() + "?mode=ro",
                uri=True,
                timeout=1,
                isolation_level=None,
            )
        except sqlite3.Error as exc:
            raise WorkspaceRegistryError("Dolphin metadata storage is unavailable") from exc
        try:
            row = connection.execute("PRAGMA user_version").fetchone()
            return row is not None and int(row[0]) == _SCHEMA_VERSION
        except sqlite3.Error as exc:
            raise WorkspaceRegistryError("Dolphin metadata storage is busy or unavailable") from exc
        finally:
            connection.close()

    def read_workspace_snapshot(self, root: Path | None = None) -> WorkspaceReadSnapshot:
        """Read mutually exclusive workspace counts and at most one exact-root workspace."""
        with self._read_connection() as connection:
            connection.execute("BEGIN")
            try:
                count_row = connection.execute(_WORKSPACE_COUNT_QUERY).fetchone()
                current_row = (
                    connection.execute(_WORKSPACE_BY_ROOT_QUERY, (str(root),)).fetchone() if root is not None else None
                )
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        if count_row is None:
            raise WorkspaceRegistryError("Dolphin workspace counts are unavailable")
        return WorkspaceReadSnapshot(
            registered=count_row[0],
            indexing=count_row[1],
            ready=count_row[2],
            failed=count_row[3],
            current_workspace=_workspace_snapshot(current_row) if current_row is not None else None,
        )

    def list_workspaces(self, cursor: str | None) -> WorkspaceListPage:
        """Read one fixed-size, revision-bound page of actionable workspaces."""
        with self._read_connection() as connection:
            connection.execute("BEGIN")
            try:
                metadata = connection.execute(
                    "SELECT store_id, list_revision, cursor_secret FROM workspace_registry_meta WHERE singleton = 1"
                ).fetchone()
                if metadata is None:
                    raise WorkspaceRegistryError("Dolphin metadata registry identity is unavailable")
                store_id, revision, cursor_secret = metadata
                after_key = None
                if cursor is not None:
                    after_key = _decode_repo_list_cursor(
                        cursor,
                        store_id=store_id,
                        revision=revision,
                        secret=cursor_secret,
                    )
                rows = connection.execute(
                    _WORKSPACE_PAGE_QUERY_WITH_CURSOR if after_key is not None else _WORKSPACE_PAGE_QUERY,
                    (*after_key, REPO_LIST_PAGE_SIZE + 1) if after_key is not None else (REPO_LIST_PAGE_SIZE + 1,),
                ).fetchall()
            except Exception:
                connection.rollback()
                raise
            connection.commit()

        page_rows = rows[:REPO_LIST_PAGE_SIZE]
        items = tuple(_workspace_snapshot(row[:8]) for row in page_rows)
        next_cursor = None
        if len(rows) > REPO_LIST_PAGE_SIZE and page_rows:
            next_cursor = _encode_repo_list_cursor(
                store_id=store_id,
                revision=revision,
                key=tuple(page_rows[-1][8:12]),
                secret=cursor_secret,
            )
        return WorkspaceListPage(items=items, next_cursor=next_cursor)

    def inspect_operation(self, operation_id: str, *, now: datetime | None = None) -> OperationSnapshot | None:
        """Read one operation without extending its diagnostic lifetime."""
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT operation_id, workspace_id, kind, state, target_head_commit, attempt,
                       created_at, updated_at, terminal_at
                FROM workspace_operations
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        snapshot = _operation_snapshot_from_row(row)
        terminal_at = snapshot.terminal_at
        observed_at = now or datetime.now(UTC)
        if terminal_at is not None and observed_at >= terminal_at + _OPERATION_STATUS_RETENTION:
            return None
        return snapshot

    def register(self, worktree: GitWorktree, *, cleanup_receipt: str) -> WorkspaceRegistration:
        """Atomically create or refresh exactly one concrete worktree registration."""
        self._require_valid_cleanup_receipt(cleanup_receipt)
        self._validate_worktree_snapshot(worktree)
        with self._connection() as connection:
            self._begin_registration_write(connection)
            try:
                registration = self._register(connection, worktree, cleanup_receipt)
                self._validate_worktree_snapshot(worktree)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            return registration

    def register_and_submit_initial_index(
        self,
        worktree: GitWorktree,
        *,
        cleanup_receipt: str,
    ) -> tuple[WorkspaceRegistration, WorkspaceOperation]:
        """Persist one discovered snapshot and its initial-index operation atomically."""
        self._require_valid_cleanup_receipt(cleanup_receipt)
        self._validate_worktree_snapshot(worktree)
        with self._connection() as connection:
            self._begin_registration_write(connection)
            try:
                registration = self._register(connection, worktree, cleanup_receipt)
                operation = self._submit_initial_index(connection, registration)
                self._validate_worktree_snapshot(worktree)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            return registration, operation

    def get_operation(self, operation_id: str) -> WorkspaceOperation | None:
        """Read one exact source-free operation snapshot without mutating retention or state."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT operation_id, workspace_id, kind, state, target_head_commit, attempt
                FROM workspace_operations
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        operation_id, workspace_id, kind, state, target_head_commit, attempt = row
        return WorkspaceOperation(
            operation_id=operation_id,
            workspace_id=workspace_id,
            kind=kind,
            state=OperationState(state),
            target_head_commit=target_head_commit,
            attempt=attempt,
            created=False,
        )

    def set_operation_state(
        self,
        operation_id: str,
        state: OperationState,
        *,
        expected_state: OperationState | None = None,
    ) -> WorkspaceOperation | None:
        """Compare-and-swap one operation through a permitted lifecycle transition."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT workspace_id, kind, state, target_head_commit, attempt
                    FROM workspace_operations
                    WHERE operation_id = ?
                    """,
                    (operation_id,),
                ).fetchone()
                if row is None:
                    connection.commit()
                    return None
                workspace_id, kind, stored_state, target_head_commit, attempt = row
                current_state = OperationState(stored_state)
                if expected_state is not None and current_state is not expected_state:
                    raise WorkspaceRegistryError("Dolphin operation state no longer matches the worker snapshot")
                if current_state is state:
                    connection.commit()
                    return WorkspaceOperation(
                        operation_id=operation_id,
                        workspace_id=workspace_id,
                        kind=kind,
                        state=current_state,
                        target_head_commit=target_head_commit,
                        attempt=attempt,
                        created=False,
                    )
                if state not in _ALLOWED_OPERATION_TRANSITIONS[current_state]:
                    raise WorkspaceRegistryError(
                        f"Dolphin operation transition from {current_state.value} to {state.value} is not allowed"
                    )
                transitioned_at = datetime.now(UTC).isoformat()
                updated = connection.execute(
                    """
                    UPDATE workspace_operations
                    SET state = ?, updated_at = ?, terminal_at = ?
                    WHERE operation_id = ? AND state = ?
                    """,
                    (
                        state.value,
                        transitioned_at,
                        transitioned_at
                        if state in {OperationState.SUCCEEDED, OperationState.FAILED, OperationState.CANCELLED}
                        else None,
                        operation_id,
                        current_state.value,
                    ),
                ).rowcount
                if not updated:
                    raise WorkspaceRegistryError("Dolphin operation state changed before this transition could commit")
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return WorkspaceOperation(
            operation_id=operation_id,
            workspace_id=workspace_id,
            kind=kind,
            state=state,
            target_head_commit=target_head_commit,
            attempt=attempt,
            created=False,
        )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self._layout.ensure_private_metadata_database()
        try:
            connection = sqlite3.connect(self._layout.metadata_db, timeout=1, isolation_level=None)
        except sqlite3.Error as exc:
            raise WorkspaceRegistryError("Dolphin metadata storage is unavailable") from exc
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 1000")
            connection.create_function("dolphin_repo_label", 1, _repository_display_name, deterministic=True)
            connection.create_function("dolphin_workspace_label", 1, _workspace_display_name, deterministic=True)
            connection.create_function("dolphin_sort_label", 1, _sort_label, deterministic=True)
            self._initialize_schema(connection)
            yield connection
        except sqlite3.Error as exc:
            raise WorkspaceRegistryError("Dolphin metadata storage is busy or unavailable") from exc
        finally:
            connection.close()

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        """Open current private registry state without creating, repairing, or migrating it."""
        if not self.database_exists() or not self.schema_is_current():
            raise WorkspaceRegistryError("Dolphin metadata storage is unavailable or requires initialization")
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self._layout.metadata_db.as_uri() + "?mode=ro",
                uri=True,
                timeout=1,
                isolation_level=None,
            )
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA busy_timeout = 1000")
            connection.create_function("dolphin_repo_label", 1, _repository_display_name, deterministic=True)
            connection.create_function("dolphin_workspace_label", 1, _workspace_display_name, deterministic=True)
            connection.create_function("dolphin_sort_label", 1, _sort_label, deterministic=True)
            yield connection
        except sqlite3.Error as exc:
            raise WorkspaceRegistryError("Dolphin metadata storage is busy or unavailable") from exc
        finally:
            if connection is not None:
                connection.close()

    def _initialize_schema(self, connection: sqlite3.Connection) -> None:
        """Perform the one-time, versioned schema migration before normal registry access."""
        if self._initialized:
            return
        with self._initialization_lock:
            if self._initialized:
                return
            version_row = connection.execute("PRAGMA user_version").fetchone()
            version = int(version_row[0]) if version_row is not None else 0
            if version == _SCHEMA_VERSION:
                self._initialized = True
                return
            if version > _SCHEMA_VERSION:
                raise WorkspaceRegistryError("Dolphin metadata storage has an unsupported schema version")

            # Only an uninitialized database needs a write lock and DDL. Once the
            # schema version is established, even a newly constructed registry can
            # serve reads without contending with indexing workers.
            connection.execute("BEGIN IMMEDIATE")
            try:
                version_row = connection.execute("PRAGMA user_version").fetchone()
                version = int(version_row[0]) if version_row is not None else 0
                if version == _SCHEMA_VERSION:
                    connection.commit()
                    self._initialized = True
                    return
                if version > _SCHEMA_VERSION:
                    raise WorkspaceRegistryError("Dolphin metadata storage has an unsupported schema version")
                if version == 0:
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS workspace_registrations (
                            workspace_id TEXT PRIMARY KEY,
                            repository_id TEXT NOT NULL,
                            root TEXT NOT NULL UNIQUE,
                            common_git_dir TEXT NOT NULL,
                            common_git_dir_identity TEXT NOT NULL,
                            branch TEXT,
                            head_commit TEXT NOT NULL,
                            registration_epoch TEXT NOT NULL,
                            cleanup_receipt_hash TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        ) STRICT
                        """
                    )
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS workspace_operations (
                            operation_id TEXT PRIMARY KEY,
                            workspace_id TEXT NOT NULL REFERENCES workspace_registrations(workspace_id),
                            kind TEXT NOT NULL CHECK (kind IN ('initial_index', 'sync', 'recovery')),
                            state TEXT NOT NULL CHECK (state IN (
                                'queued', 'running', 'awaiting_approval', 'paused', 'succeeded', 'failed', 'cancelled'
                            )),
                            target_head_commit TEXT NOT NULL,
                            attempt INTEGER NOT NULL CHECK (attempt >= 1),
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            terminal_at TEXT
                        ) STRICT
                        """
                    )
                    connection.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS workspace_operations_reusable_target
                        ON workspace_operations (workspace_id, kind, target_head_commit)
                        WHERE state IN ('queued', 'running', 'awaiting_approval', 'paused', 'succeeded')
                        """
                    )
                    self._create_registry_metadata(connection)
                elif version == 1:
                    connection.execute(
                        """
                        ALTER TABLE workspace_registrations
                        ADD COLUMN common_git_dir_identity TEXT NOT NULL DEFAULT ''
                        """
                    )
                    self._backfill_v1_repository_identities(connection)
                    connection.execute("DROP INDEX IF EXISTS workspace_operations_active_target")
                    connection.execute("DROP INDEX IF EXISTS workspace_operations_exact_target")
                    connection.execute(
                        """
                        DELETE FROM workspace_operations
                        WHERE rowid IN (
                            SELECT rowid
                            FROM (
                                SELECT
                                    rowid,
                                    ROW_NUMBER() OVER (
                                        PARTITION BY workspace_id, kind, target_head_commit
                                        ORDER BY
                                            CASE WHEN state = 'succeeded' THEN 0 ELSE 1 END,
                                            updated_at DESC,
                                            rowid DESC
                                    ) AS retention_rank
                                FROM workspace_operations
                            )
                            WHERE retention_rank > 1
                        )
                        """
                    )
                    self._migrate_operations_to_retryable_attempts(connection)
                    self._migrate_operation_terminal_timestamps(connection)
                    self._create_registry_metadata(connection)
                elif version == 2:
                    self._migrate_operations_to_retryable_attempts(connection)
                    self._migrate_operation_terminal_timestamps(connection)
                    self._create_registry_metadata(connection)
                elif version == 3:
                    self._migrate_operation_terminal_timestamps(connection)
                    self._create_registry_metadata(connection)
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            self._initialized = True

    @staticmethod
    def _migrate_operations_to_retryable_attempts(connection: sqlite3.Connection) -> None:
        """Retain terminal history while allowing a new attempt after failure or cancellation."""
        connection.execute(
            """
            ALTER TABLE workspace_operations
            ADD COLUMN attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt >= 1)
            """
        )
        connection.execute("DROP INDEX IF EXISTS workspace_operations_active_target")
        connection.execute("DROP INDEX IF EXISTS workspace_operations_exact_target")
        connection.execute(
            """
            CREATE UNIQUE INDEX workspace_operations_reusable_target
            ON workspace_operations (workspace_id, kind, target_head_commit)
            WHERE state IN ('queued', 'running', 'awaiting_approval', 'paused', 'succeeded')
            """
        )

    @staticmethod
    def _migrate_operation_terminal_timestamps(connection: sqlite3.Connection) -> None:
        connection.execute("ALTER TABLE workspace_operations ADD COLUMN terminal_at TEXT")
        connection.execute(
            """
            UPDATE workspace_operations
            SET terminal_at = updated_at
            WHERE state IN ('succeeded', 'failed', 'cancelled')
            """
        )

    @staticmethod
    def _create_registry_metadata(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_registry_meta (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                store_id TEXT NOT NULL UNIQUE,
                list_revision INTEGER NOT NULL CHECK (list_revision >= 0),
                cursor_secret BLOB NOT NULL CHECK (length(cursor_secret) = 32)
            ) STRICT
            """
        )
        workspace_count = connection.execute("SELECT COUNT(*) FROM workspace_registrations").fetchone()[0]
        connection.execute(
            """
            INSERT OR IGNORE INTO workspace_registry_meta (singleton, store_id, list_revision, cursor_secret)
            VALUES (1, ?, ?, ?)
            """,
            (f"store_{uuid.uuid4().hex}", workspace_count, secrets.token_bytes(32)),
        )

    @staticmethod
    def _validate_worktree_snapshot(worktree: GitWorktree) -> None:
        """Keep durable registration and operation state bound to the observed Git snapshot."""
        validate_git_worktree_snapshot(worktree)

    @staticmethod
    def _require_valid_cleanup_receipt(cleanup_receipt: str) -> None:
        if not is_valid_cleanup_receipt(cleanup_receipt):
            raise WorkspaceRegistryError("Dolphin cleanup receipt is malformed")

    @staticmethod
    def _begin_registration_write(connection: sqlite3.Connection) -> None:
        """Acquire the registration write lock with bounded backoff for concurrent final probes."""
        deadline = time.monotonic() + _REGISTRATION_LOCK_DEADLINE_SECONDS
        backoff = _REGISTRATION_LOCK_INITIAL_BACKOFF_SECONDS
        while True:
            try:
                connection.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                remaining = deadline - time.monotonic()
                if remaining <= 0 or ("locked" not in message and "busy" not in message):
                    raise
                time.sleep(min(backoff, remaining))
                backoff = min(backoff * 2, _REGISTRATION_LOCK_MAX_BACKOFF_SECONDS)

    @staticmethod
    def _backfill_v1_repository_identities(connection: sqlite3.Connection) -> None:
        """Bind retained v1 rows to their Git directory, pruning unreachable legacy state."""
        rows = connection.execute("SELECT workspace_id, common_git_dir FROM workspace_registrations").fetchall()
        for workspace_id, common_git_dir in rows:
            try:
                identity = git_directory_identity(Path(common_git_dir))
            except WorktreeDiscoveryError:
                connection.execute("DELETE FROM workspace_operations WHERE workspace_id = ?", (workspace_id,))
                connection.execute("DELETE FROM workspace_registrations WHERE workspace_id = ?", (workspace_id,))
                continue
            connection.execute(
                """
                UPDATE workspace_registrations
                SET repository_id = ?, common_git_dir_identity = ?
                WHERE workspace_id = ?
                """,
                (_repository_id_from_common_git_dir(common_git_dir, identity), identity, workspace_id),
            )

    def _register(
        self,
        connection: sqlite3.Connection,
        worktree: GitWorktree,
        cleanup_receipt: str,
    ) -> WorkspaceRegistration:
        root = str(worktree.root)
        existing = connection.execute(
            """
            SELECT workspace_id, repository_id, common_git_dir, common_git_dir_identity, cleanup_receipt_hash
            FROM workspace_registrations
            WHERE root = ?
            """,
            (root,),
        ).fetchone()
        now = datetime.now(UTC).isoformat()
        if existing is not None:
            workspace_id, repository_id, common_git_dir, common_git_dir_identity, cleanup_receipt_hash = existing
            if (
                common_git_dir != str(worktree.common_git_dir)
                or common_git_dir_identity != worktree.common_git_dir_identity
                or repository_id != _repository_id(worktree)
            ):
                raise WorkspaceRegistryError("Dolphin workspace root belongs to a different Git repository")
            connection.execute(
                """
                UPDATE workspace_registrations
                SET branch = ?, head_commit = ?, updated_at = ?
                WHERE workspace_id = ?
                """,
                (worktree.branch, worktree.head_commit, now, workspace_id),
            )
            return WorkspaceRegistration(
                workspace_id=workspace_id,
                repository_id=repository_id,
                root=root,
                branch=worktree.branch,
                head_commit=worktree.head_commit,
                created=False,
                cleanup_receipt=(
                    cleanup_receipt
                    if secrets.compare_digest(cleanup_receipt_hash, _receipt_hash(cleanup_receipt))
                    else None
                ),
            )

        workspace_id = f"ws_{uuid.uuid4().hex}"
        repository_id = _repository_id(worktree)
        connection.execute(
            """
            INSERT INTO workspace_registrations (
                workspace_id, repository_id, root, common_git_dir, common_git_dir_identity,
                branch, head_commit, registration_epoch, cleanup_receipt_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                repository_id,
                root,
                str(worktree.common_git_dir),
                worktree.common_git_dir_identity,
                worktree.branch,
                worktree.head_commit,
                f"epoch_{uuid.uuid4().hex}",
                _receipt_hash(cleanup_receipt),
                now,
                now,
            ),
        )
        connection.execute("UPDATE workspace_registry_meta SET list_revision = list_revision + 1 WHERE singleton = 1")
        return WorkspaceRegistration(
            workspace_id=workspace_id,
            repository_id=repository_id,
            root=root,
            branch=worktree.branch,
            head_commit=worktree.head_commit,
            created=True,
            cleanup_receipt=cleanup_receipt,
        )

    def _submit_initial_index(
        self,
        connection: sqlite3.Connection,
        registration: WorkspaceRegistration,
    ) -> WorkspaceOperation:
        persisted = connection.execute(
            """
            SELECT repository_id, root, head_commit
            FROM workspace_registrations
            WHERE workspace_id = ?
            """,
            (registration.workspace_id,),
        ).fetchone()
        if persisted is None:
            raise WorkspaceRegistryError("Dolphin workspace registration is unavailable")
        repository_id, root, target_head_commit = persisted
        if registration.repository_id != repository_id or registration.root != root:
            raise WorkspaceRegistryError("Dolphin workspace registration identity does not match persisted state")
        if registration.head_commit != target_head_commit:
            raise WorkspaceRegistryError("Dolphin workspace registration head does not match persisted state")

        existing = connection.execute(
            """
            SELECT operation_id, state, attempt
            FROM workspace_operations
            WHERE workspace_id = ?
              AND kind = 'initial_index'
              AND target_head_commit = ?
              AND state IN ('queued', 'running', 'awaiting_approval', 'paused', 'succeeded')
            ORDER BY CASE WHEN state = 'succeeded' THEN 0 ELSE 1 END, attempt DESC
            LIMIT 1
            """,
            (registration.workspace_id, target_head_commit),
        ).fetchone()
        if existing is not None:
            operation_id, state, attempt = existing
            return WorkspaceOperation(
                operation_id=operation_id,
                workspace_id=registration.workspace_id,
                kind="initial_index",
                state=OperationState(state),
                target_head_commit=target_head_commit,
                attempt=attempt,
                created=False,
            )

        attempt_row = connection.execute(
            """
            SELECT COALESCE(MAX(attempt), 0) + 1
            FROM workspace_operations
            WHERE workspace_id = ?
              AND kind = 'initial_index'
              AND target_head_commit = ?
            """,
            (registration.workspace_id, target_head_commit),
        ).fetchone()
        attempt = int(attempt_row[0]) if attempt_row is not None else 1
        operation_id = f"op_{uuid.uuid4().hex}"
        now = datetime.now(UTC).isoformat()
        connection.execute(
            """
            INSERT INTO workspace_operations (
                operation_id, workspace_id, kind, state, target_head_commit, attempt, created_at, updated_at,
                terminal_at
            ) VALUES (?, ?, 'initial_index', 'queued', ?, ?, ?, ?, NULL)
            """,
            (operation_id, registration.workspace_id, target_head_commit, attempt, now, now),
        )
        return WorkspaceOperation(
            operation_id=operation_id,
            workspace_id=registration.workspace_id,
            kind="initial_index",
            state=OperationState.QUEUED,
            target_head_commit=target_head_commit,
            attempt=attempt,
            created=True,
        )


def _repository_id(worktree: GitWorktree) -> str:
    """Derive a stable local repository-family key without a caller-controlled name."""
    return _repository_id_from_common_git_dir(str(worktree.common_git_dir), worktree.common_git_dir_identity)


def _repository_id_from_common_git_dir(common_git_dir: str, common_git_dir_identity: str) -> str:
    identity = f"{common_git_dir}\0{common_git_dir_identity}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"repo_{digest[:24]}"


def _receipt_hash(receipt: str) -> str:
    return hashlib.sha256(receipt.encode("utf-8")).hexdigest()


_WORKSPACE_PROJECTION = """
    SELECT
        w.workspace_id,
        w.repository_id,
        dolphin_repo_label(w.common_git_dir) AS repository_display_name,
        dolphin_workspace_label(w.root) AS workspace_display_name,
        w.root,
        w.branch,
        w.head_commit,
        CASE
            WHEN o.state IN ('queued', 'running', 'awaiting_approval', 'paused') THEN 'indexing'
            WHEN o.state = 'succeeded' THEN 'ready'
            WHEN o.state = 'failed' THEN 'failed'
            ELSE 'registered'
        END AS effective_state
    FROM workspace_registrations AS w
    LEFT JOIN workspace_operations AS o
      ON o.operation_id = (
          SELECT candidate.operation_id
          FROM workspace_operations AS candidate
          WHERE candidate.workspace_id = w.workspace_id
          ORDER BY candidate.updated_at DESC, candidate.rowid DESC
          LIMIT 1
      )
"""

_WORKSPACE_BY_ROOT_QUERY = _WORKSPACE_PROJECTION + " WHERE w.root = ? LIMIT 1"

_WORKSPACE_COUNT_QUERY = (
    """
    WITH workspace_states AS (
"""
    + _WORKSPACE_PROJECTION
    + """
    )
    SELECT
        COALESCE(SUM(effective_state = 'registered'), 0),
        COALESCE(SUM(effective_state = 'indexing'), 0),
        COALESCE(SUM(effective_state = 'ready'), 0),
        COALESCE(SUM(effective_state = 'failed'), 0)
    FROM workspace_states
"""
)

_WORKSPACE_PAGE_PROJECTION = """
    SELECT
        workspace_id,
        repository_id,
        repository_display_name,
        workspace_display_name,
        root,
        branch,
        head_commit,
        effective_state,
        repository_sort,
        repository_id,
        workspace_sort,
        workspace_id
    FROM (
        SELECT
            workspace_projection.*,
            dolphin_sort_label(repository_display_name) AS repository_sort,
            dolphin_sort_label(workspace_display_name) AS workspace_sort
        FROM workspace_projection
    )
"""

_WORKSPACE_PAGE_QUERY = (
    "WITH workspace_projection AS ("
    + _WORKSPACE_PROJECTION
    + ")"
    + _WORKSPACE_PAGE_PROJECTION
    + """
    ORDER BY repository_sort, repository_id, workspace_sort, workspace_id
    LIMIT ?
"""
)

_WORKSPACE_PAGE_QUERY_WITH_CURSOR = (
    "WITH workspace_projection AS ("
    + _WORKSPACE_PROJECTION
    + ")"
    + _WORKSPACE_PAGE_PROJECTION
    + """
    WHERE (repository_sort, repository_id, workspace_sort, workspace_id) > (?, ?, ?, ?)
    ORDER BY repository_sort, repository_id, workspace_sort, workspace_id
    LIMIT ?
"""
)


def _workspace_snapshot(row: tuple[object, ...]) -> WorkspaceSnapshot:
    return WorkspaceSnapshot(
        workspace_id=str(row[0]),
        repository_id=str(row[1]),
        repository_display_name=str(row[2]),
        workspace_display_name=str(row[3]),
        root=str(row[4]),
        branch=str(row[5]) if row[5] is not None else None,
        head_commit=str(row[6]),
        state=cast(WorkspaceEffectiveState, row[7]),
    )


def _repository_display_name(common_git_dir: str) -> str:
    path = Path(common_git_dir)
    return path.parent.name if path.name == ".git" else path.name


def _workspace_display_name(root: str) -> str:
    return Path(root).name


def _sort_label(label: str) -> str:
    return label.casefold()


def _encode_repo_list_cursor(
    *,
    store_id: str,
    revision: int,
    key: tuple[object, ...],
    secret: bytes,
) -> str:
    payload = json.dumps(
        {"key": [str(part) for part in key], "revision": revision, "store_id": store_id, "version": 1},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    max_envelope_bytes = ((REPO_LIST_CURSOR_MAX_LENGTH - len(_REPO_LIST_CURSOR_PREFIX)) * 3) // 4
    if len(payload) + 2 + 32 > max_envelope_bytes:
        raise WorkspaceRegistryError("Dolphin repository-list cursor exceeds its public size bound")
    signature = hmac.digest(secret, b"dolphin:repo-list:v1\x00" + payload, "sha256")
    encoded = base64.urlsafe_b64encode(len(payload).to_bytes(2, "big") + payload + signature).decode("ascii")
    cursor = _REPO_LIST_CURSOR_PREFIX + encoded.rstrip("=")
    if len(cursor) > REPO_LIST_CURSOR_MAX_LENGTH:
        raise WorkspaceRegistryError("Dolphin repository-list cursor exceeds its public size bound")
    return cursor


def _decode_repo_list_cursor(
    cursor: str,
    *,
    store_id: str,
    revision: int,
    secret: bytes,
) -> tuple[str, str, str, str]:
    if not cursor.startswith(_REPO_LIST_CURSOR_PREFIX) or len(cursor) > REPO_LIST_CURSOR_MAX_LENGTH:
        raise RepoListCursorInvalid
    encoded = cursor.removeprefix(_REPO_LIST_CURSOR_PREFIX)
    try:
        envelope = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RepoListCursorInvalid from exc
    if len(envelope) < 2 + 32:
        raise RepoListCursorInvalid
    payload_length = int.from_bytes(envelope[:2], "big")
    payload = envelope[2 : 2 + payload_length]
    signature = envelope[2 + payload_length :]
    if len(payload) != payload_length or len(signature) != 32:
        raise RepoListCursorInvalid
    expected = hmac.digest(secret, b"dolphin:repo-list:v1\x00" + payload, "sha256")
    if not hmac.compare_digest(signature, expected):
        raise RepoListCursorInvalid
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RepoListCursorInvalid from exc
    if not isinstance(decoded, dict) or set(decoded) != {"key", "revision", "store_id", "version"}:
        raise RepoListCursorInvalid
    if decoded["version"] != 1 or decoded["store_id"] != store_id:
        raise RepoListCursorInvalid
    if decoded["revision"] != revision:
        raise RepoListCursorExpired
    key = decoded["key"]
    if not isinstance(key, list) or len(key) != 4 or not all(isinstance(part, str) for part in key):
        raise RepoListCursorInvalid
    return key[0], key[1], key[2], key[3]


def _operation_snapshot_from_row(row: tuple[object, ...]) -> OperationSnapshot:
    operation_id = _bounded_registry_text(row[0], label="operation ID", max_length=OPERATION_ID_MAX_LENGTH)
    workspace_id = (
        None
        if row[1] is None
        else _bounded_registry_text(row[1], label="workspace ID", max_length=ENTITY_ID_MAX_LENGTH)
    )
    kind_text = _bounded_registry_text(row[2], label="operation kind", max_length=32)
    if kind_text not in {"initial_index", "sync", "recovery"}:
        raise WorkspaceRegistryError("Dolphin operation metadata contains an invalid kind")
    state_text = _bounded_registry_text(row[3], label="operation state", max_length=32)
    try:
        state = OperationState(state_text)
    except ValueError as exc:
        raise WorkspaceRegistryError("Dolphin operation metadata contains an invalid state") from exc
    target_head_commit = _bounded_registry_text(
        row[4],
        label="operation target commit",
        max_length=HEAD_COMMIT_MAX_LENGTH,
    )
    attempt = row[5]
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise WorkspaceRegistryError("Dolphin operation metadata contains an invalid attempt")
    created_at = _parse_registry_timestamp(row[6], label="operation creation timestamp")
    updated_at = _parse_registry_timestamp(row[7], label="operation progress timestamp")
    terminal_at = None if row[8] is None else _parse_registry_timestamp(row[8], label="operation terminal timestamp")
    terminal = state in {OperationState.SUCCEEDED, OperationState.FAILED, OperationState.CANCELLED}
    if terminal != (terminal_at is not None):
        raise WorkspaceRegistryError("Dolphin operation metadata has inconsistent terminal timestamps")
    return OperationSnapshot(
        operation_id=operation_id,
        workspace_id=workspace_id,
        kind=cast(OperationKind, kind_text),
        state=state,
        target_head_commit=target_head_commit,
        attempt=attempt,
        created_at=created_at,
        updated_at=updated_at,
        terminal_at=terminal_at,
    )


def _bounded_registry_text(value: object, *, label: str, max_length: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise WorkspaceRegistryError(f"Dolphin metadata contains an invalid {label}")
    return value


def _parse_registry_timestamp(value: object, *, label: str) -> datetime:
    encoded = _bounded_registry_text(value, label=label, max_length=ISO_TIMESTAMP_MAX_LENGTH)
    try:
        parsed = datetime.fromisoformat(encoded)
    except ValueError as exc:
        raise WorkspaceRegistryError(f"Dolphin metadata contains an invalid {label}") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
