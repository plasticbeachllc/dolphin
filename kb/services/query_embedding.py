"""Application service for exact query-embedding admission and degradation."""

from __future__ import annotations

import asyncio
from typing import Protocol

from kb.artifacts import ArtifactInputInvalid, EmbeddingInputIdentity, identify_embedding_input
from kb.generation_vector import canonicalize_embedding_vector
from kb.query_embedding import (
    MAX_QUERY_CHARACTERS,
    CachedEmbedding,
    EmbeddingContractViolation,
    QueryEmbeddingResolution,
    TransientProviderFailure,
)
from kb.store.embedding_cache import EmbeddingCacheCorrupt, EmbeddingCacheError, EmbeddingCacheUnavailable

_MAX_CONCURRENT_QUERY_PROVIDER_CALLS = 4


class _EmbeddingCache(Protocol):
    def get(self, identity: EmbeddingInputIdentity) -> CachedEmbedding | None: ...

    def put(self, identity: EmbeddingInputIdentity, vector: tuple[float, ...]) -> CachedEmbedding: ...


class _QueryProvider(Protocol):
    async def embed_query(self, query: str) -> tuple[float, ...]: ...


class QueryEmbeddingService:
    """Prefer exact cache state and share one bounded provider outcome per identity."""

    def __init__(self, cache: _EmbeddingCache, provider: _QueryProvider) -> None:
        self._cache = cache
        self._provider = provider
        self._provider_slots = asyncio.Semaphore(_MAX_CONCURRENT_QUERY_PROVIDER_CALLS)
        self._single_flights: dict[str, asyncio.Task[QueryEmbeddingResolution]] = {}
        self._single_flights_guard = asyncio.Lock()

    async def resolve(self, query: str) -> QueryEmbeddingResolution:
        identity = _query_identity(query)
        cached = await self._cached(identity)
        if cached is not None:
            return _cached_resolution(identity, cached)

        async with self._single_flights_guard:
            flight = self._single_flights.get(identity.cache_key)
            if flight is None:
                flight = asyncio.create_task(
                    self._resolve_miss(query, identity),
                    name=f"dolphin-query-embedding-{identity.cache_key[:12]}",
                )
                self._single_flights[identity.cache_key] = flight
                flight.add_done_callback(
                    lambda completed, cache_key=identity.cache_key: self._schedule_flight_retirement(
                        cache_key,
                        completed,
                    )
                )
        return await asyncio.shield(flight)

    async def _resolve_miss(
        self,
        query: str,
        identity: EmbeddingInputIdentity,
    ) -> QueryEmbeddingResolution:
        cached = await self._cached(identity)
        if cached is not None:
            return _cached_resolution(identity, cached)

        try:
            async with self._provider_slots:
                live_vector = await self._provider.embed_query(query)
        except TransientProviderFailure as exc:
            return QueryEmbeddingResolution(
                identity=identity,
                vector=None,
                source="unavailable",
                retrieval_mode="lexical_structural",
                degraded_reason=exc.category,
                retryable=True,
                cache_write="not_attempted",
            )
        try:
            live_vector = canonicalize_embedding_vector(live_vector)
        except (TypeError, ValueError):
            raise EmbeddingContractViolation("Dolphin query embedding response violates the fixed contract") from None

        try:
            persisted = await asyncio.to_thread(self._cache.put, identity, live_vector)
        except EmbeddingCacheUnavailable:
            vector = live_vector
            cache_write = "skipped_unavailable"
        except (EmbeddingCacheCorrupt, EmbeddingCacheError):
            raise EmbeddingContractViolation("Dolphin query embedding cache violates the fixed contract") from None
        else:
            if persisted.identity != identity:
                raise EmbeddingContractViolation("Dolphin query embedding cache violates the fixed contract")
            vector = persisted.vector
            cache_write = "persisted"
        return QueryEmbeddingResolution(
            identity=identity,
            vector=vector,
            source="live",
            retrieval_mode="hybrid",
            degraded_reason=None,
            retryable=False,
            cache_write=cache_write,
        )

    async def _cached(self, identity: EmbeddingInputIdentity) -> CachedEmbedding | None:
        try:
            cached = await asyncio.to_thread(self._cache.get, identity)
        except EmbeddingCacheUnavailable:
            return None
        except (EmbeddingCacheCorrupt, EmbeddingCacheError):
            raise EmbeddingContractViolation("Dolphin query embedding cache violates the fixed contract") from None
        if cached is not None and cached.identity != identity:
            raise EmbeddingContractViolation("Dolphin query embedding cache violates the fixed contract")
        return cached

    def _schedule_flight_retirement(
        self,
        cache_key: str,
        flight: asyncio.Task[QueryEmbeddingResolution],
    ) -> None:
        asyncio.create_task(
            self._retire_flight(cache_key, flight),
            name=f"dolphin-query-embedding-retire-{cache_key[:12]}",
        )

    async def _retire_flight(
        self,
        cache_key: str,
        flight: asyncio.Task[QueryEmbeddingResolution],
    ) -> None:
        if not flight.cancelled():
            flight.exception()
        async with self._single_flights_guard:
            if self._single_flights.get(cache_key) is flight:
                del self._single_flights[cache_key]


def _cached_resolution(
    identity: EmbeddingInputIdentity,
    cached: CachedEmbedding,
) -> QueryEmbeddingResolution:
    return QueryEmbeddingResolution(
        identity=identity,
        vector=cached.vector,
        source="cache",
        retrieval_mode="hybrid",
        degraded_reason=None,
        retryable=False,
        cache_write="not_needed",
    )


def _query_identity(query: str) -> EmbeddingInputIdentity:
    if not isinstance(query, str) or not 1 <= len(query) <= MAX_QUERY_CHARACTERS:
        raise EmbeddingContractViolation("Dolphin query embedding input is invalid")
    try:
        return identify_embedding_input(query)
    except ArtifactInputInvalid:
        raise EmbeddingContractViolation("Dolphin query embedding input is invalid") from None
