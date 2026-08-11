"""Tests for deterministic snapshot-pinned generation retrieval."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from kb.generation import GenerationCoordinatorError, GenerationReadLease, PublishedSnapshot
from kb.generation_keyword import (
    GenerationKeywordError,
    GenerationKeywordQueryTooBroad,
    GenerationKeywordTimeout,
    KeywordSearchHit,
)
from kb.generation_retrieval import (
    GENERATION_BRANCH_CANDIDATE_LIMIT,
    GENERATION_RANKED_TARGET_HORIZON,
    GenerationRetrievalError,
    GenerationRetrievalQueryTooBroad,
    GenerationRetrievalResult,
    GenerationRetrievalTimeout,
    GenerationRetrievalUnavailable,
    rank_generation_candidates,
)
from kb.generation_vector import GenerationVectorTimeout, VectorSearchHit
from kb.services.generation_retrieval import GenerationRetrievalService


def test_fusion_is_deterministic_score_free_and_deduplicated() -> None:
    keyword = (
        KeywordSearchHit(chunk_instance_id="chunk_c", score=1),
        KeywordSearchHit(chunk_instance_id="chunk_a", score=3),
        KeywordSearchHit(chunk_instance_id="chunk_b", score=2),
    )
    vector = (
        VectorSearchHit(chunk_instance_id="chunk_d", score=0.8, distance=0.2),
        VectorSearchHit(chunk_instance_id="chunk_b", score=0.9, distance=0.1),
    )

    targets, horizon_reached = rank_generation_candidates(keyword, vector)

    assert [(target.chunk_instance_id, target.rank, target.sources) for target in targets] == [
        ("chunk_b", 1, ("keyword", "vector")),
        ("chunk_a", 2, ("keyword",)),
        ("chunk_d", 3, ("vector",)),
        ("chunk_c", 4, ("keyword",)),
    ]
    assert horizon_reached is False
    assert all("score" not in target.model_dump() for target in targets)


def test_fusion_distinguishes_omitted_vector_branch_from_an_empty_branch() -> None:
    keyword = (KeywordSearchHit(chunk_instance_id="chunk_a", score=1),)

    lexical, _ = rank_generation_candidates(keyword, None)
    hybrid, _ = rank_generation_candidates(keyword, ())

    assert lexical == hybrid
    assert lexical[0].sources == ("keyword",)


def test_fusion_applies_the_horizon_after_cross_branch_deduplication() -> None:
    keyword = tuple(
        KeywordSearchHit(chunk_instance_id=f"chunk_{index:04d}", score=2_000 - index)
        for index in range(GENERATION_BRANCH_CANDIDATE_LIMIT)
    )
    vector = tuple(
        VectorSearchHit(
            chunk_instance_id=f"chunk_{index:04d}",
            score=(GENERATION_BRANCH_CANDIDATE_LIMIT - index) / GENERATION_BRANCH_CANDIDATE_LIMIT,
            distance=index / GENERATION_BRANCH_CANDIDATE_LIMIT,
        )
        for index in range(GENERATION_BRANCH_CANDIDATE_LIMIT)
    )

    targets, horizon_reached = rank_generation_candidates(keyword, vector)

    assert len(targets) == GENERATION_RANKED_TARGET_HORIZON
    assert [target.rank for target in targets] == list(range(1, GENERATION_RANKED_TARGET_HORIZON + 1))
    assert len({target.chunk_instance_id for target in targets}) == GENERATION_RANKED_TARGET_HORIZON
    assert horizon_reached is True


def test_fusion_rejects_duplicate_or_oversized_branch_candidates() -> None:
    duplicate = KeywordSearchHit(chunk_instance_id="chunk_a", score=1)
    with pytest.raises(GenerationRetrievalError, match="duplicate identities"):
        rank_generation_candidates((duplicate, duplicate), ())

    oversized = tuple(
        KeywordSearchHit(chunk_instance_id=f"chunk_{index}", score=index)
        for index in range(GENERATION_BRANCH_CANDIDATE_LIMIT + 1)
    )
    with pytest.raises(GenerationRetrievalError, match="candidate set is invalid"):
        rank_generation_candidates(oversized, ())


def test_ranked_result_rejects_false_horizon_metadata() -> None:
    with pytest.raises(ValidationError, match="requires a full ranked plan"):
        GenerationRetrievalResult(
            snapshot=_lease().snapshot,
            retrieval_mode="hybrid",
            ranked_targets=(),
            ranked_horizon_reached=True,
        )


def test_service_uses_one_live_snapshot_through_both_branches_and_fusion() -> None:
    coordinator = _Coordinator()
    keyword = _KeywordStore((KeywordSearchHit(chunk_instance_id="chunk_a", score=1),))
    vector = _VectorStore((VectorSearchHit(chunk_instance_id="chunk_a", score=1, distance=0),))
    service = GenerationRetrievalService(coordinator, keyword, vector)

    result = service.retrieve("workspace_1", "where is alpha", query_vector=(0.25,))

    assert result.snapshot == coordinator.lease.snapshot
    assert result.retrieval_mode == "hybrid"
    assert result.ranked_targets[0].sources == ("keyword", "vector")
    assert keyword.calls == [(coordinator.lease.lease_id, "where is alpha", GENERATION_BRANCH_CANDIDATE_LIMIT)]
    assert vector.calls == [(coordinator.lease.lease_id, (0.25,), GENERATION_BRANCH_CANDIDATE_LIMIT)]
    assert coordinator.events == ["acquire", "snapshot", "snapshot", "release"]


def test_service_uses_caller_held_lease_without_releasing_it() -> None:
    coordinator = _Coordinator()
    service = GenerationRetrievalService(coordinator, _KeywordStore(()), _VectorStore(()))

    result = service.retrieve_for_lease(
        coordinator.lease,
        "alpha",
        query_vector=(0.25,),
    )

    assert result.snapshot == coordinator.lease.snapshot
    assert coordinator.events == ["snapshot", "snapshot"]


def test_service_lexical_fallback_never_calls_vector_storage() -> None:
    coordinator = _Coordinator()
    keyword = _KeywordStore((KeywordSearchHit(chunk_instance_id="chunk_a", score=1),))
    vector = _VectorStore(())

    result = GenerationRetrievalService(coordinator, keyword, vector).retrieve(
        "workspace_1",
        "alpha",
        query_vector=None,
    )

    assert result.retrieval_mode == "lexical_structural"
    assert result.ranked_targets[0].sources == ("keyword",)
    assert vector.calls == []
    assert coordinator.events[-1] == "release"


def test_service_normalizes_branch_failure_and_releases_the_reader() -> None:
    coordinator = _Coordinator()
    keyword = _KeywordStore(error=GenerationKeywordError("raw backend detail"))
    service = GenerationRetrievalService(coordinator, keyword, _VectorStore(()))

    with pytest.raises(GenerationRetrievalUnavailable, match="retrieval is unavailable") as failure:
        service.retrieve("workspace_1", "alpha", query_vector=(0.25,))

    assert isinstance(failure.value.__cause__, GenerationKeywordError)
    assert coordinator.events == ["acquire", "snapshot", "release"]


def test_service_preserves_actionable_broad_query_guidance() -> None:
    coordinator = _Coordinator()
    keyword = _KeywordStore(error=GenerationKeywordQueryTooBroad("backend detail"))

    with pytest.raises(GenerationRetrievalQueryTooBroad, match="use rarer or more specific terms") as failure:
        GenerationRetrievalService(coordinator, keyword, _VectorStore(())).retrieve(
            "workspace_1",
            "common",
            query_vector=(0.25,),
        )

    assert failure.value.retryable is False
    assert isinstance(failure.value.__cause__, GenerationKeywordQueryTooBroad)
    assert coordinator.events == ["acquire", "snapshot", "release"]


@pytest.mark.parametrize(
    ("keyword_error", "vector_error"),
    [
        (GenerationKeywordTimeout("keyword deadline"), None),
        (None, GenerationVectorTimeout("vector deadline")),
    ],
)
def test_service_surfaces_branch_deadlines_as_retryable_timeouts(
    keyword_error: Exception | None,
    vector_error: Exception | None,
) -> None:
    coordinator = _Coordinator()
    keyword = _KeywordStore(error=keyword_error)
    vector = _VectorStore((), error=vector_error)

    with pytest.raises(GenerationRetrievalTimeout, match="retry the request") as failure:
        GenerationRetrievalService(coordinator, keyword, vector).retrieve(
            "workspace_1",
            "alpha",
            query_vector=(0.25,),
        )

    assert failure.value.retryable is True
    assert failure.value.__cause__ in (keyword_error, vector_error)
    assert coordinator.events == ["acquire", "snapshot", "release"]


def test_service_preserves_the_primary_failure_when_reader_release_also_fails() -> None:
    branch_error = GenerationKeywordError("raw backend detail")
    coordinator = _Coordinator(release_error=GenerationCoordinatorError("release failed"))
    service = GenerationRetrievalService(
        coordinator,
        _KeywordStore(error=branch_error),
        _VectorStore(()),
    )

    with pytest.raises(GenerationRetrievalUnavailable, match="retrieval is unavailable") as failure:
        service.retrieve("workspace_1", "alpha", query_vector=(0.25,))

    assert failure.value.__cause__ is branch_error
    assert coordinator.events == ["acquire", "snapshot", "release"]


def test_service_reports_reader_release_failure_after_successful_retrieval() -> None:
    coordinator = _Coordinator(release_error=GenerationCoordinatorError("release failed"))
    service = GenerationRetrievalService(coordinator, _KeywordStore(()), _VectorStore(()))

    with pytest.raises(GenerationRetrievalUnavailable, match="could not be released"):
        service.retrieve("workspace_1", "alpha", query_vector=())

    assert coordinator.events == ["acquire", "snapshot", "snapshot", "release"]


def test_service_fails_closed_when_lease_expires_before_fusion_finishes() -> None:
    coordinator = _Coordinator(snapshot_error=GenerationCoordinatorError("expired"))
    service = GenerationRetrievalService(coordinator, _KeywordStore(()), _VectorStore(()))

    with pytest.raises(GenerationRetrievalUnavailable, match="retrieval is unavailable"):
        service.retrieve("workspace_1", "alpha", query_vector=())

    assert coordinator.events == ["acquire", "snapshot", "release"]


class _Coordinator:
    def __init__(
        self,
        *,
        snapshot_error: Exception | None = None,
        release_error: Exception | None = None,
    ) -> None:
        self.lease = _lease()
        self.snapshot_error = snapshot_error
        self.release_error = release_error
        self.events: list[str] = []

    def acquire_read(self, workspace_id: str, *, lease_duration: timedelta) -> GenerationReadLease:
        assert workspace_id == "workspace_1"
        assert timedelta(0) < lease_duration <= timedelta(seconds=60)
        self.events.append("acquire")
        return self.lease

    def snapshot_for_lease(self, lease_id: str) -> PublishedSnapshot:
        assert lease_id == self.lease.lease_id
        self.events.append("snapshot")
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return self.lease.snapshot

    def release_read(self, lease: GenerationReadLease) -> None:
        assert lease == self.lease
        self.events.append("release")
        if self.release_error is not None:
            raise self.release_error


class _KeywordStore:
    def __init__(
        self,
        hits: tuple[KeywordSearchHit, ...] = (),
        *,
        error: Exception | None = None,
    ) -> None:
        self.hits = hits
        self.error = error
        self.calls: list[tuple[str, str, int]] = []

    def search(self, read_lease_id: str, query: str, *, limit: int) -> tuple[KeywordSearchHit, ...]:
        self.calls.append((read_lease_id, query, limit))
        if self.error is not None:
            raise self.error
        return self.hits


class _VectorStore:
    def __init__(
        self,
        hits: tuple[VectorSearchHit, ...],
        *,
        error: Exception | None = None,
    ) -> None:
        self.hits = hits
        self.error = error
        self.calls: list[tuple[str, tuple[float, ...], int]] = []

    def search(self, read_lease_id: str, query_vector: Any, *, limit: int) -> tuple[VectorSearchHit, ...]:
        vector = tuple(query_vector)
        self.calls.append((read_lease_id, vector, limit))
        if self.error is not None:
            raise self.error
        return self.hits


def _lease() -> GenerationReadLease:
    published_at = datetime(2026, 8, 9, tzinfo=UTC)
    snapshot = PublishedSnapshot(
        publication_id="publication_1",
        generation_id="generation_1",
        workspace_id="workspace_1",
        operation_id="operation_1",
        target_fingerprint="a" * 64,
        pipeline_key="pipeline-v1",
        manifest_id="manifest_1",
        manifest_digest="b" * 64,
        vector_commit_token="vector-token",
        vector_digest="c" * 64,
        vector_row_count=1,
        vector_provider="openai",
        vector_model="text-embedding-3-small",
        vector_dimensions=1_536,
        embedding_contract_version=1,
        metadata_item_count=1,
        keyword_item_count=1,
        revision=1,
        published_at=published_at,
    )
    return GenerationReadLease(
        lease_id="read_1",
        snapshot=snapshot,
        acquired_at=published_at,
        expires_at=published_at + timedelta(seconds=30),
    )
