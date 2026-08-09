"""End-to-end protocol checks for Dolphin's installed Python MCP transport."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from kb.mcp.registry import PUBLIC_MCP_TOOL_NAMES


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stdio_server_discovers_and_calls_lifecycle_reads(tmp_path: Path) -> None:
    environment = dict(os.environ)
    environment["HOME"] = str(tmp_path / "home")
    (tmp_path / "home").mkdir()
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from kb.mcp.server import run_stdio; run_stdio()"],
        cwd=os.getcwd(),
        env=environment,
    )

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            discovery = await session.list_tools()
            status = await session.call_tool("status", {})
            repo_list = await session.call_tool("repo_list", {"cursor": None})
            operation_status = await session.call_tool("operation_status", {"operation_id": "op_unknown"})

    assert tuple(tool.name for tool in discovery.tools) == PUBLIC_MCP_TOOL_NAMES
    assert status.is_error is False
    assert status.structured_content is not None
    assert status.structured_content["credential_variable"] == "DOLPHIN_OPENAI_API_KEY"
    assert status.structured_content["tool_availability"]["repo_list"] == "available"
    assert repo_list.is_error is False
    assert repo_list.structured_content == {"items": [], "next_cursor": None}
    assert operation_status.is_error is True
    assert operation_status.structured_content is not None
    assert operation_status.structured_content["code"] == "OPERATION_MISSING"
