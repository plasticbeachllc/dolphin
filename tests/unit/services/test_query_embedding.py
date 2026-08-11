"""Tests for exact-cache-first query embedding admission."""

from __future__ import annotations

import asyncio

import pytest

from kb.artifacts import EmbeddingInputIdentity, identify_embedding_input
from kb.generation import EMBEDDING_DIMENSIONS
from kb.query_embedding import CachedEmbedding, CredentialMissing, EmbeddingContractViolation, TransientProviderFailure
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

    def get(self, identity: EmbeddingInputIdentity) -> CachedEmbedding | None:
        return self.entries.get(identity.cache_key)

    def put(self, identity: EmbeddingInputIdentity, vector: tuple[float, ...]) -> CachedEmbedding:
        cached = CachedEmbedding(identity=identity, vector=vector)
        return self.entries.setdefault(identity.cache_key, cached)


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
async def test_concurrent_identical_misses_make_one_provider_call_and_recheck_cache() -> None:
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
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks)

    assert calls == ["same query"]
    assert [result.source for result in results].count("live") == 1
    assert [result.source for result in results].count("cache") == 9
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

    service = QueryEmbeddingService(cache, Provider())
    tasks = tuple(asyncio.create_task(service.resolve(f"query {index}")) for index in range(8))
    await asyncio.wait_for(four_started.wait(), timeout=1)

    assert active == 4
    assert calls == 4
    release.set()
    await asyncio.gather(*tasks)

    assert calls == 8
    assert maximum_active == 4
    assert service._single_flights == {}


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
