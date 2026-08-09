"""Contracts for generation-scoped immutable chunk membership."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kb.artifacts import ChunkTextArtifact, VerifiedChunkArtifactSet
from kb.generation import PublishedSnapshot, StagingGeneration, VerifiedGenerationManifest
from kb.lifecycle_limits import ENTITY_ID_MAX_LENGTH
from kb.services.workspace_registry import OperationLease

GENERATION_CONTENT_MANIFEST_FORMAT = "dolphin-generation-content-v1"
MAX_RELATIVE_PATH_LENGTH = 4_096
MAX_LANGUAGE_LENGTH = 128
MAX_CHUNKER_KEY_LENGTH = 256
MAX_SOURCE_LINE = 2_147_483_647

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_MANIFEST_DOMAIN = b"dolphin:generation-content-manifest:v1\x00"
_MEMBERSHIP_DOMAIN = b"dolphin:generation-chunk-membership:v1\x00"


class _Digest(Protocol):
    def update(self, value: bytes, /) -> None: ...


class GenerationContentError(RuntimeError):
    """Generation content could not be persisted or resolved safely."""


class GenerationContentConflict(GenerationContentError):
    """A generation already has different immutable content."""


class PublishedChunkUnavailable(GenerationContentError):
    """A chunk is not authorized by the supplied published snapshot."""


class _GenerationContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class StagedChunkMembership(_GenerationContentModel):
    """Source-free metadata binding one chunk instance to immutable exact text."""

    chunk_instance_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    artifact: ChunkTextArtifact
    relative_path: str = Field(min_length=1, max_length=MAX_RELATIVE_PATH_LENGTH)
    source_file_fingerprint: str = Field(pattern=_SHA256_PATTERN)
    start_line: int = Field(ge=1, le=MAX_SOURCE_LINE)
    end_line: int = Field(ge=1, le=MAX_SOURCE_LINE)
    language: str = Field(min_length=1, max_length=MAX_LANGUAGE_LENGTH)
    chunker_key: str = Field(min_length=1, max_length=MAX_CHUNKER_KEY_LENGTH)
    embedding_cache_key: str = Field(pattern=_SHA256_PATTERN)

    @field_validator("relative_path")
    @classmethod
    def relative_path_is_canonical(cls, value: str) -> str:
        candidate = PurePosixPath(value)
        if (
            "\x00" in value
            or "\\" in value
            or not candidate.parts
            or candidate.is_absolute()
            or value != candidate.as_posix()
            or any(part in {"", ".", ".."} for part in candidate.parts)
        ):
            raise ValueError("chunk relative path must be canonical and contained")
        return value

    @field_validator("chunk_instance_id", "language", "chunker_key")
    @classmethod
    def bounded_text_has_no_nul(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("chunk membership text cannot contain NUL")
        return value

    @model_validator(mode="after")
    def line_range_is_ordered(self) -> StagedChunkMembership:
        if self.end_line < self.start_line:
            raise ValueError("chunk line range is invalid")
        return self


class PublishedChunkMembership(StagedChunkMembership):
    """A chunk membership proven to belong to one published snapshot."""

    generation_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    workspace_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    publication_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    manifest_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    manifest_digest: str = Field(pattern=_SHA256_PATTERN)


def identify_chunk_membership(generation_id: str, membership: StagedChunkMembership) -> str:
    """Digest every authoritative field of one generation-scoped chunk membership."""
    digest = hashlib.sha256()
    digest.update(_MEMBERSHIP_DOMAIN)
    for value in (
        generation_id,
        membership.chunk_instance_id,
        membership.artifact.artifact_id,
        str(membership.artifact.utf8_bytes),
        str(membership.artifact.characters),
        str(membership.artifact.lines),
        membership.relative_path,
        membership.source_file_fingerprint,
        str(membership.start_line),
        str(membership.end_line),
        membership.language,
        membership.chunker_key,
        membership.embedding_cache_key,
    ):
        _update_frame(digest, value.encode("utf-8"))
    return digest.hexdigest()


def identify_generation_content_manifest(
    generation_id: str,
    memberships: tuple[StagedChunkMembership, ...],
    artifact_set: VerifiedChunkArtifactSet,
) -> VerifiedGenerationManifest:
    """Identify one canonical immutable generation manifest."""
    ordered = tuple(sorted(memberships, key=lambda membership: membership.chunk_instance_id))
    digest = hashlib.sha256()
    digest.update(_MANIFEST_DOMAIN)
    _update_frame(digest, GENERATION_CONTENT_MANIFEST_FORMAT.encode("ascii"))
    _update_frame(digest, generation_id.encode("utf-8"))
    _update_frame(digest, artifact_set.set_digest.encode("ascii"))
    _update_frame(digest, str(artifact_set.artifact_count).encode("ascii"))
    _update_frame(digest, str(artifact_set.total_utf8_bytes).encode("ascii"))
    for membership in ordered:
        _update_frame(digest, identify_chunk_membership(generation_id, membership).encode("ascii"))
    manifest_digest = digest.hexdigest()
    count = len(ordered)
    return VerifiedGenerationManifest(
        generation_id=generation_id,
        manifest_id=f"manifest_{manifest_digest[:55]}",
        manifest_digest=manifest_digest,
        artifact_set_digest=artifact_set.set_digest,
        artifact_count=artifact_set.artifact_count,
        artifact_utf8_bytes=artifact_set.total_utf8_bytes,
        metadata_item_count=count,
        keyword_item_count=count,
        vector_row_count=count,
    )


def _update_frame(digest: _Digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


class GenerationContentStore(Protocol):
    """Backend-neutral staging and snapshot-authorized materialization boundary."""

    def stage_manifest(
        self,
        lease: OperationLease,
        generation: StagingGeneration,
        memberships: Sequence[StagedChunkMembership],
    ) -> VerifiedGenerationManifest: ...

    def materialize_published_chunk(self, snapshot: PublishedSnapshot, chunk_instance_id: str) -> str: ...
