"""End-to-end protocol checks for Dolphin's installed Python MCP transport."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from kb.mcp.registry import PUBLIC_MCP_TOOL_NAMES
from kb.runtime.storage import macos_storage_layout
from kb.services import workspace_registry as workspace_registry_module
from kb.services.workspace_registry import OperationState, WorkspaceRegistry
from kb.services.worktree import GitWorktree


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stdio_server_pages_populated_registry_and_expires_terminal_operation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registry = WorkspaceRegistry(layout)
    monkeypatch.setattr(workspace_registry_module, "validate_git_worktree_snapshot", lambda _worktree: None)

    first_registration, operation = registry.register_and_submit_initial_index(
        _fake_worktree(tmp_path / "repositories", 0),
        cleanup_receipt=_cleanup_receipt("0"),
    )
    registry.set_operation_state(operation.operation_id, OperationState.RUNNING, expected_state=OperationState.QUEUED)
    registry.set_operation_state(
        operation.operation_id,
        OperationState.SUCCEEDED,
        expected_state=OperationState.RUNNING,
    )
    for index in range(1, 26):
        registry.register(
            _fake_worktree(tmp_path / "repositories", index),
            cleanup_receipt=_cleanup_receipt(str(index)),
        )

    environment = dict(os.environ)
    environment["HOME"] = str(home)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from kb.mcp.server import run_stdio; run_stdio()"],
        cwd=os.getcwd(),
        env=environment,
    )

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            status = await session.call_tool("status", {})
            first_page = await session.call_tool("repo_list", {"cursor": None})
            assert first_page.structured_content is not None
            second_page = await session.call_tool(
                "repo_list",
                {"cursor": first_page.structured_content["next_cursor"]},
            )
            terminal = await session.call_tool(
                "operation_status",
                {"operation_id": operation.operation_id},
            )

            expired_at = datetime.now(UTC) - timedelta(days=31)
            with sqlite3.connect(layout.metadata_db) as connection:
                connection.execute(
                    "UPDATE workspace_operations SET terminal_at = ? WHERE operation_id = ?",
                    (expired_at.isoformat(), operation.operation_id),
                )
            expired = await session.call_tool(
                "operation_status",
                {"operation_id": operation.operation_id},
            )

    assert status.is_error is False
    assert status.structured_content is not None
    assert status.structured_content["workspace_counts"] == {
        "registered": 25,
        "indexing": 0,
        "ready": 1,
        "failed": 0,
    }
    assert first_page.is_error is False
    assert first_page.structured_content is not None
    assert len(first_page.structured_content["items"]) == 25
    assert first_page.structured_content["next_cursor"] is not None
    assert second_page.is_error is False
    assert second_page.structured_content is not None
    assert len(second_page.structured_content["items"]) == 1
    assert second_page.structured_content["next_cursor"] is None
    assert terminal.is_error is False
    assert terminal.structured_content is not None
    assert terminal.structured_content["state"] == "succeeded"
    assert terminal.structured_content["workspace_id"] == first_registration.workspace_id
    assert terminal.structured_content["terminal_at"] is not None
    assert terminal.structured_content["status_expires_at"] is not None
    assert expired.is_error is True
    assert expired.structured_content is not None
    assert expired.structured_content["code"] == "OPERATION_MISSING"


def _fake_worktree(parent: Path, index: int) -> GitWorktree:
    root = parent / f"repo-{index:03d}"
    root.mkdir(parents=True)
    return GitWorktree(
        root=root,
        common_git_dir=root / ".git",
        common_git_dir_identity=f"identity-{index}",
        worktree_git_dir=root / ".git",
        worktree_git_dir_identity=f"identity-{index}",
        head_commit=f"{index:040x}",
        branch="develop",
    )


def _cleanup_receipt(seed: str) -> str:
    token = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:43]
    return f"dolphin-cleanup-v1_{token}"
