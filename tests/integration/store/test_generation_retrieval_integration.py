"""Cross-store integration tests for snapshot-pinned hybrid retrieval."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kb.artifacts import identify_embedding_input
from kb.generation import PublishedSnapshot
from kb.generation_content import StagedChunkMembership
from kb.generation_vector import StagedGenerationVector
from kb.runtime.storage import macos_storage_layout
from kb.services import search_admission as search_admission_module
from kb.services.generation_retrieval import GenerationRetrievalService
from kb.services.search_admission import SearchCoverageService
from kb.services.workspace_registry import OperationState, WorkspaceRegistration, WorkspaceRegistry
from kb.services.worktree import GitWorktree
from kb.store.chunk_artifacts import ChunkArtifactStore
from kb.store.generation_content import SQLiteGenerationContentStore
from kb.store.generation_coordinator import SQLiteGenerationCoordinator
from kb.store.generation_keyword import SQLiteGenerationKeywordStore
from kb.store.generation_vector import LanceGenerationVectorStore


def test_real_coverage_keyword_and_vector_stores_share_one_published_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    layout = macos_storage_layout(home=_directory(tmp_path / "home"))
    registry = WorkspaceRegistry(layout)
    monkeypatch.setattr("kb.services.workspace_registry.validate_git_worktree_snapshot", lambda _worktree: None)
    artifacts = ChunkArtifactStore(layout)
    content = SQLiteGenerationContentStore(layout, artifacts, clock=lambda: now)
    vectors = LanceGenerationVectorStore(layout, clock=lambda: now)
    coordinator = SQLiteGenerationCoordinator(layout, vectors=vectors, clock=lambda: now)
    registration, snapshot, lexical, semantic = _publish_workspace(
        tmp_path=tmp_path,
        suffix="retrieval",
        pid=105,
        clock=lambda: now,
        registry=registry,
        coordinator=coordinator,
        artifacts=artifacts,
        content=content,
        vectors=vectors,
    )

    retrieval = GenerationRetrievalService(
        coordinator,
        SQLiteGenerationKeywordStore(layout, clock=lambda: now),
        vectors,
    )
    admission = SearchCoverageService(registry, coordinator)

    with admission.admit([registration.workspace_id]) as coverage:
        assert coverage.snapshots == (snapshot,)
        result = retrieval.retrieve_for_lease(
            coverage.workspaces[0].read_lease,
            "needle",
            query_vector=_basis(1),
        )
        admission.validate(coverage)

    assert result.snapshot == snapshot
    assert result.retrieval_mode == "hybrid"
    assert [(target.chunk_instance_id, target.sources) for target in result.ranked_targets] == [
        (lexical.chunk_instance_id, ("keyword", "vector")),
        (semantic.chunk_instance_id, ("vector",)),
    ]
    with sqlite3.connect(layout.metadata_db) as connection:
        assert connection.execute("SELECT count(*) FROM generation_reader_leases").fetchone() == (0,)


def test_slow_multi_workspace_retrieval_renews_all_real_reader_leases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clock = _Clock(datetime(2026, 8, 10, 12, tzinfo=UTC))
    layout = macos_storage_layout(home=_directory(tmp_path / "home"))
    registry = WorkspaceRegistry(layout)
    monkeypatch.setattr("kb.services.workspace_registry.validate_git_worktree_snapshot", lambda _worktree: None)
    monkeypatch.setattr(search_admission_module, "_SEARCH_READ_LEASE_RENEW_INTERVAL_SECONDS", 0.01)
    artifacts = ChunkArtifactStore(layout)
    content = SQLiteGenerationContentStore(layout, artifacts, clock=clock)
    vectors = LanceGenerationVectorStore(layout, clock=clock)
    coordinator = SQLiteGenerationCoordinator(layout, vectors=vectors, clock=clock)
    first = _publish_workspace(
        tmp_path=tmp_path,
        suffix="first",
        pid=106,
        clock=clock,
        registry=registry,
        coordinator=coordinator,
        artifacts=artifacts,
        content=content,
        vectors=vectors,
    )
    second = _publish_workspace(
        tmp_path=tmp_path,
        suffix="second",
        pid=106,
        clock=clock,
        registry=registry,
        coordinator=coordinator,
        artifacts=artifacts,
        content=content,
        vectors=vectors,
    )
    retrieval = GenerationRetrievalService(
        coordinator,
        SQLiteGenerationKeywordStore(layout, clock=clock),
        vectors,
    )

    with SearchCoverageService(registry, coordinator).admit(
        [first[0].workspace_id, second[0].workspace_id]
    ) as coverage:
        clock.advance(seconds=25)
        time.sleep(0.04)
        first_result = retrieval.retrieve_for_lease(coverage.workspaces[0].read_lease, "needle", query_vector=None)
        clock.advance(seconds=25)
        second_result = retrieval.retrieve_for_lease(coverage.workspaces[1].read_lease, "needle", query_vector=None)

    assert {first_result.snapshot, second_result.snapshot} == {first[1], second[1]}
    with sqlite3.connect(layout.metadata_db) as connection:
        assert connection.execute("SELECT count(*) FROM generation_reader_leases").fetchone() == (0,)


def _directory(path: Path) -> Path:
    path.mkdir()
    return path


def _publish_workspace(
    *,
    tmp_path: Path,
    suffix: str,
    pid: int,
    clock: Callable[[], datetime],
    registry: WorkspaceRegistry,
    coordinator: SQLiteGenerationCoordinator,
    artifacts: ChunkArtifactStore,
    content: SQLiteGenerationContentStore,
    vectors: LanceGenerationVectorStore,
) -> tuple[WorkspaceRegistration, PublishedSnapshot, StagedChunkMembership, StagedChunkMembership]:
    root = _directory(tmp_path / f"repository-{suffix}")
    worktree = GitWorktree(
        root=root,
        common_git_dir=root / ".git",
        common_git_dir_identity=f"common-generation-{suffix}",
        worktree_git_dir=root / ".git",
        worktree_git_dir_identity=f"worktree-generation-{suffix}",
        head_commit=hashlib.sha1(suffix.encode(), usedforsecurity=False).hexdigest(),
        branch="develop",
    )
    registration, _operation = registry.register_and_submit_initial_index(
        worktree,
        cleanup_receipt=_cleanup_receipt(f"generation-{suffix}"),
    )
    now = clock()
    runtime = registry.register_runtime(
        runtime_id=f"runtime_generation_{suffix}",
        pid=pid,
        process_start_identity=f"start-generation-{suffix}",
        mode="mcp",
        operation_capable=True,
        pipeline_key="generation-pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=30),
    )
    operation_lease = registry.claim_next_operation(
        runtime_id=runtime.runtime_id,
        process_start_identity=runtime.process_start_identity,
        pipeline_key="generation-pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=15),
    )
    assert operation_lease is not None
    generation = coordinator.create_staging(operation_lease)
    lexical = _membership(artifacts, f"{suffix}-lexical", "needle lexical evidence")
    semantic = _membership(artifacts, f"{suffix}-semantic", "conceptual semantic evidence")
    manifest = content.stage_manifest(operation_lease, generation, [lexical, semantic])
    vector_commit = vectors.stage_and_commit(
        operation_lease,
        generation,
        [_vector(lexical, 0), _vector(semantic, 1)],
    )
    coordinator.record_vector_ready(operation_lease, vector_commit)
    coordinator.mark_ready(operation_lease, manifest)
    snapshot = coordinator.publish(
        operation_lease,
        generation.generation_id,
        expected_previous_generation_id=None,
    )
    registry.finish_operation(operation_lease, OperationState.SUCCEEDED, observed_at=clock())
    registry.drain_runtime(
        runtime_id=runtime.runtime_id,
        process_start_identity=runtime.process_start_identity,
        observed_at=clock(),
    )
    return registration, snapshot, lexical, semantic


@dataclass
class _Clock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def _membership(artifacts: ChunkArtifactStore, suffix: str, text: str) -> StagedChunkMembership:
    return StagedChunkMembership(
        chunk_instance_id=f"chunk_{suffix}",
        artifact=artifacts.put_exact_text(text),
        relative_path=f"src/{suffix}.py",
        source_file_fingerprint=hashlib.sha256(f"file:{suffix}".encode()).hexdigest(),
        start_line=1,
        end_line=1,
        language="python",
        chunker_key="python-tree-sitter-v1",
        embedding_cache_key=identify_embedding_input(text).cache_key,
    )


def _vector(membership: StagedChunkMembership, basis: int) -> StagedGenerationVector:
    return StagedGenerationVector(
        chunk_instance_id=membership.chunk_instance_id,
        embedding_cache_key=membership.embedding_cache_key,
        vector=_basis(basis),
    )


def _basis(index: int) -> tuple[float, ...]:
    values = [0.0] * 1_536
    values[index] = 1.0
    return tuple(values)


def _cleanup_receipt(seed: str) -> str:
    token = hashlib.sha256(seed.encode()).hexdigest()[:43]
    return f"dolphin-cleanup-v1_{token}"
