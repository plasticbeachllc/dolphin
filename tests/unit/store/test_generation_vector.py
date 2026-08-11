"""Generation-scoped LanceDB commit and snapshot-authorized retrieval tests."""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import lancedb
import pytest
from pydantic import ValidationError

from kb.artifacts import identify_embedding_input
from kb.generation import GenerationCoordinatorError, StagingGeneration, VerifiedVectorCommit
from kb.generation_content import StagedChunkMembership
from kb.generation_vector import (
    GenerationVectorConflict,
    GenerationVectorError,
    GenerationVectorTimeout,
    GenerationVectorUnavailable,
    StagedGenerationVector,
)
from kb.runtime.storage import StorageLayout, macos_storage_layout
from kb.search_scope import SearchScope
from kb.services.workspace_registry import OperationLease, OperationState, WorkspaceRegistry
from kb.services.worktree import GitWorktree
from kb.store import generation_vector as generation_vector_store
from kb.store.chunk_artifacts import ChunkArtifactStore
from kb.store.generation_content import SQLiteGenerationContentStore
from kb.store.generation_coordinator import SQLiteGenerationCoordinator
from kb.store.generation_vector import LanceGenerationVectorStore
from kb.store.search_scope import SQLiteSearchScopeStore


def test_vectors_are_invisible_until_atomic_publication_and_search_uses_the_reader_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    first = _membership(context.artifacts, "first", "semantic first")
    second = _membership(context.artifacts, "second", "semantic second")
    manifest = context.content.stage_manifest(context.lease, context.generation, [second, first])
    vectors = (_vector(first, 0), _vector(second, 1))

    commit = context.vectors.stage_and_commit(context.lease, context.generation, vectors)

    assert commit.row_count == 2
    assert context.coordinator.current_snapshot(context.generation.workspace_id) is None
    with pytest.raises(GenerationVectorUnavailable, match="read lease is unavailable or expired"):
        context.vectors.search("read_missing", _basis(0), limit=2)

    context.coordinator.record_vector_ready(context.lease, commit)
    context.coordinator.mark_ready(context.lease, manifest)
    snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))

    hits = context.vectors.search(read_lease.lease_id, _basis(0), limit=2)

    assert [hit.chunk_instance_id for hit in hits] == [first.chunk_instance_id, second.chunk_instance_id]
    assert hits[0].score == 1
    assert hits[0].distance == 0


def test_published_vector_search_surfaces_its_backend_deadline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, "timeout", "bounded vector deadline")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    commit = context.vectors.stage_and_commit(context.lease, context.generation, [_vector(membership, 0)])
    context.coordinator.record_vector_ready(context.lease, commit)
    context.coordinator.mark_ready(context.lease, manifest)
    snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    table = lancedb.connect(context.layout.vectors.as_posix()).open_table(commit.backend_token.split(":")[1])

    def time_out(_table: object, *_args: object, **_kwargs: object) -> object:
        raise TimeoutError("backend deadline")

    monkeypatch.setattr(type(table), "search", time_out)

    with pytest.raises(GenerationVectorTimeout, match="retrieval timed out"):
        context.vectors.search(read_lease.lease_id, _basis(0), limit=1)


def test_vector_prefilter_returns_best_eligible_hit_before_top_k(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    excluded_closest = _membership(
        context.artifacts,
        "excluded",
        "excluded closest",
        relative_path="tests/closest.py",
    )
    included = _membership(context.artifacts, "included", "included evidence", relative_path="src/main.py")
    manifest = context.content.stage_manifest(context.lease, context.generation, [excluded_closest, included])
    commit = context.vectors.stage_and_commit(
        context.lease,
        context.generation,
        [_vector(excluded_closest, 0), _vector(included, 1)],
    )
    context.coordinator.record_vector_ready(context.lease, commit)
    context.coordinator.mark_ready(context.lease, manifest)
    snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    query = tuple(1.0 if index in {0, 1} else 0.0 for index in range(1_536))
    scope = SearchScope.from_inputs(paths=["src/**"], exclude_paths=[], languages=["python"])

    hits = context.vectors.search(read_lease.lease_id, query, scope=scope, limit=1)

    assert [hit.chunk_instance_id for hit in hits] == [included.chunk_instance_id]


def test_scope_store_counts_exact_filtered_memberships_under_the_reader_lease(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    included = _membership(context.artifacts, "included", "included", relative_path="src/main.py")
    excluded = _membership(context.artifacts, "excluded", "excluded", relative_path="tests/main.py")
    manifest = context.content.stage_manifest(context.lease, context.generation, [included, excluded])
    commit = context.vectors.stage_and_commit(
        context.lease,
        context.generation,
        [_vector(included, 0), _vector(excluded, 1)],
    )
    context.coordinator.record_vector_ready(context.lease, commit)
    context.coordinator.mark_ready(context.lease, manifest)
    snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    store = SQLiteSearchScopeStore(context.layout, clock=lambda: context.now)

    unfiltered = store.resolve([read_lease], SearchScope.from_inputs(paths=[], exclude_paths=[], languages=[]))
    filtered = store.resolve(
        [read_lease],
        SearchScope.from_inputs(paths=["src/**"], exclude_paths=[], languages=["python"]),
    )

    assert unfiltered.searchable_chunks == 2
    assert filtered.searchable_chunks == 1
    assert filtered.workspace_counts[0].searchable_chunks == 1


def test_published_vector_search_rejects_a_successful_backend_overrun(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, "overrun", "successful vector overrun")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    commit = context.vectors.stage_and_commit(context.lease, context.generation, [_vector(membership, 0)])
    context.coordinator.record_vector_ready(context.lease, commit)
    context.coordinator.mark_ready(context.lease, manifest)
    snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    observations = iter((0.0, 11.0))
    monkeypatch.setattr(context.vectors, "_monotonic", lambda: next(observations))

    with pytest.raises(GenerationVectorTimeout, match="retrieval timed out"):
        context.vectors.search(read_lease.lease_id, _basis(0), limit=1)


def test_published_vector_search_bounds_a_stalled_materialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, "stalled-query", "stalled vector materialization")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    commit = context.vectors.stage_and_commit(context.lease, context.generation, [_vector(membership, 0)])
    context.coordinator.record_vector_ready(context.lease, commit)
    context.coordinator.mark_ready(context.lease, manifest)
    snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    table = lancedb.connect(context.layout.vectors.as_posix()).open_table(commit.backend_token.split(":")[1])
    query_type = type(table.search(list(_basis(0)), vector_column_name="vector"))
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def stalled_to_list(_query: object, *_args: object, **_kwargs: object) -> list[object]:
        entered.set()
        try:
            release.wait(timeout=1)
            return []
        finally:
            finished.set()

    monkeypatch.setattr(generation_vector_store, "_QUERY_TIMEOUT", timedelta(milliseconds=25))
    monkeypatch.setattr(query_type, "to_list", stalled_to_list)

    try:
        with pytest.raises(GenerationVectorTimeout, match="retrieval timed out"):
            context.vectors.search(read_lease.lease_id, _basis(0), limit=1)
        assert entered.is_set()
    finally:
        release.set()
        assert finished.wait(timeout=1)


@pytest.mark.parametrize("probe", ["count_rows", "version"])
def test_published_vector_search_bounds_stalled_verification_probes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    probe: str,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, f"stalled-{probe}", "stalled verification probe")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    commit = context.vectors.stage_and_commit(context.lease, context.generation, [_vector(membership, 0)])
    context.coordinator.record_vector_ready(context.lease, commit)
    context.coordinator.mark_ready(context.lease, manifest)
    snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    table = lancedb.connect(context.layout.vectors.as_posix()).open_table(commit.backend_token.split(":")[1])
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def stall_then_return(value: int) -> int:
        entered.set()
        try:
            release.wait(timeout=1)
            return value
        finally:
            finished.set()

    monkeypatch.setattr(generation_vector_store, "_QUERY_TIMEOUT", timedelta(milliseconds=25))
    if probe == "count_rows":
        monkeypatch.setattr(type(table), "count_rows", lambda _table: stall_then_return(commit.row_count))
    else:
        version = int(commit.backend_token.rsplit(":", maxsplit=1)[1])
        monkeypatch.setattr(type(table), "version", property(lambda _table: stall_then_return(version)))

    try:
        with pytest.raises(GenerationVectorTimeout, match="verification timed out"):
            context.vectors.search(read_lease.lease_id, _basis(0), limit=1)
        assert entered.is_set()
    finally:
        release.set()
        assert finished.wait(timeout=1)


def test_staging_is_idempotent_but_rejects_different_vectors_for_the_same_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, "retry", "retry vector")
    context.content.stage_manifest(context.lease, context.generation, [membership])
    original = (_vector(membership, 0),)

    first = context.vectors.stage_and_commit(context.lease, context.generation, original)
    repeated = context.vectors.stage_and_commit(context.lease, context.generation, original)

    assert repeated == first
    with pytest.raises(GenerationVectorConflict, match="already records different vectors"):
        context.vectors.stage_and_commit(context.lease, context.generation, (_vector(membership, 1),))


def test_later_generation_can_reuse_the_same_chunk_and_embedding_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, "stable", "stable reusable vector")
    first_manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    first_commit = context.vectors.stage_and_commit(context.lease, context.generation, [_vector(membership, 0)])
    context.coordinator.record_vector_ready(context.lease, first_commit)
    context.coordinator.mark_ready(context.lease, first_manifest)
    first_snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    old_read = context.coordinator.acquire_read(
        first_snapshot.workspace_id,
        lease_duration=timedelta(seconds=10),
    )
    context.registry.finish_operation(context.lease, OperationState.SUCCEEDED, observed_at=context.now)

    next_worktree = replace(context.worktree, head_commit="b" * 40)
    context.registry.register_and_submit_initial_index(
        next_worktree,
        cleanup_receipt=_cleanup_receipt("generation-vector"),
    )
    retry_now = context.now + timedelta(seconds=1)
    retry_lease = context.registry.claim_next_operation(
        runtime_id=context.lease.runtime_id,
        process_start_identity="start-generation-vector",
        pipeline_key="generation-pipeline-v1",
        now=retry_now,
        expires_at=retry_now + timedelta(seconds=15),
    )
    assert retry_lease is not None
    retry_vectors = LanceGenerationVectorStore(context.layout, clock=lambda: retry_now)
    retry_coordinator = SQLiteGenerationCoordinator(
        context.layout,
        vectors=retry_vectors,
        clock=lambda: retry_now,
    )
    retry_generation = retry_coordinator.create_staging(retry_lease)
    retry_content = SQLiteGenerationContentStore(context.layout, context.artifacts, clock=lambda: retry_now)
    retry_manifest = retry_content.stage_manifest(retry_lease, retry_generation, [membership])

    retry_commit = retry_vectors.stage_and_commit(retry_lease, retry_generation, [_vector(membership, 0)])
    retry_coordinator.record_vector_ready(retry_lease, retry_commit)
    retry_coordinator.mark_ready(retry_lease, retry_manifest)
    second_snapshot = retry_coordinator.publish(
        retry_lease,
        retry_generation.generation_id,
        expected_previous_generation_id=first_snapshot.generation_id,
    )
    new_read = retry_coordinator.acquire_read(
        second_snapshot.workspace_id,
        lease_duration=timedelta(seconds=10),
    )

    assert retry_commit.generation_id != first_commit.generation_id
    assert context.vectors.search(old_read.lease_id, _basis(0), limit=1)[0].chunk_instance_id == "chunk_stable"
    assert retry_vectors.search(new_read.lease_id, _basis(0), limit=1)[0].chunk_instance_id == "chunk_stable"


def test_staging_requires_exact_chunk_and_embedding_cache_membership(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, "membership", "bound vector")
    context.content.stage_manifest(context.lease, context.generation, [membership])
    wrong_cache_key = StagedGenerationVector(
        chunk_instance_id=membership.chunk_instance_id,
        embedding_cache_key="f" * 64,
        relative_path=membership.relative_path,
        language=membership.language,
        vector=_basis(0),
    )

    with pytest.raises(GenerationVectorConflict, match="do not match the staged chunk manifest"):
        context.vectors.stage_and_commit(context.lease, context.generation, [wrong_cache_key])


def test_coordinator_rejects_a_lancedb_version_changed_after_vector_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, "changed", "changed vector")
    context.content.stage_manifest(context.lease, context.generation, [membership])
    commit = context.vectors.stage_and_commit(context.lease, context.generation, [_vector(membership, 0)])
    _advance_table_version(context.layout, commit.backend_token)

    with pytest.raises(GenerationCoordinatorError, match="vectors are unavailable or corrupt"):
        context.coordinator.record_vector_ready(context.lease, commit)


def test_readiness_reverifies_the_recorded_lancedb_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, "ready-change", "ready vector")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    commit = context.vectors.stage_and_commit(context.lease, context.generation, [_vector(membership, 0)])
    context.coordinator.record_vector_ready(context.lease, commit)
    _advance_table_version(context.layout, commit.backend_token)

    with pytest.raises(GenerationCoordinatorError, match="vectors are unavailable or corrupt"):
        context.coordinator.mark_ready(context.lease, manifest)


def test_publication_reverifies_the_ready_lancedb_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, "publish-change", "publish vector")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    commit = context.vectors.stage_and_commit(context.lease, context.generation, [_vector(membership, 0)])
    context.coordinator.record_vector_ready(context.lease, commit)
    context.coordinator.mark_ready(context.lease, manifest)
    _advance_table_version(context.layout, commit.backend_token)

    with pytest.raises(GenerationCoordinatorError, match="vectors are unavailable or corrupt"):
        context.coordinator.publish(
            context.lease,
            context.generation.generation_id,
            expected_previous_generation_id=None,
        )


def test_published_search_fails_closed_after_lancedb_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, "published", "published vector")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    commit = context.vectors.stage_and_commit(context.lease, context.generation, [_vector(membership, 0)])
    context.coordinator.record_vector_ready(context.lease, commit)
    context.coordinator.mark_ready(context.lease, manifest)
    snapshot = context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    assert context.vectors.search(read_lease.lease_id, _basis(0), limit=1)

    _advance_table_version(context.layout, commit.backend_token)

    with pytest.raises(GenerationVectorError, match="changed after verification"):
        context.vectors.search(read_lease.lease_id, _basis(0), limit=1)


def test_vector_input_and_search_limits_are_strict_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, "bounds", "bounded vector")
    context.content.stage_manifest(context.lease, context.generation, [membership])

    with pytest.raises(ValidationError, match="1536"):
        StagedGenerationVector(
            chunk_instance_id=membership.chunk_instance_id,
            embedding_cache_key=membership.embedding_cache_key,
            relative_path=membership.relative_path,
            language=membership.language,
            vector=(1.0,),
        )
    with pytest.raises(ValidationError, match="finite"):
        StagedGenerationVector(
            chunk_instance_id=membership.chunk_instance_id,
            embedding_cache_key=membership.embedding_cache_key,
            relative_path=membership.relative_path,
            language=membership.language,
            vector=(float("nan"),) + (0.0,) * 1_535,
        )
    with pytest.raises(GenerationVectorError, match="result limit is invalid"):
        context.vectors.search("read_missing", _basis(0), limit=0)
    with pytest.raises(GenerationVectorError, match="result limit is invalid"):
        context.vectors.search("read_missing", _basis(0), limit=1_001)


def test_adapter_rejects_any_vector_path_outside_the_fixed_storage_layout(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    unsafe = StorageLayout(
        root=layout.root,
        config_file=layout.config_file,
        metadata_db=layout.metadata_db,
        vectors=tmp_path / "remote-or-user-selected-vectors",
        artifacts=layout.artifacts,
        locks=layout.locks,
        logs=layout.logs,
        temporary=layout.temporary,
    )

    with pytest.raises(GenerationVectorUnavailable, match="invalid layout"):
        LanceGenerationVectorStore(unsafe).verify_commit(
            contextless_commit("gen_fixed", "a" * 64),
        )


@dataclass(frozen=True, slots=True)
class _Context:
    layout: StorageLayout
    registry: WorkspaceRegistry
    coordinator: SQLiteGenerationCoordinator
    content: SQLiteGenerationContentStore
    vectors: LanceGenerationVectorStore
    artifacts: ChunkArtifactStore
    lease: OperationLease
    generation: StagingGeneration
    worktree: GitWorktree
    now: datetime


def _context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Context:
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
        common_git_dir_identity="common-generation-vector",
        worktree_git_dir=root / ".git",
        worktree_git_dir_identity="worktree-generation-vector",
        head_commit="a" * 40,
        branch="develop",
    )
    registry.register_and_submit_initial_index(worktree, cleanup_receipt=_cleanup_receipt("generation-vector"))
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    runtime = registry.register_runtime(
        runtime_id="runtime_generation_vector",
        pid=104,
        process_start_identity="start-generation-vector",
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
    vectors = LanceGenerationVectorStore(layout, clock=lambda: now)
    coordinator = SQLiteGenerationCoordinator(layout, vectors=vectors, clock=lambda: now)
    artifacts = ChunkArtifactStore(layout)
    return _Context(
        layout=layout,
        registry=registry,
        coordinator=coordinator,
        content=SQLiteGenerationContentStore(layout, artifacts, clock=lambda: now),
        vectors=vectors,
        artifacts=artifacts,
        lease=lease,
        generation=coordinator.create_staging(lease),
        worktree=worktree,
        now=now,
    )


def _membership(
    artifacts: ChunkArtifactStore,
    suffix: str,
    text: str,
    *,
    relative_path: str | None = None,
    language: str = "python",
) -> StagedChunkMembership:
    return StagedChunkMembership(
        chunk_instance_id=f"chunk_{suffix}",
        artifact=artifacts.put_exact_text(text),
        relative_path=relative_path or f"src/{suffix}.py",
        source_file_fingerprint=hashlib.sha256(f"file:{suffix}".encode()).hexdigest(),
        start_line=1,
        end_line=1,
        language=language,
        chunker_key="python-tree-sitter-v1",
        embedding_cache_key=identify_embedding_input(text).cache_key,
    )


def _vector(membership: StagedChunkMembership, basis: int) -> StagedGenerationVector:
    return StagedGenerationVector(
        chunk_instance_id=membership.chunk_instance_id,
        embedding_cache_key=membership.embedding_cache_key,
        relative_path=membership.relative_path,
        language=membership.language,
        vector=_basis(basis),
    )


def _basis(index: int) -> tuple[float, ...]:
    values = [0.0] * 1_536
    values[index] = 1.0
    return tuple(values)


def _advance_table_version(layout: StorageLayout, backend_token: str) -> None:
    _prefix, table_name, _version = backend_token.split(":")
    table = lancedb.connect(layout.vectors.as_posix()).open_table(table_name)
    row = table.to_arrow().to_pylist()[0]
    table.add([row], mode="append")


def contextless_commit(generation_id: str, digest: str) -> VerifiedVectorCommit:
    table_name = "generation_vectors_v1_" + hashlib.sha256(generation_id.encode()).hexdigest()
    return VerifiedVectorCommit(
        generation_id=generation_id,
        backend_token=f"lance-generation-vector-v1:{table_name}:1",
        manifest_digest=digest,
        row_count=0,
    )


def _cleanup_receipt(seed: str) -> str:
    token = hashlib.sha256(seed.encode()).hexdigest()[:43]
    return f"dolphin-cleanup-v1_{token}"
