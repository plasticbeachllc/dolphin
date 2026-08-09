"""Backend-neutral identities for immutable source-derived artifacts."""

from __future__ import annotations

from hashlib import sha256
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from kb.generation import EMBEDDING_CONTRACT_VERSION, EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, EMBEDDING_PROVIDER

CHUNK_TEXT_FORMAT = "dolphin-chunk-text-v1"
CHUNK_TEXT_DOMAIN = b"dolphin:chunk-text:v1\x00"
CHUNK_ARTIFACT_SET_FORMAT = "dolphin-chunk-artifact-set-v1"
CHUNK_ARTIFACT_SET_DOMAIN = b"dolphin:chunk-artifact-set:v1\x00"
EMBEDDING_INPUT_FORMAT = "dolphin-embedding-input-v1"
EMBEDDING_INPUT_DOMAIN = b"dolphin:embedding-input:v1\x00"
MAX_CHUNK_TEXT_UTF8_BYTES = 8 * 1024 * 1024
MAX_GENERATION_ARTIFACTS = 1_000_000

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_CONTRACT_VALUE_MAX_LENGTH = 256


class _Digest(Protocol):
    def update(self, value: bytes, /) -> None: ...


class ChunkArtifactError(RuntimeError):
    """A chunk-text artifact could not be identified or used safely."""


class ArtifactInputInvalid(ChunkArtifactError):
    """Artifact input violates the bounded exact-text contract."""


class ArtifactUnavailable(ChunkArtifactError):
    """A requested immutable artifact is absent."""


class ArtifactCorrupt(ChunkArtifactError):
    """Artifact storage or payload bytes violate the immutable contract."""


class ArtifactStoreUnavailable(ChunkArtifactError):
    """The private artifact store cannot be accessed safely."""


class _ArtifactModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ChunkTextArtifact(_ArtifactModel):
    artifact_id: str = Field(pattern=_SHA256_PATTERN)
    format: str = Field(pattern=r"^dolphin-chunk-text-v1$")
    utf8_bytes: int = Field(ge=0, le=MAX_CHUNK_TEXT_UTF8_BYTES)
    characters: int = Field(ge=0, le=MAX_CHUNK_TEXT_UTF8_BYTES)
    lines: int = Field(ge=0, le=MAX_CHUNK_TEXT_UTF8_BYTES + 1)


class VerifiedChunkArtifactSet(_ArtifactModel):
    """Physical verification only; durable membership must bind it to a generation."""

    format: str = Field(pattern=r"^dolphin-chunk-artifact-set-v1$")
    set_digest: str = Field(pattern=_SHA256_PATTERN)
    artifact_count: int = Field(ge=0, le=MAX_GENERATION_ARTIFACTS)
    total_utf8_bytes: int = Field(ge=0, le=MAX_GENERATION_ARTIFACTS * MAX_CHUNK_TEXT_UTF8_BYTES)


class EmbeddingContract(_ArtifactModel):
    provider: str = Field(min_length=1, max_length=_CONTRACT_VALUE_MAX_LENGTH)
    model: str = Field(min_length=1, max_length=_CONTRACT_VALUE_MAX_LENGTH)
    dimensions: int = Field(gt=0, le=1_000_000)
    contract_version: int = Field(gt=0, le=1_000_000)


class EmbeddingInputIdentity(_ArtifactModel):
    cache_key: str = Field(pattern=_SHA256_PATTERN)
    format: str = Field(pattern=r"^dolphin-embedding-input-v1$")
    provider: str = Field(min_length=1, max_length=_CONTRACT_VALUE_MAX_LENGTH)
    model: str = Field(min_length=1, max_length=_CONTRACT_VALUE_MAX_LENGTH)
    dimensions: int = Field(gt=0, le=1_000_000)
    contract_version: int = Field(gt=0, le=1_000_000)
    utf8_bytes: int = Field(ge=0, le=MAX_CHUNK_TEXT_UTF8_BYTES)


DOCUMENT_EMBEDDING_CONTRACT = EmbeddingContract(
    provider=EMBEDDING_PROVIDER,
    model=EMBEDDING_MODEL,
    dimensions=EMBEDDING_DIMENSIONS,
    contract_version=EMBEDDING_CONTRACT_VERSION,
)


def identify_chunk_text(text: str) -> ChunkTextArtifact:
    """Identify exact decoded chunk text without normalization or newline rewriting."""
    descriptor, _payload = encode_chunk_text(text)
    return descriptor


def encode_chunk_text(text: str) -> tuple[ChunkTextArtifact, bytes]:
    """Identify exact chunk text and return its single validated UTF-8 encoding."""
    payload = _exact_utf8(text)
    return (
        ChunkTextArtifact(
            artifact_id=sha256(CHUNK_TEXT_DOMAIN + payload).hexdigest(),
            format=CHUNK_TEXT_FORMAT,
            utf8_bytes=len(payload),
            characters=len(text),
            lines=text.count("\n") + (1 if text else 0),
        ),
        payload,
    )


def identify_embedding_input(
    text: str,
    *,
    contract: EmbeddingContract = DOCUMENT_EMBEDDING_CONTRACT,
) -> EmbeddingInputIdentity:
    """Identify the exact model-aware text submitted for document embedding."""
    payload = _exact_utf8(text)
    digest = sha256()
    digest.update(EMBEDDING_INPUT_DOMAIN)
    for value in (
        _contract_utf8(contract.provider),
        _contract_utf8(contract.model),
        str(contract.dimensions).encode("ascii"),
        str(contract.contract_version).encode("ascii"),
        payload,
    ):
        _update_frame(digest, value)
    return EmbeddingInputIdentity(
        cache_key=digest.hexdigest(),
        format=EMBEDDING_INPUT_FORMAT,
        provider=contract.provider,
        model=contract.model,
        dimensions=contract.dimensions,
        contract_version=contract.contract_version,
        utf8_bytes=len(payload),
    )


def identify_chunk_artifact_set(
    artifact_ids: tuple[str, ...],
    *,
    total_utf8_bytes: int,
) -> VerifiedChunkArtifactSet:
    """Identify a canonical physical set without asserting generation membership."""
    canonical_ids = tuple(sorted({_require_artifact_id(artifact_id) for artifact_id in artifact_ids}))
    if len(canonical_ids) > MAX_GENERATION_ARTIFACTS:
        raise ArtifactInputInvalid("Dolphin chunk artifact manifest is too large")
    if total_utf8_bytes < 0 or total_utf8_bytes > len(canonical_ids) * MAX_CHUNK_TEXT_UTF8_BYTES:
        raise ArtifactInputInvalid("Dolphin chunk artifact input is invalid")
    digest = sha256()
    digest.update(CHUNK_ARTIFACT_SET_DOMAIN)
    for artifact_id in canonical_ids:
        _update_frame(digest, artifact_id.encode("ascii"))
    _update_frame(digest, str(total_utf8_bytes).encode("ascii"))
    return VerifiedChunkArtifactSet(
        format=CHUNK_ARTIFACT_SET_FORMAT,
        set_digest=digest.hexdigest(),
        artifact_count=len(canonical_ids),
        total_utf8_bytes=total_utf8_bytes,
    )


def require_artifact_id(artifact_id: str) -> str:
    """Validate the closed lowercase SHA-256 artifact identifier grammar."""
    return _require_artifact_id(artifact_id)


def _require_artifact_id(artifact_id: str) -> str:
    if (
        not isinstance(artifact_id, str)
        or len(artifact_id) != 64
        or any(character not in "0123456789abcdef" for character in artifact_id)
    ):
        raise ArtifactInputInvalid("Dolphin chunk artifact identifier is invalid")
    return artifact_id


def _exact_utf8(text: str) -> bytes:
    if not isinstance(text, str):
        raise ArtifactInputInvalid("Dolphin chunk artifact input is invalid")
    try:
        payload = text.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ArtifactInputInvalid("Dolphin chunk artifact input is not valid Unicode") from None
    if len(payload) > MAX_CHUNK_TEXT_UTF8_BYTES:
        raise ArtifactInputInvalid("Dolphin chunk artifact input is too large")
    return payload


def _contract_utf8(value: str) -> bytes:
    try:
        return value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ArtifactInputInvalid("Dolphin embedding contract is invalid") from None


def _update_frame(digest: _Digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)
