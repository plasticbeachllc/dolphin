"""Contracts for fixed-model generation-scoped vector storage and retrieval."""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kb.artifacts import MAX_GENERATION_ARTIFACTS
from kb.generation import (
    EMBEDDING_CONTRACT_VERSION,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    StagingGeneration,
    VerifiedVectorCommit,
)
from kb.lifecycle_limits import ENTITY_ID_MAX_LENGTH
from kb.services.workspace_registry import OperationLease

GENERATION_VECTOR_COMMIT_FORMAT = "dolphin-generation-vector-v1"
MAX_VECTOR_RESULTS = 1_000

_COMMIT_DOMAIN = b"dolphin:generation-vector-commit:v1\x00"
_ROW_DOMAIN = b"dolphin:generation-vector-row:v1\x00"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_FLOAT32 = struct.Struct(">f")


class _Digest(Protocol):
    def update(self, value: bytes, /) -> None: ...


class GenerationVectorError(RuntimeError):
    """Generation vector state could not be staged, verified, or queried safely."""


class GenerationVectorConflict(GenerationVectorError):
    """A generation already records different immutable vector state."""


class GenerationVectorCorrupt(GenerationVectorError):
    """Persisted vector state violates its schema, identity, or digest contract."""


class GenerationVectorUnavailable(GenerationVectorError):
    """Published vector state or its reader authority is unavailable."""


class _VectorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class StagedGenerationVector(_VectorModel):
    """One exact fixed-contract embedding projected into a generation."""

    chunk_instance_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    embedding_cache_key: str = Field(pattern=_SHA256_PATTERN)
    vector: tuple[float, ...] = Field(min_length=EMBEDDING_DIMENSIONS, max_length=EMBEDDING_DIMENSIONS)

    @field_validator("chunk_instance_id")
    @classmethod
    def chunk_identity_has_no_nul(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("vector chunk identity cannot contain NUL")
        return value

    @field_validator("vector")
    @classmethod
    def vector_is_canonical_float32(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        return canonicalize_embedding_vector(value)


class VectorSearchHit(_VectorModel):
    """Internal snapshot-scoped semantic candidate; public ranking is assigned later."""

    chunk_instance_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    score: float = Field(ge=0, le=1)
    distance: float = Field(ge=0, le=2)

    @field_validator("score", "distance")
    @classmethod
    def values_are_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("vector result values must be finite")
        return value


class GenerationVectorCommitVerifier(Protocol):
    """Verify a backend commit fully, then cheaply prove it did not change."""

    def verify_commit(self, commit: VerifiedVectorCommit) -> None: ...

    def require_unchanged(self, commit: VerifiedVectorCommit) -> None: ...

    def hold_commit(self, commit: VerifiedVectorCommit) -> AbstractContextManager[None]: ...


class GenerationVectorStore(GenerationVectorCommitVerifier, Protocol):
    """Backend-neutral vector staging and reader-lease retrieval boundary."""

    def stage_and_commit(
        self,
        lease: OperationLease,
        generation: StagingGeneration,
        vectors: Sequence[StagedGenerationVector],
    ) -> VerifiedVectorCommit: ...

    def search(
        self,
        read_lease_id: str,
        query_vector: Sequence[float],
        *,
        limit: int,
    ) -> tuple[VectorSearchHit, ...]: ...


def canonicalize_embedding_vector(vector: Sequence[float]) -> tuple[float, ...]:
    """Validate and canonicalize an embedding to the persisted float32 contract."""
    if isinstance(vector, (str, bytes)) or len(vector) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"embedding vector must contain exactly {EMBEDDING_DIMENSIONS} values")
    canonical: list[float] = []
    squared_norm = 0.0
    for component in vector:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise ValueError("embedding vector values must be numeric")
        numeric = float(component)
        if not math.isfinite(numeric):
            raise ValueError("embedding vector values must be finite")
        try:
            persisted = _FLOAT32.unpack(_FLOAT32.pack(numeric))[0]
        except (OverflowError, struct.error) as exc:
            raise ValueError("embedding vector values must fit finite float32") from exc
        if not math.isfinite(persisted):
            raise ValueError("embedding vector values must fit finite float32")
        canonical.append(persisted)
        squared_norm += persisted * persisted
    if not math.isfinite(squared_norm) or squared_norm == 0:
        raise ValueError("embedding vector must have a finite nonzero norm")
    return tuple(canonical)


def identify_generation_vector_row(vector: StagedGenerationVector) -> str:
    """Digest the exact identity and persisted float32 bytes of one vector row."""
    digest = hashlib.sha256()
    digest.update(_ROW_DOMAIN)
    _update_frame(digest, vector.chunk_instance_id.encode("utf-8"))
    _update_frame(digest, vector.embedding_cache_key.encode("ascii"))
    for component in vector.vector:
        digest.update(_FLOAT32.pack(component))
    return digest.hexdigest()


def identify_generation_vector_commit(
    generation_id: str,
    backend_token: str,
    vectors: Sequence[StagedGenerationVector],
) -> VerifiedVectorCommit:
    """Bind one immutable backend version to its complete canonical vector projection."""
    if len(vectors) > MAX_GENERATION_ARTIFACTS:
        raise GenerationVectorError("Dolphin generation vector input is too large")
    ordered = tuple(sorted(vectors, key=lambda vector: vector.chunk_instance_id))
    if len({vector.chunk_instance_id for vector in ordered}) != len(ordered):
        raise GenerationVectorError("Dolphin generation vector input contains duplicate identities")
    digest = hashlib.sha256()
    digest.update(_COMMIT_DOMAIN)
    for value in (
        GENERATION_VECTOR_COMMIT_FORMAT,
        generation_id,
        EMBEDDING_PROVIDER,
        EMBEDDING_MODEL,
        str(EMBEDDING_DIMENSIONS),
        str(EMBEDDING_CONTRACT_VERSION),
    ):
        _update_frame(digest, value.encode("utf-8"))
    for vector in ordered:
        _update_frame(digest, identify_generation_vector_row(vector).encode("ascii"))
    return VerifiedVectorCommit(
        generation_id=generation_id,
        backend_token=backend_token,
        manifest_digest=digest.hexdigest(),
        row_count=len(ordered),
    )


def _update_frame(digest: _Digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)
