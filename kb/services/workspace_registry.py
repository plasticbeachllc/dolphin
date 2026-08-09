"""Durable explicit-worktree registrations for the 0.3.0 repository lifecycle."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from kb.runtime.storage import StorageLayout
from kb.services.worktree import (
    GitWorktree,
    WorktreeDiscoveryError,
    git_directory_identity,
    validate_git_worktree_snapshot,
)


class WorkspaceRegistryError(RuntimeError):
    """The local workspace registry cannot complete a safe transaction."""


_SCHEMA_VERSION = 2
_REGISTRATION_LOCK_DEADLINE_SECONDS = 15.0
_REGISTRATION_LOCK_INITIAL_BACKOFF_SECONDS = 0.05
_REGISTRATION_LOCK_MAX_BACKOFF_SECONDS = 0.5


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
    kind: str
    state: OperationState
    target_head_commit: str
    created: bool


class WorkspaceRegistry:
    """SQLite-backed registration authority, independent of MCP transport and indexing."""

    def __init__(self, layout: StorageLayout) -> None:
        self._layout = layout
        self._initialized = False
        self._initialization_lock = threading.Lock()

    def register(self, worktree: GitWorktree) -> WorkspaceRegistration:
        """Atomically create or refresh exactly one concrete worktree registration."""
        self._validate_worktree_snapshot(worktree)
        with self._connection() as connection:
            self._begin_registration_write(connection)
            try:
                registration = self._register(connection, worktree)
                self._validate_worktree_snapshot(worktree)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            return registration

    def register_and_submit_initial_index(
        self,
        worktree: GitWorktree,
    ) -> tuple[WorkspaceRegistration, WorkspaceOperation]:
        """Persist one discovered snapshot and its initial-index operation atomically."""
        self._validate_worktree_snapshot(worktree)
        with self._connection() as connection:
            self._begin_registration_write(connection)
            try:
                registration = self._register(connection, worktree)
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
                SELECT operation_id, workspace_id, kind, state, target_head_commit
                FROM workspace_operations
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        operation_id, workspace_id, kind, state, target_head_commit = row
        return WorkspaceOperation(
            operation_id=operation_id,
            workspace_id=workspace_id,
            kind=kind,
            state=OperationState(state),
            target_head_commit=target_head_commit,
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
                    SELECT workspace_id, kind, state, target_head_commit
                    FROM workspace_operations
                    WHERE operation_id = ?
                    """,
                    (operation_id,),
                ).fetchone()
                if row is None:
                    connection.commit()
                    return None
                workspace_id, kind, stored_state, target_head_commit = row
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
                        created=False,
                    )
                if state not in _ALLOWED_OPERATION_TRANSITIONS[current_state]:
                    raise WorkspaceRegistryError(
                        f"Dolphin operation transition from {current_state.value} to {state.value} is not allowed"
                    )
                updated = connection.execute(
                    """
                    UPDATE workspace_operations
                    SET state = ?, updated_at = ?
                    WHERE operation_id = ? AND state = ?
                    """,
                    (state.value, datetime.now(UTC).isoformat(), operation_id, current_state.value),
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
            self._initialize_schema(connection)
            yield connection
        except sqlite3.Error as exc:
            raise WorkspaceRegistryError("Dolphin metadata storage is busy or unavailable") from exc
        finally:
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
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        ) STRICT
                        """
                    )
                    connection.execute("DROP INDEX IF EXISTS workspace_operations_active_target")
                    connection.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS workspace_operations_exact_target
                        ON workspace_operations (workspace_id, kind, target_head_commit)
                        """
                    )
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
                    connection.execute(
                        """
                        CREATE UNIQUE INDEX workspace_operations_exact_target
                        ON workspace_operations (workspace_id, kind, target_head_commit)
                        """
                    )
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            self._initialized = True

    @staticmethod
    def _validate_worktree_snapshot(worktree: GitWorktree) -> None:
        """Keep durable registration and operation state bound to the observed Git snapshot."""
        validate_git_worktree_snapshot(worktree)

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

    def _register(self, connection: sqlite3.Connection, worktree: GitWorktree) -> WorkspaceRegistration:
        root = str(worktree.root)
        existing = connection.execute(
            """
            SELECT workspace_id, repository_id, common_git_dir, common_git_dir_identity
            FROM workspace_registrations
            WHERE root = ?
            """,
            (root,),
        ).fetchone()
        now = datetime.now(UTC).isoformat()
        if existing is not None:
            workspace_id, repository_id, common_git_dir, common_git_dir_identity = existing
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
                cleanup_receipt=None,
            )

        workspace_id = f"ws_{uuid.uuid4().hex}"
        repository_id = _repository_id(worktree)
        cleanup_receipt = secrets.token_urlsafe(32)
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
            SELECT operation_id, state
            FROM workspace_operations
            WHERE workspace_id = ?
              AND kind = 'initial_index'
              AND target_head_commit = ?
            ORDER BY created_at
            LIMIT 1
            """,
            (registration.workspace_id, target_head_commit),
        ).fetchone()
        if existing is not None:
            operation_id, state = existing
            return WorkspaceOperation(
                operation_id=operation_id,
                workspace_id=registration.workspace_id,
                kind="initial_index",
                state=OperationState(state),
                target_head_commit=target_head_commit,
                created=False,
            )

        operation_id = f"op_{uuid.uuid4().hex}"
        now = datetime.now(UTC).isoformat()
        connection.execute(
            """
            INSERT INTO workspace_operations (
                operation_id, workspace_id, kind, state, target_head_commit, created_at, updated_at
            ) VALUES (?, ?, 'initial_index', 'queued', ?, ?, ?)
            """,
            (operation_id, registration.workspace_id, target_head_commit, now, now),
        )
        return WorkspaceOperation(
            operation_id=operation_id,
            workspace_id=registration.workspace_id,
            kind="initial_index",
            state=OperationState.QUEUED,
            target_head_commit=target_head_commit,
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
