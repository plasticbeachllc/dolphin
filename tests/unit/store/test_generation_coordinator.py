"""Atomic SQLite generation visibility and reader-lease tests."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from kb.artifacts import identify_embedding_input
from kb.generation import (
    GenerationConflict,
    GenerationCoordinatorError,
    GenerationReadLeaseUnavailable,
    StagingGeneration,
    VerifiedGenerationManifest,
    VerifiedVectorCommit,
)
from kb.generation_content import StagedChunkMembership
from kb.runtime.storage import StorageLayout, macos_storage_layout
from kb.services.workspace_registry import OperationLease, OperationState, WorkspaceRegistry
from kb.services.worktree import GitWorktree
from kb.store.chunk_artifacts import ChunkArtifactStore
from kb.store.generation_content import SQLiteGenerationContentStore
from kb.store.generation_coordinator import SQLiteGenerationCoordinator


def test_staging_and_component_readiness_remain_invisible_until_atomic_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, registry, layout, _worktree, lease, clock = _coordinator_with_lease(monkeypatch, tmp_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        created = list(executor.map(lambda _index: coordinator.create_staging(lease), range(2)))
    generation = created[0]

    assert created[1].generation_id == generation.generation_id
    assert coordinator.current_snapshot(lease.operation.workspace_id) is None

    clock.advance(seconds=1)
    vector_ready = coordinator.record_vector_ready(
        lease,
        _vector_commit(generation.generation_id, suffix="v1", row_count=11),
    )
    assert vector_ready.vector_row_count == 11
    assert coordinator.current_snapshot(lease.operation.workspace_id) is None

    manifest = _stage_content(layout, generation, lease, clock, suffix="v1", count=11)
    clock.advance(seconds=1)
    ready = coordinator.mark_ready(
        lease,
        manifest,
    )
    assert ready.state == "ready"
    assert coordinator.current_snapshot(lease.operation.workspace_id) is None

    clock.advance(seconds=1)
    with ThreadPoolExecutor(max_workers=2) as executor:
        published = list(
            executor.map(
                lambda _index: coordinator.publish(
                    lease,
                    generation.generation_id,
                    expected_previous_generation_id=None,
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
    assert (
        coordinator.publish(
            lease,
            generation.generation_id,
            expected_previous_generation_id=None,
        )
        == current
    )
    with pytest.raises(GenerationConflict, match="different predecessor"):
        coordinator.publish(
            lease,
            generation.generation_id,
            expected_previous_generation_id="gen_unrelated",
        )
    operation = registry.inspect_operation(lease.operation.operation_id)
    assert operation is not None
    assert operation.phase == "publish"


def test_incomplete_or_mismatched_components_never_publish(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, _registry, layout, _worktree, lease, clock = _coordinator_with_lease(monkeypatch, tmp_path)
    generation = coordinator.create_staging(lease)
    manifest = _stage_content(layout, generation, lease, clock, suffix="incomplete", count=1)

    with pytest.raises(GenerationCoordinatorError, match="vectors are not durably verified"):
        coordinator.mark_ready(lease, manifest)
    coordinator.record_vector_ready(
        lease,
        _vector_commit(generation.generation_id, suffix="v1", row_count=2),
    )
    with pytest.raises(GenerationConflict, match="count does not match"):
        coordinator.mark_ready(lease, manifest)

    assert coordinator.current_snapshot(lease.operation.workspace_id) is None
    with pytest.raises(GenerationCoordinatorError, match="not ready"):
        coordinator.publish(
            lease,
            generation.generation_id,
            expected_previous_generation_id=None,
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
    coordinator, registry, layout, worktree, lease, clock = _coordinator_with_lease(monkeypatch, tmp_path)
    generation_id = _ready_generation(coordinator, layout, lease, clock, suffix="stale-target")
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

    clock.advance(seconds=1)
    with pytest.raises(GenerationConflict, match="workspace target changed"):
        coordinator.publish(
            lease,
            generation_id,
            expected_previous_generation_id=None,
        )
    assert coordinator.current_snapshot(lease.operation.workspace_id) is None


def test_pointer_swap_is_compare_and_set_and_old_reader_remains_pinned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, registry, layout, worktree, first_lease, clock = _coordinator_with_lease(monkeypatch, tmp_path)
    first_generation = _ready_generation(coordinator, layout, first_lease, clock, suffix="first")
    clock.advance(seconds=1)
    first = coordinator.publish(
        first_lease,
        first_generation,
        expected_previous_generation_id=None,
    )
    clock.advance(seconds=1)
    read_lease = coordinator.acquire_read(
        first.workspace_id,
        lease_duration=timedelta(seconds=10),
    )
    with pytest.raises(GenerationCoordinatorError, match="lease window is invalid"):
        coordinator.acquire_read(
            first.workspace_id,
            lease_duration=timedelta(seconds=61),
        )
    registry.finish_operation(first_lease, OperationState.SUCCEEDED, observed_at=clock.current)

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
        now=clock.current + timedelta(seconds=1),
        expires_at=clock.current + timedelta(seconds=16),
    )
    assert second_lease is not None
    assert second_lease.operation.operation_id == next_operation.operation_id
    clock.advance(seconds=1)
    second_generation = _ready_generation(coordinator, layout, second_lease, clock, suffix="second")

    clock.advance(seconds=1)
    with pytest.raises(GenerationConflict, match="changed before pointer swap"):
        coordinator.publish(
            second_lease,
            second_generation,
            expected_previous_generation_id=None,
        )
    assert coordinator.current_snapshot(first.workspace_id) == first

    second = coordinator.publish(
        second_lease,
        second_generation,
        expected_previous_generation_id=first.generation_id,
    )

    assert second.revision == 2
    assert coordinator.current_snapshot(first.workspace_id) == second
    assert (
        coordinator.publish(
            second_lease,
            second_generation,
            expected_previous_generation_id=first.generation_id,
        )
        == second
    )
    with pytest.raises(GenerationConflict, match="different predecessor"):
        coordinator.publish(
            second_lease,
            second_generation,
            expected_previous_generation_id=None,
        )
    assert coordinator.snapshot_for_lease(read_lease.lease_id) == first
    clock.current = read_lease.expires_at
    with pytest.raises(GenerationReadLeaseUnavailable, match="expired"):
        coordinator.snapshot_for_lease(read_lease.lease_id)
    coordinator.release_read(read_lease)
    coordinator.release_read(read_lease)


def test_expired_operation_lease_cannot_change_generation_visibility(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, _registry, _layout, _worktree, lease, clock = _coordinator_with_lease(monkeypatch, tmp_path)
    generation = coordinator.create_staging(lease)

    clock.current = lease.expires_at
    with pytest.raises(GenerationCoordinatorError, match="unavailable or expired"):
        coordinator.record_vector_ready(
            lease,
            _vector_commit(generation.generation_id, suffix="v1", row_count=1),
        )
    assert coordinator.current_snapshot(lease.operation.workspace_id) is None


def test_acquiring_a_reader_prunes_abandoned_expired_reader_leases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, _registry, layout, _worktree, lease, clock = _coordinator_with_lease(monkeypatch, tmp_path)
    generation_id = _ready_generation(coordinator, layout, lease, clock, suffix="reader-prune")
    clock.advance(seconds=1)
    snapshot = coordinator.publish(
        lease,
        generation_id,
        expected_previous_generation_id=None,
    )
    abandoned = coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=2))
    clock.current = abandoned.expires_at

    replacement = coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=2))

    with sqlite3.connect(layout.metadata_db) as connection:
        lease_ids = {str(row[0]) for row in connection.execute("SELECT lease_id FROM generation_reader_leases")}
    assert abandoned.lease_id not in lease_ids
    assert replacement.lease_id in lease_ids


def test_writer_acquisition_retries_brief_sqlite_contention(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, _registry, layout, _worktree, lease, _clock = _coordinator_with_lease(monkeypatch, tmp_path)
    lock_connection = sqlite3.connect(layout.metadata_db, timeout=0, isolation_level=None, check_same_thread=False)
    lock_connection.execute("BEGIN IMMEDIATE")

    def release_lock() -> None:
        time.sleep(1.2)
        lock_connection.rollback()

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            release = executor.submit(release_lock)
            generation = coordinator.create_staging(lease)
            release.result()
    finally:
        lock_connection.close()

    assert generation.operation_id == lease.operation.operation_id


def test_writer_acquisition_stops_at_its_bounded_contention_deadline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, _registry, layout, _worktree, lease, _clock = _coordinator_with_lease(monkeypatch, tmp_path)
    lock_connection = sqlite3.connect(layout.metadata_db, timeout=0, isolation_level=None)
    lock_connection.execute("BEGIN IMMEDIATE")
    started = time.monotonic()
    try:
        with pytest.raises(GenerationCoordinatorError, match="busy or unavailable"):
            coordinator.create_staging(lease)
    finally:
        elapsed = time.monotonic() - started
        lock_connection.rollback()
        lock_connection.close()

    assert 2.5 <= elapsed < 3.5


def test_database_rejects_impossible_generation_and_reader_lease_states(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator, registry, layout, worktree, lease, clock = _coordinator_with_lease(monkeypatch, tmp_path)
    generation = coordinator.create_staging(lease)
    with sqlite3.connect(layout.metadata_db) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE generations
                SET manifest_id = 'invalid_manifest', manifest_digest = 'invalid_digest',
                    metadata_item_count = 1, keyword_item_count = 1, ready_at = ?
                WHERE generation_id = ?
                """,
                (clock.current.isoformat(), generation.generation_id),
            )
        connection.rollback()

    generation_id = _ready_generation(coordinator, layout, lease, clock, suffix="database-invariants")
    clock.advance(seconds=1)
    snapshot = coordinator.publish(
        lease,
        generation_id,
        expected_previous_generation_id=None,
    )
    other_root = tmp_path / "other-repository"
    other_root.mkdir()
    other_registration, _other_operation = registry.register_and_submit_initial_index(
        GitWorktree(
            root=other_root,
            common_git_dir=other_root / ".git",
            common_git_dir_identity="other-common-identity",
            worktree_git_dir=other_root / ".git",
            worktree_git_dir_identity="other-worktree-identity",
            head_commit="d" * 40,
            branch=worktree.branch,
        ),
        cleanup_receipt=_cleanup_receipt("other-generation-coordinator"),
    )
    acquired_at = clock.current.isoformat()
    with sqlite3.connect(layout.metadata_db) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO generation_reader_leases (
                    lease_id, workspace_id, generation_id, publication_id, acquired_at, expires_at
                ) VALUES ('read_invalid', ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.workspace_id,
                    snapshot.generation_id,
                    snapshot.publication_id,
                    acquired_at,
                    acquired_at,
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO generation_reader_leases (
                    lease_id, workspace_id, generation_id, publication_id, acquired_at, expires_at
                ) VALUES ('read_wrong_workspace', ?, ?, ?, ?, ?)
                """,
                (
                    other_registration.workspace_id,
                    snapshot.generation_id,
                    snapshot.publication_id,
                    acquired_at,
                    (clock.current + timedelta(seconds=1)).isoformat(),
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE workspace_publications SET workspace_id = ? WHERE workspace_id = ?",
                (other_registration.workspace_id, snapshot.workspace_id),
            )


def _coordinator_with_lease(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[
    SQLiteGenerationCoordinator,
    WorkspaceRegistry,
    StorageLayout,
    GitWorktree,
    OperationLease,
    _TestClock,
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
    clock = _TestClock(now)
    return SQLiteGenerationCoordinator(layout, clock=clock), registry, layout, worktree, lease, clock


def _ready_generation(
    coordinator: SQLiteGenerationCoordinator,
    layout: StorageLayout,
    lease: OperationLease,
    clock: _TestClock,
    *,
    suffix: str,
) -> str:
    generation = coordinator.create_staging(lease)
    clock.advance(seconds=1)
    coordinator.record_vector_ready(
        lease,
        _vector_commit(generation.generation_id, suffix=suffix, row_count=3),
    )
    manifest = _stage_content(layout, generation, lease, clock, suffix=suffix, count=3)
    clock.advance(seconds=1)
    coordinator.mark_ready(lease, manifest)
    return generation.generation_id


def _cleanup_receipt(seed: str) -> str:
    token = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:43]
    return f"dolphin-cleanup-v1_{token}"


@dataclass
class _TestClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def _vector_commit(generation_id: str, *, suffix: str, row_count: int) -> VerifiedVectorCommit:
    return VerifiedVectorCommit(
        generation_id=generation_id,
        backend_token=f"vector-commit-{suffix}",
        manifest_digest=f"vector-digest-{suffix}",
        row_count=row_count,
    )


def _stage_content(
    layout: StorageLayout,
    generation: StagingGeneration,
    lease: OperationLease,
    clock: _TestClock,
    *,
    suffix: str,
    count: int,
) -> VerifiedGenerationManifest:
    artifacts = ChunkArtifactStore(layout)
    memberships = []
    for index in range(count):
        text = f"{suffix} exact chunk {index}\n"
        artifact = artifacts.put_exact_text(text)
        memberships.append(
            StagedChunkMembership(
                chunk_instance_id=f"chunk_{suffix}_{index}",
                artifact=artifact,
                relative_path=f"src/{suffix}-{index}.py",
                source_file_fingerprint=hashlib.sha256(f"{suffix}:{index}".encode()).hexdigest(),
                start_line=index + 1,
                end_line=index + 1,
                language="python",
                chunker_key="python-tree-sitter-v1",
                embedding_cache_key=identify_embedding_input(text).cache_key,
            )
        )
    return SQLiteGenerationContentStore(layout, artifacts, clock=clock).stage_manifest(
        lease,
        generation,
        memberships,
    )
