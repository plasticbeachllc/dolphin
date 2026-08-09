"""Bounded public projections shared by Dolphin lifecycle read tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class LifecycleResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NextAction(LifecycleResultModel):
    action: str
    reason: str
    tool: str | None = None
    arguments: dict[str, str] | None = None


class RepositoryFamilySummary(LifecycleResultModel):
    id: str
    display_name: str


class WorkspaceSummary(LifecycleResultModel):
    id: str
    repository_id: str
    display_name: str
    root: str
    branch: str | None
    head_commit: str
    state: Literal["registered", "indexing", "ready", "missing", "cleanup_pending", "failed"]
