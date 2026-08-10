"""Generation-scoped chunk membership and authorized materialization tests."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

import kb.store.generation_content as generation_content_implementation
from kb.artifacts import ArtifactCorrupt, ChunkTextArtifact, identify_embedding_input
from kb.generation import GenerationCoordinatorError, PublishedSnapshot, StagingGeneration, VerifiedVectorCommit
from kb.generation_content import (
    GenerationContentConflict,
    GenerationContentError,
    PublishedChunkUnavailable,
    StagedChunkMembership,
    identify_chunk_membership,
)
from kb.runtime.storage import StorageLayout, macos_storage_layout
from kb.services.workspace_registry import OperationLease, OperationState, WorkspaceRegistry
from kb.services.worktree import GitWorktree
from kb.store.chunk_artifacts import ChunkArtifactStore
from kb.store.generation_content import SQLiteGenerationContentStore
from kb.store.generation_coordinator import SQLiteGenerationCoordinator
from tests.vector_fakes import AcceptingVectorCommitVerifier


def test_staged_content_is_invisible_until_publication_then_materializes_exact_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="visible", text="exact published text\r\nλ\n")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])

    assert context.coordinator.current_snapshot(context.lease.operation.workspace_id) is None
    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, row_count=1),
    )
    context.coordinator.mark_ready(context.lease, manifest)
    assert context.coordinator.current_snapshot(context.lease.operation.workspace_id) is None

    snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    read_lease_id = _read_lease_id(context, snapshot)

    materialized = context.content.materialize_published_chunk(read_lease_id, membership.chunk_instance_id)

    assert materialized == "exact published text\r\nλ\n"


def test_manifest_staging_is_idempotent_but_rejects_different_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="idempotent", text="same immutable text")

    first = context.content.stage_manifest(context.lease, context.generation, [membership])
    repeated = context.content.stage_manifest(context.lease, context.generation, [membership])
    changed = membership.model_copy(update={"relative_path": "src/changed.py"})

    assert repeated == first
    assert first.artifact_count == 1
    assert first.metadata_item_count == 1
    with pytest.raises(GenerationContentConflict, match="different chunk content"):
        context.content.stage_manifest(context.lease, context.generation, [changed])


def test_manifest_deduplicates_shared_artifacts_without_collapsing_membership(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    first = _membership(context.artifacts, suffix="shared-first", text="shared exact bytes")
    second = first.model_copy(
        update={
            "chunk_instance_id": "chunk_shared_second",
            "relative_path": "src/second.py",
            "source_file_fingerprint": "2" * 64,
        }
    )

    manifest = context.content.stage_manifest(context.lease, context.generation, [second, first])

    assert manifest.artifact_count == 1
    assert manifest.metadata_item_count == 2
    assert manifest.artifact_utf8_bytes == len(b"shared exact bytes")


def test_same_chunk_instance_id_can_be_staged_in_later_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="stable", text="stable chunk identity")
    first_manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    context.registry.finish_operation(
        context.lease,
        OperationState.FAILED,
        observed_at=context.generation.created_at,
    )

    _registration, retry = context.registry.register_and_submit_initial_index(
        context.worktree,
        cleanup_receipt=_cleanup_receipt("generation-content"),
    )
    retry_now = context.generation.created_at + timedelta(seconds=1)
    retry_lease = context.registry.claim_next_operation(
        runtime_id=context.lease.runtime_id,
        process_start_identity="start-generation-content",
        pipeline_key="generation-pipeline-v1",
        now=retry_now,
        expires_at=retry_now + timedelta(seconds=15),
    )
    assert retry_lease is not None
    assert retry_lease.operation.operation_id == retry.operation_id
    retry_coordinator = SQLiteGenerationCoordinator(
        context.layout,
        vectors=AcceptingVectorCommitVerifier(),
        clock=lambda: retry_now,
    )
    retry_generation = retry_coordinator.create_staging(retry_lease)
    retry_content = SQLiteGenerationContentStore(context.layout, context.artifacts, clock=lambda: retry_now)

    second_manifest = retry_content.stage_manifest(retry_lease, retry_generation, [membership])

    assert second_manifest.generation_id != first_manifest.generation_id
    with sqlite3.connect(context.layout.metadata_db) as connection:
        rows = connection.execute(
            """
            SELECT generation_id
            FROM generation_chunk_memberships
            WHERE chunk_instance_id = ?
            ORDER BY generation_id
            """,
            (membership.chunk_instance_id,),
        ).fetchall()
    assert rows == sorted([(first_manifest.generation_id,), (second_manifest.generation_id,)])


def test_readiness_rejects_unpersisted_or_incomplete_membership(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="binding", text="bound text")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, row_count=1),
    )
    unpersisted = manifest.model_copy(update={"manifest_digest": "f" * 64})

    with pytest.raises(GenerationCoordinatorError, match="unavailable or incompatible"):
        context.coordinator.mark_ready(context.lease, unpersisted)

    with sqlite3.connect(context.layout.metadata_db) as connection:
        connection.execute(
            "DELETE FROM generation_chunk_memberships WHERE chunk_instance_id = ?",
            (membership.chunk_instance_id,),
        )
    with pytest.raises(ArtifactCorrupt, match="artifact set does not match"):
        context.coordinator.mark_ready(context.lease, manifest)


def test_readiness_reverifies_every_manifest_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="ready-corrupt", text="ready only with verified bytes")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, row_count=1),
    )
    _artifact_path(context, membership).write_bytes(b"corrupt before readiness")

    with pytest.raises(ArtifactCorrupt):
        context.coordinator.mark_ready(context.lease, manifest)


def test_manifest_staging_requires_the_exact_live_operation_lease(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="lease", text="lease-authorized text")
    wrong_lease = replace(context.lease, lease_id="lease_unrelated")
    expired_store = SQLiteGenerationContentStore(
        context.layout,
        context.artifacts,
        clock=lambda: context.lease.expires_at,
    )
    clock_values = iter((context.generation.created_at, context.lease.expires_at))
    expires_during_verification = SQLiteGenerationContentStore(
        context.layout,
        context.artifacts,
        clock=lambda: next(clock_values),
    )

    with pytest.raises(GenerationContentError, match="lease is unavailable or expired"):
        context.content.stage_manifest(wrong_lease, context.generation, [membership])
    with pytest.raises(GenerationContentError, match="lease is unavailable or expired"):
        expired_store.stage_manifest(context.lease, context.generation, [membership])
    with pytest.raises(GenerationContentError, match="lease is unavailable or expired"):
        expires_during_verification.stage_manifest(context.lease, context.generation, [membership])


def test_readiness_and_publication_recompute_persisted_membership_digests(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="recompute", text="recompute manifest")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, row_count=1),
    )
    with sqlite3.connect(context.layout.metadata_db) as connection:
        connection.execute(
            "UPDATE generation_chunk_memberships SET relative_path = 'src/tampered.py' WHERE chunk_instance_id = ?",
            (membership.chunk_instance_id,),
        )
    with pytest.raises(GenerationCoordinatorError, match="membership digest is invalid"):
        context.coordinator.mark_ready(context.lease, manifest)

    with sqlite3.connect(context.layout.metadata_db) as connection:
        connection.execute(
            "UPDATE generation_chunk_memberships SET relative_path = ? WHERE chunk_instance_id = ?",
            (membership.relative_path, membership.chunk_instance_id),
        )
    context.coordinator.mark_ready(context.lease, manifest)
    with sqlite3.connect(context.layout.metadata_db) as connection:
        connection.execute(
            "UPDATE generation_chunk_memberships SET language = 'rust' WHERE chunk_instance_id = ?",
            (membership.chunk_instance_id,),
        )
    with pytest.raises(GenerationCoordinatorError, match="membership digest is invalid"):
        context.coordinator.mark_ready(context.lease, manifest)
    with pytest.raises(GenerationCoordinatorError, match="membership digest is invalid"):
        context.coordinator.publish(
            context.lease,
            context.generation.generation_id,
            expected_previous_generation_id=None,
        )


def test_materialization_requires_a_live_reader_lease_and_resolves_its_snapshot_server_side(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership, snapshot = _publish_one(context, suffix="scope", text="scoped text")
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    assert read_lease.snapshot == snapshot

    with pytest.raises(PublishedChunkUnavailable, match="read lease is unavailable or expired"):
        context.content.materialize_published_chunk("read_unrelated", membership.chunk_instance_id)
    with pytest.raises(PublishedChunkUnavailable, match="membership is unavailable"):
        context.content.materialize_published_chunk(read_lease.lease_id, "chunk_unknown")

    expired = SQLiteGenerationContentStore(
        context.layout,
        context.artifacts,
        clock=lambda: read_lease.expires_at,
    )
    with pytest.raises(PublishedChunkUnavailable, match="read lease is unavailable or expired"):
        expired.materialize_published_chunk(read_lease.lease_id, membership.chunk_instance_id)

    context.coordinator.release_read(read_lease)
    with pytest.raises(PublishedChunkUnavailable, match="read lease is unavailable or expired"):
        context.content.materialize_published_chunk(read_lease.lease_id, membership.chunk_instance_id)


def test_validated_revision_keeps_large_generation_reads_bounded_and_fails_closed_on_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    first = _membership(context.artifacts, suffix="bounded-000", text="shared bounded chunk")
    memberships = tuple(
        first.model_copy(
            update={
                "chunk_instance_id": f"chunk_bounded_{index:03d}",
                "relative_path": f"src/bounded-{index:03d}.py",
                "source_file_fingerprint": hashlib.sha256(f"bounded:{index}".encode()).hexdigest(),
            }
        )
        for index in range(256)
    )
    last = memberships[-1]
    manifest = context.content.stage_manifest(context.lease, context.generation, memberships)
    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, row_count=len(memberships)),
    )
    context.coordinator.mark_ready(context.lease, manifest)
    snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    read_lease_id = _read_lease_id(context, snapshot)
    original_read = context.artifacts.read_verified_artifact
    artifact_reads = 0

    def count_artifact_read(artifact_id: str) -> tuple[str, ChunkTextArtifact]:
        nonlocal artifact_reads
        artifact_reads += 1
        return original_read(artifact_id)

    def unexpected_full_manifest_rebuild(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("materialization rebuilt the complete generation manifest")

    monkeypatch.setattr(
        generation_content_implementation,
        "identify_generation_content_manifest",
        unexpected_full_manifest_rebuild,
    )
    monkeypatch.setattr(context.artifacts, "read_verified_artifact", count_artifact_read)

    assert (
        context.content.materialize_published_chunk(read_lease_id, memberships[0].chunk_instance_id)
        == "shared bounded chunk"
    )
    assert context.content.materialize_published_chunk(read_lease_id, last.chunk_instance_id) == "shared bounded chunk"
    assert artifact_reads == 2

    changed = last.model_copy(update={"relative_path": "src/bounded-corrupt.py"})
    changed_digest = identify_chunk_membership(snapshot.generation_id, changed)
    with sqlite3.connect(context.layout.metadata_db) as connection:
        before = connection.execute(
            """
            SELECT content_revision, validated_content_revision
            FROM generation_content_manifests
            WHERE generation_id = ?
            """,
            (snapshot.generation_id,),
        ).fetchone()
        connection.execute(
            """
            UPDATE generation_chunk_memberships
            SET relative_path = ?, membership_digest = ?
            WHERE generation_id = ? AND chunk_instance_id = ?
            """,
            (changed.relative_path, changed_digest, snapshot.generation_id, last.chunk_instance_id),
        )
        after = connection.execute(
            """
            SELECT content_revision, validated_content_revision
            FROM generation_content_manifests
            WHERE generation_id = ?
            """,
            (snapshot.generation_id,),
        ).fetchone()
    assert before is not None
    assert before[0] == before[1]
    assert after == (before[0] + 1, before[1])
    with pytest.raises(GenerationContentError, match="manifest binding is corrupt"):
        context.content.materialize_published_chunk(read_lease_id, memberships[0].chunk_instance_id)
    assert artifact_reads == 2


def test_materialization_fails_closed_for_membership_or_artifact_corruption(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership, snapshot = _publish_one(context, suffix="corrupt", text="verified source")
    read_lease_id = _read_lease_id(context, snapshot)
    with sqlite3.connect(context.layout.metadata_db) as connection:
        connection.execute(
            "UPDATE generation_chunk_memberships SET relative_path = 'src/swapped.py' WHERE chunk_instance_id = ?",
            (membership.chunk_instance_id,),
        )
    with pytest.raises(GenerationContentError, match="manifest binding is corrupt"):
        context.content.materialize_published_chunk(read_lease_id, membership.chunk_instance_id)

    original_digest = identify_chunk_membership(snapshot.generation_id, membership)
    with sqlite3.connect(context.layout.metadata_db) as connection:
        connection.execute(
            """
            UPDATE generation_chunk_memberships
            SET relative_path = ?, membership_digest = ?
            WHERE generation_id = ? AND chunk_instance_id = ?
            """,
            (membership.relative_path, original_digest, snapshot.generation_id, membership.chunk_instance_id),
        )
        connection.execute(
            """
            UPDATE generation_content_manifests
            SET validated_content_revision = content_revision
            WHERE generation_id = ?
            """,
            (snapshot.generation_id,),
        )
    _artifact_path(context, membership).write_bytes(b"corrupt")
    with pytest.raises(ArtifactCorrupt):
        context.content.materialize_published_chunk(read_lease_id, membership.chunk_instance_id)


def test_publication_reverifies_every_manifest_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="publish-corrupt", text="publish only verified bytes")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, row_count=1),
    )
    context.coordinator.mark_ready(context.lease, manifest)
    _artifact_path(context, membership).write_bytes(b"corrupt before publication")

    with pytest.raises(ArtifactCorrupt):
        context.coordinator.publish(
            context.lease,
            context.generation.generation_id,
            expected_previous_generation_id=None,
        )

    assert context.coordinator.current_snapshot(context.lease.operation.workspace_id) is None


def test_publication_authorizes_before_artifact_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="publish-authority", text="authorized publication")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, row_count=1),
    )
    context.coordinator.mark_ready(context.lease, manifest)
    wrong_lease = replace(context.lease, lease_id="lease_unrelated")

    def unexpected_artifact_io(
        _coordinator: SQLiteGenerationCoordinator,
        _generation_id: str,
    ) -> None:
        raise AssertionError("artifact verification ran before publication authority")

    monkeypatch.setattr(SQLiteGenerationCoordinator, "_verify_generation_artifacts", unexpected_artifact_io)

    with pytest.raises(GenerationCoordinatorError, match="lease is unavailable or expired"):
        context.coordinator.publish(
            wrong_lease,
            context.generation.generation_id,
            expected_previous_generation_id=None,
        )


def test_publication_reads_artifacts_before_acquiring_the_visibility_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="publish-lock", text="locked publication")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, row_count=1),
    )
    context.coordinator.mark_ready(context.lease, manifest)
    original = SQLiteGenerationCoordinator._verify_generation_artifacts
    observed_without_write_lock = False

    def verify_before_lock(
        coordinator: SQLiteGenerationCoordinator,
        generation_id: str,
    ) -> object:
        nonlocal observed_without_write_lock
        competing = sqlite3.connect(context.layout.metadata_db, timeout=0, isolation_level=None)
        try:
            competing.execute("BEGIN IMMEDIATE")
            competing.rollback()
            observed_without_write_lock = True
        finally:
            competing.close()
        return original(coordinator, generation_id)

    monkeypatch.setattr(SQLiteGenerationCoordinator, "_verify_generation_artifacts", verify_before_lock)

    context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )

    assert observed_without_write_lock is True


def test_publication_rejects_an_artifact_changed_after_full_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _generation_context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="publish-race", text="stable through publication")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, row_count=1),
    )
    context.coordinator.mark_ready(context.lease, manifest)
    original = SQLiteGenerationCoordinator._verify_generation_artifacts

    def verify_then_corrupt(coordinator: SQLiteGenerationCoordinator, generation_id: str) -> object:
        verified = original(coordinator, generation_id)
        _artifact_path(context, membership).write_bytes(b"changed after full verification")
        return verified

    monkeypatch.setattr(SQLiteGenerationCoordinator, "_verify_generation_artifacts", verify_then_corrupt)

    with pytest.raises(ArtifactCorrupt, match="changed after verification"):
        context.coordinator.publish(
            context.lease,
            context.generation.generation_id,
            expected_previous_generation_id=None,
        )

    assert context.coordinator.current_snapshot(context.lease.operation.workspace_id) is None


def test_membership_contract_rejects_noncanonical_paths_and_ranges() -> None:
    base = {
        "chunk_instance_id": "chunk_invalid",
        "artifact": {
            "artifact_id": "1" * 64,
            "format": "dolphin-chunk-text-v1",
            "utf8_bytes": 1,
            "characters": 1,
            "lines": 1,
        },
        "relative_path": "../escape.py",
        "source_file_fingerprint": "2" * 64,
        "start_line": 2,
        "end_line": 1,
        "language": "python",
        "chunker_key": "python-v1",
        "embedding_cache_key": "3" * 64,
    }

    with pytest.raises(ValidationError):
        StagedChunkMembership.model_validate(base)


@dataclass(frozen=True)
class _GenerationContext:
    layout: StorageLayout
    registry: WorkspaceRegistry
    coordinator: SQLiteGenerationCoordinator
    content: SQLiteGenerationContentStore
    artifacts: ChunkArtifactStore
    lease: OperationLease
    generation: StagingGeneration
    worktree: GitWorktree


def _generation_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> _GenerationContext:
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
        common_git_dir_identity="common-generation-content",
        worktree_git_dir=root / ".git",
        worktree_git_dir_identity="worktree-generation-content",
        head_commit="a" * 40,
        branch="develop",
    )
    _registration, _operation = registry.register_and_submit_initial_index(
        worktree,
        cleanup_receipt=_cleanup_receipt("generation-content"),
    )
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    runtime = registry.register_runtime(
        runtime_id="runtime_generation_content",
        pid=102,
        process_start_identity="start-generation-content",
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
    coordinator = SQLiteGenerationCoordinator(
        layout,
        vectors=AcceptingVectorCommitVerifier(),
        clock=lambda: now,
    )
    artifacts = ChunkArtifactStore(layout)
    return _GenerationContext(
        layout=layout,
        registry=registry,
        coordinator=coordinator,
        content=SQLiteGenerationContentStore(layout, artifacts, clock=lambda: now),
        artifacts=artifacts,
        lease=lease,
        generation=coordinator.create_staging(lease),
        worktree=worktree,
    )


def _membership(
    artifacts: ChunkArtifactStore,
    *,
    suffix: str,
    text: str,
) -> StagedChunkMembership:
    return StagedChunkMembership(
        chunk_instance_id=f"chunk_{suffix}",
        artifact=artifacts.put_exact_text(text),
        relative_path=f"src/{suffix}.py",
        source_file_fingerprint=hashlib.sha256(f"file:{suffix}".encode()).hexdigest(),
        start_line=1,
        end_line=max(1, text.count("\n") + 1),
        language="python",
        chunker_key="python-tree-sitter-v1",
        embedding_cache_key=identify_embedding_input(text).cache_key,
    )


def _artifact_path(context: _GenerationContext, membership: StagedChunkMembership) -> Path:
    return (
        context.layout.artifacts
        / "dolphin-chunk-text-v1"
        / membership.artifact.artifact_id[:2]
        / membership.artifact.artifact_id[2:]
    )


def _publish_one(
    context: _GenerationContext,
    *,
    suffix: str,
    text: str,
) -> tuple[StagedChunkMembership, PublishedSnapshot]:
    membership = _membership(context.artifacts, suffix=suffix, text=text)
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, row_count=1),
    )
    context.coordinator.mark_ready(context.lease, manifest)
    snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    return membership, snapshot


def _read_lease_id(context: _GenerationContext, snapshot: PublishedSnapshot) -> str:
    lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    assert lease.snapshot == snapshot
    return lease.lease_id


def _vector_commit(generation_id: str, *, row_count: int) -> VerifiedVectorCommit:
    return VerifiedVectorCommit(
        generation_id=generation_id,
        backend_token="vector-commit-generation-content",
        manifest_digest=hashlib.sha256(b"vector-digest-generation-content").hexdigest(),
        row_count=row_count,
    )


def _cleanup_receipt(seed: str) -> str:
    token = hashlib.sha256(seed.encode()).hexdigest()[:43]
    return f"dolphin-cleanup-v1_{token}"
