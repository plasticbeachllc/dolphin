"""Tests for durable, receipt-scoped explicit worktree registrations."""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import rmtree

import pytest

from kb.lifecycle_limits import REPO_LIST_CURSOR_MAX_LENGTH
from kb.runtime.storage import macos_storage_layout
from kb.services import workspace_registry as workspace_registry_module
from kb.services.repo_add import RepoAddService
from kb.services.workspace_registry import (
    OperationState,
    RepoListCursorExpired,
    RepoListCursorInvalid,
    WorkspaceOperation,
    WorkspaceRegistry,
    WorkspaceRegistryError,
)
from kb.services.worktree import GitWorktree, WorktreeDiscoveryError, discover_git_worktree


@pytest.mark.asyncio
async def test_register_persists_only_the_caller_cleanup_receipt_hash(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registry = WorkspaceRegistry(layout)

    cleanup_receipt = _cleanup_receipt("first-registration")
    registration = registry.register(
        await discover_git_worktree(worktree_root),
        cleanup_receipt=cleanup_receipt,
    )

    assert registration.created is True
    assert registration.workspace_id.startswith("ws_")
    assert registration.repository_id.startswith("repo_")
    assert registration.cleanup_receipt is not None
    assert layout.metadata_db.stat().st_mode & 0o077 == 0
    with sqlite3.connect(layout.metadata_db) as connection:
        stored = connection.execute(
            """
            SELECT cleanup_receipt_hash, common_git_dir, common_git_dir_identity,
                   worktree_git_dir, worktree_git_dir_identity
            FROM workspace_registrations
            """
        ).fetchone()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert stored is not None
    stored_hash, common_git_dir, common_git_dir_identity, worktree_git_dir, worktree_git_dir_identity = stored
    assert stored_hash == hashlib.sha256(cleanup_receipt.encode("utf-8")).hexdigest()
    assert common_git_dir == str(worktree_root / ".git")
    assert common_git_dir_identity == worktree_git_dir_identity
    assert worktree_git_dir == common_git_dir
    assert version == 5
    assert registration.cleanup_receipt not in layout.metadata_db.read_text(errors="ignore")


@pytest.mark.asyncio
async def test_register_retry_reissues_only_matching_cleanup_authority(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registry = WorkspaceRegistry(layout)
    worktree = await discover_git_worktree(worktree_root)

    cleanup_receipt = _cleanup_receipt("retry-safe-registration")
    first = registry.register(worktree, cleanup_receipt=cleanup_receipt)
    second = WorkspaceRegistry(layout).register(worktree, cleanup_receipt=cleanup_receipt)
    unrelated = WorkspaceRegistry(layout).register(
        worktree,
        cleanup_receipt=_cleanup_receipt("unrelated-caller"),
    )

    assert first.created is True
    assert second.created is False
    assert second.workspace_id == first.workspace_id
    assert second.cleanup_receipt == cleanup_receipt
    assert unrelated.cleanup_receipt is None


@pytest.mark.asyncio
async def test_initial_index_submission_is_durable_and_idempotent_for_one_head(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    worktree = await discover_git_worktree(worktree_root)

    cleanup_receipt = _cleanup_receipt("idempotent-index")
    registration, first = registry.register_and_submit_initial_index(
        worktree,
        cleanup_receipt=cleanup_receipt,
    )
    repeated_registration, second = registry.register_and_submit_initial_index(
        worktree,
        cleanup_receipt=cleanup_receipt,
    )
    loaded = registry.get_operation(first.operation_id)

    assert first.created is True
    assert first.kind == "initial_index"
    assert first.state is OperationState.QUEUED
    assert first.attempt == 1
    assert second.created is False
    assert second.operation_id == first.operation_id
    assert loaded is not None
    assert loaded.operation_id == first.operation_id
    assert loaded.workspace_id == registration.workspace_id
    assert loaded.attempt == 1
    assert repeated_registration.cleanup_receipt == cleanup_receipt


@pytest.mark.asyncio
async def test_initial_index_submission_reuses_a_terminal_operation_for_the_same_head(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    worktree = await discover_git_worktree(worktree_root)

    cleanup_receipt = _cleanup_receipt("succeeded-index")
    registration, first = registry.register_and_submit_initial_index(
        worktree,
        cleanup_receipt=cleanup_receipt,
    )
    registry.set_operation_state(first.operation_id, OperationState.RUNNING, expected_state=OperationState.QUEUED)
    terminal = registry.set_operation_state(
        first.operation_id, OperationState.SUCCEEDED, expected_state=OperationState.RUNNING
    )
    _, repeated = registry.register_and_submit_initial_index(worktree, cleanup_receipt=cleanup_receipt)

    assert terminal is not None
    assert terminal.state is OperationState.SUCCEEDED
    assert repeated.created is False
    assert repeated.operation_id == first.operation_id
    assert repeated.state is OperationState.SUCCEEDED
    assert repeated.attempt == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_state", [OperationState.FAILED, OperationState.CANCELLED])
async def test_failed_or_cancelled_initial_index_is_retried_as_a_new_attempt(
    terminal_state: OperationState,
    tmp_path: Path,
) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    worktree = await discover_git_worktree(worktree_root)

    cleanup_receipt = _cleanup_receipt(f"retry-{terminal_state.value}")
    _, first = registry.register_and_submit_initial_index(worktree, cleanup_receipt=cleanup_receipt)
    if terminal_state is OperationState.FAILED:
        registry.set_operation_state(first.operation_id, OperationState.RUNNING, expected_state=OperationState.QUEUED)
        registry.set_operation_state(first.operation_id, terminal_state, expected_state=OperationState.RUNNING)
    else:
        registry.set_operation_state(first.operation_id, terminal_state, expected_state=OperationState.QUEUED)

    _, retry = registry.register_and_submit_initial_index(worktree, cleanup_receipt=cleanup_receipt)
    _, repeated = registry.register_and_submit_initial_index(worktree, cleanup_receipt=cleanup_receipt)
    original = registry.get_operation(first.operation_id)

    assert original is not None
    assert original.state is terminal_state
    assert original.attempt == 1
    assert retry.created is True
    assert retry.operation_id != first.operation_id
    assert retry.state is OperationState.QUEUED
    assert retry.attempt == 2
    assert repeated.created is False
    assert repeated.operation_id == retry.operation_id
    assert repeated.attempt == 2


@pytest.mark.asyncio
async def test_terminal_operation_cannot_be_restarted(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    _, operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(worktree_root),
        cleanup_receipt=_cleanup_receipt("terminal-operation"),
    )

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
    _, operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(worktree_root),
        cleanup_receipt=_cleanup_receipt("competing-transition"),
    )

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
async def test_atomic_submission_replaces_an_unsubmitted_stale_registration(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    cleanup_receipt = _cleanup_receipt("stale-registration")
    stale_registration = registry.register(
        await discover_git_worktree(worktree_root),
        cleanup_receipt=cleanup_receipt,
    )
    _commit_change(worktree_root)

    current_registration, operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(worktree_root),
        cleanup_receipt=cleanup_receipt,
    )

    assert current_registration.head_commit != stale_registration.head_commit
    assert operation.target_head_commit == current_registration.head_commit


@pytest.mark.asyncio
async def test_atomic_registration_and_submission_uses_one_discovered_head(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    worktree = await discover_git_worktree(worktree_root)

    registration, operation = registry.register_and_submit_initial_index(
        worktree,
        cleanup_receipt=_cleanup_receipt("atomic-snapshot"),
    )

    assert operation.workspace_id == registration.workspace_id
    assert operation.target_head_commit == worktree.head_commit


@pytest.mark.asyncio
async def test_distinct_repositories_receive_distinct_workspace_and_operation_ids(tmp_path: Path) -> None:
    first_root = _commit_repository(tmp_path / "first-repository")
    second_root = _commit_repository(tmp_path / "second-repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))

    first_registration, first_operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(first_root),
        cleanup_receipt=_cleanup_receipt("first-repository"),
    )
    second_registration, second_operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(second_root),
        cleanup_receipt=_cleanup_receipt("second-repository"),
    )

    assert first_registration.workspace_id != second_registration.workspace_id
    assert first_registration.repository_id != second_registration.repository_id
    assert first_operation.operation_id != second_operation.operation_id


@pytest.mark.asyncio
async def test_linked_worktrees_share_repository_identity_but_not_workspace_identity(tmp_path: Path) -> None:
    primary_root = _commit_repository(tmp_path / "primary")
    linked_root = tmp_path / "linked"
    _git(primary_root, "worktree", "add", "-q", "-b", "linked-branch", str(linked_root))
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))

    primary = registry.register(
        await discover_git_worktree(primary_root),
        cleanup_receipt=_cleanup_receipt("primary-worktree"),
    )
    linked = registry.register(
        await discover_git_worktree(linked_root),
        cleanup_receipt=_cleanup_receipt("linked-worktree"),
    )

    assert primary.repository_id == linked.repository_id
    assert primary.workspace_id != linked.workspace_id
    page = registry.list_workspaces(None)
    assert {item.root for item in page.items} == {str(primary_root), str(linked_root)}


@pytest.mark.asyncio
async def test_same_volume_worktree_move_preserves_registration_and_operation_identity(tmp_path: Path) -> None:
    original_root = _commit_repository(tmp_path / "original")
    moved_root = tmp_path / "moved"
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    cleanup_receipt = _cleanup_receipt("moved-worktree")
    first_registration, first_operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(original_root),
        cleanup_receipt=cleanup_receipt,
    )

    original_root.rename(moved_root)
    moved_registration, moved_operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(moved_root),
        cleanup_receipt=cleanup_receipt,
    )

    assert moved_registration.created is False
    assert moved_registration.workspace_id == first_registration.workspace_id
    assert moved_registration.repository_id == first_registration.repository_id
    assert moved_registration.root == str(moved_root)
    assert moved_operation.created is False
    assert moved_operation.operation_id == first_operation.operation_id
    assert registry.read_workspace_snapshot(original_root).current_workspace is None
    current = registry.read_workspace_snapshot(moved_root).current_workspace
    assert current is not None
    assert current.workspace_id == first_registration.workspace_id


@pytest.mark.asyncio
async def test_register_rejects_replaced_concrete_worktree_identity_at_the_same_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    worktree = await discover_git_worktree(worktree_root)
    cleanup_receipt = _cleanup_receipt("concrete-worktree-replacement")
    registry.register(worktree, cleanup_receipt=cleanup_receipt)
    replacement = replace(worktree, worktree_git_dir_identity="replacement-worktree-generation")
    monkeypatch.setattr(workspace_registry_module, "validate_git_worktree_snapshot", lambda _worktree: None)

    with pytest.raises(WorkspaceRegistryError, match="different Git repository or worktree"):
        registry.register(replacement, cleanup_receipt=cleanup_receipt)


@pytest.mark.asyncio
async def test_register_rejects_identity_transfer_while_the_prior_root_still_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    worktree = await discover_git_worktree(worktree_root)
    cleanup_receipt = _cleanup_receipt("existing-prior-root")
    registry.register(worktree, cleanup_receipt=cleanup_receipt)
    claimed_move = replace(worktree, root=tmp_path / "claimed-move")
    monkeypatch.setattr(workspace_registry_module, "validate_git_worktree_snapshot", lambda _worktree: None)

    with pytest.raises(WorkspaceRegistryError, match="already registered at an existing filesystem path"):
        registry.register(claimed_move, cleanup_receipt=cleanup_receipt)


@pytest.mark.asyncio
async def test_register_rejects_a_replacement_repository_at_the_same_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    cleanup_receipt = _cleanup_receipt("replacement-repository")
    registration, operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(worktree_root),
        cleanup_receipt=cleanup_receipt,
    )
    rmtree(worktree_root / ".git")
    _initialize_repository(worktree_root)
    _git(worktree_root, "add", "example.py")
    _git(worktree_root, "commit", "-qm", "Replacement repository commit")
    replacement = replace(
        await discover_git_worktree(worktree_root),
        common_git_dir_identity="replacement-repository-generation",
    )
    monkeypatch.setattr(workspace_registry_module, "validate_git_worktree_snapshot", lambda _worktree: None)

    with pytest.raises(WorkspaceRegistryError, match="different Git repository"):
        registry.register(replacement, cleanup_receipt=cleanup_receipt)

    assert registry.get_operation(operation.operation_id) is not None


@pytest.mark.asyncio
async def test_registration_rolls_back_if_the_worktree_changes_before_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registry = WorkspaceRegistry(layout)
    worktree = await discover_git_worktree(worktree_root)
    validation_calls = 0

    def validate_then_fail(_worktree: object) -> None:
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 2:
            raise WorktreeDiscoveryError("WORKTREE_SNAPSHOT_CHANGED")

    monkeypatch.setattr(workspace_registry_module, "validate_git_worktree_snapshot", validate_then_fail)

    with pytest.raises(WorktreeDiscoveryError, match="WORKTREE_SNAPSHOT_CHANGED"):
        registry.register_and_submit_initial_index(
            worktree,
            cleanup_receipt=_cleanup_receipt("rollback-registration"),
        )

    with sqlite3.connect(layout.metadata_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM workspace_registrations").fetchone()[0] == 0


def test_legacy_prerelease_schema_requires_clean_reenrollment(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    layout.ensure_private_metadata_database()
    with sqlite3.connect(layout.metadata_db) as connection:
        connection.execute("PRAGMA user_version = 4")
    registry = WorkspaceRegistry(layout)

    assert registry.schema_is_current() is False
    with pytest.raises(WorkspaceRegistryError, match="remove it and re-enroll worktrees"):
        registry.get_operation("op_missing")


@pytest.mark.asyncio
async def test_new_registry_reads_an_initialized_database_without_a_write_lock(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registration = WorkspaceRegistry(layout).register(
        await discover_git_worktree(worktree_root),
        cleanup_receipt=_cleanup_receipt("initialized-read"),
    )

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
    registry.register(
        await discover_git_worktree(worktree_root),
        cleanup_receipt=_cleanup_receipt("sqlite-contention"),
    )

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

    cleanup_receipt = _cleanup_receipt("repo-add-service")
    first = await service.submit(worktree_root, cleanup_receipt)
    second = await service.submit(worktree_root, cleanup_receipt)

    assert first.registration.created is True
    assert first.registration.cleanup_receipt is not None
    assert first.operation.created is True
    assert second.registration.created is False
    assert second.registration.cleanup_receipt == cleanup_receipt
    assert second.operation.created is False
    assert second.operation.operation_id == first.operation.operation_id


def test_workspace_snapshot_counts_effective_states_and_resolves_exact_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workspace_registry_module, "validate_git_worktree_snapshot", lambda _worktree: None)
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    worktree = _fake_worktree(tmp_path / "repositories", 1)
    registration, operation = registry.register_and_submit_initial_index(
        worktree,
        cleanup_receipt=_cleanup_receipt("status-counts"),
    )

    indexing = registry.read_workspace_snapshot(worktree.root)
    registry.set_operation_state(operation.operation_id, OperationState.RUNNING, expected_state=OperationState.QUEUED)
    registry.set_operation_state(
        operation.operation_id, OperationState.SUCCEEDED, expected_state=OperationState.RUNNING
    )
    ready = registry.read_workspace_snapshot(worktree.root)

    assert indexing.indexing == 1
    assert indexing.current_workspace is not None
    assert indexing.current_workspace.workspace_id == registration.workspace_id
    assert ready.ready == 1
    assert ready.indexing == 0
    assert ready.current_workspace is not None
    assert ready.current_workspace.state == "ready"


def test_repo_list_cursor_is_bounded_revision_bound_and_integrity_protected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workspace_registry_module, "validate_git_worktree_snapshot", lambda _worktree: None)
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    for index in range(24):
        registry.register(
            _fake_worktree(tmp_path / "repositories", index), cleanup_receipt=_cleanup_receipt(str(index))
        )

    page_of_24 = registry.list_workspaces(None)
    registry.register(_fake_worktree(tmp_path / "repositories", 24), cleanup_receipt=_cleanup_receipt("24"))
    page_of_25 = registry.list_workspaces(None)
    registry.register(_fake_worktree(tmp_path / "repositories", 25), cleanup_receipt=_cleanup_receipt("25"))
    first_page = registry.list_workspaces(None)
    second_page = registry.list_workspaces(first_page.next_cursor)

    assert len(page_of_24.items) == 24
    assert page_of_24.next_cursor is None
    assert len(page_of_25.items) == 25
    assert page_of_25.next_cursor is None
    assert len(first_page.items) == 25
    assert first_page.next_cursor is not None
    assert len(first_page.next_cursor) <= REPO_LIST_CURSOR_MAX_LENGTH
    assert len(second_page.items) == 1
    assert second_page.next_cursor is None
    assert [item.workspace_display_name for item in first_page.items] == [f"repo-{index:03d}" for index in range(25)]

    tampered = first_page.next_cursor[:-1] + ("A" if first_page.next_cursor[-1] != "A" else "B")
    with pytest.raises(RepoListCursorInvalid):
        registry.list_workspaces(tampered)

    other_home = tmp_path / "other-home"
    other_home.mkdir()
    other_registry = WorkspaceRegistry(macos_storage_layout(home=other_home))
    other_registry.register(
        _fake_worktree(tmp_path / "other-repositories", 1),
        cleanup_receipt=_cleanup_receipt("other-store"),
    )
    with pytest.raises(RepoListCursorInvalid):
        other_registry.list_workspaces(first_page.next_cursor)

    registry.register(_fake_worktree(tmp_path / "repositories", 26), cleanup_receipt=_cleanup_receipt("new-member"))
    with pytest.raises(RepoListCursorExpired):
        registry.list_workspaces(first_page.next_cursor)


def test_repo_list_cursor_generation_fails_closed_before_exceeding_its_public_bound() -> None:
    with pytest.raises(WorkspaceRegistryError, match="cursor exceeds"):
        workspace_registry_module._encode_repo_list_cursor(
            store_id="store_1",
            revision=1,
            key=("x" * REPO_LIST_CURSOR_MAX_LENGTH, "repo_1", "workspace", "ws_1"),
            secret=b"x" * 32,
        )


def test_operation_snapshot_expires_terminal_status_without_extending_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workspace_registry_module, "validate_git_worktree_snapshot", lambda _worktree: None)
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    _, operation = registry.register_and_submit_initial_index(
        _fake_worktree(tmp_path / "repositories", 1),
        cleanup_receipt=_cleanup_receipt("operation-expiry"),
    )
    registry.set_operation_state(operation.operation_id, OperationState.RUNNING, expected_state=OperationState.QUEUED)
    registry.set_operation_state(
        operation.operation_id, OperationState.SUCCEEDED, expected_state=OperationState.RUNNING
    )
    snapshot = registry.inspect_operation(operation.operation_id)

    assert snapshot is not None
    assert snapshot.terminal_at is not None
    assert (
        registry.inspect_operation(
            operation.operation_id,
            now=snapshot.terminal_at + timedelta(days=30) - timedelta(microseconds=1),
        )
        is not None
    )
    assert (
        registry.inspect_operation(
            operation.operation_id,
            now=snapshot.terminal_at + timedelta(days=30),
        )
        is None
    )
    assert snapshot.created_at <= datetime.now(UTC)


@pytest.mark.parametrize(
    ("field_index", "value"),
    [
        (0, "o" * 129),
        (4, "a" * 65),
        (6, "2" * 65),
        (7, "2" * 65),
        (8, "2" * 65),
    ],
)
def test_operation_snapshot_boundary_rejects_oversized_metadata(field_index: int, value: str) -> None:
    row: list[object] = [
        "op_valid",
        "ws_valid",
        "initial_index",
        "succeeded",
        "a" * 40,
        1,
        "2026-08-09T12:00:00+00:00",
        "2026-08-09T12:01:00+00:00",
        "2026-08-09T12:01:00+00:00",
    ]
    row[field_index] = value

    with pytest.raises(WorkspaceRegistryError, match="invalid"):
        workspace_registry_module._operation_snapshot_from_row(tuple(row))


def _commit_repository(path: Path) -> Path:
    path.mkdir(parents=True)
    _initialize_repository(path)
    (path / "example.py").write_text("print('dolphin')\n")
    _git(path, "add", "example.py")
    _git(path, "commit", "-qm", "Initial test commit")
    return path


def _cleanup_receipt(seed: str) -> str:
    token = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:43]
    return f"dolphin-cleanup-v1_{token}"


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
        branch="main",
    )


def _commit_change(path: Path) -> None:
    (path / "example.py").write_text("print('dolphin changed')\n")
    _git(path, "add", "example.py")
    _git(path, "commit", "-qm", "Change worktree head")


def _initialize_repository(path: Path) -> None:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "dolphin-tests@example.invalid")
    _git(path, "config", "user.name", "Dolphin Tests")


def _git(path: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(path), *arguments], check=True, capture_output=True, text=True)
