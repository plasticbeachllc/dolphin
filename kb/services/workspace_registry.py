"""Durable explicit-worktree registrations for the 0.3.0 repository lifecycle."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path, PurePosixPath
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
from kb.runtime.schema import METADATA_SCHEMA_VERSION
from kb.runtime.storage import StorageLayout, StorageLayoutError
from kb.services.repository_boundaries import (
    ParentScanPlan,
    RepositoryBoundary,
    RepositoryBoundaryError,
    RepositoryBoundaryKind,
    RepositoryBoundaryState,
    validate_parent_scan,
)
from kb.services.worktree import GitWorktree, validate_git_worktree_snapshot
from kb.version import get_version


class WorkspaceRegistryError(RuntimeError):
    """The local workspace registry cannot complete a safe transaction."""


class RepoListCursorInvalid(ValueError):
    """The repository-list cursor is malformed or belongs to another store."""


class RepoListCursorExpired(ValueError):
    """The repository-list cursor names an obsolete actionable-list revision."""


_SCHEMA_VERSION = METADATA_SCHEMA_VERSION
_MAX_BOUNDARIES_PER_READ = 8
_MAX_STORED_BOUNDARIES = 100_000
_REPO_LIST_CURSOR_PREFIX = "dolphin-repo-list-v1_"
_OPERATION_STATUS_RETENTION = timedelta(days=30)
_REGISTRATION_LOCK_DEADLINE_SECONDS = 15.0
_REGISTRATION_LOCK_INITIAL_BACKOFF_SECONDS = 0.05
_REGISTRATION_LOCK_MAX_BACKOFF_SECONDS = 0.5

type OperationKind = Literal["initial_index", "sync", "recovery"]
type WorkspaceEffectiveState = Literal["registered", "indexing", "ready", "failed"]
type RuntimeMode = Literal["mcp", "foreground_cli"]
type RuntimeState = Literal["active", "draining", "stopped"]
type OperationPhase = Literal["preflight", "scan", "chunk", "embed", "store", "publish"]
type OperationPauseReason = Literal[
    "runtime_absent",
    "credential_missing",
    "disk_pressure",
    "awaiting_approval",
    "shutdown",
]

_OPERATION_PHASES: tuple[OperationPhase, ...] = ("preflight", "scan", "chunk", "embed", "store", "publish")
_RUNTIME_ID_MAX_LENGTH = 64
_PROCESS_IDENTITY_MAX_LENGTH = 256
_PIPELINE_KEY_MAX_LENGTH = 256
_TARGET_FINGERPRINT_MAX_LENGTH = 256
_MAX_ACTIVE_RUNTIMES = 64


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
    repository_boundaries: tuple[RepositoryBoundary, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceReadSnapshot:
    """One consistent registry status projection."""

    registered: int
    indexing: int
    ready: int
    failed: int
    current_workspace: WorkspaceSnapshot | None


@dataclass(frozen=True, slots=True)
class BoundaryPathMatch:
    """One persisted child boundary containing a requested local path."""

    parent_workspace_id: str
    root: str
    boundary: RepositoryBoundary


@dataclass(frozen=True, slots=True)
class WorkspacePathMatch:
    """The deepest registered workspace or blocking boundary for one path."""

    workspace: WorkspaceSnapshot | None = None
    boundary: BoundaryPathMatch | None = None


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
    phase: OperationPhase | None = None
    counters: OperationCountersSnapshot | None = None
    pause_reason: OperationPauseReason | None = None
    pipeline_key: str | None = None


@dataclass(frozen=True, slots=True)
class OperationCountersSnapshot:
    """Bounded source-free progress counters persisted with an operation checkpoint."""

    known_eligible_files: int | None = None
    processed_files: int = 0
    parsed_files: int = 0
    reused_chunks: int = 0
    embedding_cache_hits: int = 0
    embedding_cache_misses: int = 0
    embedded_chunks: int = 0


@dataclass(frozen=True, slots=True)
class OperationCheckpoint:
    """Normalized resumable state for one leased operation."""

    operation_id: str
    workspace_id: str
    target_fingerprint: str
    pipeline_key: str
    phase: OperationPhase
    counters: OperationCountersSnapshot
    checkpointed_at: datetime
    pause_reason: OperationPauseReason | None = None
    staging_generation_id: str | None = None
    completed_manifest_id: str | None = None
    resume_count: int = 0


@dataclass(frozen=True, slots=True)
class RuntimeOwner:
    """One visible foreground process recorded as a bounded runtime owner."""

    runtime_id: str
    pid: int
    process_start_identity: str
    mode: RuntimeMode
    operation_capable: bool
    pipeline_key: str | None
    state: RuntimeState
    started_at: datetime
    heartbeat_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RuntimeStatusSnapshot:
    """Aggregate-only active runtime health for status output."""

    active_processes: int
    operation_executors: int


@dataclass(frozen=True, slots=True)
class OperationLease:
    """Exclusive expiring authority to advance one durable operation."""

    lease_id: str
    runtime_id: str
    operation: WorkspaceOperation
    checkpoint: OperationCheckpoint
    expires_at: datetime


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
                current_boundaries = (
                    self._read_boundaries(connection, str(current_row[0])) if current_row is not None else ()
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
            current_workspace=(
                replace(_workspace_snapshot(current_row), repository_boundaries=current_boundaries)
                if current_row is not None
                else None
            ),
        )

    def inspect_workspace(self, workspace_id: str) -> WorkspaceSnapshot | None:
        """Read one exact active workspace by its stable ID."""
        with self._read_connection() as connection:
            row = connection.execute(_WORKSPACE_BY_ID_QUERY, (workspace_id,)).fetchone()
            boundaries = self._read_boundaries(connection, str(row[0])) if row is not None else ()
        if row is None:
            return None
        return replace(_workspace_snapshot(row), repository_boundaries=boundaries)

    def resolve_workspace_path(self, path: Path) -> WorkspacePathMatch:
        """Resolve one absolute path to its deepest workspace or hard child boundary."""
        normalized_path = _normalize_resolution_path(path)
        with self._read_connection() as connection:
            workspace_row = connection.execute(
                _DEEPEST_WORKSPACE_FOR_PATH_QUERY,
                (normalized_path, normalized_path, normalized_path),
            ).fetchone()
            boundary_row = connection.execute(
                _DEEPEST_BOUNDARY_FOR_PATH_QUERY,
                (normalized_path, normalized_path, normalized_path),
            ).fetchone()
            workspace = _workspace_snapshot(workspace_row) if workspace_row is not None else None
            if workspace is not None:
                workspace = replace(
                    workspace,
                    repository_boundaries=self._read_boundaries(connection, workspace.workspace_id),
                )
            boundary_match = None
            if boundary_row is not None:
                boundary = _boundary_from_row(tuple(boundary_row[3:10]))
                if boundary_row[10] is not None:
                    boundary = replace(
                        boundary,
                        workspace_id=_bounded_registry_text(
                            boundary_row[10],
                            label="workspace ID",
                            max_length=ENTITY_ID_MAX_LENGTH,
                        ),
                    )
                parent_workspace_id = _bounded_registry_text(
                    boundary_row[0],
                    label="workspace ID",
                    max_length=ENTITY_ID_MAX_LENGTH,
                )
                boundary_root = _bounded_registry_text(
                    boundary_row[1],
                    label="repository boundary root",
                    max_length=4_096,
                )
                if not Path(boundary_root).is_absolute():
                    raise WorkspaceRegistryError("Dolphin repository boundary metadata contains an invalid root")
                boundary_match = BoundaryPathMatch(
                    parent_workspace_id=parent_workspace_id,
                    root=boundary_root,
                    boundary=boundary,
                )

        if workspace is not None and (boundary_match is None or len(workspace.root) >= len(boundary_match.root)):
            return WorkspacePathMatch(workspace=workspace)
        if boundary_match is not None:
            return WorkspacePathMatch(boundary=boundary_match)
        return WorkspacePathMatch()

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
                page_rows = rows[:REPO_LIST_PAGE_SIZE]
                page_boundaries = {str(row[0]): self._read_boundaries(connection, str(row[0])) for row in page_rows}
            except Exception:
                connection.rollback()
                raise
            connection.commit()

        items = tuple(
            replace(
                _workspace_snapshot(row[:8]),
                repository_boundaries=page_boundaries[str(row[0])],
            )
            for row in page_rows
        )
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
                SELECT o.operation_id, o.workspace_id, o.kind, o.state, o.target_head_commit, o.attempt,
                       o.created_at, o.updated_at, o.terminal_at, c.phase, c.known_eligible_files,
                       c.processed_files, c.parsed_files, c.reused_chunks, c.embedding_cache_hits,
                       c.embedding_cache_misses, c.embedded_chunks, c.pause_reason, c.pipeline_key
                FROM workspace_operations AS o
                LEFT JOIN operation_checkpoints AS c ON c.operation_id = o.operation_id
                WHERE o.operation_id = ?
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

    def register_runtime(
        self,
        *,
        runtime_id: str,
        pid: int,
        process_start_identity: str,
        mode: RuntimeMode,
        operation_capable: bool,
        pipeline_key: str | None,
        now: datetime,
        expires_at: datetime,
    ) -> RuntimeOwner:
        """Create one active foreground runtime record after process identity is proven."""
        _validate_runtime_identity(runtime_id, pid, process_start_identity)
        _validate_lease_window(now, expires_at)
        if mode not in {"mcp", "foreground_cli"}:
            raise WorkspaceRegistryError("Dolphin runtime mode is invalid")
        if not isinstance(operation_capable, bool):
            raise WorkspaceRegistryError("Dolphin runtime capability is invalid")
        if operation_capable:
            if pipeline_key is None:
                raise WorkspaceRegistryError("Dolphin operation runtime requires a pipeline key")
            _validate_bounded_key(pipeline_key, label="pipeline key", maximum=_PIPELINE_KEY_MAX_LENGTH)
        elif pipeline_key is not None:
            raise WorkspaceRegistryError("Dolphin non-executing runtime cannot advertise a pipeline key")
        encoded_now = _utc_timestamp(now).isoformat()
        encoded_expiry = _utc_timestamp(expires_at).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    DELETE FROM runtime_instances
                    WHERE state = 'stopped'
                      AND runtime_id NOT IN (SELECT runtime_id FROM operation_leases)
                    """
                )
                active_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM runtime_instances
                    WHERE state = 'active' AND expires_at > ?
                    """,
                    (encoded_now,),
                ).fetchone()
                if active_count is None or not isinstance(active_count[0], int):
                    raise WorkspaceRegistryError("Dolphin runtime ownership metadata is invalid")
                if active_count[0] >= _MAX_ACTIVE_RUNTIMES:
                    raise WorkspaceRegistryError("Dolphin has too many active runtime processes")
                connection.execute(
                    """
                    INSERT INTO runtime_instances (
                        runtime_id, pid, process_start_identity, mode, operation_capable, pipeline_key, state,
                        dolphin_version, schema_version, started_at, heartbeat_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                    """,
                    (
                        runtime_id,
                        pid,
                        process_start_identity,
                        mode,
                        int(operation_capable),
                        pipeline_key,
                        _runtime_version(),
                        _SCHEMA_VERSION,
                        encoded_now,
                        encoded_now,
                        encoded_expiry,
                    ),
                )
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return RuntimeOwner(
            runtime_id=runtime_id,
            pid=pid,
            process_start_identity=process_start_identity,
            mode=mode,
            operation_capable=operation_capable,
            pipeline_key=pipeline_key,
            state="active",
            started_at=_utc_timestamp(now),
            heartbeat_at=_utc_timestamp(now),
            expires_at=_utc_timestamp(expires_at),
        )

    def list_runtime_owners(self) -> tuple[RuntimeOwner, ...]:
        """Return bounded source-free owner records for startup reconciliation."""
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT runtime_id, pid, process_start_identity, mode, operation_capable, pipeline_key, state,
                       started_at, heartbeat_at, expires_at
                FROM runtime_instances
                WHERE state != 'stopped'
                ORDER BY started_at, runtime_id
                LIMIT ?
                """,
                (_MAX_ACTIVE_RUNTIMES + 1,),
            ).fetchall()
        if len(rows) > _MAX_ACTIVE_RUNTIMES:
            raise WorkspaceRegistryError("Dolphin has too many runtime owners to reconcile safely")
        return tuple(_runtime_owner_from_row(row) for row in rows)

    def read_runtime_status(self, *, now: datetime | None = None) -> RuntimeStatusSnapshot:
        """Read aggregate active runtime ownership without mutating expiry state."""
        observed_at = _utc_timestamp(now or datetime.now(UTC)).isoformat()
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(operation_capable), 0)
                FROM runtime_instances
                WHERE state = 'active' AND expires_at > ?
                """,
                (observed_at,),
            ).fetchone()
        if row is None or not all(isinstance(value, int) for value in row):
            raise WorkspaceRegistryError("Dolphin runtime ownership metadata is invalid")
        return RuntimeStatusSnapshot(active_processes=row[0], operation_executors=row[1])

    def compatible_operation_executor_available(
        self,
        pipeline_key: str | None,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Report whether a live executor can claim an operation's pipeline."""
        if pipeline_key is not None:
            _validate_bounded_key(pipeline_key, label="pipeline key", maximum=_PIPELINE_KEY_MAX_LENGTH)
        observed_at = _utc_timestamp(now or datetime.now(UTC)).isoformat()
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM runtime_instances
                    WHERE state = 'active'
                      AND expires_at > ?
                      AND operation_capable = 1
                      AND (? IS NULL OR pipeline_key = ?)
                )
                """,
                (observed_at, pipeline_key, pipeline_key),
            ).fetchone()
        if row is None or row[0] not in {0, 1}:
            raise WorkspaceRegistryError("Dolphin runtime compatibility metadata is invalid")
        return bool(row[0])

    def heartbeat_runtime(
        self,
        *,
        runtime_id: str,
        process_start_identity: str,
        now: datetime,
        expires_at: datetime,
    ) -> RuntimeOwner:
        """Renew one active runtime and every operation lease it still owns."""
        _validate_runtime_identity(runtime_id, 1, process_start_identity, validate_pid=False)
        _validate_lease_window(now, expires_at)
        encoded_now = _utc_timestamp(now).isoformat()
        encoded_expiry = _utc_timestamp(expires_at).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT runtime_id, pid, process_start_identity, mode, operation_capable, pipeline_key, state,
                           started_at, heartbeat_at, expires_at
                    FROM runtime_instances
                    WHERE runtime_id = ?
                    """,
                    (runtime_id,),
                ).fetchone()
                if row is None:
                    raise WorkspaceRegistryError("Dolphin runtime ownership is unavailable")
                owner = _runtime_owner_from_row(row)
                if (
                    owner.process_start_identity != process_start_identity
                    or owner.state != "active"
                    or owner.expires_at <= _utc_timestamp(now)
                ):
                    raise WorkspaceRegistryError("Dolphin runtime ownership no longer matches this process")
                connection.execute(
                    """
                    UPDATE runtime_instances
                    SET heartbeat_at = ?, expires_at = ?
                    WHERE runtime_id = ? AND process_start_identity = ? AND state = 'active'
                    """,
                    (encoded_now, encoded_expiry, runtime_id, process_start_identity),
                )
                connection.execute(
                    """
                    UPDATE operation_leases
                    SET heartbeat_at = ?, expires_at = ?
                    WHERE runtime_id = ?
                    """,
                    (encoded_now, encoded_expiry, runtime_id),
                )
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return replace(owner, heartbeat_at=_utc_timestamp(now), expires_at=_utc_timestamp(expires_at))

    def reconcile_stale_runtime(
        self,
        *,
        runtime_id: str,
        process_start_identity: str,
        observed_at: datetime,
        stale_identity_proven: bool,
    ) -> int:
        """Pause work only when expiry or a PID/start-identity mismatch proves an owner stale."""
        _validate_runtime_identity(runtime_id, 1, process_start_identity, validate_pid=False)
        encoded_now = _utc_timestamp(observed_at).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT process_start_identity, expires_at, state
                    FROM runtime_instances
                    WHERE runtime_id = ?
                    """,
                    (runtime_id,),
                ).fetchone()
                if row is None or row[0] != process_start_identity or row[2] == "stopped":
                    connection.commit()
                    return 0
                expires_at = _parse_registry_timestamp(row[1], label="runtime expiry timestamp")
                if not stale_identity_proven and _utc_timestamp(observed_at) < expires_at:
                    connection.commit()
                    return 0
                paused = self._pause_runtime_operations(
                    connection,
                    runtime_id=runtime_id,
                    pause_reason="runtime_absent",
                    transitioned_at=encoded_now,
                )
                connection.execute(
                    """
                    UPDATE runtime_instances
                    SET state = 'stopped', heartbeat_at = ?, expires_at = ?
                    WHERE runtime_id = ? AND process_start_identity = ?
                    """,
                    (encoded_now, encoded_now, runtime_id, process_start_identity),
                )
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return paused

    def claim_next_operation(
        self,
        *,
        runtime_id: str,
        process_start_identity: str,
        pipeline_key: str,
        now: datetime,
        expires_at: datetime,
    ) -> OperationLease | None:
        """Atomically claim the oldest compatible queued or resumable paused operation."""
        _validate_runtime_identity(runtime_id, 1, process_start_identity, validate_pid=False)
        _validate_bounded_key(pipeline_key, label="pipeline key", maximum=_PIPELINE_KEY_MAX_LENGTH)
        _validate_lease_window(now, expires_at)
        encoded_now = _utc_timestamp(now).isoformat()
        encoded_expiry = _utc_timestamp(expires_at).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._require_active_runtime(
                    connection,
                    runtime_id=runtime_id,
                    process_start_identity=process_start_identity,
                    observed_at=encoded_now,
                    require_operation_capable=True,
                    pipeline_key=pipeline_key,
                )
                self._reconcile_expired_operation_leases(connection, transitioned_at=encoded_now)
                row = connection.execute(
                    """
                    SELECT o.operation_id, o.workspace_id, o.kind, o.state, o.target_head_commit, o.attempt,
                           c.target_fingerprint, c.pipeline_key, c.phase, c.known_eligible_files,
                           c.processed_files, c.parsed_files, c.reused_chunks, c.embedding_cache_hits,
                           c.embedding_cache_misses, c.embedded_chunks, c.pause_reason,
                           c.staging_generation_id, c.completed_manifest_id, c.checkpointed_at, c.resume_count
                    FROM workspace_operations AS o
                    LEFT JOIN operation_checkpoints AS c ON c.operation_id = o.operation_id
                    LEFT JOIN operation_leases AS l ON l.operation_id = o.operation_id
                    WHERE l.operation_id IS NULL
                      AND (
                          o.state = 'queued'
                          OR (o.state = 'paused' AND c.pause_reason IN ('runtime_absent', 'shutdown'))
                      )
                      AND (c.pipeline_key IS NULL OR c.pipeline_key = ?)
                    ORDER BY o.created_at, o.operation_id
                    LIMIT 1
                    """,
                    (pipeline_key,),
                ).fetchone()
                if row is None:
                    connection.commit()
                    return None
                operation = _workspace_operation_from_claim_row(row)
                checkpoint = _checkpoint_from_claim_row(row, pipeline_key=pipeline_key, checkpointed_at=now)
                if row[6] is None:
                    self._insert_checkpoint(connection, checkpoint)
                else:
                    checkpoint = replace(
                        checkpoint,
                        pause_reason=None,
                        resume_count=checkpoint.resume_count + (1 if operation.state is OperationState.PAUSED else 0),
                        checkpointed_at=_utc_timestamp(now),
                    )
                    self._update_checkpoint(connection, checkpoint)
                updated = connection.execute(
                    """
                    UPDATE workspace_operations
                    SET state = 'running', updated_at = ?, terminal_at = NULL
                    WHERE operation_id = ? AND state = ?
                    """,
                    (encoded_now, operation.operation_id, operation.state.value),
                ).rowcount
                if updated != 1:
                    raise WorkspaceRegistryError("Dolphin operation changed before its lease could be claimed")
                lease_id = f"lease_{uuid.uuid4().hex}"
                connection.execute(
                    """
                    INSERT INTO operation_leases (
                        operation_id, lease_id, runtime_id, acquired_at, heartbeat_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (operation.operation_id, lease_id, runtime_id, encoded_now, encoded_now, encoded_expiry),
                )
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return OperationLease(
            lease_id=lease_id,
            runtime_id=runtime_id,
            operation=replace(operation, state=OperationState.RUNNING),
            checkpoint=checkpoint,
            expires_at=_utc_timestamp(expires_at),
        )

    def checkpoint_operation(
        self,
        lease: OperationLease,
        checkpoint: OperationCheckpoint,
        *,
        observed_at: datetime,
    ) -> OperationCheckpoint:
        """Replace one checkpoint under its unexpired execution lease."""
        _validate_checkpoint(checkpoint)
        if (
            checkpoint.operation_id != lease.operation.operation_id
            or checkpoint.workspace_id != lease.operation.workspace_id
        ):
            raise WorkspaceRegistryError("Dolphin checkpoint belongs to another operation")
        encoded_now = _utc_timestamp(observed_at).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = self._require_operation_lease(connection, lease, observed_at=encoded_now)
                stored = self._read_checkpoint(connection, checkpoint.operation_id)
                if stored is None:
                    raise WorkspaceRegistryError("Dolphin operation checkpoint is unavailable")
                _validate_checkpoint_progress(stored, checkpoint)
                persisted = replace(checkpoint, checkpointed_at=_utc_timestamp(observed_at))
                self._update_checkpoint(connection, persisted)
                connection.execute(
                    "UPDATE workspace_operations SET updated_at = ? WHERE operation_id = ?",
                    (encoded_now, checkpoint.operation_id),
                )
                if current[0] != "running":
                    raise WorkspaceRegistryError("Dolphin operation is not running")
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return persisted

    def finish_operation(
        self,
        lease: OperationLease,
        state: OperationState,
        *,
        observed_at: datetime,
    ) -> WorkspaceOperation:
        """Commit a terminal outcome and release its execution lease atomically."""
        if state not in {OperationState.SUCCEEDED, OperationState.FAILED, OperationState.CANCELLED}:
            raise WorkspaceRegistryError("Dolphin operation finish state is not terminal")
        encoded_now = _utc_timestamp(observed_at).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._require_operation_lease(connection, lease, observed_at=encoded_now)
                updated = connection.execute(
                    """
                    UPDATE workspace_operations
                    SET state = ?, updated_at = ?, terminal_at = ?
                    WHERE operation_id = ? AND state = 'running'
                    """,
                    (state.value, encoded_now, encoded_now, lease.operation.operation_id),
                ).rowcount
                if updated != 1:
                    raise WorkspaceRegistryError("Dolphin operation changed before completion")
                connection.execute("DELETE FROM operation_leases WHERE lease_id = ?", (lease.lease_id,))
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return replace(lease.operation, state=state)

    def pause_operation(
        self,
        lease: OperationLease,
        reason: OperationPauseReason,
        *,
        observed_at: datetime,
    ) -> WorkspaceOperation:
        """Checkpoint a blocked operation and release its execution lease."""
        if reason not in {
            "runtime_absent",
            "credential_missing",
            "disk_pressure",
            "awaiting_approval",
            "shutdown",
        }:
            raise WorkspaceRegistryError("Dolphin operation pause reason is invalid")
        encoded_now = _utc_timestamp(observed_at).isoformat()
        replacement_state = OperationState.AWAITING_APPROVAL if reason == "awaiting_approval" else OperationState.PAUSED
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._require_operation_lease(connection, lease, observed_at=encoded_now)
                updated = connection.execute(
                    """
                    UPDATE workspace_operations
                    SET state = ?, updated_at = ?, terminal_at = NULL
                    WHERE operation_id = ? AND state = 'running'
                    """,
                    (replacement_state.value, encoded_now, lease.operation.operation_id),
                ).rowcount
                if updated != 1:
                    raise WorkspaceRegistryError("Dolphin operation changed before it could be paused")
                checkpoint_updated = connection.execute(
                    """
                    UPDATE operation_checkpoints
                    SET pause_reason = ?, checkpointed_at = ?
                    WHERE operation_id = ?
                    """,
                    (reason, encoded_now, lease.operation.operation_id),
                ).rowcount
                if checkpoint_updated != 1:
                    raise WorkspaceRegistryError("Dolphin operation checkpoint is unavailable")
                connection.execute("DELETE FROM operation_leases WHERE lease_id = ?", (lease.lease_id,))
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return replace(lease.operation, state=replacement_state)

    def drain_runtime(
        self,
        *,
        runtime_id: str,
        process_start_identity: str,
        observed_at: datetime,
    ) -> int:
        """Pause owned work, release leases, and stop one foreground runtime."""
        _validate_runtime_identity(runtime_id, 1, process_start_identity, validate_pid=False)
        encoded_now = _utc_timestamp(observed_at).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT process_start_identity, state FROM runtime_instances WHERE runtime_id = ?",
                    (runtime_id,),
                ).fetchone()
                if row is None:
                    connection.commit()
                    return 0
                if row[0] != process_start_identity:
                    raise WorkspaceRegistryError("Dolphin runtime ownership no longer matches this process")
                if row[1] == "stopped":
                    connection.commit()
                    return 0
                connection.execute(
                    "UPDATE runtime_instances SET state = 'draining' WHERE runtime_id = ?",
                    (runtime_id,),
                )
                paused = self._pause_runtime_operations(
                    connection,
                    runtime_id=runtime_id,
                    pause_reason="shutdown",
                    transitioned_at=encoded_now,
                )
                connection.execute(
                    """
                    UPDATE runtime_instances
                    SET state = 'stopped', heartbeat_at = ?, expires_at = ?
                    WHERE runtime_id = ?
                    """,
                    (encoded_now, encoded_now, runtime_id),
                )
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return paused

    @staticmethod
    def _require_active_runtime(
        connection: sqlite3.Connection,
        *,
        runtime_id: str,
        process_start_identity: str,
        observed_at: str,
        require_operation_capable: bool,
        pipeline_key: str | None = None,
    ) -> None:
        row = connection.execute(
            """
            SELECT process_start_identity, operation_capable, pipeline_key, state, expires_at
            FROM runtime_instances
            WHERE runtime_id = ?
            """,
            (runtime_id,),
        ).fetchone()
        if row is None or row[0] != process_start_identity or row[3] != "active" or row[4] <= observed_at:
            raise WorkspaceRegistryError("Dolphin runtime ownership is inactive or expired")
        if require_operation_capable and row[1] != 1:
            raise WorkspaceRegistryError("Dolphin runtime is not configured to execute operations")
        if pipeline_key is not None and row[2] != pipeline_key:
            raise WorkspaceRegistryError("Dolphin runtime pipeline does not match the operation claim")

    @staticmethod
    def _require_operation_lease(
        connection: sqlite3.Connection,
        lease: OperationLease,
        *,
        observed_at: str,
    ) -> tuple[str, str]:
        row = connection.execute(
            """
            SELECT o.state, l.expires_at
            FROM operation_leases AS l
            JOIN workspace_operations AS o ON o.operation_id = l.operation_id
            JOIN runtime_instances AS r ON r.runtime_id = l.runtime_id
            WHERE l.operation_id = ? AND l.lease_id = ? AND l.runtime_id = ?
              AND r.state = 'active' AND r.expires_at > ?
            """,
            (lease.operation.operation_id, lease.lease_id, lease.runtime_id, observed_at),
        ).fetchone()
        if row is None or row[1] <= observed_at:
            raise WorkspaceRegistryError("Dolphin operation lease is unavailable or expired")
        return str(row[0]), str(row[1])

    @staticmethod
    def _insert_checkpoint(connection: sqlite3.Connection, checkpoint: OperationCheckpoint) -> None:
        _validate_checkpoint(checkpoint)
        connection.execute(
            """
            INSERT INTO operation_checkpoints (
                operation_id, schema_version, workspace_id, target_fingerprint, pipeline_key, phase,
                staging_generation_id, completed_manifest_id, known_eligible_files, processed_files,
                parsed_files, reused_chunks, embedding_cache_hits, embedding_cache_misses,
                embedded_chunks, pause_reason, checkpointed_at, resume_count
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _checkpoint_storage_values(checkpoint),
        )

    @staticmethod
    def _update_checkpoint(connection: sqlite3.Connection, checkpoint: OperationCheckpoint) -> None:
        _validate_checkpoint(checkpoint)
        values = _checkpoint_storage_values(checkpoint)
        updated = connection.execute(
            """
            UPDATE operation_checkpoints
            SET workspace_id = ?, target_fingerprint = ?, pipeline_key = ?, phase = ?,
                staging_generation_id = ?, completed_manifest_id = ?, known_eligible_files = ?,
                processed_files = ?, parsed_files = ?, reused_chunks = ?, embedding_cache_hits = ?,
                embedding_cache_misses = ?, embedded_chunks = ?, pause_reason = ?, checkpointed_at = ?,
                resume_count = ?
            WHERE operation_id = ? AND schema_version = 1
            """,
            (*values[1:], values[0]),
        ).rowcount
        if updated != 1:
            raise WorkspaceRegistryError("Dolphin operation checkpoint changed before it could be replaced")

    @staticmethod
    def _read_checkpoint(connection: sqlite3.Connection, operation_id: str) -> OperationCheckpoint | None:
        row = connection.execute(
            """
            SELECT operation_id, workspace_id, target_fingerprint, pipeline_key, phase,
                   known_eligible_files, processed_files, parsed_files, reused_chunks,
                   embedding_cache_hits, embedding_cache_misses, embedded_chunks, pause_reason,
                   staging_generation_id, completed_manifest_id, checkpointed_at, resume_count
            FROM operation_checkpoints
            WHERE operation_id = ? AND schema_version = 1
            """,
            (operation_id,),
        ).fetchone()
        return None if row is None else _checkpoint_from_storage_row(row)

    @staticmethod
    def _reconcile_expired_operation_leases(
        connection: sqlite3.Connection,
        *,
        transitioned_at: str,
    ) -> int:
        runtime_ids = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT runtime_id
                FROM operation_leases
                WHERE expires_at <= ?
                """,
                (transitioned_at,),
            ).fetchall()
        ]
        paused = 0
        for runtime_id in runtime_ids:
            paused += WorkspaceRegistry._pause_runtime_operations(
                connection,
                runtime_id=runtime_id,
                pause_reason="runtime_absent",
                transitioned_at=transitioned_at,
                only_expired_at=transitioned_at,
            )
        return paused

    @staticmethod
    def _pause_runtime_operations(
        connection: sqlite3.Connection,
        *,
        runtime_id: str,
        pause_reason: OperationPauseReason,
        transitioned_at: str,
        only_expired_at: str | None = None,
    ) -> int:
        rows = connection.execute(
            """
            SELECT l.operation_id
            FROM operation_leases AS l
            JOIN workspace_operations AS o ON o.operation_id = l.operation_id
            WHERE l.runtime_id = ? AND o.state = 'running'
              AND (? IS NULL OR l.expires_at <= ?)
            ORDER BY l.operation_id
            """,
            (runtime_id, only_expired_at, only_expired_at),
        ).fetchall()
        operation_ids = [str(row[0]) for row in rows]
        for operation_id in operation_ids:
            connection.execute(
                """
                UPDATE workspace_operations
                SET state = 'paused', updated_at = ?, terminal_at = NULL
                WHERE operation_id = ? AND state = 'running'
                """,
                (transitioned_at, operation_id),
            )
            connection.execute(
                """
                UPDATE operation_checkpoints
                SET pause_reason = ?, checkpointed_at = ?
                WHERE operation_id = ?
                """,
                (pause_reason, transitioned_at, operation_id),
            )
        if operation_ids:
            connection.executemany(
                "DELETE FROM operation_leases WHERE operation_id = ?",
                ((operation_id,) for operation_id in operation_ids),
            )
        return len(operation_ids)

    def register(
        self,
        worktree: GitWorktree,
        *,
        cleanup_receipt: str,
        parent_scan: ParentScanPlan | None = None,
    ) -> WorkspaceRegistration:
        """Atomically create or refresh exactly one concrete worktree registration."""
        self._require_valid_cleanup_receipt(cleanup_receipt)
        self._require_matching_parent_scan(worktree, parent_scan)
        self._validate_worktree_snapshot(worktree)
        with self._connection() as connection:
            self._begin_registration_write(connection)
            try:
                registration = self._register(connection, worktree, cleanup_receipt)
                if parent_scan is not None:
                    self._replace_boundaries(
                        connection,
                        registration.workspace_id,
                        parent_scan.repository_boundaries,
                    )
                self._validate_worktree_snapshot(worktree)
                self._validate_parent_scan_snapshot(parent_scan)
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
        parent_scan: ParentScanPlan | None = None,
    ) -> tuple[WorkspaceRegistration, WorkspaceOperation]:
        """Persist one discovered snapshot and its initial-index operation atomically."""
        self._require_valid_cleanup_receipt(cleanup_receipt)
        self._require_matching_parent_scan(worktree, parent_scan)
        self._validate_worktree_snapshot(worktree)
        with self._connection() as connection:
            self._begin_registration_write(connection)
            try:
                registration = self._register(connection, worktree, cleanup_receipt)
                if parent_scan is not None:
                    self._replace_boundaries(
                        connection,
                        registration.workspace_id,
                        parent_scan.repository_boundaries,
                    )
                operation = self._submit_initial_index(connection, registration)
                self._validate_worktree_snapshot(worktree)
                self._validate_parent_scan_snapshot(parent_scan)
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
        """Create the current prerelease schema without carrying legacy migrations."""
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
            if version != 0:
                raise WorkspaceRegistryError(
                    "Dolphin metadata storage uses an unsupported prerelease schema; remove it and re-enroll worktrees"
                )

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
                if version != 0:
                    raise WorkspaceRegistryError(
                        "Dolphin metadata storage uses an unsupported prerelease schema; "
                        "remove it and re-enroll worktrees"
                    )
                if version == 0:
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS workspace_registrations (
                            workspace_id TEXT PRIMARY KEY,
                            repository_id TEXT NOT NULL,
                            root TEXT NOT NULL UNIQUE,
                            common_git_dir TEXT NOT NULL,
                            common_git_dir_identity TEXT NOT NULL,
                            worktree_git_dir TEXT NOT NULL,
                            worktree_git_dir_identity TEXT NOT NULL,
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
                        CREATE UNIQUE INDEX workspace_registrations_git_identity
                        ON workspace_registrations (common_git_dir_identity, worktree_git_dir_identity)
                        """
                    )
                    connection.execute(
                        """
                        CREATE TABLE workspace_repository_boundaries (
                            workspace_id TEXT NOT NULL REFERENCES workspace_registrations(workspace_id)
                                ON DELETE CASCADE,
                            relative_path TEXT NOT NULL,
                            kind TEXT NOT NULL CHECK (kind IN ('submodule', 'nested_git')),
                            state TEXT NOT NULL CHECK (state IN (
                                'enrollable', 'uninitialized', 'missing', 'conflicted', 'invalid'
                            )),
                            root TEXT,
                            expected_commit TEXT,
                            observed_commit TEXT,
                            dirty INTEGER CHECK (dirty IS NULL OR dirty IN (0, 1)),
                            PRIMARY KEY (workspace_id, relative_path)
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
                        CREATE TABLE runtime_instances (
                            runtime_id TEXT PRIMARY KEY,
                            pid INTEGER NOT NULL CHECK (pid > 0),
                            process_start_identity TEXT NOT NULL,
                            mode TEXT NOT NULL CHECK (mode IN ('mcp', 'foreground_cli')),
                            operation_capable INTEGER NOT NULL CHECK (operation_capable IN (0, 1)),
                            pipeline_key TEXT,
                            state TEXT NOT NULL CHECK (state IN ('active', 'draining', 'stopped')),
                            dolphin_version TEXT NOT NULL,
                            schema_version INTEGER NOT NULL,
                            started_at TEXT NOT NULL,
                            heartbeat_at TEXT NOT NULL,
                            expires_at TEXT NOT NULL,
                            CHECK (
                                (operation_capable = 0 AND pipeline_key IS NULL)
                                OR (operation_capable = 1 AND pipeline_key IS NOT NULL)
                            )
                        ) STRICT
                        """
                    )
                    connection.execute(
                        """
                        CREATE TABLE operation_checkpoints (
                            operation_id TEXT PRIMARY KEY REFERENCES workspace_operations(operation_id)
                                ON DELETE CASCADE,
                            schema_version INTEGER NOT NULL CHECK (schema_version = 1),
                            workspace_id TEXT NOT NULL REFERENCES workspace_registrations(workspace_id),
                            target_fingerprint TEXT NOT NULL,
                            pipeline_key TEXT NOT NULL,
                            phase TEXT NOT NULL CHECK (phase IN (
                                'preflight', 'scan', 'chunk', 'embed', 'store', 'publish'
                            )),
                            staging_generation_id TEXT,
                            completed_manifest_id TEXT,
                            known_eligible_files INTEGER CHECK (
                                known_eligible_files IS NULL OR known_eligible_files >= 0
                            ),
                            processed_files INTEGER NOT NULL CHECK (processed_files >= 0),
                            parsed_files INTEGER NOT NULL CHECK (parsed_files >= 0),
                            reused_chunks INTEGER NOT NULL CHECK (reused_chunks >= 0),
                            embedding_cache_hits INTEGER NOT NULL CHECK (embedding_cache_hits >= 0),
                            embedding_cache_misses INTEGER NOT NULL CHECK (embedding_cache_misses >= 0),
                            embedded_chunks INTEGER NOT NULL CHECK (embedded_chunks >= 0),
                            pause_reason TEXT CHECK (pause_reason IS NULL OR pause_reason IN (
                                'runtime_absent', 'credential_missing', 'disk_pressure', 'awaiting_approval', 'shutdown'
                            )),
                            checkpointed_at TEXT NOT NULL,
                            resume_count INTEGER NOT NULL CHECK (resume_count >= 0)
                        ) STRICT
                        """
                    )
                    connection.execute(
                        """
                        CREATE TABLE operation_leases (
                            operation_id TEXT PRIMARY KEY REFERENCES workspace_operations(operation_id)
                                ON DELETE CASCADE,
                            lease_id TEXT NOT NULL UNIQUE,
                            runtime_id TEXT NOT NULL REFERENCES runtime_instances(runtime_id),
                            acquired_at TEXT NOT NULL,
                            heartbeat_at TEXT NOT NULL,
                            expires_at TEXT NOT NULL
                        ) STRICT
                        """
                    )
                    connection.execute(
                        """
                        CREATE INDEX operation_leases_runtime
                        ON operation_leases (runtime_id, expires_at)
                        """
                    )
                    connection.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS workspace_operations_reusable_target
                        ON workspace_operations (workspace_id, kind, target_head_commit)
                        WHERE state IN ('queued', 'running', 'awaiting_approval', 'paused', 'succeeded')
                        """
                    )
                    connection.execute(
                        """
                        CREATE INDEX workspace_operations_claimable
                        ON workspace_operations (state, created_at, operation_id)
                        """
                    )
                    connection.execute(
                        """
                        CREATE TABLE generations (
                            generation_id TEXT PRIMARY KEY,
                            operation_id TEXT NOT NULL UNIQUE REFERENCES workspace_operations(operation_id),
                            workspace_id TEXT NOT NULL REFERENCES workspace_registrations(workspace_id),
                            target_fingerprint TEXT NOT NULL,
                            pipeline_key TEXT NOT NULL,
                            state TEXT NOT NULL CHECK (state IN ('staging', 'ready', 'published')),
                            vector_commit_token TEXT,
                            vector_digest TEXT,
                            vector_row_count INTEGER CHECK (vector_row_count IS NULL OR vector_row_count >= 0),
                            vector_provider TEXT CHECK (vector_provider IS NULL OR vector_provider = 'openai'),
                            vector_model TEXT CHECK (
                                vector_model IS NULL OR vector_model = 'text-embedding-3-small'
                            ),
                            vector_dimensions INTEGER CHECK (
                                vector_dimensions IS NULL OR vector_dimensions = 1536
                            ),
                            embedding_contract_version INTEGER CHECK (
                                embedding_contract_version IS NULL OR embedding_contract_version = 1
                            ),
                            manifest_id TEXT UNIQUE,
                            manifest_digest TEXT,
                            metadata_item_count INTEGER CHECK (
                                metadata_item_count IS NULL OR metadata_item_count >= 0
                            ),
                            keyword_item_count INTEGER CHECK (
                                keyword_item_count IS NULL OR keyword_item_count >= 0
                            ),
                            publication_id TEXT UNIQUE,
                            publication_revision INTEGER CHECK (
                                publication_revision IS NULL OR publication_revision >= 1
                            ),
                            previous_generation_id TEXT,
                            created_at TEXT NOT NULL,
                            ready_at TEXT,
                            published_at TEXT,
                            CHECK (
                                (
                                    vector_commit_token IS NULL
                                    AND vector_digest IS NULL
                                    AND vector_row_count IS NULL
                                    AND vector_provider IS NULL
                                    AND vector_model IS NULL
                                    AND vector_dimensions IS NULL
                                    AND embedding_contract_version IS NULL
                                )
                                OR (
                                    vector_commit_token IS NOT NULL
                                    AND vector_digest IS NOT NULL
                                    AND vector_row_count IS NOT NULL
                                    AND vector_provider IS NOT NULL
                                    AND vector_model IS NOT NULL
                                    AND vector_dimensions IS NOT NULL
                                    AND embedding_contract_version IS NOT NULL
                                )
                            ),
                            CHECK (
                                (
                                    state = 'staging'
                                    AND manifest_id IS NULL
                                    AND manifest_digest IS NULL
                                    AND metadata_item_count IS NULL
                                    AND keyword_item_count IS NULL
                                    AND ready_at IS NULL
                                )
                                OR (
                                    state IN ('ready', 'published')
                                    AND vector_commit_token IS NOT NULL
                                    AND manifest_id IS NOT NULL
                                    AND manifest_digest IS NOT NULL
                                    AND metadata_item_count IS NOT NULL
                                    AND keyword_item_count IS NOT NULL
                                    AND ready_at IS NOT NULL
                                )
                            ),
                            CHECK (
                                (
                                    state = 'published'
                                    AND publication_id IS NOT NULL
                                    AND publication_revision IS NOT NULL
                                    AND published_at IS NOT NULL
                                )
                                OR (
                                    state != 'published'
                                    AND publication_id IS NULL
                                    AND publication_revision IS NULL
                                    AND previous_generation_id IS NULL
                                    AND published_at IS NULL
                                )
                            ),
                            UNIQUE (generation_id, publication_id),
                            UNIQUE (workspace_id, generation_id)
                        ) STRICT
                        """
                    )
                    connection.execute(
                        """
                        CREATE INDEX generations_workspace_state
                        ON generations (workspace_id, state, created_at, generation_id)
                        """
                    )
                    connection.execute(
                        """
                        CREATE TABLE workspace_publications (
                            workspace_id TEXT PRIMARY KEY REFERENCES workspace_registrations(workspace_id),
                            generation_id TEXT NOT NULL UNIQUE REFERENCES generations(generation_id),
                            publication_id TEXT NOT NULL UNIQUE,
                            revision INTEGER NOT NULL CHECK (revision >= 1),
                            published_at TEXT NOT NULL,
                            FOREIGN KEY (generation_id, publication_id)
                                REFERENCES generations(generation_id, publication_id),
                            FOREIGN KEY (workspace_id, generation_id)
                                REFERENCES generations(workspace_id, generation_id)
                        ) STRICT
                        """
                    )
                    connection.execute(
                        """
                        CREATE TABLE generation_reader_leases (
                            lease_id TEXT PRIMARY KEY,
                            generation_id TEXT NOT NULL,
                            publication_id TEXT NOT NULL,
                            acquired_at TEXT NOT NULL,
                            expires_at TEXT NOT NULL,
                            CHECK (expires_at > acquired_at),
                            FOREIGN KEY (generation_id, publication_id)
                                REFERENCES generations(generation_id, publication_id)
                        ) STRICT
                        """
                    )
                    connection.execute(
                        """
                        CREATE INDEX generation_reader_leases_expiry
                        ON generation_reader_leases (expires_at, generation_id)
                        """
                    )
                    self._create_registry_metadata(connection)
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            except Exception:
                connection.rollback()
                raise
            connection.commit()
            self._initialized = True

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
    def _require_matching_parent_scan(worktree: GitWorktree, parent_scan: ParentScanPlan | None) -> None:
        if parent_scan is not None and parent_scan.worktree != worktree:
            raise WorkspaceRegistryError("Dolphin repository boundary snapshot belongs to another worktree")

    @staticmethod
    def _validate_parent_scan_snapshot(parent_scan: ParentScanPlan | None) -> None:
        if parent_scan is None:
            return
        try:
            validate_parent_scan(parent_scan)
        except RepositoryBoundaryError as exc:
            raise WorkspaceRegistryError("Dolphin repository boundaries changed before registration") from exc

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

    def _register(
        self,
        connection: sqlite3.Connection,
        worktree: GitWorktree,
        cleanup_receipt: str,
    ) -> WorkspaceRegistration:
        root = str(worktree.root)
        existing = connection.execute(
            """
            SELECT workspace_id, repository_id, common_git_dir, common_git_dir_identity,
                   worktree_git_dir_identity, cleanup_receipt_hash
            FROM workspace_registrations
            WHERE root = ?
            """,
            (root,),
        ).fetchone()
        now = datetime.now(UTC).isoformat()
        if existing is not None:
            (
                workspace_id,
                repository_id,
                common_git_dir,
                common_git_dir_identity,
                worktree_git_dir_identity,
                cleanup_receipt_hash,
            ) = existing
            if (
                common_git_dir_identity != worktree.common_git_dir_identity
                or worktree_git_dir_identity != worktree.worktree_git_dir_identity
                or repository_id != _repository_id(worktree)
            ):
                raise WorkspaceRegistryError("Dolphin workspace root belongs to a different Git repository or worktree")
            connection.execute(
                """
                UPDATE workspace_registrations
                SET common_git_dir = ?, worktree_git_dir = ?, branch = ?, head_commit = ?, updated_at = ?
                WHERE workspace_id = ?
                """,
                (
                    str(worktree.common_git_dir),
                    str(worktree.worktree_git_dir),
                    worktree.branch,
                    worktree.head_commit,
                    now,
                    workspace_id,
                ),
            )
            if common_git_dir != str(worktree.common_git_dir):
                connection.execute(
                    "UPDATE workspace_registry_meta SET list_revision = list_revision + 1 WHERE singleton = 1"
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

        identity_match = connection.execute(
            """
            SELECT workspace_id, repository_id, root, cleanup_receipt_hash
            FROM workspace_registrations
            WHERE common_git_dir_identity = ? AND worktree_git_dir_identity = ?
            """,
            (worktree.common_git_dir_identity, worktree.worktree_git_dir_identity),
        ).fetchone()
        if identity_match is not None:
            workspace_id, repository_id, previous_root, cleanup_receipt_hash = identity_match
            if repository_id != _repository_id(worktree):
                raise WorkspaceRegistryError("Dolphin Git filesystem identity is inconsistent")
            if _path_entry_exists(previous_root):
                raise WorkspaceRegistryError(
                    "Dolphin Git worktree identity is already registered at an existing filesystem path"
                )
            connection.execute(
                """
                UPDATE workspace_registrations
                SET root = ?, common_git_dir = ?, worktree_git_dir = ?, branch = ?, head_commit = ?, updated_at = ?
                WHERE workspace_id = ?
                """,
                (
                    root,
                    str(worktree.common_git_dir),
                    str(worktree.worktree_git_dir),
                    worktree.branch,
                    worktree.head_commit,
                    now,
                    workspace_id,
                ),
            )
            connection.execute(
                "UPDATE workspace_registry_meta SET list_revision = list_revision + 1 WHERE singleton = 1"
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
                worktree_git_dir, worktree_git_dir_identity, branch, head_commit, registration_epoch,
                cleanup_receipt_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                repository_id,
                root,
                str(worktree.common_git_dir),
                worktree.common_git_dir_identity,
                str(worktree.worktree_git_dir),
                worktree.worktree_git_dir_identity,
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

    @staticmethod
    def _replace_boundaries(
        connection: sqlite3.Connection,
        workspace_id: str,
        boundaries: Sequence[RepositoryBoundary],
    ) -> None:
        ordered = sorted(boundaries, key=lambda boundary: boundary.relative_path)
        if len(ordered) > _MAX_STORED_BOUNDARIES:
            raise WorkspaceRegistryError("Dolphin repository boundary count is invalid")
        if len({boundary.relative_path for boundary in ordered}) != len(ordered):
            raise WorkspaceRegistryError("Dolphin repository boundaries contain duplicate paths")
        for boundary in ordered:
            _validate_boundary_for_storage(boundary)
        serialized = [_boundary_storage_row(workspace_id, boundary) for boundary in ordered]
        existing = connection.execute(
            """
            SELECT workspace_id, relative_path, kind, state, root, expected_commit, observed_commit, dirty
            FROM workspace_repository_boundaries
            WHERE workspace_id = ?
            ORDER BY relative_path
            """,
            (workspace_id,),
        ).fetchall()
        if existing == serialized:
            return
        connection.execute("DELETE FROM workspace_repository_boundaries WHERE workspace_id = ?", (workspace_id,))
        connection.executemany(
            """
            INSERT INTO workspace_repository_boundaries (
                workspace_id, relative_path, kind, state, root, expected_commit, observed_commit, dirty
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            serialized,
        )
        connection.execute("UPDATE workspace_registry_meta SET list_revision = list_revision + 1 WHERE singleton = 1")

    @staticmethod
    def _read_boundaries(
        connection: sqlite3.Connection,
        workspace_id: str,
    ) -> tuple[RepositoryBoundary, ...]:
        rows = connection.execute(
            """
            SELECT b.kind, b.relative_path, b.state, b.root, b.expected_commit, b.observed_commit, b.dirty,
                   child.workspace_id
            FROM workspace_repository_boundaries AS b
            LEFT JOIN workspace_registrations AS child ON child.root = b.root
            WHERE b.workspace_id = ?
            ORDER BY b.relative_path
            LIMIT ?
            """,
            (workspace_id, _MAX_BOUNDARIES_PER_READ),
        ).fetchall()
        boundaries: list[RepositoryBoundary] = []
        for row in rows:
            boundary = _boundary_from_row(tuple(row[:7]))
            if row[7] is not None:
                boundary = replace(
                    boundary,
                    workspace_id=_bounded_registry_text(
                        row[7],
                        label="workspace ID",
                        max_length=ENTITY_ID_MAX_LENGTH,
                    ),
                )
            boundaries.append(boundary)
        return tuple(boundaries)

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
    return _repository_id_from_common_git_identity(worktree.common_git_dir_identity)


def _repository_id_from_common_git_identity(common_git_dir_identity: str) -> str:
    digest = hashlib.sha256(common_git_dir_identity.encode("utf-8")).hexdigest()
    return f"repo_{digest[:24]}"


def _validate_boundary_for_storage(boundary: RepositoryBoundary) -> None:
    path = PurePosixPath(boundary.relative_path)
    if (
        not boundary.relative_path
        or len(boundary.relative_path) > 4_096
        or path.is_absolute()
        or boundary.relative_path != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise WorkspaceRegistryError("Dolphin repository boundary path is invalid")
    if boundary.root is not None and (not boundary.root.is_absolute() or len(str(boundary.root)) > 4_096):
        raise WorkspaceRegistryError("Dolphin repository boundary root is invalid")
    for commit in (boundary.expected_commit, boundary.observed_commit):
        if commit is not None and (not commit or len(commit) > HEAD_COMMIT_MAX_LENGTH):
            raise WorkspaceRegistryError("Dolphin repository boundary commit is invalid")
    if boundary.workspace_id is not None and (
        not boundary.workspace_id or len(boundary.workspace_id) > ENTITY_ID_MAX_LENGTH
    ):
        raise WorkspaceRegistryError("Dolphin repository boundary workspace ID is invalid")


def _boundary_storage_row(workspace_id: str, boundary: RepositoryBoundary) -> tuple[object, ...]:
    return (
        workspace_id,
        boundary.relative_path,
        boundary.kind.value,
        boundary.state.value,
        str(boundary.root) if boundary.root is not None else None,
        boundary.expected_commit,
        boundary.observed_commit,
        int(boundary.dirty) if boundary.dirty is not None else None,
    )


def _boundary_from_row(row: tuple[object, ...]) -> RepositoryBoundary:
    try:
        dirty_value = row[6]
        if dirty_value not in {None, 0, 1}:
            raise ValueError("invalid dirty state")
        boundary = RepositoryBoundary(
            kind=RepositoryBoundaryKind(str(row[0])),
            relative_path=str(row[1]),
            state=RepositoryBoundaryState(str(row[2])),
            root=Path(str(row[3])) if row[3] is not None else None,
            expected_commit=str(row[4]) if row[4] is not None else None,
            observed_commit=str(row[5]) if row[5] is not None else None,
            dirty=bool(dirty_value) if dirty_value is not None else None,
        )
        _validate_boundary_for_storage(boundary)
    except (IndexError, TypeError, ValueError) as exc:
        raise WorkspaceRegistryError("Dolphin repository boundary metadata is invalid") from exc
    return boundary


def _path_entry_exists(path: str) -> bool:
    """Check the prior registered root without following a replacement symlink."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise WorkspaceRegistryError("Dolphin cannot verify the prior worktree filesystem path") from exc
    return True


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
_WORKSPACE_BY_ID_QUERY = _WORKSPACE_PROJECTION + " WHERE w.workspace_id = ? LIMIT 1"

_DEEPEST_WORKSPACE_FOR_PATH_QUERY = (
    "WITH workspace_projection AS ("
    + _WORKSPACE_PROJECTION
    + ")"
    + """
    SELECT workspace_id, repository_id, repository_display_name, workspace_display_name,
           root, branch, head_commit, effective_state
    FROM workspace_projection
    WHERE ? = root OR (length(?) > length(root) AND substr(?, 1, length(root) + 1) = root || '/')
    ORDER BY length(root) DESC, workspace_id
    LIMIT 1
"""
)

_DEEPEST_BOUNDARY_FOR_PATH_QUERY = """
    WITH boundary_projection AS (
        SELECT
            w.workspace_id AS parent_workspace_id,
            rtrim(w.root, '/') || '/' || b.relative_path AS boundary_root,
            w.root AS parent_root,
            b.kind,
            b.relative_path,
            b.state,
            b.root,
            b.expected_commit,
            b.observed_commit,
            b.dirty,
            child.workspace_id AS child_workspace_id
        FROM workspace_repository_boundaries AS b
        JOIN workspace_registrations AS w ON w.workspace_id = b.workspace_id
        LEFT JOIN workspace_registrations AS child ON child.root = b.root
    )
    SELECT parent_workspace_id, boundary_root, parent_root, kind, relative_path, state,
           root, expected_commit, observed_commit, dirty, child_workspace_id
    FROM boundary_projection
    WHERE ? = boundary_root
       OR (length(?) > length(boundary_root) AND substr(?, 1, length(boundary_root) + 1) = boundary_root || '/')
    ORDER BY length(boundary_root) DESC, parent_workspace_id, relative_path
    LIMIT 1
"""

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
    workspace_id = _bounded_registry_text(row[0], label="workspace ID", max_length=ENTITY_ID_MAX_LENGTH)
    repository_id = _bounded_registry_text(row[1], label="repository ID", max_length=ENTITY_ID_MAX_LENGTH)
    repository_display_name = _bounded_registry_text(row[2], label="repository display name", max_length=512)
    workspace_display_name = _bounded_registry_text(row[3], label="workspace display name", max_length=512)
    root = _bounded_registry_text(row[4], label="workspace root", max_length=4_096)
    if not Path(root).is_absolute():
        raise WorkspaceRegistryError("Dolphin workspace metadata contains an invalid root")
    branch = None if row[5] is None else _bounded_registry_text(row[5], label="workspace branch", max_length=1_024)
    head_commit = _bounded_registry_text(row[6], label="workspace commit", max_length=HEAD_COMMIT_MAX_LENGTH)
    state = str(row[7])
    if state not in {"registered", "indexing", "ready", "failed"}:
        raise WorkspaceRegistryError("Dolphin workspace metadata contains an invalid state")
    return WorkspaceSnapshot(
        workspace_id=workspace_id,
        repository_id=repository_id,
        repository_display_name=repository_display_name,
        workspace_display_name=workspace_display_name,
        root=root,
        branch=branch,
        head_commit=head_commit,
        state=cast(WorkspaceEffectiveState, state),
    )


def _normalize_resolution_path(path: Path) -> str:
    raw_path = str(path)
    if not path.is_absolute() or not raw_path or "\x00" in raw_path or len(raw_path) > 4_096:
        raise WorkspaceRegistryError("Dolphin workspace resolution path is invalid")
    normalized = os.path.normpath(raw_path)
    if not Path(normalized).is_absolute() or len(normalized) > 4_096:
        raise WorkspaceRegistryError("Dolphin workspace resolution path is invalid")
    return normalized


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


def _runtime_version() -> str:
    version = get_version()
    _validate_bounded_key(version, label="runtime version", maximum=64)
    return version


def _utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise WorkspaceRegistryError("Dolphin runtime timestamp must include a timezone")
    return value.astimezone(UTC)


def _validate_lease_window(now: datetime, expires_at: datetime) -> None:
    if _utc_timestamp(expires_at) <= _utc_timestamp(now):
        raise WorkspaceRegistryError("Dolphin lease expiry must be later than its heartbeat")


def _validate_bounded_key(value: str, *, label: str, maximum: int) -> None:
    if not value or len(value) > maximum or "\x00" in value:
        raise WorkspaceRegistryError(f"Dolphin {label} is invalid")


def _validate_runtime_identity(
    runtime_id: str,
    pid: int,
    process_start_identity: str,
    *,
    validate_pid: bool = True,
) -> None:
    _validate_bounded_key(runtime_id, label="runtime ID", maximum=_RUNTIME_ID_MAX_LENGTH)
    _validate_bounded_key(
        process_start_identity,
        label="process start identity",
        maximum=_PROCESS_IDENTITY_MAX_LENGTH,
    )
    if validate_pid and (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0):
        raise WorkspaceRegistryError("Dolphin runtime PID is invalid")


def _runtime_owner_from_row(row: tuple[object, ...]) -> RuntimeOwner:
    runtime_id = _bounded_registry_text(row[0], label="runtime ID", max_length=_RUNTIME_ID_MAX_LENGTH)
    pid = row[1]
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise WorkspaceRegistryError("Dolphin runtime ownership metadata contains an invalid PID")
    process_start_identity = _bounded_registry_text(
        row[2],
        label="process start identity",
        max_length=_PROCESS_IDENTITY_MAX_LENGTH,
    )
    mode = _bounded_registry_text(row[3], label="runtime mode", max_length=32)
    pipeline_key = (
        _bounded_registry_text(row[5], label="pipeline key", max_length=_PIPELINE_KEY_MAX_LENGTH)
        if row[5] is not None
        else None
    )
    state = _bounded_registry_text(row[6], label="runtime state", max_length=32)
    if mode not in {"mcp", "foreground_cli"} or state not in {"active", "draining", "stopped"}:
        raise WorkspaceRegistryError("Dolphin runtime ownership metadata is invalid")
    if row[4] not in {0, 1}:
        raise WorkspaceRegistryError("Dolphin runtime capability metadata is invalid")
    operation_capable = bool(row[4])
    if operation_capable != (pipeline_key is not None):
        raise WorkspaceRegistryError("Dolphin runtime pipeline metadata is invalid")
    return RuntimeOwner(
        runtime_id=runtime_id,
        pid=pid,
        process_start_identity=process_start_identity,
        mode=cast(RuntimeMode, mode),
        operation_capable=operation_capable,
        pipeline_key=pipeline_key,
        state=cast(RuntimeState, state),
        started_at=_parse_registry_timestamp(row[7], label="runtime start timestamp"),
        heartbeat_at=_parse_registry_timestamp(row[8], label="runtime heartbeat timestamp"),
        expires_at=_parse_registry_timestamp(row[9], label="runtime expiry timestamp"),
    )


def _workspace_operation_from_claim_row(row: tuple[object, ...]) -> WorkspaceOperation:
    operation_id = _bounded_registry_text(row[0], label="operation ID", max_length=OPERATION_ID_MAX_LENGTH)
    workspace_id = _bounded_registry_text(row[1], label="workspace ID", max_length=ENTITY_ID_MAX_LENGTH)
    kind = _bounded_registry_text(row[2], label="operation kind", max_length=32)
    if kind not in {"initial_index", "sync", "recovery"}:
        raise WorkspaceRegistryError("Dolphin operation metadata contains an invalid kind")
    try:
        state = OperationState(_bounded_registry_text(row[3], label="operation state", max_length=32))
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
    return WorkspaceOperation(
        operation_id=operation_id,
        workspace_id=workspace_id,
        kind=cast(OperationKind, kind),
        state=state,
        target_head_commit=target_head_commit,
        attempt=attempt,
        created=False,
    )


def _checkpoint_from_claim_row(
    row: tuple[object, ...],
    *,
    pipeline_key: str,
    checkpointed_at: datetime,
) -> OperationCheckpoint:
    operation = _workspace_operation_from_claim_row(row)
    if row[6] is None:
        return OperationCheckpoint(
            operation_id=operation.operation_id,
            workspace_id=operation.workspace_id,
            target_fingerprint=f"git-head-v1:{operation.target_head_commit}",
            pipeline_key=pipeline_key,
            phase="preflight",
            counters=OperationCountersSnapshot(),
            checkpointed_at=_utc_timestamp(checkpointed_at),
        )
    return _checkpoint_from_storage_row(
        (
            operation.operation_id,
            operation.workspace_id,
            *row[6:17],
            row[17],
            row[18],
            row[19],
            row[20],
        )
    )


def _checkpoint_from_storage_row(row: tuple[object, ...]) -> OperationCheckpoint:
    operation_id = _bounded_registry_text(row[0], label="operation ID", max_length=OPERATION_ID_MAX_LENGTH)
    workspace_id = _bounded_registry_text(row[1], label="workspace ID", max_length=ENTITY_ID_MAX_LENGTH)
    target_fingerprint = _bounded_registry_text(
        row[2], label="target fingerprint", max_length=_TARGET_FINGERPRINT_MAX_LENGTH
    )
    pipeline_key = _bounded_registry_text(row[3], label="pipeline key", max_length=_PIPELINE_KEY_MAX_LENGTH)
    phase = _bounded_registry_text(row[4], label="operation phase", max_length=32)
    if phase not in _OPERATION_PHASES:
        raise WorkspaceRegistryError("Dolphin operation checkpoint contains an invalid phase")
    counters = _operation_counters_from_values(row[5:12])
    pause_reason = None if row[12] is None else _bounded_registry_text(row[12], label="pause reason", max_length=32)
    if pause_reason is not None and pause_reason not in {
        "runtime_absent",
        "credential_missing",
        "disk_pressure",
        "awaiting_approval",
        "shutdown",
    }:
        raise WorkspaceRegistryError("Dolphin operation checkpoint contains an invalid pause reason")
    staging_generation_id = (
        None
        if row[13] is None
        else _bounded_registry_text(row[13], label="staging generation ID", max_length=ENTITY_ID_MAX_LENGTH)
    )
    completed_manifest_id = (
        None
        if row[14] is None
        else _bounded_registry_text(row[14], label="completed manifest ID", max_length=ENTITY_ID_MAX_LENGTH)
    )
    resume_count = row[16]
    if not isinstance(resume_count, int) or isinstance(resume_count, bool) or resume_count < 0:
        raise WorkspaceRegistryError("Dolphin operation checkpoint contains an invalid resume count")
    checkpoint = OperationCheckpoint(
        operation_id=operation_id,
        workspace_id=workspace_id,
        target_fingerprint=target_fingerprint,
        pipeline_key=pipeline_key,
        phase=cast(OperationPhase, phase),
        counters=counters,
        pause_reason=cast(OperationPauseReason | None, pause_reason),
        staging_generation_id=staging_generation_id,
        completed_manifest_id=completed_manifest_id,
        checkpointed_at=_parse_registry_timestamp(row[15], label="operation checkpoint timestamp"),
        resume_count=resume_count,
    )
    _validate_checkpoint(checkpoint)
    return checkpoint


def _operation_counters_from_values(values: Sequence[object]) -> OperationCountersSnapshot:
    if len(values) != 7:
        raise WorkspaceRegistryError("Dolphin operation counters are incomplete")
    known = values[0]
    if known is not None and (not isinstance(known, int) or isinstance(known, bool) or known < 0):
        raise WorkspaceRegistryError("Dolphin operation counters are invalid")
    remaining = values[1:]
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in remaining):
        raise WorkspaceRegistryError("Dolphin operation counters are invalid")
    counters = OperationCountersSnapshot(
        known_eligible_files=cast(int | None, known),
        processed_files=cast(int, remaining[0]),
        parsed_files=cast(int, remaining[1]),
        reused_chunks=cast(int, remaining[2]),
        embedding_cache_hits=cast(int, remaining[3]),
        embedding_cache_misses=cast(int, remaining[4]),
        embedded_chunks=cast(int, remaining[5]),
    )
    if counters.known_eligible_files is not None and counters.processed_files > counters.known_eligible_files:
        raise WorkspaceRegistryError("Dolphin operation counters exceed the known eligible file count")
    if counters.parsed_files > counters.processed_files:
        raise WorkspaceRegistryError("Dolphin parsed file count exceeds processed files")
    return counters


def _checkpoint_storage_values(checkpoint: OperationCheckpoint) -> tuple[object, ...]:
    counters = checkpoint.counters
    return (
        checkpoint.operation_id,
        checkpoint.workspace_id,
        checkpoint.target_fingerprint,
        checkpoint.pipeline_key,
        checkpoint.phase,
        checkpoint.staging_generation_id,
        checkpoint.completed_manifest_id,
        counters.known_eligible_files,
        counters.processed_files,
        counters.parsed_files,
        counters.reused_chunks,
        counters.embedding_cache_hits,
        counters.embedding_cache_misses,
        counters.embedded_chunks,
        checkpoint.pause_reason,
        _utc_timestamp(checkpoint.checkpointed_at).isoformat(),
        checkpoint.resume_count,
    )


def _validate_checkpoint(checkpoint: OperationCheckpoint) -> None:
    _validate_bounded_key(checkpoint.operation_id, label="operation ID", maximum=OPERATION_ID_MAX_LENGTH)
    _validate_bounded_key(checkpoint.workspace_id, label="workspace ID", maximum=ENTITY_ID_MAX_LENGTH)
    _validate_bounded_key(
        checkpoint.target_fingerprint,
        label="target fingerprint",
        maximum=_TARGET_FINGERPRINT_MAX_LENGTH,
    )
    _validate_bounded_key(checkpoint.pipeline_key, label="pipeline key", maximum=_PIPELINE_KEY_MAX_LENGTH)
    if checkpoint.phase not in _OPERATION_PHASES:
        raise WorkspaceRegistryError("Dolphin operation checkpoint phase is invalid")
    if checkpoint.pause_reason is not None and checkpoint.pause_reason not in {
        "runtime_absent",
        "credential_missing",
        "disk_pressure",
        "awaiting_approval",
        "shutdown",
    }:
        raise WorkspaceRegistryError("Dolphin operation checkpoint pause reason is invalid")
    for value, label in (
        (checkpoint.staging_generation_id, "staging generation ID"),
        (checkpoint.completed_manifest_id, "completed manifest ID"),
    ):
        if value is not None:
            _validate_bounded_key(value, label=label, maximum=ENTITY_ID_MAX_LENGTH)
    if checkpoint.resume_count < 0:
        raise WorkspaceRegistryError("Dolphin operation checkpoint resume count is invalid")
    _utc_timestamp(checkpoint.checkpointed_at)
    _operation_counters_from_values(
        (
            checkpoint.counters.known_eligible_files,
            checkpoint.counters.processed_files,
            checkpoint.counters.parsed_files,
            checkpoint.counters.reused_chunks,
            checkpoint.counters.embedding_cache_hits,
            checkpoint.counters.embedding_cache_misses,
            checkpoint.counters.embedded_chunks,
        )
    )


def _validate_checkpoint_progress(previous: OperationCheckpoint, replacement: OperationCheckpoint) -> None:
    if (
        previous.operation_id != replacement.operation_id
        or previous.workspace_id != replacement.workspace_id
        or previous.target_fingerprint != replacement.target_fingerprint
        or previous.pipeline_key != replacement.pipeline_key
    ):
        raise WorkspaceRegistryError("Dolphin operation checkpoint identity cannot change")
    if _OPERATION_PHASES.index(replacement.phase) < _OPERATION_PHASES.index(previous.phase):
        raise WorkspaceRegistryError("Dolphin operation checkpoint phase cannot regress")
    prior = previous.counters
    current = replacement.counters
    if prior.known_eligible_files is not None and (
        current.known_eligible_files is None or current.known_eligible_files < prior.known_eligible_files
    ):
        raise WorkspaceRegistryError("Dolphin operation checkpoint counters cannot regress")
    for old_value, new_value in (
        (prior.processed_files, current.processed_files),
        (prior.parsed_files, current.parsed_files),
        (prior.reused_chunks, current.reused_chunks),
        (prior.embedding_cache_hits, current.embedding_cache_hits),
        (prior.embedding_cache_misses, current.embedding_cache_misses),
        (prior.embedded_chunks, current.embedded_chunks),
        (previous.resume_count, replacement.resume_count),
    ):
        if new_value < old_value:
            raise WorkspaceRegistryError("Dolphin operation checkpoint counters cannot regress")


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
    checkpoint_present = len(row) > 9 and row[9] is not None
    phase = None
    counters = None
    pause_reason = None
    pipeline_key = None
    if checkpoint_present:
        phase_text = _bounded_registry_text(row[9], label="operation phase", max_length=32)
        if phase_text not in _OPERATION_PHASES:
            raise WorkspaceRegistryError("Dolphin operation metadata contains an invalid phase")
        phase = cast(OperationPhase, phase_text)
        counters = _operation_counters_from_values(row[10:17])
        pause_text = None if row[17] is None else _bounded_registry_text(row[17], label="pause reason", max_length=32)
        if pause_text is not None and pause_text not in {
            "runtime_absent",
            "credential_missing",
            "disk_pressure",
            "awaiting_approval",
            "shutdown",
        }:
            raise WorkspaceRegistryError("Dolphin operation metadata contains an invalid pause reason")
        pause_reason = cast(OperationPauseReason | None, pause_text)
        pipeline_key = _bounded_registry_text(row[18], label="pipeline key", max_length=_PIPELINE_KEY_MAX_LENGTH)
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
        phase=phase,
        counters=counters,
        pause_reason=pause_reason,
        pipeline_key=pipeline_key,
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
