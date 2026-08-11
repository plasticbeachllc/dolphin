"""Application service for exact query-embedding admission and degradation."""

from __future__ import annotations

import asyncio
import threading
import weakref
from typing import Protocol

from kb.artifacts import ArtifactInputInvalid, EmbeddingInputIdentity, identify_embedding_input
from kb.generation_vector import canonicalize_embedding_vector
from kb.query_embedding import (
    MAX_QUERY_CHARACTERS,
    CachedEmbedding,
    EmbeddingContractViolation,
    QueryEmbeddingOverloaded,
    QueryEmbeddingResolution,
    TransientProviderFailure,
)
from kb.store.embedding_cache import EmbeddingCacheCorrupt, EmbeddingCacheError, EmbeddingCacheUnavailable

_MAX_CONCURRENT_QUERY_PROVIDER_CALLS = 4
_MAX_CONCURRENT_QUERY_EMBEDDING_ADMISSIONS = 32
_MAX_CONCURRENT_QUERY_CACHE_CALLS = 4


class _EmbeddingCache(Protocol):
    def get(self, identity: EmbeddingInputIdentity) -> CachedEmbedding | None: ...

    def put(self, identity: EmbeddingInputIdentity, vector: tuple[float, ...]) -> CachedEmbedding: ...


class _QueryProvider(Protocol):
    async def embed_query(self, query: str) -> tuple[float, ...]: ...


class _RuntimeAdmission:
    """One event-loop-wide capacity boundary shared by every service instance."""

    def __init__(self) -> None:
        self.guard = asyncio.Lock()
        self.active = 0
        self.provider_slots = asyncio.Semaphore(_MAX_CONCURRENT_QUERY_PROVIDER_CALLS)
        self.cache_slots = asyncio.Semaphore(_MAX_CONCURRENT_QUERY_CACHE_CALLS)

    async def try_acquire(self) -> bool:
        async with self.guard:
            if self.active >= _MAX_CONCURRENT_QUERY_EMBEDDING_ADMISSIONS:
                return False
            self.active += 1
            return True

    async def release(self) -> None:
        async with self.guard:
            if self.active <= 0:
                raise RuntimeError("Dolphin query embedding admission accounting is invalid")
            self.active -= 1


_RUNTIME_ADMISSIONS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _RuntimeAdmission] = (
    weakref.WeakKeyDictionary()
)
_RUNTIME_ADMISSIONS_GUARD = threading.Lock()


class QueryEmbeddingService:
    """Prefer exact cache state and share one bounded provider outcome per identity."""

    def __init__(self, cache: _EmbeddingCache, provider: _QueryProvider) -> None:
        self._cache = cache
        self._provider = provider
        self._single_flights: dict[str, asyncio.Task[QueryEmbeddingResolution]] = {}
        self._single_flights_guard = asyncio.Lock()

    async def resolve(self, query: str) -> QueryEmbeddingResolution:
        identity = _query_identity(query)
        runtime = _runtime_admission()
        async with self._single_flights_guard:
            flight = self._single_flights.get(identity.cache_key)
            if flight is None:
                if not await runtime.try_acquire():
                    raise QueryEmbeddingOverloaded("Dolphin query embedding admission is temporarily full")
                flight = asyncio.create_task(
                    self._run_flight(query, identity, runtime),
                    name=f"dolphin-query-embedding-{identity.cache_key[:12]}",
                )
                self._single_flights[identity.cache_key] = flight
                flight.add_done_callback(_consume_flight_exception)
        return await asyncio.shield(flight)

    async def _run_flight(
        self,
        query: str,
        identity: EmbeddingInputIdentity,
        runtime: _RuntimeAdmission,
    ) -> QueryEmbeddingResolution:
        try:
            return await self._resolve_admitted(query, identity, runtime)
        finally:
            try:
                await runtime.release()
            finally:
                flight = asyncio.current_task()
                async with self._single_flights_guard:
                    if self._single_flights.get(identity.cache_key) is flight:
                        del self._single_flights[identity.cache_key]

    async def _resolve_admitted(
        self,
        query: str,
        identity: EmbeddingInputIdentity,
        runtime: _RuntimeAdmission,
    ) -> QueryEmbeddingResolution:
        cached = await self._cached(identity, runtime)
        if cached is not None:
            return _cached_resolution(identity, cached)

        try:
            async with runtime.provider_slots:
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
            async with runtime.cache_slots:
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

    async def _cached(
        self,
        identity: EmbeddingInputIdentity,
        runtime: _RuntimeAdmission,
    ) -> CachedEmbedding | None:
        try:
            async with runtime.cache_slots:
                cached = await asyncio.to_thread(self._cache.get, identity)
        except EmbeddingCacheUnavailable:
            return None
        except (EmbeddingCacheCorrupt, EmbeddingCacheError):
            raise EmbeddingContractViolation("Dolphin query embedding cache violates the fixed contract") from None
        if cached is not None and cached.identity != identity:
            raise EmbeddingContractViolation("Dolphin query embedding cache violates the fixed contract")
        return cached


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


def _consume_flight_exception(flight: asyncio.Task[QueryEmbeddingResolution]) -> None:
    if not flight.cancelled():
        flight.exception()


def _runtime_admission() -> _RuntimeAdmission:
    loop = asyncio.get_running_loop()
    with _RUNTIME_ADMISSIONS_GUARD:
        runtime = _RUNTIME_ADMISSIONS.get(loop)
        if runtime is None:
            runtime = _RuntimeAdmission()
            _RUNTIME_ADMISSIONS[loop] = runtime
        return runtime


def _query_identity(query: str) -> EmbeddingInputIdentity:
    if not isinstance(query, str) or not 1 <= len(query) <= MAX_QUERY_CHARACTERS:
        raise EmbeddingContractViolation("Dolphin query embedding input is invalid")
    try:
        return identify_embedding_input(query)
    except ArtifactInputInvalid:
        raise EmbeddingContractViolation("Dolphin query embedding input is invalid") from None
