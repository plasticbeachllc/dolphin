"""The bounded, side-effect-free Dolphin runtime status service."""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from kb.mcp.contracts import StatusInput
from kb.version import get_version


class _ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EffectiveWorkspaceCounts(_ResultModel):
    registered: int = Field(ge=0)
    indexing: int = Field(ge=0)
    ready: int = Field(ge=0)
    missing: int = Field(ge=0)
    cleanup_pending: int = Field(ge=0)
    failed: int = Field(ge=0)


class ForgottenStateAggregates(_ResultModel):
    replay_tombstones: int = Field(ge=0)
    tombstone_metadata_bytes: int = Field(ge=0)
    awaiting_physical_reclamation: int = Field(ge=0)


class NextAction(_ResultModel):
    action: str
    reason: str
    tool: str | None = None
    arguments: dict[str, str] | None = None


class StatusResult(_ResultModel):
    version: str
    readiness: Literal["ready", "degraded", "blocked"]
    credential_present: bool
    credential_variable: Literal["DOLPHIN_OPENAI_API_KEY"]
    workspace_counts: EffectiveWorkspaceCounts
    forgotten: ForgottenStateAggregates
    current_workspace_resolution: Literal["resolved", "unregistered", "ambiguous", "outside_worktree", "unavailable"]
    current_workspace: None = None
    current_repository_boundaries: list[dict[str, str]]
    next_actions: list[NextAction]


class StatusService:
    """Report cheap local readiness without enrolling or reconciling anything."""

    def __init__(self, *, cwd: Path | None = None, environment: Mapping[str, str] | None = None) -> None:
        self._cwd = (cwd or Path.cwd()).resolve()
        self._environment = environment if environment is not None else os.environ

    async def __call__(self, _input: StatusInput) -> StatusResult:
        credential_present = bool(self._environment.get("DOLPHIN_OPENAI_API_KEY"))
        worktree_root = await asyncio.to_thread(_worktree_root, self._cwd)
        next_actions = [] if worktree_root is None else [_repo_add_action(worktree_root)]

        return StatusResult(
            version=get_version(),
            # Most public tools are intentionally still represented by bounded
            # readiness errors while their application services are built.
            # Do not advertise overall readiness merely because a credential is
            # present: agents use this field to decide whether to proceed.
            readiness="degraded",
            credential_present=credential_present,
            credential_variable="DOLPHIN_OPENAI_API_KEY",
            workspace_counts=EffectiveWorkspaceCounts(
                registered=0,
                indexing=0,
                ready=0,
                missing=0,
                cleanup_pending=0,
                failed=0,
            ),
            forgotten=ForgottenStateAggregates(
                replay_tombstones=0,
                tombstone_metadata_bytes=0,
                awaiting_physical_reclamation=0,
            ),
            current_workspace_resolution="unregistered" if worktree_root else "outside_worktree",
            current_workspace=None,
            current_repository_boundaries=[],
            next_actions=next_actions,
        )


def _worktree_root(cwd: Path) -> Path | None:
    """Resolve only the process's own worktree root; never enroll it."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    root = result.stdout.removesuffix("\n")
    if result.returncode != 0 or not root:
        return None
    return Path(root)


def _repo_add_action(worktree_root: Path) -> NextAction:
    return NextAction(
        action="register_worktree",
        reason="Dolphin has not registered this Git worktree.",
        tool="repo_add",
        arguments={"path": str(worktree_root)},
    )
