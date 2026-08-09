"""Atomic SQLite generation visibility and reader-lease tests."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from kb.generation import (
    GenerationConflict,
    GenerationCoordinatorError,
    GenerationReadLeaseUnavailable,
    VerifiedGenerationManifest,
    VerifiedVectorCommit,
)
from kb.runtime.storage import StorageLayout, macos_storage_layout
from kb.services.workspace_registry import OperationLease, OperationState, WorkspaceRegistry
from kb.services.worktree import GitWorktree
from kb.store.generation_coordinator import SQLiteGenerationCoordinator


def test_staging_and_component_readiness_remain_invisible_until_atomic_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, registry, _layout, _worktree, lease, now = _coordinator_with_lease(monkeypatch, tmp_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        created = list(executor.map(lambda _index: coordinator.create_staging(lease, now=now), range(2)))
    generation = created[0]

    assert created[1].generation_id == generation.generation_id
    assert coordinator.current_snapshot(lease.operation.workspace_id) is None

    vector_ready = coordinator.record_vector_ready(
        lease,
        _vector_commit(generation.generation_id, suffix="v1", row_count=11),
        now=now + timedelta(seconds=1),
    )
    assert vector_ready.vector_row_count == 11
    assert coordinator.current_snapshot(lease.operation.workspace_id) is None

    ready = coordinator.mark_ready(
        lease,
        _manifest(generation.generation_id, suffix="v1", vector_row_count=11, item_count=7),
        now=now + timedelta(seconds=2),
    )
    assert ready.state == "ready"
    assert coordinator.current_snapshot(lease.operation.workspace_id) is None

    with ThreadPoolExecutor(max_workers=2) as executor:
        published = list(
            executor.map(
                lambda _index: coordinator.publish(
                    lease,
                    generation.generation_id,
                    expected_previous_generation_id=None,
                    now=now + timedelta(seconds=3),
                ),
                range(2),
            )
        )
    current = coordinator.current_snapshot(lease.operation.workspace_id)

    assert published[0] == published[1]
    assert current == published[0]
    assert current is not None
    assert current.generation_id == generation.generation_id
    assert current.revision == 1
    operation = registry.inspect_operation(lease.operation.operation_id)
    assert operation is not None
    assert operation.phase == "publish"


def test_incomplete_or_mismatched_components_never_publish(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, _registry, _layout, _worktree, lease, now = _coordinator_with_lease(monkeypatch, tmp_path)
    generation = coordinator.create_staging(lease, now=now)

    with pytest.raises(GenerationCoordinatorError, match="vectors are not durably verified"):
        coordinator.mark_ready(
            lease,
            _manifest(generation.generation_id, suffix="v1", vector_row_count=1),
            now=now + timedelta(seconds=1),
        )
    coordinator.record_vector_ready(
        lease,
        _vector_commit(generation.generation_id, suffix="v1", row_count=2),
        now=now + timedelta(seconds=1),
    )
    with pytest.raises(GenerationConflict, match="count does not match"):
        coordinator.mark_ready(
            lease,
            _manifest(generation.generation_id, suffix="v1", vector_row_count=1),
            now=now + timedelta(seconds=2),
        )

    assert coordinator.current_snapshot(lease.operation.workspace_id) is None
    with pytest.raises(GenerationCoordinatorError, match="not ready"):
        coordinator.publish(
            lease,
            generation.generation_id,
            expected_previous_generation_id=None,
            now=now + timedelta(seconds=3),
        )


def test_verified_vector_commit_rejects_any_other_embedding_contract() -> None:
    with pytest.raises(ValidationError):
        VerifiedVectorCommit.model_validate(
            {
                "generation_id": "gen_contract",
                "backend_token": "vector-commit",
                "manifest_digest": "vector-digest",
                "row_count": 1,
                "provider": "openai",
                "model": "text-embedding-3-large",
                "dimensions": 3_072,
                "contract_version": 1,
            }
        )


def test_publication_rejects_a_workspace_target_that_advanced_after_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, registry, _layout, worktree, lease, now = _coordinator_with_lease(monkeypatch, tmp_path)
    generation_id = _ready_generation(coordinator, lease, now, suffix="stale-target")
    advanced_worktree = GitWorktree(
        root=worktree.root,
        common_git_dir=worktree.common_git_dir,
        common_git_dir_identity=worktree.common_git_dir_identity,
        worktree_git_dir=worktree.worktree_git_dir,
        worktree_git_dir_identity=worktree.worktree_git_dir_identity,
        head_commit="c" * 40,
        branch=worktree.branch,
    )
    registry.register_and_submit_initial_index(
        advanced_worktree,
        cleanup_receipt=_cleanup_receipt("generation-coordinator"),
    )

    with pytest.raises(GenerationConflict, match="workspace target changed"):
        coordinator.publish(
            lease,
            generation_id,
            expected_previous_generation_id=None,
            now=now + timedelta(seconds=3),
        )
    assert coordinator.current_snapshot(lease.operation.workspace_id) is None


def test_pointer_swap_is_compare_and_set_and_old_reader_remains_pinned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, registry, _layout, worktree, first_lease, now = _coordinator_with_lease(monkeypatch, tmp_path)
    first_generation = _ready_generation(coordinator, first_lease, now, suffix="first")
    first = coordinator.publish(
        first_lease,
        first_generation,
        expected_previous_generation_id=None,
        now=now + timedelta(seconds=3),
    )
    read_lease = coordinator.acquire_read(
        first.workspace_id,
        now=now + timedelta(seconds=4),
        expires_at=now + timedelta(seconds=14),
    )
    with pytest.raises(GenerationCoordinatorError, match="lease window is invalid"):
        coordinator.acquire_read(
            first.workspace_id,
            now=now + timedelta(seconds=4),
            expires_at=now + timedelta(seconds=65),
        )
    registry.finish_operation(first_lease, OperationState.SUCCEEDED, observed_at=now + timedelta(seconds=4))

    next_worktree = GitWorktree(
        root=worktree.root,
        common_git_dir=worktree.common_git_dir,
        common_git_dir_identity=worktree.common_git_dir_identity,
        worktree_git_dir=worktree.worktree_git_dir,
        worktree_git_dir_identity=worktree.worktree_git_dir_identity,
        head_commit="b" * 40,
        branch=worktree.branch,
    )
    _registration, next_operation = registry.register_and_submit_initial_index(
        next_worktree,
        cleanup_receipt=_cleanup_receipt("generation-coordinator"),
    )
    second_lease = registry.claim_next_operation(
        runtime_id=first_lease.runtime_id,
        process_start_identity="start-worker",
        pipeline_key="generation-pipeline-v1",
        now=now + timedelta(seconds=5),
        expires_at=now + timedelta(seconds=20),
    )
    assert second_lease is not None
    assert second_lease.operation.operation_id == next_operation.operation_id
    second_generation = _ready_generation(coordinator, second_lease, now + timedelta(seconds=5), suffix="second")

    with pytest.raises(GenerationConflict, match="changed before pointer swap"):
        coordinator.publish(
            second_lease,
            second_generation,
            expected_previous_generation_id=None,
            now=now + timedelta(seconds=8),
        )
    assert coordinator.current_snapshot(first.workspace_id) == first

    second = coordinator.publish(
        second_lease,
        second_generation,
        expected_previous_generation_id=first.generation_id,
        now=now + timedelta(seconds=8),
    )

    assert second.revision == 2
    assert coordinator.current_snapshot(first.workspace_id) == second
    assert coordinator.snapshot_for_lease(read_lease.lease_id, now=now + timedelta(seconds=9)) == first
    with pytest.raises(GenerationReadLeaseUnavailable, match="expired"):
        coordinator.snapshot_for_lease(read_lease.lease_id, now=now + timedelta(seconds=14))
    coordinator.release_read(read_lease)
    coordinator.release_read(read_lease)


def test_expired_operation_lease_cannot_change_generation_visibility(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, _registry, _layout, _worktree, lease, now = _coordinator_with_lease(monkeypatch, tmp_path)
    generation = coordinator.create_staging(lease, now=now)

    with pytest.raises(GenerationCoordinatorError, match="unavailable or expired"):
        coordinator.record_vector_ready(
            lease,
            _vector_commit(generation.generation_id, suffix="v1", row_count=1),
            now=lease.expires_at,
        )
    assert coordinator.current_snapshot(lease.operation.workspace_id) is None


def _coordinator_with_lease(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[
    SQLiteGenerationCoordinator,
    WorkspaceRegistry,
    StorageLayout,
    GitWorktree,
    OperationLease,
    datetime,
]:
    root = tmp_path / "repository"
    root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    registry = WorkspaceRegistry(layout)
    monkeypatch.setattr("kb.services.workspace_registry.validate_git_worktree_snapshot", lambda _worktree: None)
    worktree = GitWorktree(
        root=root,
        common_git_dir=root / ".git",
        common_git_dir_identity="common-identity",
        worktree_git_dir=root / ".git",
        worktree_git_dir_identity="worktree-identity",
        head_commit="a" * 40,
        branch="develop",
    )
    _registration, _operation = registry.register_and_submit_initial_index(
        worktree,
        cleanup_receipt=_cleanup_receipt("generation-coordinator"),
    )
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    runtime = registry.register_runtime(
        runtime_id="runtime_generation_worker",
        pid=101,
        process_start_identity="start-worker",
        mode="mcp",
        operation_capable=True,
        pipeline_key="generation-pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=30),
    )
    lease = registry.claim_next_operation(
        runtime_id=runtime.runtime_id,
        process_start_identity=runtime.process_start_identity,
        pipeline_key="generation-pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=15),
    )
    assert lease is not None
    return SQLiteGenerationCoordinator(layout), registry, layout, worktree, lease, now


def _ready_generation(
    coordinator: SQLiteGenerationCoordinator,
    lease: OperationLease,
    now: datetime,
    *,
    suffix: str,
) -> str:
    generation = coordinator.create_staging(lease, now=now)
    coordinator.record_vector_ready(
        lease,
        _vector_commit(generation.generation_id, suffix=suffix, row_count=3),
        now=now + timedelta(seconds=1),
    )
    coordinator.mark_ready(
        lease,
        _manifest(generation.generation_id, suffix=suffix, vector_row_count=3, item_count=2),
        now=now + timedelta(seconds=2),
    )
    return generation.generation_id


def _cleanup_receipt(seed: str) -> str:
    token = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:43]
    return f"dolphin-cleanup-v1_{token}"


def _vector_commit(generation_id: str, *, suffix: str, row_count: int) -> VerifiedVectorCommit:
    return VerifiedVectorCommit(
        generation_id=generation_id,
        backend_token=f"vector-commit-{suffix}",
        manifest_digest=f"vector-digest-{suffix}",
        row_count=row_count,
    )


def _manifest(
    generation_id: str,
    *,
    suffix: str,
    vector_row_count: int,
    item_count: int = 1,
) -> VerifiedGenerationManifest:
    return VerifiedGenerationManifest(
        generation_id=generation_id,
        manifest_id=f"manifest_{suffix}",
        manifest_digest=f"manifest-digest-{suffix}",
        metadata_item_count=item_count,
        keyword_item_count=item_count,
        vector_row_count=vector_row_count,
    )
