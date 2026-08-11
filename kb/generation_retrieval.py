"""Deterministic fusion contracts for one published generation snapshot."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb.generation import PublishedSnapshot
from kb.generation_keyword import KeywordSearchHit
from kb.generation_vector import VectorSearchHit
from kb.lifecycle_limits import ENTITY_ID_MAX_LENGTH

GENERATION_RANKING_POLICY_VERSION = "generation-rrf-v1"
GENERATION_RANKING_POLICY_RRF_CONSTANT = 60
GENERATION_BRANCH_CANDIDATE_LIMIT = 1_000
GENERATION_RANKED_TARGET_HORIZON = 500

RetrievalMode = Literal["hybrid", "lexical_structural"]
RetrievalSource = Literal["keyword", "vector"]


class GenerationRetrievalError(RuntimeError):
    """Generation-scoped retrieval could not produce a trustworthy ranked plan."""


class GenerationRetrievalUnavailable(GenerationRetrievalError):
    """A required published snapshot, reader lease, or retrieval branch is unavailable."""


class GenerationRetrievalQueryTooBroad(GenerationRetrievalError):
    """A safe lexical work bound requires the caller to narrow the query."""

    retryable: ClassVar[Literal[False]] = False


class GenerationRetrievalTimeout(GenerationRetrievalUnavailable):
    """A retrieval branch exceeded its deadline and a later retry may succeed."""

    retryable: ClassVar[Literal[True]] = True


class _RetrievalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RankedGenerationTarget(_RetrievalModel):
    """One score-free target retained from the bounded internal candidate pool."""

    chunk_instance_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    rank: int = Field(ge=1, le=GENERATION_RANKED_TARGET_HORIZON)
    sources: tuple[RetrievalSource, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def sources_are_unique_and_canonical(self) -> RankedGenerationTarget:
        expected = tuple(source for source in ("keyword", "vector") if source in self.sources)
        if self.sources != expected:
            raise ValueError("retrieval sources must be unique and canonically ordered")
        return self


class GenerationRetrievalResult(_RetrievalModel):
    """A finite ranked plan bound to the exact snapshot used by both branches."""

    snapshot: PublishedSnapshot
    retrieval_mode: RetrievalMode
    ranking_policy_version: Literal["generation-rrf-v1"] = GENERATION_RANKING_POLICY_VERSION
    ranked_target_horizon: Literal[500] = GENERATION_RANKED_TARGET_HORIZON
    ranked_targets: tuple[RankedGenerationTarget, ...] = Field(max_length=GENERATION_RANKED_TARGET_HORIZON)
    ranked_horizon_reached: bool

    @model_validator(mode="after")
    def ranked_plan_is_complete_and_mode_consistent(self) -> GenerationRetrievalResult:
        expected_ranks = tuple(range(1, len(self.ranked_targets) + 1))
        observed_ranks = tuple(target.rank for target in self.ranked_targets)
        identities = tuple(target.chunk_instance_id for target in self.ranked_targets)
        if observed_ranks != expected_ranks or len(set(identities)) != len(identities):
            raise ValueError("ranked targets must have contiguous ranks and unique identities")
        if self.ranked_horizon_reached and len(self.ranked_targets) != self.ranked_target_horizon:
            raise ValueError("a reached retrieval horizon requires a full ranked plan")
        if self.retrieval_mode == "lexical_structural" and any(
            target.sources != ("keyword",) for target in self.ranked_targets
        ):
            raise ValueError("lexical retrieval cannot contain vector provenance")
        return self


@dataclass(frozen=True, slots=True, repr=False)
class TransientGenerationCandidates:
    """Canonical scored candidates that must never cross a result or persistence boundary."""

    snapshot: PublishedSnapshot
    retrieval_mode: RetrievalMode
    keyword_hits: tuple[KeywordSearchHit, ...]
    vector_hits: tuple[VectorSearchHit, ...] | None


def rank_generation_candidates(
    keyword_hits: Sequence[KeywordSearchHit],
    vector_hits: Sequence[VectorSearchHit] | None,
) -> tuple[tuple[RankedGenerationTarget, ...], bool]:
    """Fuse bounded branches without allowing backend score scales to cross the boundary.

    ``None`` means the vector branch was deliberately omitted. An empty sequence
    means that the vector branch ran successfully and found no candidates.
    """

    keyword, vector = canonicalize_generation_candidates(keyword_hits, vector_hits)
    branch_ranks: dict[str, dict[RetrievalSource, int]] = {}
    for rank, hit in enumerate(keyword, start=1):
        branch_ranks.setdefault(hit.chunk_instance_id, {})["keyword"] = rank
    if vector is not None:
        for rank, hit in enumerate(vector, start=1):
            branch_ranks.setdefault(hit.chunk_instance_id, {})["vector"] = rank

    ordered = sorted(
        branch_ranks.items(),
        key=lambda item: (
            -sum(Fraction(1, GENERATION_RANKING_POLICY_RRF_CONSTANT + rank) for rank in item[1].values()),
            item[0],
        ),
    )
    retained = ordered[:GENERATION_RANKED_TARGET_HORIZON]
    targets = tuple(
        RankedGenerationTarget(
            chunk_instance_id=chunk_instance_id,
            rank=rank,
            sources=tuple(source for source in ("keyword", "vector") if source in ranks),
        )
        for rank, (chunk_instance_id, ranks) in enumerate(retained, start=1)
    )
    return targets, len(ordered) > GENERATION_RANKED_TARGET_HORIZON


def canonicalize_generation_candidates(
    keyword_hits: Sequence[KeywordSearchHit],
    vector_hits: Sequence[VectorSearchHit] | None,
) -> tuple[tuple[KeywordSearchHit, ...], tuple[VectorSearchHit, ...] | None]:
    """Validate and order transient branch candidates without comparing score scales."""

    keyword = _canonical_keyword_hits(keyword_hits)
    vector = None if vector_hits is None else _canonical_vector_hits(vector_hits)
    return keyword, vector


def _canonical_keyword_hits(hits: Sequence[KeywordSearchHit]) -> tuple[KeywordSearchHit, ...]:
    _require_bounded_unique_hits(hits, branch="keyword")
    return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.chunk_instance_id)))


def _canonical_vector_hits(hits: Sequence[VectorSearchHit]) -> tuple[VectorSearchHit, ...]:
    _require_bounded_unique_hits(hits, branch="vector")
    return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.chunk_instance_id)))


def _require_bounded_unique_hits(
    hits: Sequence[KeywordSearchHit] | Sequence[VectorSearchHit],
    *,
    branch: str,
) -> None:
    if isinstance(hits, (str, bytes)) or len(hits) > GENERATION_BRANCH_CANDIDATE_LIMIT:
        raise GenerationRetrievalError(f"Dolphin {branch} candidate set is invalid")
    identities = [hit.chunk_instance_id for hit in hits]
    if len(set(identities)) != len(identities):
        raise GenerationRetrievalError(f"Dolphin {branch} candidate set contains duplicate identities")
