"""Tests for durable, receipt-scoped explicit worktree registrations."""

from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from kb.runtime.storage import macos_storage_layout
from kb.services.repo_add import RepoAddService
from kb.services.workspace_registry import OperationState, WorkspaceOperation, WorkspaceRegistry, WorkspaceRegistryError
from kb.services.worktree import discover_git_worktree


@pytest.mark.asyncio
async def test_register_persists_one_worktree_and_returns_a_one_time_receipt(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registry = WorkspaceRegistry(layout)

    registration = registry.register(await discover_git_worktree(worktree_root))

    assert registration.created is True
    assert registration.workspace_id.startswith("ws_")
    assert registration.repository_id.startswith("repo_")
    assert registration.cleanup_receipt is not None
    assert layout.metadata_db.stat().st_mode & 0o077 == 0
    with sqlite3.connect(layout.metadata_db) as connection:
        stored_hash = connection.execute("SELECT cleanup_receipt_hash FROM workspace_registrations").fetchone()[0]
    assert stored_hash == hashlib.sha256(registration.cleanup_receipt.encode("utf-8")).hexdigest()
    assert registration.cleanup_receipt not in layout.metadata_db.read_text(errors="ignore")


@pytest.mark.asyncio
async def test_register_is_idempotent_and_never_reissues_cleanup_authority(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    worktree = await discover_git_worktree(worktree_root)

    first = registry.register(worktree)
    second = registry.register(worktree)

    assert first.created is True
    assert second.created is False
    assert second.workspace_id == first.workspace_id
    assert second.cleanup_receipt is None


@pytest.mark.asyncio
async def test_initial_index_submission_is_durable_and_idempotent_for_one_head(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    registration = registry.register(await discover_git_worktree(worktree_root))

    first = registry.submit_initial_index(registration)
    second = registry.submit_initial_index(registration)
    loaded = registry.get_operation(first.operation_id)

    assert first.created is True
    assert first.kind == "initial_index"
    assert first.state is OperationState.QUEUED
    assert second.created is False
    assert second.operation_id == first.operation_id
    assert loaded is not None
    assert loaded.operation_id == first.operation_id
    assert loaded.workspace_id == registration.workspace_id


@pytest.mark.asyncio
async def test_initial_index_submission_reuses_a_terminal_operation_for_the_same_head(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    registration = registry.register(await discover_git_worktree(worktree_root))

    first = registry.submit_initial_index(registration)
    registry.set_operation_state(first.operation_id, OperationState.RUNNING, expected_state=OperationState.QUEUED)
    terminal = registry.set_operation_state(
        first.operation_id, OperationState.SUCCEEDED, expected_state=OperationState.RUNNING
    )
    repeated = registry.submit_initial_index(registration)

    assert terminal is not None
    assert terminal.state is OperationState.SUCCEEDED
    assert repeated.created is False
    assert repeated.operation_id == first.operation_id
    assert repeated.state is OperationState.SUCCEEDED


@pytest.mark.asyncio
async def test_terminal_operation_cannot_be_restarted(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    registration = registry.register(await discover_git_worktree(worktree_root))
    operation = registry.submit_initial_index(registration)

    running = registry.set_operation_state(
        operation.operation_id, OperationState.RUNNING, expected_state=OperationState.QUEUED
    )
    succeeded = registry.set_operation_state(
        operation.operation_id,
        OperationState.SUCCEEDED,
        expected_state=OperationState.RUNNING,
    )

    assert running is not None
    assert succeeded is not None
    with pytest.raises(WorkspaceRegistryError, match="not allowed"):
        registry.set_operation_state(
            operation.operation_id, OperationState.RUNNING, expected_state=OperationState.SUCCEEDED
        )


@pytest.mark.asyncio
async def test_competing_state_transitions_allow_only_one_observed_state(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    registration = registry.register(await discover_git_worktree(worktree_root))
    operation = registry.submit_initial_index(registration)

    def transition(state: OperationState) -> WorkspaceOperation | None:
        return registry.set_operation_state(operation.operation_id, state, expected_state=OperationState.QUEUED)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(transition, OperationState.RUNNING),
            executor.submit(transition, OperationState.CANCELLED),
        ]
        results = [future.result() if future.exception() is None else future.exception() for future in futures]

    assert sum(isinstance(result, WorkspaceOperation) for result in results) == 1
    assert sum(isinstance(result, WorkspaceRegistryError) for result in results) == 1
    loaded = registry.get_operation(operation.operation_id)
    assert loaded is not None
    assert loaded.state in {OperationState.RUNNING, OperationState.CANCELLED}


@pytest.mark.asyncio
async def test_initial_index_submission_rejects_a_stale_head_or_forged_identity(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    registration = registry.register(await discover_git_worktree(worktree_root))

    with pytest.raises(WorkspaceRegistryError, match="head does not match"):
        registry.submit_initial_index(replace(registration, head_commit="forged-head"))
    with pytest.raises(WorkspaceRegistryError, match="identity does not match"):
        registry.submit_initial_index(replace(registration, root="/forged/root"))


@pytest.mark.asyncio
async def test_initial_index_submission_rejects_a_snapshot_replaced_by_another_registration(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    initial_worktree = await discover_git_worktree(worktree_root)
    initial_registration = registry.register(initial_worktree)

    registry.register(replace(initial_worktree, head_commit="replacement-head"))

    with pytest.raises(WorkspaceRegistryError, match="head does not match"):
        registry.submit_initial_index(initial_registration)


@pytest.mark.asyncio
async def test_atomic_registration_and_submission_uses_one_discovered_head(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    worktree = await discover_git_worktree(worktree_root)

    registration, operation = registry.register_and_submit_initial_index(worktree)

    assert operation.workspace_id == registration.workspace_id
    assert operation.target_head_commit == worktree.head_commit


@pytest.mark.asyncio
async def test_distinct_repositories_receive_distinct_workspace_and_operation_ids(tmp_path: Path) -> None:
    first_root = _commit_repository(tmp_path / "first-repository")
    second_root = _commit_repository(tmp_path / "second-repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))

    first_registration = registry.register(await discover_git_worktree(first_root))
    second_registration = registry.register(await discover_git_worktree(second_root))
    first_operation = registry.submit_initial_index(first_registration)
    second_operation = registry.submit_initial_index(second_registration)

    assert first_registration.workspace_id != second_registration.workspace_id
    assert first_registration.repository_id != second_registration.repository_id
    assert first_operation.operation_id != second_operation.operation_id


@pytest.mark.asyncio
async def test_new_registry_reads_an_initialized_database_without_a_write_lock(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registration = WorkspaceRegistry(layout).register(await discover_git_worktree(worktree_root))

    # A concurrent writer may hold a RESERVED lock, but a fresh registry should
    # inspect the schema version and perform this read without trying schema DDL.
    lock_connection = sqlite3.connect(layout.metadata_db, timeout=0)
    lock_connection.execute("BEGIN IMMEDIATE")
    try:
        loaded = WorkspaceRegistry(layout).get_operation("missing-operation")
    finally:
        lock_connection.rollback()
        lock_connection.close()

    assert registration.workspace_id.startswith("ws_")
    assert loaded is None


@pytest.mark.asyncio
async def test_sqlite_contention_is_reported_as_a_registry_error(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registry = WorkspaceRegistry(layout)
    registry.register(await discover_git_worktree(worktree_root))

    lock_connection = sqlite3.connect(layout.metadata_db, timeout=0)
    lock_connection.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(WorkspaceRegistryError, match="busy or unavailable"):
            registry.get_operation("missing-operation")
    finally:
        lock_connection.rollback()
        lock_connection.close()


@pytest.mark.asyncio
async def test_repo_add_service_coordinates_registration_and_operation_reuse(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    service = RepoAddService(WorkspaceRegistry(macos_storage_layout(home=home)))

    first = await service.submit(worktree_root)
    second = await service.submit(worktree_root)

    assert first.registration.created is True
    assert first.registration.cleanup_receipt is not None
    assert first.operation.created is True
    assert second.registration.created is False
    assert second.registration.cleanup_receipt is None
    assert second.operation.created is False
    assert second.operation.operation_id == first.operation.operation_id


def _commit_repository(path: Path) -> Path:
    path.mkdir(parents=True)
    import subprocess

    def git(*arguments: str) -> None:
        subprocess.run(["git", "-C", str(path), *arguments], check=True, capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "dolphin-tests@example.invalid")
    git("config", "user.name", "Dolphin Tests")
    (path / "example.py").write_text("print('dolphin')\n")
    git("add", "example.py")
    git("commit", "-qm", "Initial test commit")
    return path
