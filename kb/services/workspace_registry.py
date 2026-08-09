"""Durable explicit-worktree registrations for the 0.3.0 repository lifecycle."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from kb.runtime.storage import StorageLayout
from kb.services.worktree import GitWorktree


class WorkspaceRegistryError(RuntimeError):
    """The local workspace registry cannot complete a safe transaction."""


class OperationState(StrEnum):
    """Durable lifecycle states for correctness-preserving indexing work."""

    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


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

    def register(self, worktree: GitWorktree) -> WorkspaceRegistration:
        """Atomically create or refresh exactly one concrete worktree registration."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                registration = self._register(connection, worktree)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            return registration

    def submit_initial_index(self, registration: WorkspaceRegistration) -> WorkspaceOperation:
        """Create or reuse one queued initial-index operation for an exact workspace head."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                operation = self._submit_initial_index(connection, registration)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            return operation

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

    def set_operation_state(self, operation_id: str, state: OperationState) -> WorkspaceOperation | None:
        """Record a worker-owned state transition and return its updated source-free snapshot."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                updated = connection.execute(
                    """
                    UPDATE workspace_operations
                    SET state = ?, updated_at = ?
                    WHERE operation_id = ?
                    """,
                    (state.value, datetime.now(UTC).isoformat(), operation_id),
                ).rowcount
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return self.get_operation(operation_id) if updated else None

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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workspace_registrations (
                    workspace_id TEXT PRIMARY KEY,
                    repository_id TEXT NOT NULL,
                    root TEXT NOT NULL UNIQUE,
                    common_git_dir TEXT NOT NULL,
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
            yield connection
        finally:
            connection.close()

    def _register(self, connection: sqlite3.Connection, worktree: GitWorktree) -> WorkspaceRegistration:
        root = str(worktree.root)
        existing = connection.execute(
            """
            SELECT workspace_id, repository_id, branch, head_commit
            FROM workspace_registrations
            WHERE root = ?
            """,
            (root,),
        ).fetchone()
        now = datetime.now(UTC).isoformat()
        if existing is not None:
            workspace_id, repository_id, _branch, _head_commit = existing
            connection.execute(
                """
                UPDATE workspace_registrations
                SET branch = ?, head_commit = ?, common_git_dir = ?, updated_at = ?
                WHERE workspace_id = ?
                """,
                (worktree.branch, worktree.head_commit, str(worktree.common_git_dir), now, workspace_id),
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
                workspace_id, repository_id, root, common_git_dir, branch,
                head_commit, registration_epoch, cleanup_receipt_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                repository_id,
                root,
                str(worktree.common_git_dir),
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
    digest = hashlib.sha256(str(worktree.common_git_dir).encode("utf-8")).hexdigest()
    return f"repo_{digest[:24]}"


def _receipt_hash(receipt: str) -> str:
    return hashlib.sha256(receipt.encode("utf-8")).hexdigest()
