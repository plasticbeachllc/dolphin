"""Tests for the thin Python MCP transport adapter."""

from __future__ import annotations

import json

import mcp.types as mcp_types
import pytest
from pydantic import BaseModel

from kb.mcp.contracts import StatusInput
from kb.mcp.registry import TOOL_REGISTRY
from kb.mcp.server import _complete_handlers, _wire_tool, create_adapter
from kb.services.status import StatusService


@pytest.mark.asyncio
async def test_server_discovery_uses_the_frozen_registry() -> None:
    result = await create_adapter().list_tools()

    assert [tool.name for tool in result.tools] == [
        "status",
        "repo_list",
        "repo_add",
        "repo_forget",
        "repo_sync",
        "operation_status",
        "search",
        "open_ref",
    ]
    repo_forget = next(tool for tool in result.tools if tool.name == "repo_forget")
    assert repo_forget.annotations is not None
    assert repo_forget.annotations.destructive_hint is True
    assert repo_forget.annotations.idempotent_hint is True


@pytest.mark.asyncio
async def test_server_validates_before_invoking_a_handler() -> None:
    called = False

    def status_handler(_input: BaseModel) -> dict[str, str]:
        nonlocal called
        called = True
        return {"readiness": "ready"}

    result = await create_adapter({"status": status_handler}).call_tool(
        mcp_types.CallToolRequestParams(name="status", arguments={"unexpected": True})
    )

    assert called is False
    assert result.is_error is True
    assert result.structured_content["code"] == "INVALID_ARGUMENTS"


@pytest.mark.asyncio
async def test_server_returns_structured_success_and_bounded_not_ready_errors() -> None:
    adapter = create_adapter({"status": lambda _input: {"readiness": "ready"}})

    success = await adapter.call_tool(mcp_types.CallToolRequestParams(name="status", arguments={}))
    not_ready = await adapter.call_tool(mcp_types.CallToolRequestParams(name="repo_list", arguments={"cursor": None}))

    assert success.is_error is False
    success_content = success.content[0]
    assert isinstance(success_content, mcp_types.TextContent)
    assert json.loads(success_content.text) == {"readiness": "ready"}
    assert success.structured_content == {"readiness": "ready"}
    assert not_ready.is_error is True
    assert not_ready.structured_content["code"] == "RUNTIME_NOT_READY"
    assert not_ready.structured_content["retryable"] is False


@pytest.mark.asyncio
async def test_server_can_call_the_real_status_application_service(tmp_path) -> None:
    status = StatusService(cwd=tmp_path, environment={})

    async def status_handler(input_model: BaseModel) -> BaseModel:
        assert isinstance(input_model, StatusInput)
        return await status(input_model)

    result = await create_adapter({"status": status_handler}).call_tool(
        mcp_types.CallToolRequestParams(name="status", arguments={})
    )

    assert result.is_error is False
    assert result.structured_content["credential_variable"] == "DOLPHIN_OPENAI_API_KEY"
    assert result.structured_content["current_workspace_resolution"] == "outside_worktree"


def test_server_rejects_unknown_handlers_and_preserves_wire_annotations() -> None:
    with pytest.raises(RuntimeError, match="unknown Dolphin MCP handler"):
        _complete_handlers({"not_a_tool": lambda _input: {}}, ())

    tool = _wire_tool(next(spec for spec in TOOL_REGISTRY if spec.name == "repo_forget"))
    assert tool.annotations is not None
    assert tool.annotations.destructive_hint is True
