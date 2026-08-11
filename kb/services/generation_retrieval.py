"""Application service for snapshot-pinned generation retrieval."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Protocol

from kb.generation import GenerationCoordinatorError, GenerationReadLease, PublishedSnapshot
from kb.generation_keyword import (
    GenerationKeywordError,
    GenerationKeywordQueryTooBroad,
    GenerationKeywordTimeout,
    KeywordSearchHit,
)
from kb.generation_retrieval import (
    GENERATION_BRANCH_CANDIDATE_LIMIT,
    GenerationRetrievalError,
    GenerationRetrievalQueryTooBroad,
    GenerationRetrievalResult,
    GenerationRetrievalTimeout,
    GenerationRetrievalUnavailable,
    TransientGenerationCandidates,
    canonicalize_generation_candidates,
    rank_generation_candidates,
)
from kb.generation_vector import GenerationVectorError, GenerationVectorTimeout, VectorSearchHit
from kb.search_admission import AdmittedSearchWorkspace

_RETRIEVAL_READ_LEASE_DURATION = timedelta(seconds=30)


class _RetrievalCoordinator(Protocol):
    def acquire_read(self, workspace_id: str, *, lease_duration: timedelta) -> GenerationReadLease: ...

    def snapshot_for_lease(self, lease_id: str) -> PublishedSnapshot: ...

    def release_read(self, lease: GenerationReadLease) -> None: ...


class _KeywordReader(Protocol):
    def search(self, read_lease_id: str, query: str, *, limit: int) -> tuple[KeywordSearchHit, ...]: ...


class _VectorReader(Protocol):
    def search(
        self,
        read_lease_id: str,
        query_vector: Sequence[float],
        *,
        limit: int,
    ) -> tuple[VectorSearchHit, ...]: ...


class GenerationRetrievalService:
    """Retrieve and fuse candidates while one exact publication remains pinned."""

    def __init__(
        self,
        coordinator: _RetrievalCoordinator,
        keyword_store: _KeywordReader,
        vector_store: _VectorReader,
    ) -> None:
        self._coordinator = coordinator
        self._keyword_store = keyword_store
        self._vector_store = vector_store

    def retrieve(
        self,
        workspace_id: str,
        query: str,
        *,
        query_vector: Sequence[float] | None,
    ) -> GenerationRetrievalResult:
        """Build one score-free ranked plan; ``None`` explicitly omits vector retrieval."""

        try:
            lease = self._coordinator.acquire_read(
                workspace_id,
                lease_duration=_RETRIEVAL_READ_LEASE_DURATION,
            )
        except GenerationCoordinatorError as exc:
            raise GenerationRetrievalUnavailable("Dolphin published generation is unavailable") from exc

        try:
            return self._retrieve_for_lease(
                lease,
                query,
                query_vector=query_vector,
                deadline_exceeded=lambda: False,
            )
        finally:
            primary_failure = sys.exception()
            try:
                self._coordinator.release_read(lease)
            except GenerationCoordinatorError as exc:
                if primary_failure is None:
                    raise GenerationRetrievalUnavailable("Dolphin generation read lease could not be released") from exc

    def retrieve_for_admitted_workspace(
        self,
        admitted: AdmittedSearchWorkspace,
        query: str,
        *,
        query_vector: Sequence[float] | None,
    ) -> GenerationRetrievalResult:
        """Retrieve under admitted caller-held authority without releasing it."""

        return self._retrieve_for_lease(
            admitted.read_lease,
            query,
            query_vector=query_vector,
            deadline_exceeded=admitted.deadline_exceeded,
        )

    def candidates_for_admitted_workspace(
        self,
        admitted: AdmittedSearchWorkspace,
        query: str,
        *,
        query_vector: Sequence[float] | None,
    ) -> TransientGenerationCandidates:
        """Return canonical transient candidates under caller-held authority."""

        return self._candidates_for_lease(
            admitted.read_lease,
            query,
            query_vector=query_vector,
            deadline_exceeded=admitted.deadline_exceeded,
        )

    def _retrieve_for_lease(
        self,
        lease: GenerationReadLease,
        query: str,
        *,
        query_vector: Sequence[float] | None,
        deadline_exceeded: Callable[[], bool],
    ) -> GenerationRetrievalResult:
        """Execute bounded retrieval under one exact retained lease."""

        candidates = self._candidates_for_lease(
            lease,
            query,
            query_vector=query_vector,
            deadline_exceeded=deadline_exceeded,
        )
        ranked_targets, horizon_reached = rank_generation_candidates(
            candidates.keyword_hits,
            candidates.vector_hits,
        )
        return GenerationRetrievalResult(
            snapshot=candidates.snapshot,
            retrieval_mode=candidates.retrieval_mode,
            ranked_targets=ranked_targets,
            ranked_horizon_reached=horizon_reached,
        )

    def _candidates_for_lease(
        self,
        lease: GenerationReadLease,
        query: str,
        *,
        query_vector: Sequence[float] | None,
        deadline_exceeded: Callable[[], bool],
    ) -> TransientGenerationCandidates:
        """Execute bounded branches and retain scores only for immediate in-process fusion."""

        try:
            _require_search_deadline(deadline_exceeded)
            if self._coordinator.snapshot_for_lease(lease.lease_id) != lease.snapshot:
                raise GenerationRetrievalUnavailable("Dolphin generation read lease changed before retrieval")
            keyword_hits = self._keyword_store.search(
                lease.lease_id,
                query,
                limit=GENERATION_BRANCH_CANDIDATE_LIMIT,
            )
            _require_search_deadline(deadline_exceeded)
            vector_hits = (
                None
                if query_vector is None
                else self._vector_store.search(
                    lease.lease_id,
                    query_vector,
                    limit=GENERATION_BRANCH_CANDIDATE_LIMIT,
                )
            )
            _require_search_deadline(deadline_exceeded)
            keyword_hits, vector_hits = canonicalize_generation_candidates(keyword_hits, vector_hits)
            if self._coordinator.snapshot_for_lease(lease.lease_id) != lease.snapshot:
                raise GenerationRetrievalUnavailable("Dolphin generation read lease changed during retrieval")
            return TransientGenerationCandidates(
                snapshot=lease.snapshot,
                retrieval_mode="lexical_structural" if vector_hits is None else "hybrid",
                keyword_hits=keyword_hits,
                vector_hits=vector_hits,
            )
        except GenerationKeywordQueryTooBroad as exc:
            raise GenerationRetrievalQueryTooBroad(
                "Dolphin keyword query is too broad; use rarer or more specific terms"
            ) from exc
        except (GenerationKeywordTimeout, GenerationVectorTimeout) as exc:
            raise GenerationRetrievalTimeout("Dolphin generation retrieval timed out; retry the request") from exc
        except GenerationRetrievalError:
            raise
        except (GenerationCoordinatorError, GenerationKeywordError, GenerationVectorError) as exc:
            raise GenerationRetrievalUnavailable("Dolphin generation retrieval is unavailable") from exc


def _require_search_deadline(deadline_exceeded: Callable[[], bool]) -> None:
    if deadline_exceeded():
        raise GenerationRetrievalTimeout("Dolphin search read deadline expired; retry the request")
