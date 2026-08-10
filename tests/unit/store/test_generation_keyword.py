"""Generation-scoped FTS5 staging and reader-lease retrieval tests."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kb.artifacts import identify_embedding_input
from kb.generation import (
    GenerationCoordinatorError,
    PublishedSnapshot,
    StagingGeneration,
    VerifiedGenerationManifest,
    VerifiedVectorCommit,
)
from kb.generation_content import StagedChunkMembership
from kb.generation_keyword import GenerationKeywordError, GenerationKeywordQueryTooBroad, GenerationKeywordUnavailable
from kb.runtime.storage import StorageLayout, macos_storage_layout
from kb.services.workspace_registry import OperationLease, WorkspaceRegistry
from kb.services.worktree import GitWorktree
from kb.store.chunk_artifacts import ChunkArtifactStore
from kb.store.generation_content import SQLiteGenerationContentStore
from kb.store.generation_coordinator import SQLiteGenerationCoordinator
from kb.store.generation_keyword import SQLiteGenerationKeywordStore
from tests.vector_fakes import AcceptingVectorCommitVerifier


def test_keyword_rows_are_invisible_until_publication_and_search_is_snapshot_scoped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    first = _membership(context.artifacts, suffix="alpha", text="needle shared evidence")
    second = _membership(context.artifacts, suffix="beta", text="needle shared evidence")
    unrelated = _membership(context.artifacts, suffix="gamma", text="different symbols only")
    manifest = context.content.stage_manifest(context.lease, context.generation, [second, unrelated, first])
    repeated = context.content.stage_manifest(context.lease, context.generation, [first, second, unrelated])

    assert repeated == manifest
    with sqlite3.connect(context.layout.metadata_db) as connection:
        assert connection.execute("SELECT count(*) FROM generation_keyword_documents").fetchone() == (3,)
    with pytest.raises(GenerationKeywordUnavailable, match="read lease is unavailable or expired"):
        context.keyword.search("read_missing", "needle", limit=10)

    snapshot = _publish(context, manifest)
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))

    hits = context.keyword.search(read_lease.lease_id, "needle", limit=10)

    assert [hit.chunk_instance_id for hit in hits] == [first.chunk_instance_id, second.chunk_instance_id]
    assert all(hit.score >= 0 for hit in hits)
    path_hits = context.keyword.search(read_lease.lease_id, "alpha", limit=10)
    assert path_hits[0].chunk_instance_id == first.chunk_instance_id
    assert len(context.keyword.search(read_lease.lease_id, "python", limit=10)) == 3
    assert context.keyword.search(read_lease.lease_id, "no-such-token", limit=10) == ()


def test_keyword_search_requires_a_live_reader_lease(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="lease", text="lease bounded keyword")
    snapshot = _publish(context, context.content.stage_manifest(context.lease, context.generation, [membership]))
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))

    hits = context.keyword.search(read_lease.lease_id, "bounded", limit=1)
    assert hits[0].chunk_instance_id == membership.chunk_instance_id

    expired = SQLiteGenerationKeywordStore(context.layout, clock=lambda: read_lease.expires_at)
    with pytest.raises(GenerationKeywordUnavailable, match="read lease is unavailable or expired"):
        expired.search(read_lease.lease_id, "bounded", limit=1)
    context.coordinator.release_read(read_lease)
    with pytest.raises(GenerationKeywordUnavailable, match="read lease is unavailable or expired"):
        context.keyword.search(read_lease.lease_id, "bounded", limit=1)


def test_keyword_revision_invalidates_published_search_after_any_document_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="revision", text="original searchable keyword")
    snapshot = _publish(context, context.content.stage_manifest(context.lease, context.generation, [membership]))
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    assert context.keyword.search(read_lease.lease_id, "original", limit=10)

    with sqlite3.connect(context.layout.metadata_db) as connection:
        before = connection.execute(
            """
            SELECT keyword_revision, validated_keyword_revision
            FROM generation_keyword_commits
            WHERE generation_id = ?
            """,
            (snapshot.generation_id,),
        ).fetchone()
        connection.execute(
            """
            UPDATE generation_keyword_documents
            SET text = 'coherently changed keyword text'
            WHERE generation_id = ? AND chunk_instance_id = ?
            """,
            (snapshot.generation_id, membership.chunk_instance_id),
        )
        after = connection.execute(
            """
            SELECT keyword_revision, validated_keyword_revision
            FROM generation_keyword_commits
            WHERE generation_id = ?
            """,
            (snapshot.generation_id,),
        ).fetchone()
    assert before is not None
    assert before[0] == before[1]
    assert after == (before[0] + 1, before[1])
    with pytest.raises(GenerationKeywordError, match="keyword binding is corrupt"):
        context.keyword.search(read_lease.lease_id, "original", limit=10)


def test_readiness_rejects_direct_fts_index_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="fts-corrupt", text="indexed integrity evidence")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    _delete_fts_membership(context, context.generation.generation_id, membership)

    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, manifest.vector_row_count),
    )
    with pytest.raises(GenerationCoordinatorError, match="keyword index is invalid"):
        context.coordinator.mark_ready(context.lease, manifest)


def test_keyword_search_rejects_post_publication_fts_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="published-corrupt", text="published integrity evidence")
    unrelated = _membership(context.artifacts, suffix="unrelated-corrupt", text="isolated tamper token")
    snapshot = _publish(
        context,
        context.content.stage_manifest(context.lease, context.generation, [membership, unrelated]),
    )
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    assert context.keyword.search(read_lease.lease_id, "integrity", limit=10)

    _delete_fts_membership(context, snapshot.generation_id, unrelated)

    assert context.keyword.search(read_lease.lease_id, "integrity", limit=10)
    with pytest.raises(GenerationKeywordError, match="published keyword index is corrupt"):
        context.keyword.search(read_lease.lease_id, "isolated", limit=10)


def test_keyword_search_rejects_tampered_commit_digest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="commit-corrupt", text="commit integrity evidence")
    snapshot = _publish(context, context.content.stage_manifest(context.lease, context.generation, [membership]))
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))

    with sqlite3.connect(context.layout.metadata_db) as connection:
        connection.execute(
            """
            UPDATE generation_keyword_commits
            SET commit_digest = ?
            WHERE generation_id = ?
            """,
            ("f" * 64, snapshot.generation_id),
        )

    with pytest.raises(GenerationKeywordError, match="keyword binding is corrupt"):
        context.keyword.search(read_lease.lease_id, "integrity", limit=10)


def test_keyword_search_rejects_tampered_term_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="term-commit-corrupt", text="term commitment evidence")
    snapshot = _publish(context, context.content.stage_manifest(context.lease, context.generation, [membership]))
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))

    with sqlite3.connect(context.layout.metadata_db) as connection:
        connection.execute(
            """
            UPDATE generation_keyword_term_commits
            SET posting_digest = ?
            WHERE generation_id = ? AND term = 'commitment'
            """,
            ("f" * 64, snapshot.generation_id),
        )

    with pytest.raises(GenerationKeywordError, match="keyword binding is corrupt"):
        context.keyword.search(read_lease.lease_id, "commitment", limit=10)


def test_readiness_rejects_missing_or_changed_keyword_documents(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="ready", text="ready requires keyword binding")
    manifest = context.content.stage_manifest(context.lease, context.generation, [membership])
    context.coordinator.record_vector_ready(context.lease, _vector_commit(context.generation.generation_id, 1))
    with sqlite3.connect(context.layout.metadata_db) as connection:
        connection.execute(
            """
            DELETE FROM generation_keyword_documents
            WHERE generation_id = ? AND chunk_instance_id = ?
            """,
            (context.generation.generation_id, membership.chunk_instance_id),
        )

    with pytest.raises(GenerationCoordinatorError, match="keyword binding is invalid"):
        context.coordinator.mark_ready(context.lease, manifest)


def test_keyword_query_is_bounded_and_treats_fts_operators_as_plain_terms(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    membership = _membership(context.artifacts, suffix="query", text="literal operator search")
    snapshot = _publish(context, context.content.stage_manifest(context.lease, context.generation, [membership]))
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))

    assert context.keyword.search(read_lease.lease_id, 'operator AND "search"', limit=10)
    assert context.keyword.search(read_lease.lease_id, ":: -- !!", limit=10) == ()
    with pytest.raises(GenerationKeywordError, match="query is invalid"):
        context.keyword.search(read_lease.lease_id, "x" * 4_097, limit=10)
    with pytest.raises(GenerationKeywordError, match="result limit is invalid"):
        context.keyword.search(read_lease.lease_id, "literal", limit=0)
    with pytest.raises(GenerationKeywordError, match="result limit is invalid"):
        context.keyword.search(read_lease.lease_id, "literal", limit=1_001)


def test_keyword_search_fails_explicitly_when_posting_budget_is_exceeded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _context(monkeypatch, tmp_path)
    first = _membership(context.artifacts, suffix="broad-first", text="common evidence")
    second = _membership(context.artifacts, suffix="broad-second", text="common evidence")
    snapshot = _publish(context, context.content.stage_manifest(context.lease, context.generation, [first, second]))
    read_lease = context.coordinator.acquire_read(snapshot.workspace_id, lease_duration=timedelta(seconds=10))
    monkeypatch.setattr("kb.store.generation_keyword.MAX_KEYWORD_POSTINGS_PER_QUERY", 1)

    with pytest.raises(GenerationKeywordQueryTooBroad, match="use rarer or more specific terms"):
        context.keyword.search(read_lease.lease_id, "common", limit=10)


@dataclass(frozen=True)
class _Context:
    layout: StorageLayout
    registry: WorkspaceRegistry
    coordinator: SQLiteGenerationCoordinator
    content: SQLiteGenerationContentStore
    keyword: SQLiteGenerationKeywordStore
    artifacts: ChunkArtifactStore
    lease: OperationLease
    generation: StagingGeneration


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
        common_git_dir_identity="common-generation-keyword",
        worktree_git_dir=root / ".git",
        worktree_git_dir_identity="worktree-generation-keyword",
        head_commit="a" * 40,
        branch="develop",
    )
    registry.register_and_submit_initial_index(worktree, cleanup_receipt=_cleanup_receipt("generation-keyword"))
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    runtime = registry.register_runtime(
        runtime_id="runtime_generation_keyword",
        pid=103,
        process_start_identity="start-generation-keyword",
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
    return _Context(
        layout=layout,
        registry=registry,
        coordinator=coordinator,
        content=SQLiteGenerationContentStore(layout, artifacts, clock=lambda: now),
        keyword=SQLiteGenerationKeywordStore(layout, clock=lambda: now),
        artifacts=artifacts,
        lease=lease,
        generation=coordinator.create_staging(lease),
    )


def _membership(artifacts: ChunkArtifactStore, *, suffix: str, text: str) -> StagedChunkMembership:
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


def _delete_fts_membership(
    context: _Context,
    generation_id: str,
    membership: StagedChunkMembership,
) -> None:
    with sqlite3.connect(context.layout.metadata_db) as connection:
        row = connection.execute(
            """
            SELECT document_rowid, text, relative_path, language
            FROM generation_keyword_documents
            WHERE generation_id = ? AND chunk_instance_id = ?
            """,
            (generation_id, membership.chunk_instance_id),
        ).fetchone()
        assert row is not None
        connection.execute(
            """
            INSERT INTO generation_keyword_fts(
                generation_keyword_fts, rowid, text, relative_path, language
            ) VALUES('delete', ?, ?, ?, ?)
            """,
            row,
        )


def _publish(context: _Context, manifest: VerifiedGenerationManifest) -> PublishedSnapshot:
    context.coordinator.record_vector_ready(
        context.lease,
        _vector_commit(context.generation.generation_id, manifest.vector_row_count),
    )
    context.coordinator.mark_ready(context.lease, manifest)
    return context.coordinator.publish(
        context.lease,
        context.generation.generation_id,
        expected_previous_generation_id=None,
    )


def _vector_commit(generation_id: str, row_count: int) -> VerifiedVectorCommit:
    return VerifiedVectorCommit(
        generation_id=generation_id,
        backend_token="vector-commit-generation-keyword",
        manifest_digest=hashlib.sha256(b"vector-digest-generation-keyword").hexdigest(),
        row_count=row_count,
    )


def _cleanup_receipt(seed: str) -> str:
    token = hashlib.sha256(seed.encode()).hexdigest()[:43]
    return f"dolphin-cleanup-v1_{token}"
