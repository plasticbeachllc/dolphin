"""Composition root for MCP-facing Dolphin application services."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from kb.mcp.contracts import OperationStatusInput, RepoListInput, StatusInput
from kb.runtime.storage import macos_storage_layout
from kb.services.lifecycle_read import OperationStatusService, RepoListService
from kb.services.status import StatusService
from kb.services.workspace_registry import WorkspaceRegistry


def default_mcp_handlers() -> dict[str, Callable[[BaseModel], Awaitable[BaseModel]]]:
    """Return the currently available 0.3.0 application-service handlers."""
    registry = WorkspaceRegistry(macos_storage_layout())
    status = StatusService(registry=registry)
    repo_list = RepoListService(registry)
    operation_status = OperationStatusService(registry)

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
