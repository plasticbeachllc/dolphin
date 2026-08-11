"""Contracts for generation-scoped keyword indexing and retrieval."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kb.artifacts import MAX_CHUNK_TEXT_UTF8_BYTES, MAX_GENERATION_ARTIFACTS, identify_chunk_text
from kb.generation_content import MAX_LANGUAGE_LENGTH, MAX_RELATIVE_PATH_LENGTH
from kb.lifecycle_limits import ENTITY_ID_MAX_LENGTH
from kb.search_scope import SearchScope

GENERATION_KEYWORD_COMMIT_FORMAT = "dolphin-generation-keyword-v1"
MAX_KEYWORD_QUERY_LENGTH = 4_096
MAX_KEYWORD_QUERY_TERMS = 128
MAX_KEYWORD_RESULTS = 1_000
MAX_KEYWORD_POSTINGS_PER_QUERY = 100_000

_COMMIT_DOMAIN = b"dolphin:generation-keyword:v1\x00"
_INDEX_DOMAIN = b"dolphin:generation-keyword-index:v1\x00"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class _Digest(Protocol):
    def update(self, value: bytes, /) -> None: ...


class GenerationKeywordError(RuntimeError):
    """Generation keyword state could not be staged or queried safely."""


class GenerationKeywordConflict(GenerationKeywordError):
    """A generation already records different keyword state."""


class GenerationKeywordUnavailable(GenerationKeywordError):
    """Published keyword state or its reader authority is unavailable."""


class GenerationKeywordQueryTooBroad(GenerationKeywordError):
    """A keyword query exceeds the fixed internal candidate-work budget."""


class GenerationKeywordTimeout(GenerationKeywordError):
    """A keyword query exceeded its fixed cooperative execution deadline."""


class _KeywordModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class GenerationKeywordDocument(_KeywordModel):
    """Exact source-derived text and metadata indexed for one chunk membership."""

    chunk_instance_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    artifact_id: str = Field(pattern=_SHA256_PATTERN)
    relative_path: str = Field(min_length=1, max_length=MAX_RELATIVE_PATH_LENGTH)
    language: str = Field(min_length=1, max_length=MAX_LANGUAGE_LENGTH)
    text: str = Field(max_length=MAX_CHUNK_TEXT_UTF8_BYTES)

    @field_validator("chunk_instance_id", "relative_path", "language", "text")
    @classmethod
    def values_have_no_nul(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("keyword document values cannot contain NUL")
        return value

    @model_validator(mode="after")
    def text_matches_artifact_identity(self) -> GenerationKeywordDocument:
        if identify_chunk_text(self.text).artifact_id != self.artifact_id:
            raise ValueError("keyword document text does not match its artifact identity")
        return self


class VerifiedGenerationKeywordCommit(_KeywordModel):
    generation_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    manifest_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    manifest_digest: str = Field(pattern=_SHA256_PATTERN)
    commit_digest: str = Field(pattern=_SHA256_PATTERN)
    item_count: int = Field(ge=0, le=MAX_GENERATION_ARTIFACTS)


class KeywordSearchHit(_KeywordModel):
    """Internal snapshot-scoped lexical candidate; public ranking is assigned later."""

    chunk_instance_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    score: float

    @field_validator("score")
    @classmethod
    def score_is_finite_and_nonnegative(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("keyword score must be finite and nonnegative")
        return value


def identify_generation_keyword_commit(
    generation_id: str,
    manifest_id: str,
    manifest_digest: str,
    documents: Sequence[GenerationKeywordDocument],
) -> VerifiedGenerationKeywordCommit:
    """Bind every indexed document to one immutable generation content manifest."""
    ordered = tuple(sorted(documents, key=lambda document: document.chunk_instance_id))
    if len(ordered) > MAX_GENERATION_ARTIFACTS:
        raise GenerationKeywordError("Dolphin generation keyword input is too large")
    if len({document.chunk_instance_id for document in ordered}) != len(ordered):
        raise GenerationKeywordError("Dolphin generation keyword input contains duplicate identities")
    digest = hashlib.sha256()
    digest.update(_COMMIT_DOMAIN)
    for value in (GENERATION_KEYWORD_COMMIT_FORMAT, generation_id, manifest_id, manifest_digest):
        _update_frame(digest, value.encode("utf-8"))
    for document in ordered:
        for value in (
            document.chunk_instance_id,
            document.artifact_id,
            document.relative_path,
            document.language,
        ):
            _update_frame(digest, value.encode("utf-8"))
    return VerifiedGenerationKeywordCommit(
        generation_id=generation_id,
        manifest_id=manifest_id,
        manifest_digest=manifest_digest,
        commit_digest=digest.hexdigest(),
        item_count=len(ordered),
    )


def identify_generation_keyword_index(
    generation_id: str,
    postings: Iterable[tuple[str, str, str, int]],
) -> str:
    """Digest one generation's canonically ordered FTS5 token postings."""
    digest = hashlib.sha256()
    digest.update(_INDEX_DOMAIN)
    _update_frame(digest, generation_id.encode("utf-8"))
    previous: tuple[str, str, str, int] | None = None
    for posting in postings:
        if (
            not isinstance(posting, tuple)
            or len(posting) != 4
            or not all(isinstance(value, str) and "\x00" not in value for value in posting[:3])
            or not isinstance(posting[3], int)
            or isinstance(posting[3], bool)
            or posting[3] < 0
            or (previous is not None and posting < previous)
        ):
            raise GenerationKeywordError("Dolphin generation keyword index posting is invalid")
        for value in posting[:3]:
            _update_frame(digest, value.encode("utf-8"))
        digest.update(posting[3].to_bytes(8, "big"))
        previous = posting
    return digest.hexdigest()


def _update_frame(digest: _Digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


class GenerationKeywordStore(Protocol):
    def search(
        self,
        read_lease_id: str,
        query: str,
        *,
        scope: SearchScope,
        limit: int,
    ) -> tuple[KeywordSearchHit, ...]: ...
