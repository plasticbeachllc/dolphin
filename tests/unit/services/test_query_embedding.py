"""Tests for exact-cache-first query embedding admission."""

from __future__ import annotations

import asyncio
import threading

import pytest

from kb.artifacts import EmbeddingInputIdentity, identify_embedding_input
from kb.generation import EMBEDDING_DIMENSIONS
from kb.query_embedding import (
    CachedEmbedding,
    CredentialMissing,
    EmbeddingContractViolation,
    QueryEmbeddingOverloaded,
    TransientProviderFailure,
)
from kb.services import query_embedding as query_embedding_module
from kb.services.query_embedding import QueryEmbeddingService
from kb.store.embedding_cache import EmbeddingCacheCorrupt, EmbeddingCacheUnavailable


def _vector(component: float = 0.125) -> tuple[float, ...]:
    return (component,) * EMBEDDING_DIMENSIONS


class _Cache:
    def __init__(
        self,
        *,
        cached: CachedEmbedding | None = None,
        get_failure: Exception | None = None,
        put_failure: Exception | None = None,
        winner: CachedEmbedding | None = None,
    ) -> None:
        self.cached = cached
        self.get_failure = get_failure
        self.put_failure = put_failure
        self.winner = winner
        self.get_calls: list[EmbeddingInputIdentity] = []
        self.put_calls: list[tuple[EmbeddingInputIdentity, tuple[float, ...]]] = []

    def get(self, identity: EmbeddingInputIdentity) -> CachedEmbedding | None:
        self.get_calls.append(identity)
        if self.get_failure is not None:
            raise self.get_failure
        return self.cached

    def put(self, identity: EmbeddingInputIdentity, vector: tuple[float, ...]) -> CachedEmbedding:
        self.put_calls.append((identity, vector))
        if self.put_failure is not None:
            raise self.put_failure
        return self.winner or CachedEmbedding(identity=identity, vector=vector)


class _Provider:
    def __init__(self, outcome: tuple[float, ...] | Exception) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    async def embed_query(self, query: str) -> tuple[float, ...]:
        self.calls.append(query)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _MemoryCache:
    def __init__(self) -> None:
        self.entries: dict[str, CachedEmbedding] = {}
        self.get_calls = 0

    def get(self, identity: EmbeddingInputIdentity) -> CachedEmbedding | None:
        self.get_calls += 1
        return self.entries.get(identity.cache_key)

    def put(self, identity: EmbeddingInputIdentity, vector: tuple[float, ...]) -> CachedEmbedding:
        cached = CachedEmbedding(identity=identity, vector=vector)
        return self.entries.setdefault(identity.cache_key, cached)


class _UnavailableCache:
    def __init__(self) -> None:
        self.get_calls = 0

    def get(self, identity: EmbeddingInputIdentity) -> CachedEmbedding | None:
        assert identity.cache_key
        self.get_calls += 1
        raise EmbeddingCacheUnavailable("unavailable")

    def put(self, identity: EmbeddingInputIdentity, vector: tuple[float, ...]) -> CachedEmbedding:
        assert identity.cache_key and vector
        raise EmbeddingCacheUnavailable("unavailable")


async def _wait_for_cache_reads(cache: _MemoryCache | _UnavailableCache, minimum: int) -> None:
    async with asyncio.timeout(1):
        while cache.get_calls < minimum:
            await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_exact_cache_hit_skips_provider_and_is_normal_hybrid() -> None:
    identity = identify_embedding_input("find publication")
    cache = _Cache(cached=CachedEmbedding(identity=identity, vector=_vector()))
    provider = _Provider(AssertionError("provider must not run"))

    result = await QueryEmbeddingService(cache, provider).resolve("find publication")

    assert result.source == "cache"
    assert result.retrieval_mode == "hybrid"
    assert result.degraded_reason is None
    assert result.cache_write == "not_needed"
    assert provider.calls == []
    assert cache.put_calls == []


@pytest.mark.asyncio
async def test_cache_miss_calls_provider_and_persists_exact_vector() -> None:
    cache = _Cache()
    provider = _Provider(_vector())

    result = await QueryEmbeddingService(cache, provider).resolve("find publication")

    assert result.source == "live"
    assert result.retrieval_mode == "hybrid"
    assert result.cache_write == "persisted"
    assert provider.calls == ["find publication"]
    assert len(cache.put_calls) == 1
    assert cache.put_calls[0][0] == identify_embedding_input("find publication")
    assert cache.put_calls[0][1] == _vector()


@pytest.mark.asyncio
async def test_concurrent_identical_misses_share_one_cache_check_and_provider_call() -> None:
    cache = _MemoryCache()
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    class Provider:
        async def embed_query(self, query: str) -> tuple[float, ...]:
            calls.append(query)
            started.set()
            await release.wait()
            return _vector()

    service = QueryEmbeddingService(cache, Provider())
    tasks = tuple(asyncio.create_task(service.resolve("same query")) for _index in range(10))
    await asyncio.wait_for(started.wait(), timeout=1)
    await _wait_for_cache_reads(cache, 1)
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks)
    await asyncio.sleep(0)

    assert calls == ["same query"]
    assert all(result.source == "live" for result in results)
    assert all(result is results[0] for result in results)
    assert service._single_flights == {}


@pytest.mark.asyncio
async def test_concurrent_transient_failure_is_shared_by_every_identical_waiter() -> None:
    cache = _MemoryCache()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    class Provider:
        async def embed_query(self, query: str) -> tuple[float, ...]:
            nonlocal calls
            assert query == "same query"
            calls += 1
            started.set()
            await release.wait()
            raise TransientProviderFailure("rate_limited")

    service = QueryEmbeddingService(cache, Provider())
    tasks = tuple(asyncio.create_task(service.resolve("same query")) for _index in range(10))
    await asyncio.wait_for(started.wait(), timeout=1)
    await _wait_for_cache_reads(cache, 1)
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks)
    await asyncio.sleep(0)

    assert calls == 1
    assert all(result.retrieval_mode == "lexical_structural" for result in results)
    assert all(result is results[0] for result in results)
    assert service._single_flights == {}


@pytest.mark.asyncio
async def test_concurrent_cache_unavailable_live_result_is_shared_by_every_identical_waiter() -> None:
    cache = _UnavailableCache()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    class Provider:
        async def embed_query(self, query: str) -> tuple[float, ...]:
            nonlocal calls
            assert query == "same query"
            calls += 1
            started.set()
            await release.wait()
            return _vector()

    service = QueryEmbeddingService(cache, Provider())
    tasks = tuple(asyncio.create_task(service.resolve("same query")) for _index in range(10))
    await asyncio.wait_for(started.wait(), timeout=1)
    await _wait_for_cache_reads(cache, 1)
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks)
    await asyncio.sleep(0)

    assert calls == 1
    assert all(result.cache_write == "skipped_unavailable" for result in results)
    assert all(result is results[0] for result in results)
    assert service._single_flights == {}


@pytest.mark.asyncio
async def test_different_query_misses_share_a_fixed_provider_concurrency_limit() -> None:
    cache = _MemoryCache()
    four_started = asyncio.Event()
    release = asyncio.Event()
    active = 0
    maximum_active = 0
    calls = 0

    class Provider:
        async def embed_query(self, query: str) -> tuple[float, ...]:
            nonlocal active, calls, maximum_active
            assert query.startswith("query ")
            calls += 1
            active += 1
            maximum_active = max(maximum_active, active)
            if active == 4:
                four_started.set()
            try:
                await release.wait()
                return _vector()
            finally:
                active -= 1

    services = tuple(QueryEmbeddingService(cache, Provider()) for _index in range(8))
    tasks = tuple(asyncio.create_task(service.resolve(f"query {index}")) for index, service in enumerate(services))
    await asyncio.wait_for(four_started.wait(), timeout=1)

    assert active == 4
    assert calls == 4
    release.set()
    await asyncio.gather(*tasks)
    await asyncio.sleep(0)

    assert calls == 8
    assert maximum_active == 4
    assert all(service._single_flights == {} for service in services)


@pytest.mark.asyncio
async def test_distinct_admissions_and_cache_threads_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_embedding_module, "_MAX_CONCURRENT_QUERY_EMBEDDING_ADMISSIONS", 8)
    cache_release = threading.Event()
    four_cache_reads_started = threading.Event()
    cache_guard = threading.Lock()
    active_cache_reads = 0
    maximum_cache_reads = 0

    class Cache(_MemoryCache):
        def get(self, identity: EmbeddingInputIdentity) -> CachedEmbedding | None:
            nonlocal active_cache_reads, maximum_cache_reads
            with cache_guard:
                self.get_calls += 1
                active_cache_reads += 1
                maximum_cache_reads = max(maximum_cache_reads, active_cache_reads)
                if active_cache_reads == 4:
                    four_cache_reads_started.set()
            try:
                assert cache_release.wait(timeout=1)
                return self.entries.get(identity.cache_key)
            finally:
                with cache_guard:
                    active_cache_reads -= 1

    cache = Cache()
    services = tuple(QueryEmbeddingService(cache, _Provider(_vector())) for _index in range(8))
    tasks = tuple(asyncio.create_task(service.resolve(f"query {index}")) for index, service in enumerate(services))
    assert await asyncio.to_thread(four_cache_reads_started.wait, 1)

    with pytest.raises(QueryEmbeddingOverloaded, match="temporarily full") as raised:
        await QueryEmbeddingService(cache, _Provider(_vector())).resolve("overflow query")

    assert raised.value.retryable is True
    assert cache.get_calls == 4
    cache_release.set()
    await asyncio.gather(*tasks)

    assert maximum_cache_reads == 4
    assert cache.get_calls == 8
    assert all(service._single_flights == {} for service in services)


@pytest.mark.asyncio
async def test_identical_waiter_can_share_a_flight_when_distinct_admission_is_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(query_embedding_module, "_MAX_CONCURRENT_QUERY_EMBEDDING_ADMISSIONS", 1)
    started = asyncio.Event()
    release = asyncio.Event()

    class Provider:
        async def embed_query(self, query: str) -> tuple[float, ...]:
            assert query == "same query"
            started.set()
            await release.wait()
            return _vector()

    service = QueryEmbeddingService(_MemoryCache(), Provider())
    first = asyncio.create_task(service.resolve("same query"))
    await asyncio.wait_for(started.wait(), timeout=1)
    second = asyncio.create_task(service.resolve("same query"))
    await asyncio.sleep(0)

    with pytest.raises(QueryEmbeddingOverloaded):
        await service.resolve("different query")

    release.set()
    first_result, second_result = await asyncio.gather(first, second)
    assert first_result is second_result


@pytest.mark.asyncio
async def test_cancellation_after_admission_transfers_capacity_to_the_registered_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = query_embedding_module._runtime_admission()
    original_try_acquire = runtime.try_acquire
    cancel_once = True

    def acquire_then_cancel() -> bool:
        nonlocal cancel_once
        acquired = original_try_acquire()
        if acquired and cancel_once:
            cancel_once = False
            task = asyncio.current_task()
            assert task is not None
            task.cancel()
        return acquired

    monkeypatch.setattr(runtime, "try_acquire", acquire_then_cancel)
    provider = _Provider(_vector())
    service = QueryEmbeddingService(_MemoryCache(), provider)

    cancelled = asyncio.create_task(service.resolve("cancelled waiter"))
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    async with asyncio.timeout(1):
        while runtime.active:
            await asyncio.sleep(0)

    recovered = await service.resolve("later query")
    assert recovered.source == "live"
    assert runtime.active == 0
    assert provider.calls == ["cancelled waiter", "later query"]


@pytest.mark.asyncio
async def test_optional_cache_outage_still_allows_correct_live_vector() -> None:
    cache = _Cache(
        get_failure=EmbeddingCacheUnavailable("unavailable"),
        put_failure=EmbeddingCacheUnavailable("unavailable"),
    )
    provider = _Provider(_vector())

    result = await QueryEmbeddingService(cache, provider).resolve("query")

    assert result.source == "live"
    assert result.vector == _vector()
    assert result.cache_write == "skipped_unavailable"
    assert provider.calls == ["query"]


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["connection", "timeout", "rate_limited", "server"])
async def test_only_classified_transient_failure_degrades_locally(category: str) -> None:
    cache = _Cache()
    provider = _Provider(TransientProviderFailure(category))  # type: ignore[arg-type]

    result = await QueryEmbeddingService(cache, provider).resolve("query")

    assert result.source == "unavailable"
    assert result.vector is None
    assert result.retrieval_mode == "lexical_structural"
    assert result.degraded_reason == category
    assert result.retryable is True
    assert result.cache_write == "not_attempted"
    assert cache.put_calls == []


@pytest.mark.asyncio
async def test_credential_failure_never_degrades_to_partial_success() -> None:
    cache = _Cache()
    provider = _Provider(CredentialMissing("missing"))

    with pytest.raises(CredentialMissing):
        await QueryEmbeddingService(cache, provider).resolve("query")

    assert cache.put_calls == []


@pytest.mark.asyncio
async def test_invalid_provider_vector_is_a_hard_contract_failure_even_when_cache_is_unavailable() -> None:
    cache = _Cache(get_failure=EmbeddingCacheUnavailable("unavailable"))
    provider = _Provider((0.0,) * EMBEDDING_DIMENSIONS)

    with pytest.raises(EmbeddingContractViolation, match="response violates"):
        await QueryEmbeddingService(cache, provider).resolve("query")

    assert cache.put_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["read", "write"])
async def test_cache_corruption_fails_closed(phase: str) -> None:
    failure = EmbeddingCacheCorrupt("raw cache detail")
    cache = _Cache(
        get_failure=failure if phase == "read" else None,
        put_failure=failure if phase == "write" else None,
    )
    provider = _Provider(_vector())

    with pytest.raises(EmbeddingContractViolation, match="fixed contract") as raised:
        await QueryEmbeddingService(cache, provider).resolve("query")

    assert "raw cache detail" not in str(raised.value)
    assert provider.calls == ([] if phase == "read" else ["query"])


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["read", "write"])
async def test_cache_must_return_the_exact_requested_identity(phase: str) -> None:
    wrong = CachedEmbedding(identity=identify_embedding_input("another query"), vector=_vector())
    cache = _Cache(cached=wrong if phase == "read" else None, winner=wrong if phase == "write" else None)
    provider = _Provider(_vector())

    with pytest.raises(EmbeddingContractViolation, match="fixed contract"):
        await QueryEmbeddingService(cache, provider).resolve("query")

    assert provider.calls == ([] if phase == "read" else ["query"])


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "x" * 2_001, "\ud800"])
async def test_invalid_query_performs_no_cache_or_provider_work(query: str) -> None:
    cache = _Cache()
    provider = _Provider(_vector())

    with pytest.raises(EmbeddingContractViolation):
        await QueryEmbeddingService(cache, provider).resolve(query)

    assert cache.get_calls == []
    assert provider.calls == []
