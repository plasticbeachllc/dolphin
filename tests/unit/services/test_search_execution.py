"""Tests for eager globally ranked first-page search execution."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest

from kb.generation import GenerationReadLease, PublishedSnapshot
from kb.generation_keyword import KeywordSearchHit
from kb.generation_retrieval import TransientGenerationCandidates
from kb.generation_vector import VectorSearchHit
from kb.query_embedding import QueryEmbeddingResolution
from kb.search_admission import AdmittedSearchWorkspace, SearchCoverage, SearchWorkspaceMissing
from kb.search_execution import SearchExecutionError, build_first_page_search_plan
from kb.services.search_execution import SearchExecutionService
from kb.services.workspace_registry import WorkspaceSnapshot

_NOW = datetime(2026, 8, 10, tzinfo=UTC)


def test_global_fusion_preserves_cross_workspace_targets_and_discards_scores() -> None:
    first = _candidates(
        "ws_a",
        keyword=(
            KeywordSearchHit(chunk_instance_id="shared", score=3),
            KeywordSearchHit(chunk_instance_id="other", score=2),
        ),
        vector=(VectorSearchHit(chunk_instance_id="shared", score=0.9, distance=0.1),),
    )
    second = _candidates(
        "ws_b",
        keyword=(KeywordSearchHit(chunk_instance_id="shared", score=5),),
        vector=(),
    )

    plan = build_first_page_search_plan((second, first), _embedding())

    assert [
        (target.workspace_id, target.chunk_instance_id, target.rank, target.sources) for target in plan.ranked_targets
    ] == [
        ("ws_a", "shared", 1, ("keyword", "vector")),
        ("ws_b", "shared", 2, ("keyword",)),
        ("ws_a", "other", 3, ("keyword",)),
    ]
    assert [snapshot.workspace_id for snapshot in plan.snapshots] == ["ws_a", "ws_b"]
    assert plan.ranked_targets_retained == 3
    assert "score" not in plan.model_dump_json()


def test_global_fusion_round_robins_local_ranks_without_comparing_cross_index_scores() -> None:
    weak = _candidates(
        "ws_a",
        keyword=(
            KeywordSearchHit(chunk_instance_id="weak", score=1),
            KeywordSearchHit(chunk_instance_id="weaker", score=0.5),
        ),
        vector=None,
    )
    strong = _candidates(
        "ws_b",
        keyword=(KeywordSearchHit(chunk_instance_id="strong", score=10),),
        vector=None,
    )

    plan = build_first_page_search_plan((weak, strong), _embedding(degraded=True))

    assert [(target.workspace_id, target.chunk_instance_id) for target in plan.ranked_targets] == [
        ("ws_a", "weak"),
        ("ws_b", "strong"),
        ("ws_a", "weaker"),
    ]


def test_global_fusion_reports_one_horizon_after_all_workspace_candidates() -> None:
    first = _candidates(
        "ws_a",
        keyword=tuple(
            KeywordSearchHit(chunk_instance_id=f"a_{index:04d}", score=1_000 - index) for index in range(500)
        ),
        vector=(),
    )
    second = _candidates(
        "ws_b",
        keyword=(KeywordSearchHit(chunk_instance_id="b_0000", score=1),),
        vector=(),
    )

    plan = build_first_page_search_plan((first, second), _embedding())

    assert len(plan.ranked_targets) == 500
    assert plan.ranked_horizon_reached is True
    assert [target.rank for target in plan.ranked_targets] == list(range(1, 501))


def test_lexical_plan_carries_prominent_degradation_without_vector_targets() -> None:
    plan = build_first_page_search_plan(
        (
            _candidates(
                "ws_a",
                keyword=(KeywordSearchHit(chunk_instance_id="chunk", score=1),),
                vector=None,
            ),
        ),
        _embedding(degraded=True),
    )

    assert plan.retrieval_mode == "lexical_structural"
    assert plan.query_embedding_source == "unavailable"
    assert plan.degraded_reason == "timeout"
    assert plan.retryable is True
    assert plan.ranked_targets[0].sources == ("keyword",)


def test_global_fusion_rejects_candidate_branch_state_that_disagrees_with_its_mode() -> None:
    malformed = TransientGenerationCandidates(
        snapshot=_snapshot("ws_a"),
        retrieval_mode="hybrid",
        keyword_hits=(),
        vector_hits=None,
    )

    with pytest.raises(SearchExecutionError, match="branch state is inconsistent"):
        build_first_page_search_plan((malformed,), _embedding())


@pytest.mark.asyncio
async def test_service_admits_before_one_embedding_and_retrieves_every_workspace() -> None:
    coverage = _coverage("ws_a", "ws_b")
    events: list[str] = []
    executor = _CoverageExecutor(coverage, events)
    embeddings = _EmbeddingResolver(_embedding(), events)
    retrieval = _CandidateRetriever(
        {
            "ws_a": _candidates(
                "ws_a",
                keyword=(KeywordSearchHit(chunk_instance_id="a", score=1),),
                vector=(),
            ),
            "ws_b": _candidates(
                "ws_b",
                keyword=(KeywordSearchHit(chunk_instance_id="b", score=1),),
                vector=(),
            ),
        },
        events,
    )

    plan = await SearchExecutionService(executor, embeddings, retrieval).execute_first_page(
        "find the behavior",
        ["ws_b", "ws_a"],
    )

    assert events[:2] == ["coverage", "embedding"]
    assert events.count("embedding") == 1
    assert set(events[2:]) == {"retrieve:ws_a", "retrieve:ws_b"}
    assert [target.workspace_id for target in plan.ranked_targets] == ["ws_a", "ws_b"]
    assert executor.requested_workspace_ids == ("ws_b", "ws_a")
    assert retrieval.query_vectors and all(len(vector) == 1_536 for vector in retrieval.query_vectors)


@pytest.mark.asyncio
async def test_coverage_failure_performs_no_embedding_or_retrieval_work() -> None:
    events: list[str] = []
    executor = _CoverageExecutor(_coverage("ws_a"), events, error=SearchWorkspaceMissing(("ws_missing",)))
    service = SearchExecutionService(
        executor,
        _EmbeddingResolver(_embedding(), events),
        _CandidateRetriever({}, events),
    )

    with pytest.raises(SearchWorkspaceMissing):
        await service.execute_first_page("query", ["ws_missing"])

    assert events == ["coverage"]


@pytest.mark.asyncio
async def test_service_degradation_omits_vector_retrieval_for_every_workspace() -> None:
    events: list[str] = []
    retrieval = _CandidateRetriever(
        {
            "ws_a": _candidates(
                "ws_a",
                keyword=(KeywordSearchHit(chunk_instance_id="a", score=1),),
                vector=None,
            )
        },
        events,
    )

    plan = await SearchExecutionService(
        _CoverageExecutor(_coverage("ws_a"), events),
        _EmbeddingResolver(_embedding(degraded=True), events),
        retrieval,
    ).execute_first_page("query", ["ws_a"])

    assert plan.retrieval_mode == "lexical_structural"
    assert plan.degraded_reason == "timeout"
    assert retrieval.query_vectors == [()]


@pytest.mark.asyncio
async def test_retrieval_failure_waits_for_every_dispatched_workspace() -> None:
    events: list[str] = []
    completed = Event()
    retrieval = _CandidateRetriever(
        {"ws_a": RuntimeError("first failed"), "ws_b": _candidates("ws_b", keyword=(), vector=())},
        events,
        slow_workspace="ws_b",
        slow_completed=completed,
    )
    service = SearchExecutionService(
        _CoverageExecutor(_coverage("ws_a", "ws_b"), events),
        _EmbeddingResolver(_embedding(), events),
        retrieval,
    )

    with pytest.raises(RuntimeError, match="first failed"):
        await service.execute_first_page("query", ["ws_a", "ws_b"])

    assert completed.is_set()


@pytest.mark.asyncio
async def test_cancellation_drains_dispatched_retrieval_before_returning() -> None:
    events: list[str] = []
    started = Event()
    release = Event()
    retrieval = _CandidateRetriever(
        {"ws_a": _candidates("ws_a", keyword=(), vector=())},
        events,
        blocker=(started, release),
    )
    service = SearchExecutionService(
        _CoverageExecutor(_coverage("ws_a"), events),
        _EmbeddingResolver(_embedding(), events),
        retrieval,
    )
    execution = asyncio.create_task(service.execute_first_page("query", ["ws_a"]))
    assert await asyncio.to_thread(started.wait, 1)

    execution.cancel()
    await asyncio.sleep(0.02)
    assert not execution.done()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(execution, timeout=1)


@pytest.mark.asyncio
async def test_cancellation_does_not_start_workspace_retrievals_waiting_for_capacity() -> None:
    workspace_ids = tuple(f"ws_{index:02d}" for index in range(9))
    started: list[str] = []
    all_slots_started = Event()
    release = Event()
    retrieval = _CapacityBlockingRetriever(started, all_slots_started, release)
    service = SearchExecutionService(
        _CoverageExecutor(_coverage(*workspace_ids), []),
        _EmbeddingResolver(_embedding(), []),
        retrieval,
    )
    execution = asyncio.create_task(service.execute_first_page("query", workspace_ids))
    assert await asyncio.to_thread(all_slots_started.wait, 1)

    execution.cancel()
    await asyncio.sleep(0.02)
    assert len(started) == 8
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(execution, timeout=1)
    assert len(started) == 8


class _CoverageExecutor:
    def __init__(
        self,
        coverage: SearchCoverage,
        events: list[str],
        *,
        error: Exception | None = None,
    ) -> None:
        self.coverage = coverage
        self.events = events
        self.error = error
        self.requested_workspace_ids: tuple[str, ...] | None = None

    async def execute_async(self, workspace_ids, operation, *, current_resolution=None):
        del current_resolution
        self.events.append("coverage")
        self.requested_workspace_ids = None if workspace_ids is None else tuple(workspace_ids)
        if self.error is not None:
            raise self.error
        return await operation(self.coverage)


class _EmbeddingResolver:
    def __init__(self, resolution: QueryEmbeddingResolution, events: list[str]) -> None:
        self.resolution = resolution
        self.events = events

    async def resolve(self, query: str) -> QueryEmbeddingResolution:
        assert query
        self.events.append("embedding")
        return self.resolution


class _CandidateRetriever:
    def __init__(
        self,
        outcomes: dict[str, TransientGenerationCandidates | Exception],
        events: list[str],
        *,
        slow_workspace: str | None = None,
        slow_completed: Event | None = None,
        blocker: tuple[Event, Event] | None = None,
    ) -> None:
        self.outcomes = outcomes
        self.events = events
        self.slow_workspace = slow_workspace
        self.slow_completed = slow_completed
        self.blocker = blocker
        self.query_vectors: list[tuple[float, ...]] = []

    def candidates_for_admitted_workspace(
        self,
        admitted: AdmittedSearchWorkspace,
        query: str,
        *,
        query_vector,
    ) -> TransientGenerationCandidates:
        assert query
        self.events.append(f"retrieve:{admitted.workspace.workspace_id}")
        self.query_vectors.append(tuple(query_vector) if query_vector is not None else ())
        if self.blocker is not None:
            started, release = self.blocker
            started.set()
            assert release.wait(timeout=1)
        if admitted.workspace.workspace_id == self.slow_workspace:
            time.sleep(0.03)
            assert self.slow_completed is not None
            self.slow_completed.set()
        outcome = self.outcomes[admitted.workspace.workspace_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _CapacityBlockingRetriever:
    def __init__(self, started: list[str], all_slots_started: Event, release: Event) -> None:
        self.started = started
        self.all_slots_started = all_slots_started
        self.release = release

    def candidates_for_admitted_workspace(
        self,
        admitted: AdmittedSearchWorkspace,
        query: str,
        *,
        query_vector,
    ) -> TransientGenerationCandidates:
        assert query and query_vector is not None
        self.started.append(admitted.workspace.workspace_id)
        if len(self.started) == 8:
            self.all_slots_started.set()
        assert self.release.wait(timeout=1)
        return _candidates(admitted.workspace.workspace_id, keyword=(), vector=())


def _embedding(*, degraded: bool = False) -> QueryEmbeddingResolution:
    from kb.artifacts import identify_embedding_input

    return QueryEmbeddingResolution(
        identity=identify_embedding_input("query"),
        vector=None if degraded else (1.0, *([0.0] * 1_535)),
        source="unavailable" if degraded else "cache",
        retrieval_mode="lexical_structural" if degraded else "hybrid",
        degraded_reason="timeout" if degraded else None,
        retryable=degraded,
        cache_write="not_attempted" if degraded else "not_needed",
    )


def _candidates(
    workspace_id: str,
    *,
    keyword: tuple[KeywordSearchHit, ...],
    vector: tuple[VectorSearchHit, ...] | None,
) -> TransientGenerationCandidates:
    return TransientGenerationCandidates(
        snapshot=_snapshot(workspace_id),
        retrieval_mode="lexical_structural" if vector is None else "hybrid",
        keyword_hits=keyword,
        vector_hits=vector,
    )


def _coverage(*workspace_ids: str) -> SearchCoverage:
    return SearchCoverage(workspaces=tuple(_admitted(workspace_id) for workspace_id in sorted(workspace_ids)))


def _admitted(workspace_id: str) -> AdmittedSearchWorkspace:
    snapshot = _snapshot(workspace_id)
    return AdmittedSearchWorkspace(
        workspace=WorkspaceSnapshot(
            workspace_id=workspace_id,
            repository_id=f"repo_{workspace_id}",
            repository_display_name=workspace_id,
            workspace_display_name=workspace_id,
            root=f"/repos/{workspace_id}",
            branch="develop",
            head_commit="a" * 40,
            state="ready",
        ),
        read_lease=GenerationReadLease(
            lease_id=f"read_{workspace_id}",
            snapshot=snapshot,
            acquired_at=_NOW,
            expires_at=_NOW + timedelta(seconds=30),
        ),
    )


def _snapshot(workspace_id: str) -> PublishedSnapshot:
    return PublishedSnapshot(
        publication_id=f"publication_{workspace_id}",
        generation_id=f"generation_{workspace_id}",
        workspace_id=workspace_id,
        operation_id=f"operation_{workspace_id}",
        target_fingerprint="a" * 64,
        pipeline_key="pipeline-v1",
        manifest_id=f"manifest_{workspace_id}",
        manifest_digest="b" * 64,
        vector_commit_token=f"vector-{workspace_id}",
        vector_digest="c" * 64,
        vector_row_count=1,
        vector_provider="openai",
        vector_model="text-embedding-3-small",
        vector_dimensions=1_536,
        embedding_contract_version=1,
        metadata_item_count=1,
        keyword_item_count=1,
        revision=1,
        published_at=_NOW,
    )
