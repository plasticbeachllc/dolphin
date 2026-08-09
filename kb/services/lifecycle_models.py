"""Bounded public projections shared by Dolphin lifecycle read tools."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

type BoundaryKey = Annotated[str, StringConstraints(min_length=1, max_length=64)]
type BoundaryValue = Annotated[str, StringConstraints(max_length=256)]
type ActionArgumentValue = Annotated[str, StringConstraints(max_length=4_096)]
type RepositoryBoundarySummary = Annotated[dict[BoundaryKey, BoundaryValue], Field(max_length=6)]
type NextActionArguments = Annotated[dict[BoundaryKey, ActionArgumentValue], Field(max_length=8)]


class LifecycleResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NextAction(LifecycleResultModel):
    action: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=512)
    tool: str | None = Field(default=None, min_length=1, max_length=64)
    arguments: NextActionArguments | None = None


class RepositoryFamilySummary(LifecycleResultModel):
    id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=512)


class WorkspaceSummary(LifecycleResultModel):
    id: str = Field(min_length=1, max_length=64)
    repository_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=512)
    root: str = Field(min_length=1, max_length=4_096)
    branch: str | None = Field(default=None, max_length=1_024)
    head_commit: str = Field(min_length=1, max_length=64)
    state: Literal["registered", "indexing", "ready", "missing", "cleanup_pending", "failed"]
