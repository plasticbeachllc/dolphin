"""Tests for bounded read-only lifecycle application services."""

from __future__ import annotations

import hashlib
import stat
import subprocess
from pathlib import Path

import pytest

from kb.mcp.contracts import OperationStatusInput, RepoListInput, StatusInput
from kb.mcp.errors import ToolFailure
from kb.runtime.storage import macos_storage_layout
from kb.services.lifecycle_read import OperationStatusService, RepoListService
from kb.services.status import StatusService
from kb.services.workspace_registry import OperationState, WorkspaceRegistry
from kb.services.worktree import discover_git_worktree


@pytest.mark.asyncio
async def test_empty_lifecycle_reads_do_not_create_registry_state(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registry = WorkspaceRegistry(layout)

    repo_list = await RepoListService(registry)(RepoListInput(cursor=None))
    status = await StatusService(cwd=tmp_path, environment={}, registry=registry)(StatusInput())

    assert repo_list.items == []
    assert repo_list.next_cursor is None
    assert status.workspace_counts.registered == 0
    assert status.tool_availability.repo_list == "available"
    assert not layout.metadata_db.exists()


@pytest.mark.asyncio
async def test_status_reports_real_registry_counts_and_exact_current_workspace(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registry = WorkspaceRegistry(layout)
    registration, _operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(worktree_root),
        cleanup_receipt=_cleanup_receipt("status"),
    )

    result = await StatusService(cwd=worktree_root, environment={}, registry=registry)(StatusInput())

    assert result.current_workspace_resolution == "resolved"
    assert result.current_workspace is not None
    assert result.current_workspace.id == registration.workspace_id
    assert result.current_workspace.state == "indexing"
    assert result.workspace_counts.indexing == 1
    assert result.next_actions == []
    assert result.tool_availability.operation_status == "available"
    assert result.tool_availability.repo_add == "unavailable"


@pytest.mark.asyncio
async def test_status_blocks_on_unsafe_storage_without_repairing_it(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    layout.ensure_private_metadata_database()
    layout.metadata_db.chmod(0o644)

    result = await StatusService(cwd=tmp_path, environment={}, registry=WorkspaceRegistry(layout))(StatusInput())

    assert result.readiness == "blocked"
    assert result.current_workspace_resolution == "unavailable"
    assert result.tool_availability.repo_list == "unavailable"
    assert stat.S_IMODE(layout.metadata_db.stat().st_mode) == 0o644


@pytest.mark.asyncio
async def test_repo_list_and_operation_status_return_bounded_durable_projections(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registry = WorkspaceRegistry(layout)
    registration, operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(worktree_root),
        cleanup_receipt=_cleanup_receipt("read-services"),
    )
    layout.vectors.rmdir()

    repo_list = await RepoListService(registry)(RepoListInput(cursor=None))
    operation_status = await OperationStatusService(registry)(OperationStatusInput(operation_id=operation.operation_id))

    assert len(repo_list.items) == 1
    assert repo_list.items[0].workspace.id == registration.workspace_id
    assert repo_list.items[0].workspace.state == "indexing"
    assert repo_list.items[0].repository_boundaries == []
    assert operation_status.operation_id == operation.operation_id
    assert operation_status.state is OperationState.QUEUED
    assert operation_status.attempt == 1
    assert operation_status.pause_reason == "runtime_absent"
    assert operation_status.recommended_poll_after_ms == 1_000
    assert operation_status.counters.processed_files == 0
    assert not layout.vectors.exists()

    registry.set_operation_state(operation.operation_id, OperationState.RUNNING, expected_state=OperationState.QUEUED)
    registry.set_operation_state(
        operation.operation_id, OperationState.SUCCEEDED, expected_state=OperationState.RUNNING
    )
    terminal_status = await OperationStatusService(registry)(OperationStatusInput(operation_id=operation.operation_id))

    assert terminal_status.state is OperationState.SUCCEEDED
    assert terminal_status.terminal_at is not None
    assert terminal_status.status_expires_at is not None
    assert terminal_status.recommended_poll_after_ms is None
    assert terminal_status.pause_reason is None


@pytest.mark.asyncio
async def test_lifecycle_read_errors_are_constant_shape(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))

    with pytest.raises(ToolFailure) as invalid_cursor:
        await RepoListService(registry)(RepoListInput(cursor="not-a-cursor"))
    with pytest.raises(ToolFailure) as missing_operation:
        await OperationStatusService(registry)(OperationStatusInput(operation_id="op_unknown"))

    assert invalid_cursor.value.error.code == "CURSOR_INVALID"
    assert missing_operation.value.error.code == "OPERATION_MISSING"
    assert invalid_cursor.value.error.details["next_action"]["arguments"] == {"cursor": None}


def _commit_repository(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "dolphin@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Dolphin Tests"], check=True)
    (path / "example.py").write_text("print('dolphin')\n")
    subprocess.run(["git", "-C", str(path), "add", "example.py"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "Initial"], check=True)
    return path


def _cleanup_receipt(seed: str) -> str:
    return f"dolphin-cleanup-v1_{hashlib.sha256(seed.encode()).hexdigest()[:43]}"
