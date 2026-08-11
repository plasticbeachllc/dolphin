"""Strict, transport-independent MCP input contracts for Dolphin 0.3.0.

Every optional MCP input is represented by an explicitly required nullable
field.  This keeps the JSON Schema compatible with strict tool callers while
making automatic behavior unambiguous to application services.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kb.cleanup_authority import CLEANUP_RECEIPT_LENGTH, CLEANUP_RECEIPT_PATTERN
from kb.lifecycle_limits import ENTITY_ID_MAX_LENGTH, OPERATION_ID_MAX_LENGTH, REPO_LIST_CURSOR_MAX_LENGTH
from kb.search_scope import (
    MAX_SEARCH_LANGUAGES,
    MAX_SEARCH_PATH_PATTERN_LENGTH,
    MAX_SEARCH_PATH_PATTERNS,
    MAX_SEARCH_SCOPE_WORKSPACES,
    SearchLanguage,
    SearchScope,
    SearchScopeError,
)

_SearchPathPattern = Annotated[str, Field(min_length=1, max_length=MAX_SEARCH_PATH_PATTERN_LENGTH)]
_SearchWorkspaceId = Annotated[str, Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)]


class StrictInput(BaseModel):
    """Base model for every public MCP tool input."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class StatusInput(StrictInput):
    """Status has an intentionally empty input object."""


class RepoListInput(StrictInput):
    """Page through actionable workspace registrations."""

    cursor: str | None = Field(
        max_length=REPO_LIST_CURSOR_MAX_LENGTH,
        description="Opaque cursor from repo_list; null starts the first page.",
    )


class RepoAddInput(StrictInput):
    """Explicitly register one concrete Git worktree."""

    path: Path = Field(description="Absolute path to the concrete Git worktree root.")
    cleanup_receipt: str = Field(
        min_length=CLEANUP_RECEIPT_LENGTH,
        max_length=CLEANUP_RECEIPT_LENGTH,
        pattern=CLEANUP_RECEIPT_PATTERN,
        repr=False,
        description=(
            "Caller-supplied dolphin-cleanup-v1_ receipt containing 32 random bytes encoded as unpadded "
            "base64url; retain it to retry repo_add or authorize repo_forget."
        ),
    )

    @field_validator("path")
    @classmethod
    def require_absolute_path(cls, path: Path) -> Path:
        """Keep relative client paths out of the frozen public contract."""
        if not path.is_absolute():
            raise ValueError("path must be absolute")
        return path


class RepoForgetInput(StrictInput):
    """Release one registration epoch authorized by its creation receipt."""

    workspace_id: str = Field(min_length=1)
    cleanup_receipt: str = Field(min_length=1, repr=False)


class RepoSyncInput(StrictInput):
    """Request freshness reconciliation for one registered workspace."""

    workspace_id: str = Field(min_length=1)


class OperationStatusInput(StrictInput):
    """Inspect one exact durable operation."""

    operation_id: str = Field(min_length=1, max_length=OPERATION_ID_MAX_LENGTH)


class SearchQueryRequest(StrictInput):
    """The complete first-page search variant."""

    kind: Literal["query"]
    query: str = Field(min_length=1, max_length=2_000)
    workspace_ids: list[_SearchWorkspaceId] | None = Field(
        max_length=MAX_SEARCH_SCOPE_WORKSPACES,
        description="Explicit workspace scope; null requests deterministic current-workspace resolution.",
    )
    paths: list[_SearchPathPattern] = Field(
        max_length=MAX_SEARCH_PATH_PATTERNS,
        description="Canonical workspace-relative include globs; [] means no narrowing.",
    )
    exclude_paths: list[_SearchPathPattern] = Field(
        max_length=MAX_SEARCH_PATH_PATTERNS,
        description="Canonical workspace-relative exclude globs; [] means none.",
    )
    languages: list[SearchLanguage] = Field(
        max_length=MAX_SEARCH_LANGUAGES,
        description="Normalized first-class language names; [] means all languages.",
    )
    max_results: int | None = Field(
        ge=1,
        le=50,
        description="Null selects the adaptive per-page result default.",
    )
    max_context_tokens: int | None = Field(
        ge=0,
        le=20_000,
        description="Null selects the adaptive per-page snippet budget.",
    )

    @model_validator(mode="after")
    def task_scope_is_safe_and_bounded(self) -> SearchQueryRequest:
        try:
            SearchScope.from_inputs(
                paths=self.paths,
                exclude_paths=self.exclude_paths,
                languages=self.languages,
            )
        except SearchScopeError as exc:
            raise ValueError(str(exc)) from exc
        if self.workspace_ids is not None and len(set(self.workspace_ids)) != len(self.workspace_ids):
            raise ValueError("workspace_ids must not contain duplicates")
        return self


class SearchContinuationRequest(StrictInput):
    """The cursor-only continuation variant."""

    kind: Literal["continue"]
    cursor: str = Field(min_length=1, description="Opaque cursor returned by the previous search page.")


class SearchInput(StrictInput):
    """Nested query-or-continuation search envelope."""

    request: SearchQueryRequest | SearchContinuationRequest


class OpenRefInput(StrictInput):
    """Read a bounded current excerpt through a Dolphin-issued reference."""

    ref: str = Field(min_length=1, description="Opaque dolphin://ref/... value returned by search.")
