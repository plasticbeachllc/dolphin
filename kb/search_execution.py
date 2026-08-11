"""Eager first-page search execution contracts and global candidate fusion."""

from __future__ import annotations

from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb.generation import PublishedSnapshot
from kb.generation_retrieval import (
    GENERATION_RANKED_TARGET_HORIZON,
    GENERATION_RANKING_POLICY_RRF_CONSTANT,
    TransientGenerationCandidates,
    canonicalize_generation_candidates,
)
from kb.lifecycle_limits import ENTITY_ID_MAX_LENGTH
from kb.query_embedding import QueryEmbeddingResolution, TransientProviderCategory
from kb.search_scope import ResolvedSearchScope, SearchFilterShape

SEARCH_RANKING_POLICY_VERSION = "search-global-rrf-v1"
MAX_SEARCH_EXECUTION_WORKSPACES = 32

SearchRetrievalMode = Literal["hybrid", "lexical_structural", "not_needed"]
SearchRetrievalSource = Literal["keyword", "vector"]


class SearchExecutionError(RuntimeError):
    """Transient candidates could not produce one trustworthy global ranked plan."""


class _SearchExecutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SearchRankedTarget(_SearchExecutionModel):
    """One score-free exact target in the complete first-page continuation horizon."""

    workspace_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    publication_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    generation_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    chunk_instance_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    rank: int = Field(ge=1, le=GENERATION_RANKED_TARGET_HORIZON)
    sources: tuple[SearchRetrievalSource, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def sources_are_unique_and_canonical(self) -> SearchRankedTarget:
        expected = tuple(source for source in ("keyword", "vector") if source in self.sources)
        if self.sources != expected:
            raise ValueError("search retrieval sources must be unique and canonically ordered")
        return self

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (
            self.workspace_id,
            self.publication_id,
            self.generation_id,
            self.chunk_instance_id,
        )


class FirstPageSearchPlan(_SearchExecutionModel):
    """One eager score-free ranked plan retained under exact publication authority."""

    snapshots: tuple[PublishedSnapshot, ...] = Field(
        min_length=1,
        max_length=MAX_SEARCH_EXECUTION_WORKSPACES,
    )
    scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    filter_shape: SearchFilterShape
    scope_searchable_chunks: int = Field(ge=0)
    retrieval_mode: SearchRetrievalMode
    query_embedding_source: Literal["cache", "live", "unavailable", "not_needed"]
    degraded_reason: TransientProviderCategory | None
    retryable: bool
    ranking_policy_version: Literal["search-global-rrf-v1"] = SEARCH_RANKING_POLICY_VERSION
    ranked_target_horizon: Literal[500] = GENERATION_RANKED_TARGET_HORIZON
    ranked_targets_retained: int = Field(ge=0, le=GENERATION_RANKED_TARGET_HORIZON)
    ranked_horizon_reached: bool
    ranked_targets: tuple[SearchRankedTarget, ...] = Field(max_length=GENERATION_RANKED_TARGET_HORIZON)

    @model_validator(mode="after")
    def authority_mode_and_ranks_are_consistent(self) -> FirstPageSearchPlan:
        workspace_ids = tuple(snapshot.workspace_id for snapshot in self.snapshots)
        if workspace_ids != tuple(sorted(workspace_ids)) or len(set(workspace_ids)) != len(workspace_ids):
            raise ValueError("search snapshots must have unique canonically ordered workspaces")
        authorities = {
            (snapshot.workspace_id, snapshot.publication_id, snapshot.generation_id) for snapshot in self.snapshots
        }
        identities = tuple(target.identity for target in self.ranked_targets)
        if tuple(target.rank for target in self.ranked_targets) != tuple(range(1, len(self.ranked_targets) + 1)):
            raise ValueError("search targets must have contiguous global ranks")
        if len(set(identities)) != len(identities):
            raise ValueError("search targets must have unique exact identities")
        if any(target.identity[:3] not in authorities for target in self.ranked_targets):
            raise ValueError("search target authority is absent from the admitted snapshots")
        if self.ranked_targets_retained != len(self.ranked_targets):
            raise ValueError("search retained-target metadata does not match the ranked plan")
        if self.ranked_horizon_reached and len(self.ranked_targets) != self.ranked_target_horizon:
            raise ValueError("a reached search horizon requires a full ranked plan")
        if self.retrieval_mode == "not_needed":
            valid_execution = (
                self.scope_searchable_chunks == 0
                and self.query_embedding_source == "not_needed"
                and self.degraded_reason is None
                and not self.retryable
                and not self.ranked_targets
                and not self.ranked_horizon_reached
            )
        elif self.retrieval_mode == "hybrid":
            valid_execution = (
                self.scope_searchable_chunks > 0
                and self.query_embedding_source in {"cache", "live"}
                and self.degraded_reason is None
                and not self.retryable
            )
        else:
            valid_execution = (
                self.scope_searchable_chunks > 0
                and self.query_embedding_source == "unavailable"
                and self.degraded_reason is not None
                and self.retryable
                and all("vector" not in target.sources for target in self.ranked_targets)
            )
        if not valid_execution:
            raise ValueError("search execution metadata is inconsistent")
        return self


def build_first_page_search_plan(
    candidates: tuple[TransientGenerationCandidates, ...],
    embedding: QueryEmbeddingResolution,
    resolved_scope: ResolvedSearchScope,
) -> FirstPageSearchPlan:
    """Fuse every workspace/branch list once, then permanently discard scores."""

    if not 1 <= len(candidates) <= MAX_SEARCH_EXECUTION_WORKSPACES:
        raise SearchExecutionError("Dolphin search candidate workspace set is empty or too large")
    if resolved_scope.searchable_chunks == 0:
        raise SearchExecutionError("Dolphin empty search scope must not run retrieval")
    ordered = tuple(sorted(candidates, key=lambda item: item.snapshot.workspace_id))
    workspace_ids = tuple(item.snapshot.workspace_id for item in ordered)
    if len(set(workspace_ids)) != len(workspace_ids):
        raise SearchExecutionError("Dolphin search candidate workspace set contains duplicates")
    expected_counts = tuple((item.snapshot.workspace_id, item.snapshot.generation_id) for item in ordered)
    observed_counts = tuple((item.workspace_id, item.generation_id) for item in resolved_scope.workspace_counts)
    if observed_counts != expected_counts:
        raise SearchExecutionError("Dolphin resolved search scope does not match candidate authority")

    keyword_candidates: list[tuple[int, tuple[str, str, str, str]]] = []
    vector_candidates: list[tuple[int, tuple[str, str, str, str]]] = []
    for item in ordered:
        if item.retrieval_mode != embedding.retrieval_mode:
            raise SearchExecutionError("Dolphin search candidate retrieval mode is inconsistent")
        keyword_hits, vector_hits = canonicalize_generation_candidates(item.keyword_hits, item.vector_hits)
        if keyword_hits != item.keyword_hits or vector_hits != item.vector_hits:
            raise SearchExecutionError("Dolphin search candidates are not canonically ordered")
        if (item.retrieval_mode == "hybrid") != (vector_hits is not None):
            raise SearchExecutionError("Dolphin search candidate branch state is inconsistent")
        authority = (
            item.snapshot.workspace_id,
            item.snapshot.publication_id,
            item.snapshot.generation_id,
        )
        keyword_candidates.extend(
            (local_rank, (*authority, hit.chunk_instance_id)) for local_rank, hit in enumerate(keyword_hits, start=1)
        )
        if vector_hits is not None:
            vector_candidates.extend(
                (local_rank, (*authority, hit.chunk_instance_id)) for local_rank, hit in enumerate(vector_hits, start=1)
            )

    branch_ranks: dict[tuple[str, str, str, str], dict[SearchRetrievalSource, int]] = {}
    for rank, (_local_rank, identity) in enumerate(sorted(keyword_candidates), start=1):
        branch_ranks.setdefault(identity, {})["keyword"] = rank
    for rank, (_local_rank, identity) in enumerate(sorted(vector_candidates), start=1):
        branch_ranks.setdefault(identity, {})["vector"] = rank

    ranked = sorted(
        branch_ranks.items(),
        key=lambda item: (
            -sum(Fraction(1, GENERATION_RANKING_POLICY_RRF_CONSTANT + rank) for rank in item[1].values()),
            item[0],
        ),
    )
    retained = ranked[:GENERATION_RANKED_TARGET_HORIZON]
    targets = tuple(
        SearchRankedTarget(
            workspace_id=identity[0],
            publication_id=identity[1],
            generation_id=identity[2],
            chunk_instance_id=identity[3],
            rank=rank,
            sources=tuple(source for source in ("keyword", "vector") if source in ranks),
        )
        for rank, (identity, ranks) in enumerate(retained, start=1)
    )
    return FirstPageSearchPlan(
        snapshots=tuple(item.snapshot for item in ordered),
        scope_digest=resolved_scope.scope_digest,
        filter_shape=resolved_scope.filter_shape,
        scope_searchable_chunks=resolved_scope.searchable_chunks,
        retrieval_mode=embedding.retrieval_mode,
        query_embedding_source=embedding.source,
        degraded_reason=embedding.degraded_reason,
        retryable=embedding.retryable,
        ranked_targets_retained=len(targets),
        ranked_horizon_reached=len(ranked) > GENERATION_RANKED_TARGET_HORIZON,
        ranked_targets=targets,
    )


def build_empty_scope_search_plan(
    snapshots: tuple[PublishedSnapshot, ...],
    resolved_scope: ResolvedSearchScope,
) -> FirstPageSearchPlan:
    """Return a provider-free empty plan under the exact admitted authority."""

    ordered = tuple(sorted(snapshots, key=lambda snapshot: snapshot.workspace_id))
    if not 1 <= len(ordered) <= MAX_SEARCH_EXECUTION_WORKSPACES or len(
        {snapshot.workspace_id for snapshot in ordered}
    ) != len(ordered):
        raise SearchExecutionError("Dolphin empty search snapshot set is invalid")
    expected = tuple((snapshot.workspace_id, snapshot.generation_id) for snapshot in ordered)
    observed = tuple((item.workspace_id, item.generation_id) for item in resolved_scope.workspace_counts)
    if resolved_scope.searchable_chunks != 0 or observed != expected:
        raise SearchExecutionError("Dolphin empty search scope does not match admitted authority")
    return FirstPageSearchPlan(
        snapshots=ordered,
        scope_digest=resolved_scope.scope_digest,
        filter_shape=resolved_scope.filter_shape,
        scope_searchable_chunks=0,
        retrieval_mode="not_needed",
        query_embedding_source="not_needed",
        degraded_reason=None,
        retryable=False,
        ranked_targets_retained=0,
        ranked_horizon_reached=False,
        ranked_targets=(),
    )
