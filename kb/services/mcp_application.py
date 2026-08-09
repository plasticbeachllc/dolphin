"""Composition root for MCP-facing Dolphin application services."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from kb.mcp.contracts import OperationStatusInput, RepoListInput, StatusInput
from kb.runtime.storage import macos_storage_layout
from kb.services.lifecycle_read import OperationStatusService, RepoListService
from kb.services.status import StatusService
from kb.services.workspace_registry import WorkspaceRegistry
from kb.services.workspace_resolution import WorkspaceSessionScope


def default_mcp_handlers(
    *,
    session_scope: WorkspaceSessionScope,
    registry: WorkspaceRegistry | None = None,
    runtime_ownership_available: Callable[[], bool] | None = None,
) -> dict[str, Callable[[BaseModel], Awaitable[BaseModel]]]:
    """Build handlers for one caller-owned MCP connection scope."""
    resolved_registry = registry or WorkspaceRegistry(macos_storage_layout())
    status = StatusService(
        registry=resolved_registry,
        session_scope=session_scope,
        runtime_ownership_available=runtime_ownership_available,
    )
    repo_list = RepoListService(resolved_registry)
    operation_status = OperationStatusService(resolved_registry)

    async def handle_status(input_model: BaseModel) -> BaseModel:
        if not isinstance(input_model, StatusInput):
            raise TypeError("status must receive StatusInput")
        return await status(input_model)

    async def handle_repo_list(input_model: BaseModel) -> BaseModel:
        if not isinstance(input_model, RepoListInput):
            raise TypeError("repo_list must receive RepoListInput")
        return await repo_list(input_model)

    async def handle_operation_status(input_model: BaseModel) -> BaseModel:
        if not isinstance(input_model, OperationStatusInput):
            raise TypeError("operation_status must receive OperationStatusInput")
        return await operation_status(input_model)

    return {
        "status": handle_status,
        "repo_list": handle_repo_list,
        "operation_status": handle_operation_status,
    }
