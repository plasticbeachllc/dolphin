"""Bounded public projections shared by Dolphin lifecycle read tools."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from kb.lifecycle_limits import ENTITY_ID_MAX_LENGTH, HEAD_COMMIT_MAX_LENGTH
from kb.services.repository_boundaries import RepositoryBoundaryKind, RepositoryBoundaryState

type BoundaryKey = Annotated[str, StringConstraints(min_length=1, max_length=64)]
type ActionArgumentValue = Annotated[str, StringConstraints(max_length=4_096)] | None
type NextActionArguments = Annotated[dict[BoundaryKey, ActionArgumentValue], Field(max_length=8)]


class LifecycleResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NextAction(LifecycleResultModel):
    action: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=512)
    tool: str | None = Field(default=None, min_length=1, max_length=64)
    arguments: NextActionArguments | None = None


class RepositoryBoundarySummary(LifecycleResultModel):
    kind: RepositoryBoundaryKind
    relative_path: str = Field(min_length=1, max_length=4_096)
    root: str | None = Field(default=None, min_length=1, max_length=4_096)
    state: RepositoryBoundaryState
    expected_commit: str | None = Field(default=None, min_length=1, max_length=HEAD_COMMIT_MAX_LENGTH)
    observed_commit: str | None = Field(default=None, min_length=1, max_length=HEAD_COMMIT_MAX_LENGTH)
    dirty: bool | None = None
    workspace_id: str | None = Field(default=None, min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    next_actions: list[NextAction] = Field(default_factory=list, max_length=4)


class RepositoryFamilySummary(LifecycleResultModel):
    id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    display_name: str = Field(min_length=1, max_length=512)


class WorkspaceSummary(LifecycleResultModel):
    id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    repository_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    display_name: str = Field(min_length=1, max_length=512)
    root: str = Field(min_length=1, max_length=4_096)
    branch: str | None = Field(default=None, max_length=1_024)
    head_commit: str = Field(min_length=1, max_length=HEAD_COMMIT_MAX_LENGTH)
    state: Literal["registered", "indexing", "ready", "missing", "cleanup_pending", "failed"]
