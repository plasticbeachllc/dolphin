"""Read-only lifecycle application services for repository inventory and operations."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Literal

from pydantic import Field

from kb.lifecycle_limits import (
    ENTITY_ID_MAX_LENGTH,
    HEAD_COMMIT_MAX_LENGTH,
    ISO_TIMESTAMP_MAX_LENGTH,
    OPERATION_ID_MAX_LENGTH,
    REPO_LIST_CURSOR_MAX_LENGTH,
    REPO_LIST_PAGE_SIZE,
)
from kb.mcp.contracts import OperationStatusInput, RepoListInput
from kb.mcp.errors import ToolError, ToolFailure, cursor_expired, cursor_invalid, operation_missing, storage_unavailable
from kb.services.lifecycle_models import (
    LifecycleResultModel,
    NextAction,
    RepositoryBoundarySummary,
    RepositoryFamilySummary,
    WorkspaceSummary,
)
from kb.services.workspace_registry import (
    OperationSnapshot,
    OperationState,
    RepoListCursorExpired,
    RepoListCursorInvalid,
    WorkspaceListPage,
    WorkspaceRegistry,
    WorkspaceRegistryError,
    WorkspaceSnapshot,
)

type PauseReason = Literal[
    "runtime_absent",
    "credential_missing",
    "disk_pressure",
    "awaiting_approval",
    "shutdown",
]


class RepoListItem(LifecycleResultModel):
    repository: RepositoryFamilySummary
    workspace: WorkspaceSummary
    repository_boundaries: list[RepositoryBoundarySummary] = Field(max_length=8)


class RepoListResult(LifecycleResultModel):
    items: list[RepoListItem] = Field(max_length=REPO_LIST_PAGE_SIZE)
    next_cursor: str | None = Field(max_length=REPO_LIST_CURSOR_MAX_LENGTH)


class OperationCounters(LifecycleResultModel):
    known_eligible_files: int | None = Field(default=None, ge=0)
    processed_files: int = Field(default=0, ge=0)
    parsed_files: int = Field(default=0, ge=0)
    reused_chunks: int = Field(default=0, ge=0)
    embedding_cache_hits: int = Field(default=0, ge=0)
    embedding_cache_misses: int = Field(default=0, ge=0)
    embedded_chunks: int = Field(default=0, ge=0)


class OperationStatusResult(LifecycleResultModel):
    operation_id: str = Field(min_length=1, max_length=OPERATION_ID_MAX_LENGTH)
    kind: Literal["initial_index", "sync", "recovery"]
    state: OperationState
    attempt: int = Field(ge=1)
    target_head_commit: str = Field(min_length=1, max_length=HEAD_COMMIT_MAX_LENGTH)
    workspace_available: bool
    workspace_id: str | None = Field(default=None, min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    phase: Literal["preflight", "scan", "chunk", "embed", "store", "publish"] | None
    counters: OperationCounters
    reuse: None = None
    pause_reason: PauseReason | None
    failure: ToolError | None
    created_at: str = Field(min_length=1, max_length=ISO_TIMESTAMP_MAX_LENGTH)
    last_progress_at: str | None = Field(default=None, max_length=ISO_TIMESTAMP_MAX_LENGTH)
    terminal_at: str | None = Field(default=None, max_length=ISO_TIMESTAMP_MAX_LENGTH)
    status_expires_at: str | None = Field(default=None, max_length=ISO_TIMESTAMP_MAX_LENGTH)
    recommended_poll_after_ms: int | None = Field(default=None, ge=250, le=5_000)
    next_actions: list[NextAction] = Field(max_length=8)


class RepoListService:
    def __init__(self, registry: WorkspaceRegistry) -> None:
        self._registry = registry

    async def __call__(self, input_model: RepoListInput) -> RepoListResult:
        try:
            if not await asyncio.to_thread(self._registry.database_exists):
                if input_model.cursor is not None:
                    raise ToolFailure(cursor_invalid())
                return RepoListResult(items=[], next_cursor=None)
            if not await asyncio.to_thread(self._registry.schema_is_current):
                raise ToolFailure(storage_unavailable())
            page = await asyncio.to_thread(self._registry.list_workspaces, input_model.cursor)
        except RepoListCursorExpired as exc:
            raise ToolFailure(cursor_expired()) from exc
        except RepoListCursorInvalid as exc:
            raise ToolFailure(cursor_invalid()) from exc
        except WorkspaceRegistryError as exc:
            raise ToolFailure(storage_unavailable()) from exc
        return _repo_list_result(page)


class OperationStatusService:
    def __init__(self, registry: WorkspaceRegistry) -> None:
        self._registry = registry

    async def __call__(self, input_model: OperationStatusInput) -> OperationStatusResult:
        try:
            if not await asyncio.to_thread(self._registry.database_exists):
                raise ToolFailure(operation_missing())
            if not await asyncio.to_thread(self._registry.schema_is_current):
                raise ToolFailure(storage_unavailable())
            operation = await asyncio.to_thread(self._registry.inspect_operation, input_model.operation_id)
        except WorkspaceRegistryError as exc:
            raise ToolFailure(storage_unavailable()) from exc
        if operation is None:
            raise ToolFailure(operation_missing())
        return _operation_status_result(operation)


def workspace_summary(snapshot: WorkspaceSnapshot) -> WorkspaceSummary:
    return WorkspaceSummary(
        id=snapshot.workspace_id,
        repository_id=snapshot.repository_id,
        display_name=snapshot.workspace_display_name,
        root=snapshot.root,
        branch=snapshot.branch,
        head_commit=snapshot.head_commit,
        state=snapshot.state,
    )


def _repo_list_result(page: WorkspaceListPage) -> RepoListResult:
    return RepoListResult(
        items=[
            RepoListItem(
                repository=RepositoryFamilySummary(
                    id=snapshot.repository_id,
                    display_name=snapshot.repository_display_name,
                ),
                workspace=workspace_summary(snapshot),
                repository_boundaries=[],
            )
            for snapshot in page.items
        ],
        next_cursor=page.next_cursor,
    )


def _operation_status_result(operation: OperationSnapshot) -> OperationStatusResult:
    terminal = operation.state in {OperationState.SUCCEEDED, OperationState.FAILED, OperationState.CANCELLED}
    pause_reason = _pause_reason(operation.state)
    failure = None
    if operation.state is OperationState.FAILED:
        failure = ToolError(
            code="OPERATION_FAILED",
            message="Dolphin could not complete this operation.",
            retryable=False,
        )
    terminal_at = operation.terminal_at.isoformat() if operation.terminal_at is not None else None
    status_expires_at = (
        (operation.terminal_at + timedelta(days=30)).isoformat() if operation.terminal_at is not None else None
    )
    return OperationStatusResult(
        operation_id=operation.operation_id,
        kind=operation.kind,
        state=operation.state,
        attempt=operation.attempt,
        target_head_commit=operation.target_head_commit,
        workspace_available=operation.workspace_id is not None,
        workspace_id=operation.workspace_id,
        phase=None,
        counters=OperationCounters(),
        pause_reason=pause_reason,
        failure=failure,
        created_at=operation.created_at.isoformat(),
        last_progress_at=operation.updated_at.isoformat(),
        terminal_at=terminal_at,
        status_expires_at=status_expires_at,
        recommended_poll_after_ms=None if terminal else 1_000,
        next_actions=(
            [
                NextAction(
                    action="inspect_status",
                    reason="Check Dolphin's current runtime and workspace guidance.",
                    tool="status",
                    arguments={},
                )
            ]
            if operation.state is OperationState.FAILED
            else []
        ),
    )


def _pause_reason(state: OperationState) -> PauseReason | None:
    if state is OperationState.QUEUED:
        return "runtime_absent"
    if state is OperationState.AWAITING_APPROVAL:
        return "awaiting_approval"
    if state is OperationState.PAUSED:
        return "shutdown"
    return None
