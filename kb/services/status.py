"""The bounded, side-effect-free Dolphin runtime status service."""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from kb.mcp.contracts import StatusInput
from kb.services.lifecycle_models import NextAction, RepositoryBoundarySummary, WorkspaceSummary
from kb.services.lifecycle_read import repository_boundary_summary, workspace_summary
from kb.services.workspace_registry import WorkspaceReadSnapshot, WorkspaceRegistry, WorkspaceRegistryError
from kb.services.worktree import sanitized_git_environment
from kb.version import get_version


class _ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EffectiveWorkspaceCounts(_ResultModel):
    registered: int = Field(ge=0)
    indexing: int = Field(ge=0)
    ready: int = Field(ge=0)
    failed: int = Field(ge=0)


class ToolAvailability(_ResultModel):
    status: Literal["available", "unavailable"]
    repo_list: Literal["available", "unavailable"]
    repo_add: Literal["available", "unavailable"]
    repo_forget: Literal["available", "unavailable"]
    repo_sync: Literal["available", "unavailable"]
    operation_status: Literal["available", "unavailable"]
    search: Literal["available", "unavailable"]
    open_ref: Literal["available", "unavailable"]


class StatusResult(_ResultModel):
    version: str
    readiness: Literal["ready", "degraded", "blocked"]
    credential_present: bool
    credential_variable: Literal["DOLPHIN_OPENAI_API_KEY"]
    tool_availability: ToolAvailability
    workspace_counts: EffectiveWorkspaceCounts
    current_workspace_resolution: Literal["resolved", "unregistered", "ambiguous", "outside_worktree", "unavailable"]
    current_workspace: WorkspaceSummary | None = None
    current_repository_boundaries: list[RepositoryBoundarySummary] = Field(max_length=8)
    next_actions: list[NextAction] = Field(max_length=8)


@dataclass(frozen=True, slots=True)
class _WorktreeProbe:
    resolution: Literal["unregistered", "outside_worktree", "unavailable"]
    root: Path | None = None
    unavailable_reason: str | None = None


class StatusService:
    """Report cheap local readiness without enrolling or reconciling anything."""

    def __init__(
        self,
        *,
        cwd: Path | None = None,
        environment: Mapping[str, str] | None = None,
        registry: WorkspaceRegistry | None = None,
    ) -> None:
        self._cwd = (cwd or Path.cwd()).resolve()
        self._environment = environment if environment is not None else os.environ
        self._registry = registry

    async def __call__(self, _input: StatusInput) -> StatusResult:
        credential_present = bool(self._environment.get("DOLPHIN_OPENAI_API_KEY"))
        probe = await asyncio.to_thread(_probe_worktree, self._cwd)
        registry_snapshot = WorkspaceReadSnapshot(registered=0, indexing=0, ready=0, failed=0, current_workspace=None)
        storage_available = True
        if self._registry is not None:
            try:
                database_exists = await asyncio.to_thread(self._registry.database_exists)
                if database_exists:
                    if not await asyncio.to_thread(self._registry.schema_is_current):
                        raise WorkspaceRegistryError("Dolphin metadata storage requires initialization")
                    registry_snapshot = await asyncio.to_thread(self._registry.read_workspace_snapshot, probe.root)
            except WorkspaceRegistryError:
                storage_available = False

        current_workspace = (
            workspace_summary(registry_snapshot.current_workspace)
            if registry_snapshot.current_workspace is not None
            else None
        )
        if current_workspace is not None:
            resolution: Literal["resolved", "unregistered", "ambiguous", "outside_worktree", "unavailable"] = "resolved"
            next_actions: list[NextAction] = []
        elif not storage_available:
            resolution = "unavailable"
            next_actions = [NextAction(action="inspect_storage", reason="Dolphin metadata storage is unavailable.")]
        else:
            resolution = probe.resolution
            next_actions = _next_actions_for_probe(probe)

        return StatusResult(
            version=get_version(),
            # Most public tools are intentionally still represented by bounded
            # readiness errors while their application services are built.
            # Do not advertise overall readiness merely because a credential is
            # present: agents use this field to decide whether to proceed.
            readiness="degraded" if storage_available else "blocked",
            credential_present=credential_present,
            credential_variable="DOLPHIN_OPENAI_API_KEY",
            tool_availability=_tool_availability(storage_available),
            workspace_counts=EffectiveWorkspaceCounts(
                registered=registry_snapshot.registered,
                indexing=registry_snapshot.indexing,
                ready=registry_snapshot.ready,
                failed=registry_snapshot.failed,
            ),
            current_workspace_resolution=resolution,
            current_workspace=current_workspace,
            current_repository_boundaries=(
                [
                    repository_boundary_summary(boundary)
                    for boundary in registry_snapshot.current_workspace.repository_boundaries
                ]
                if registry_snapshot.current_workspace is not None
                else []
            ),
            next_actions=next_actions,
        )


def _probe_worktree(cwd: Path) -> _WorktreeProbe:
    """Resolve the process worktree without disguising probe failures as absence."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
            env=sanitized_git_environment(),
            text=True,
            timeout=1,
        )
    except FileNotFoundError:
        return _WorktreeProbe(resolution="unavailable", unavailable_reason="Git is unavailable to Dolphin.")
    except subprocess.TimeoutExpired:
        return _WorktreeProbe(resolution="unavailable", unavailable_reason="Git worktree detection timed out.")
    except OSError:
        return _WorktreeProbe(resolution="unavailable", unavailable_reason="Git worktree detection failed.")
    root = result.stdout.removesuffix("\n")
    if result.returncode == 0 and root:
        return _WorktreeProbe(resolution="unregistered", root=Path(root))
    if result.returncode == 128 and _is_outside_worktree_error(result.stderr):
        return _WorktreeProbe(resolution="outside_worktree")
    return _WorktreeProbe(resolution="unavailable", unavailable_reason="Git worktree detection failed.")


def _is_outside_worktree_error(stderr: str | None) -> bool:
    normalized = (stderr or "").lower()
    return "not a git repository" in normalized or "not a git work tree" in normalized


def _next_actions_for_probe(probe: _WorktreeProbe) -> list[NextAction]:
    if probe.root is not None:
        return [
            NextAction(
                action="registration_unavailable",
                reason="Dolphin has not registered this Git worktree, but repo_add is unavailable in this runtime.",
            )
        ]
    if probe.unavailable_reason is not None:
        return [NextAction(action="inspect_git", reason=probe.unavailable_reason)]
    return []


def _tool_availability(storage_available: bool) -> ToolAvailability:
    read_state: Literal["available", "unavailable"] = "available" if storage_available else "unavailable"
    return ToolAvailability(
        status="available",
        repo_list=read_state,
        repo_add="unavailable",
        repo_forget="unavailable",
        repo_sync="unavailable",
        operation_status=read_state,
        search="unavailable",
        open_ref="unavailable",
    )
