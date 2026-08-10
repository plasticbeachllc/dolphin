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


class _EmbeddingCache(Protocol):
    def get(self, identity: EmbeddingInputIdentity) -> CachedEmbedding | None: ...

    def put(self, identity: EmbeddingInputIdentity, vector: tuple[float, ...]) -> CachedEmbedding: ...


class _QueryProvider(Protocol):
    async def embed_query(self, query: str) -> tuple[float, ...]: ...


class QueryEmbeddingService:
    """Prefer exact cache state and degrade only after a transient live failure."""

    def __init__(self, cache: _EmbeddingCache, provider: _QueryProvider) -> None:
        self._cache = cache
        self._provider = provider

    async def resolve(self, query: str) -> QueryEmbeddingResolution:
        identity = _query_identity(query)
        try:
            cached = await asyncio.to_thread(self._cache.get, identity)
        except EmbeddingCacheUnavailable:
            cached = None
        except (EmbeddingCacheCorrupt, EmbeddingCacheError):
            raise EmbeddingContractViolation("Dolphin query embedding cache violates the fixed contract") from None
        if cached is not None:
            if cached.identity != identity:
                raise EmbeddingContractViolation("Dolphin query embedding cache violates the fixed contract")
            return QueryEmbeddingResolution(
                identity=identity,
                vector=cached.vector,
                source="cache",
                retrieval_mode="hybrid",
                degraded_reason=None,
                retryable=False,
                cache_write="not_needed",
            )

        try:
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


def _query_identity(query: str) -> EmbeddingInputIdentity:
    if not isinstance(query, str) or not 1 <= len(query) <= MAX_QUERY_CHARACTERS:
        raise EmbeddingContractViolation("Dolphin query embedding input is invalid")
    try:
        return identify_embedding_input(query)
    except ArtifactInputInvalid:
        raise EmbeddingContractViolation("Dolphin query embedding input is invalid") from None
