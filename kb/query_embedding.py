"""Fixed-contract query embedding admission models and failure taxonomy."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kb.artifacts import EmbeddingInputIdentity
from kb.generation import EMBEDDING_DIMENSIONS
from kb.generation_vector import canonicalize_embedding_vector

MAX_QUERY_CHARACTERS = 2_000

TransientProviderCategory = Literal["connection", "timeout", "rate_limited", "server"]
PermanentProviderCategory = Literal["request_rejected", "provider_error"]
QueryEmbeddingSource = Literal["cache", "live", "unavailable"]
QueryRetrievalMode = Literal["hybrid", "lexical_structural"]
QueryCacheWrite = Literal["not_needed", "persisted", "skipped_unavailable", "not_attempted"]


class QueryEmbeddingError(RuntimeError):
    """A query embedding could not be admitted under the fixed contract."""


class CredentialMissing(QueryEmbeddingError):
    """The one supported environment credential is absent."""

    retryable: ClassVar[Literal[False]] = False


class CredentialRejected(QueryEmbeddingError):
    """OpenAI rejected the supplied credential or its authorization."""

    retryable: ClassVar[Literal[False]] = False


class TransientProviderFailure(QueryEmbeddingError):
    """OpenAI failed in a classified way that permits local degradation."""

    retryable: ClassVar[Literal[True]] = True

    def __init__(self, category: TransientProviderCategory) -> None:
        self.category = category
        super().__init__(f"Dolphin query embedding provider is temporarily unavailable ({category})")


class PermanentProviderFailure(QueryEmbeddingError):
    """OpenAI failed in a way that local fallback must not conceal."""

    retryable: ClassVar[Literal[False]] = False

    def __init__(self, category: PermanentProviderCategory) -> None:
        self.category = category
        super().__init__(f"Dolphin query embedding request failed ({category})")


class EmbeddingContractViolation(QueryEmbeddingError):
    """A provider response or persisted vector violates the fixed contract."""

    retryable: ClassVar[Literal[False]] = False


class _QueryEmbeddingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CachedEmbedding(_QueryEmbeddingModel):
    """One exact immutable vector recovered from the global embedding cache."""

    identity: EmbeddingInputIdentity
    vector: tuple[float, ...] = Field(min_length=EMBEDDING_DIMENSIONS, max_length=EMBEDDING_DIMENSIONS)

    @field_validator("vector")
    @classmethod
    def vector_is_canonical_float32(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        return canonicalize_embedding_vector(value)


class QueryEmbeddingResolution(_QueryEmbeddingModel):
    """Vector admission outcome consumed by snapshot-scoped retrieval."""

    identity: EmbeddingInputIdentity
    vector: tuple[float, ...] | None
    source: QueryEmbeddingSource
    retrieval_mode: QueryRetrievalMode
    degraded_reason: TransientProviderCategory | None
    retryable: bool
    cache_write: QueryCacheWrite

    @field_validator("vector")
    @classmethod
    def optional_vector_is_canonical_float32(cls, value: tuple[float, ...] | None) -> tuple[float, ...] | None:
        return None if value is None else canonicalize_embedding_vector(value)

    @model_validator(mode="after")
    def mode_matches_vector_and_failure(self) -> QueryEmbeddingResolution:
        if self.retrieval_mode == "hybrid":
            if (
                self.vector is None
                or self.source == "unavailable"
                or self.degraded_reason is not None
                or self.retryable
            ):
                raise ValueError("hybrid query embedding resolution is inconsistent")
            if self.source == "cache" and self.cache_write != "not_needed":
                raise ValueError("cached query embedding cannot report a cache write")
            if self.source == "live" and self.cache_write not in {"persisted", "skipped_unavailable"}:
                raise ValueError("live query embedding must report its cache write outcome")
        elif (
            self.vector is not None
            or self.source != "unavailable"
            or self.degraded_reason is None
            or not self.retryable
            or self.cache_write != "not_attempted"
        ):
            raise ValueError("degraded query embedding resolution is inconsistent")
        return self
