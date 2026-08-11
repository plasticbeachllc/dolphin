"""Async first-page search orchestration over exact admitted publications."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Coroutine, Sequence
from typing import Protocol

from kb.generation_retrieval import TransientGenerationCandidates
from kb.query_embedding import QueryEmbeddingResolution
from kb.search_admission import AdmittedSearchWorkspace, SearchCoverage
from kb.search_execution import FirstPageSearchPlan, build_first_page_search_plan
from kb.services.workspace_resolution import WorkspaceResolution

_MAX_CONCURRENT_WORKSPACE_RETRIEVALS = 8


class _CoverageExecutor(Protocol):
    async def execute_async(
        self,
        workspace_ids: Sequence[str] | None,
        operation: Callable[[SearchCoverage], Coroutine[object, object, FirstPageSearchPlan]],
        *,
        current_resolution: WorkspaceResolution | None = None,
    ) -> FirstPageSearchPlan: ...


class _EmbeddingResolver(Protocol):
    async def resolve(self, query: str) -> QueryEmbeddingResolution: ...


class _CandidateRetriever(Protocol):
    def candidates_for_admitted_workspace(
        self,
        admitted: AdmittedSearchWorkspace,
        query: str,
        *,
        query_vector: Sequence[float] | None,
    ) -> TransientGenerationCandidates: ...


class SearchExecutionService:
    """Resolve one embedding and one global ranked plan under retained coverage."""

    def __init__(
        self,
        coverage: _CoverageExecutor,
        embeddings: _EmbeddingResolver,
        retrieval: _CandidateRetriever,
    ) -> None:
        self._coverage = coverage
        self._embeddings = embeddings
        self._retrieval = retrieval
        self._retrieval_slots = asyncio.Semaphore(_MAX_CONCURRENT_WORKSPACE_RETRIEVALS)

    async def execute_first_page(
        self,
        query: str,
        workspace_ids: Sequence[str] | None,
        *,
        current_resolution: WorkspaceResolution | None = None,
    ) -> FirstPageSearchPlan:
        """Build one eager first-page plan; public filters and pagination remain upstream."""

        async def execute_admitted(coverage: SearchCoverage) -> FirstPageSearchPlan:
            embedding = await self._embeddings.resolve(query)
            candidates = await self._retrieve_all(coverage, query, embedding)
            return build_first_page_search_plan(candidates, embedding)

        return await self._coverage.execute_async(
            workspace_ids,
            execute_admitted,
            current_resolution=current_resolution,
        )

    async def _retrieve_all(
        self,
        coverage: SearchCoverage,
        query: str,
        embedding: QueryEmbeddingResolution,
    ) -> tuple[TransientGenerationCandidates, ...]:
        async def retrieve(admitted: AdmittedSearchWorkspace) -> TransientGenerationCandidates:
            async with self._retrieval_slots:
                return await asyncio.to_thread(
                    self._retrieval.candidates_for_admitted_workspace,
                    admitted,
                    query,
                    query_vector=embedding.vector,
                )

        async def collect() -> tuple[TransientGenerationCandidates | BaseException, ...]:
            return tuple(
                await asyncio.gather(
                    *(retrieve(admitted) for admitted in coverage.workspaces),
                    return_exceptions=True,
                )
            )

        group = asyncio.create_task(collect(), name="dolphin-search-retrieval")
        try:
            outcomes = await asyncio.shield(group)
        except BaseException:
            primary_failure = sys.exception()
            await _drain_after_cancellation(group)
            assert primary_failure is not None
            raise primary_failure

        candidates: list[TransientGenerationCandidates] = []
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
            candidates.append(outcome)
        return tuple(candidates)


async def _drain_after_cancellation[TaskResultT](task: asyncio.Task[TaskResultT]) -> None:
    """Keep admitted leases live until already-dispatched bounded retrieval finishes."""

    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except BaseException:
            return
