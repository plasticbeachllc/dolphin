"""Tests for durable, receipt-scoped explicit worktree registrations."""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from shutil import rmtree

import pytest

from kb.runtime.storage import StorageLayout, macos_storage_layout
from kb.services import workspace_registry as workspace_registry_module
from kb.services.repo_add import RepoAddService
from kb.services.workspace_registry import OperationState, WorkspaceOperation, WorkspaceRegistry, WorkspaceRegistryError
from kb.services.worktree import WorktreeDiscoveryError, discover_git_worktree


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
    worktree = await discover_git_worktree(worktree_root)

    registration, first = registry.register_and_submit_initial_index(worktree)
    _, second = registry.register_and_submit_initial_index(worktree)
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
    worktree = await discover_git_worktree(worktree_root)

    registration, first = registry.register_and_submit_initial_index(worktree)
    registry.set_operation_state(first.operation_id, OperationState.RUNNING, expected_state=OperationState.QUEUED)
    terminal = registry.set_operation_state(
        first.operation_id, OperationState.SUCCEEDED, expected_state=OperationState.RUNNING
    )
    _, repeated = registry.register_and_submit_initial_index(worktree)

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
    _, operation = registry.register_and_submit_initial_index(await discover_git_worktree(worktree_root))

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
    _, operation = registry.register_and_submit_initial_index(await discover_git_worktree(worktree_root))

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
    stale_registration = registry.register(await discover_git_worktree(worktree_root))
    _commit_change(worktree_root)

    current_registration, operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(worktree_root)
    )

    assert current_registration.head_commit != stale_registration.head_commit
    assert operation.target_head_commit == current_registration.head_commit


@pytest.mark.asyncio
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

    first_registration, first_operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(first_root)
    )
    second_registration, second_operation = registry.register_and_submit_initial_index(
        await discover_git_worktree(second_root)
    )

    assert first_registration.workspace_id != second_registration.workspace_id
    assert first_registration.repository_id != second_registration.repository_id
    assert first_operation.operation_id != second_operation.operation_id


@pytest.mark.asyncio
async def test_register_rejects_a_replacement_repository_at_the_same_root(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    registration, operation = registry.register_and_submit_initial_index(await discover_git_worktree(worktree_root))
    rmtree(worktree_root / ".git")
    _initialize_repository(worktree_root)
    _git(worktree_root, "add", "example.py")
    _git(worktree_root, "commit", "-qm", "Replacement repository commit")
    replacement = await discover_git_worktree(worktree_root)

    with pytest.raises(WorkspaceRegistryError, match="different Git repository"):
        registry.register(replacement)

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
        registry.register_and_submit_initial_index(worktree)

    with sqlite3.connect(layout.metadata_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM workspace_registrations").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_v1_migration_backfills_git_identity_and_installs_exact_target_deduplication(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    worktree = await discover_git_worktree(worktree_root)
    _create_v1_registry(
        layout, root=str(worktree.root), common_git_dir=str(worktree.common_git_dir), head=worktree.head_commit
    )

    registration = WorkspaceRegistry(layout).register(worktree)

    assert registration.created is False
    assert registration.repository_id.startswith("repo_")
    with sqlite3.connect(layout.metadata_db) as connection:
        identity = connection.execute(
            "SELECT common_git_dir_identity FROM workspace_registrations WHERE workspace_id = 'ws_v1'"
        ).fetchone()[0]
        operation_count = connection.execute("SELECT COUNT(*) FROM workspace_operations").fetchone()[0]
        indexes = {row[1] for row in connection.execute("PRAGMA index_list('workspace_operations')")}
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert identity == worktree.common_git_dir_identity
    assert operation_count == 1
    assert "workspace_operations_exact_target" in indexes
    assert version == 2


@pytest.mark.asyncio
async def test_v1_migration_prunes_unreachable_workspace_for_clean_reenrollment(tmp_path: Path) -> None:
    worktree_root = _commit_repository(tmp_path / "repository")
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    worktree = await discover_git_worktree(worktree_root)
    _create_v1_registry(
        layout,
        root=str(worktree.root),
        common_git_dir=str(tmp_path / "missing-git-directory"),
        head=worktree.head_commit,
    )

    registration = WorkspaceRegistry(layout).register(worktree)

    assert registration.created is True


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
    _initialize_repository(path)
    (path / "example.py").write_text("print('dolphin')\n")
    _git(path, "add", "example.py")
    _git(path, "commit", "-qm", "Initial test commit")
    return path


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


def _create_v1_registry(layout: StorageLayout, *, root: str, common_git_dir: str, head: str) -> None:
    metadata_db = layout.metadata_db
    layout.ensure_private_metadata_database()
    with sqlite3.connect(metadata_db) as connection:
        connection.executescript(
            """
            CREATE TABLE workspace_registrations (
                workspace_id TEXT PRIMARY KEY,
                repository_id TEXT NOT NULL,
                root TEXT NOT NULL UNIQUE,
                common_git_dir TEXT NOT NULL,
                branch TEXT,
                head_commit TEXT NOT NULL,
                registration_epoch TEXT NOT NULL,
                cleanup_receipt_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            ) STRICT;
            CREATE TABLE workspace_operations (
                operation_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspace_registrations(workspace_id),
                kind TEXT NOT NULL,
                state TEXT NOT NULL,
                target_head_commit TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            ) STRICT;
            CREATE UNIQUE INDEX workspace_operations_active_target
            ON workspace_operations (workspace_id, kind, target_head_commit)
            WHERE state IN ('queued', 'running', 'awaiting_approval', 'paused');
            """
        )
        connection.execute(
            """
            INSERT INTO workspace_registrations VALUES
            ('ws_v1', 'repo_legacy', ?, ?, 'main', ?, 'epoch_v1', 'receipt_hash', 'now', 'now')
            """,
            (root, common_git_dir, head),
        )
        connection.executemany(
            """
            INSERT INTO workspace_operations VALUES (?, 'ws_v1', 'initial_index', ?, ?, 'now', 'now')
            """,
            [("op_v1_queued", "queued", head), ("op_v1_terminal", "succeeded", head)],
        )
        connection.execute("PRAGMA user_version = 1")
