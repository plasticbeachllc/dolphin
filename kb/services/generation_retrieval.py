"""Application service for snapshot-pinned generation retrieval."""

from __future__ import annotations

import sys
from collections.abc import Sequence
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
    rank_generation_candidates,
)
from kb.generation_vector import GenerationVectorError, GenerationVectorTimeout, VectorSearchHit

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
            return self.retrieve_for_lease(lease, query, query_vector=query_vector)
        finally:
            primary_failure = sys.exception()
            try:
                self._coordinator.release_read(lease)
            except GenerationCoordinatorError as exc:
                if primary_failure is None:
                    raise GenerationRetrievalUnavailable("Dolphin generation read lease could not be released") from exc

    def retrieve_for_lease(
        self,
        lease: GenerationReadLease,
        query: str,
        *,
        query_vector: Sequence[float] | None,
    ) -> GenerationRetrievalResult:
        """Retrieve under caller-held authority without releasing its reader lease."""

        try:
            if self._coordinator.snapshot_for_lease(lease.lease_id) != lease.snapshot:
                raise GenerationRetrievalUnavailable("Dolphin generation read lease changed before retrieval")
            keyword_hits = self._keyword_store.search(
                lease.lease_id,
                query,
                limit=GENERATION_BRANCH_CANDIDATE_LIMIT,
            )
            vector_hits = (
                None
                if query_vector is None
                else self._vector_store.search(
                    lease.lease_id,
                    query_vector,
                    limit=GENERATION_BRANCH_CANDIDATE_LIMIT,
                )
            )
            ranked_targets, horizon_reached = rank_generation_candidates(keyword_hits, vector_hits)
            if self._coordinator.snapshot_for_lease(lease.lease_id) != lease.snapshot:
                raise GenerationRetrievalUnavailable("Dolphin generation read lease changed during retrieval")
            return GenerationRetrievalResult(
                snapshot=lease.snapshot,
                retrieval_mode="lexical_structural" if vector_hits is None else "hybrid",
                ranked_targets=ranked_targets,
                ranked_horizon_reached=horizon_reached,
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
