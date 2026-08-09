"""Tests for durable, receipt-scoped explicit worktree registrations."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from kb.runtime.storage import macos_storage_layout
from kb.services.repo_add import RepoAddService
from kb.services.workspace_registry import OperationState, WorkspaceRegistry
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
