"""End-to-end protocol checks for Dolphin's installed Python MCP transport."""

from __future__ import annotations

import os
import sys

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from kb.mcp.registry import PUBLIC_MCP_TOOL_NAMES


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stdio_server_discovers_and_calls_status() -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from kb.mcp.server import run_stdio; run_stdio()"],
        cwd=os.getcwd(),
        env=dict(os.environ),
    )

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            discovery = await session.list_tools()
            status = await session.call_tool("status", {})

    assert tuple(tool.name for tool in discovery.tools) == PUBLIC_MCP_TOOL_NAMES
    assert status.is_error is False
    assert status.structured_content is not None
    assert status.structured_content["credential_variable"] == "DOLPHIN_OPENAI_API_KEY"
