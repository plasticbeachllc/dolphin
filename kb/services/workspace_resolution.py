"""Deterministic, connection-local workspace scope resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from kb.lifecycle_limits import ENTITY_ID_MAX_LENGTH
from kb.mcp.errors import ToolError
from kb.services.repository_boundaries import RepositoryBoundaryKind, RepositoryBoundaryState
from kb.services.workspace_registry import BoundaryPathMatch, WorkspaceRegistry, WorkspaceSnapshot

MCP_ROOT_LIMIT = 32
_MAX_RESOLUTION_CHOICES = 8


class WorkspaceResolutionOutcome(StrEnum):
    RESOLVED = "resolved"
    UNREGISTERED = "unregistered"
    AMBIGUOUS = "ambiguous"
    REQUIRED = "required"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"


class WorkspaceResolutionSource(StrEnum):
    EXPLICIT = "explicit"
    MCP_ROOT = "mcp_root"
    SESSION = "session"
    CWD = "cwd"


@dataclass(slots=True)
class WorkspaceSessionScope:
    """One MCP connection's inferred default; never shared across connections."""

    _workspace_id: str | None = None

    @property
    def workspace_id(self) -> str | None:
        return self._workspace_id

    def select(self, workspace_id: str) -> None:
        if not workspace_id or len(workspace_id) > ENTITY_ID_MAX_LENGTH:
            raise ValueError("workspace ID is invalid")
        self._workspace_id = workspace_id

    def clear(self) -> None:
        self._workspace_id = None

    def clear_if_selected(self, workspace_id: str) -> None:
        if self._workspace_id == workspace_id:
            self.clear()


@dataclass(frozen=True, slots=True)
class MCPRootSnapshot:
    """One client root bound to a bounded local Git probe result."""

    path: Path
    worktree_root: Path | None
    probe_available: bool


@dataclass(frozen=True, slots=True)
class WorkspaceResolution:
    outcome: WorkspaceResolutionOutcome
    source: WorkspaceResolutionSource | None = None
    workspace: WorkspaceSnapshot | None = None
    boundary: BoundaryPathMatch | None = None
    unregistered_root: Path | None = None
    workspace_candidates: tuple[WorkspaceSnapshot, ...] = ()
    boundary_candidates: tuple[BoundaryPathMatch, ...] = ()
    unregistered_candidates: tuple[Path, ...] = ()
    candidates_truncated: bool = False


class WorkspaceResolver:
    """Resolve one current workspace without filesystem or registry mutation."""

    def __init__(
        self,
        registry: WorkspaceRegistry,
        *,
        session_scope: WorkspaceSessionScope | None = None,
    ) -> None:
        self._registry = registry
        self._session_scope = session_scope or WorkspaceSessionScope()

    @property
    def session_scope(self) -> WorkspaceSessionScope:
        return self._session_scope

    def resolve(
        self,
        *,
        explicit_workspace_id: str | None = None,
        mcp_roots: tuple[MCPRootSnapshot, ...] = (),
        cwd: Path | None = None,
        cwd_worktree_root: Path | None = None,
    ) -> WorkspaceResolution:
        if explicit_workspace_id is not None:
            workspace = self._registry.inspect_workspace(explicit_workspace_id)
            if workspace is None:
                return WorkspaceResolution(
                    outcome=WorkspaceResolutionOutcome.MISSING,
                    source=WorkspaceResolutionSource.EXPLICIT,
                )
            self._session_scope.select(workspace.workspace_id)
            return _resolved(workspace, WorkspaceResolutionSource.EXPLICIT)

        root_resolution = self._resolve_mcp_roots(mcp_roots)
        if root_resolution is not None:
            return root_resolution

        if self._session_scope.workspace_id is not None:
            workspace = self._registry.inspect_workspace(self._session_scope.workspace_id)
            if workspace is None:
                return WorkspaceResolution(
                    outcome=WorkspaceResolutionOutcome.MISSING,
                    source=WorkspaceResolutionSource.SESSION,
                )
            return _resolved(workspace, WorkspaceResolutionSource.SESSION)

        if cwd is None:
            return WorkspaceResolution(outcome=WorkspaceResolutionOutcome.REQUIRED)
        match_path = cwd_worktree_root or cwd
        match = self._registry.resolve_workspace_path(match_path)
        if match.boundary is not None:
            return WorkspaceResolution(
                outcome=WorkspaceResolutionOutcome.UNREGISTERED,
                source=WorkspaceResolutionSource.CWD,
                boundary=match.boundary,
            )
        if match.workspace is not None:
            if cwd_worktree_root is not None and Path(match.workspace.root) != cwd_worktree_root:
                return WorkspaceResolution(
                    outcome=WorkspaceResolutionOutcome.UNREGISTERED,
                    source=WorkspaceResolutionSource.CWD,
                    unregistered_root=cwd_worktree_root,
                )
            return _resolved(match.workspace, WorkspaceResolutionSource.CWD)
        if cwd_worktree_root is not None:
            return WorkspaceResolution(
                outcome=WorkspaceResolutionOutcome.UNREGISTERED,
                source=WorkspaceResolutionSource.CWD,
                unregistered_root=cwd_worktree_root,
            )
        return WorkspaceResolution(outcome=WorkspaceResolutionOutcome.REQUIRED, source=WorkspaceResolutionSource.CWD)

    def _resolve_mcp_roots(self, roots: tuple[MCPRootSnapshot, ...]) -> WorkspaceResolution | None:
        if not roots:
            return None
        if len(roots) > MCP_ROOT_LIMIT:
            return WorkspaceResolution(
                outcome=WorkspaceResolutionOutcome.AMBIGUOUS,
                source=WorkspaceResolutionSource.MCP_ROOT,
                candidates_truncated=True,
            )

        matches: dict[tuple[str, str], WorkspaceResolution] = {}
        unavailable = False
        for root in roots:
            resolution = self._resolve_mcp_root(root)
            if resolution is None:
                continue
            if resolution.outcome is WorkspaceResolutionOutcome.UNAVAILABLE:
                unavailable = True
                continue
            key = _resolution_key(resolution)
            matches[key] = resolution
        if unavailable:
            return WorkspaceResolution(
                outcome=WorkspaceResolutionOutcome.UNAVAILABLE,
                source=WorkspaceResolutionSource.MCP_ROOT,
            )
        if not matches:
            return None
        if len(matches) == 1:
            return next(iter(matches.values()))

        workspace_candidates = tuple(
            sorted(
                (resolution.workspace for resolution in matches.values() if resolution.workspace is not None),
                key=lambda workspace: workspace.workspace_id,
            )[:_MAX_RESOLUTION_CHOICES]
        )
        boundary_candidates = tuple(
            sorted(
                (resolution.boundary for resolution in matches.values() if resolution.boundary is not None),
                key=lambda boundary: boundary.root,
            )[:_MAX_RESOLUTION_CHOICES]
        )
        unregistered_candidate_values: list[Path] = []
        for resolution in matches.values():
            if resolution.unregistered_root is not None:
                unregistered_candidate_values.append(resolution.unregistered_root)
        unregistered_candidates = tuple(
            sorted(unregistered_candidate_values, key=lambda candidate: str(candidate))[:_MAX_RESOLUTION_CHOICES]
        )
        return WorkspaceResolution(
            outcome=WorkspaceResolutionOutcome.AMBIGUOUS,
            source=WorkspaceResolutionSource.MCP_ROOT,
            workspace_candidates=workspace_candidates,
            boundary_candidates=boundary_candidates,
            unregistered_candidates=unregistered_candidates,
            candidates_truncated=len(matches) > _MAX_RESOLUTION_CHOICES,
        )

    def _resolve_mcp_root(self, root: MCPRootSnapshot) -> WorkspaceResolution | None:
        if not _is_bounded_absolute_path(root.path) or (
            root.worktree_root is not None and not _is_bounded_absolute_path(root.worktree_root)
        ):
            return WorkspaceResolution(
                outcome=WorkspaceResolutionOutcome.UNAVAILABLE,
                source=WorkspaceResolutionSource.MCP_ROOT,
            )
        if root.worktree_root is not None:
            match = self._registry.resolve_workspace_path(root.worktree_root)
            if match.boundary is not None:
                return WorkspaceResolution(
                    outcome=WorkspaceResolutionOutcome.UNREGISTERED,
                    source=WorkspaceResolutionSource.MCP_ROOT,
                    boundary=match.boundary,
                )
            if match.workspace is not None and Path(match.workspace.root) == root.worktree_root:
                return _resolved(match.workspace, WorkspaceResolutionSource.MCP_ROOT)
            return WorkspaceResolution(
                outcome=WorkspaceResolutionOutcome.UNREGISTERED,
                source=WorkspaceResolutionSource.MCP_ROOT,
                unregistered_root=root.worktree_root,
            )

        persisted_match = self._registry.resolve_workspace_path(root.path)
        if persisted_match.boundary is not None:
            return WorkspaceResolution(
                outcome=WorkspaceResolutionOutcome.UNREGISTERED,
                source=WorkspaceResolutionSource.MCP_ROOT,
                boundary=persisted_match.boundary,
            )
        if not root.probe_available:
            return WorkspaceResolution(
                outcome=WorkspaceResolutionOutcome.UNAVAILABLE,
                source=WorkspaceResolutionSource.MCP_ROOT,
            )
        if root.worktree_root is None:
            return None
        raise AssertionError("unreachable MCP root resolution state")


def workspace_resolution_error(resolution: WorkspaceResolution, *, tool_name: str) -> ToolError:
    """Project a failed resolution into a bounded, task-ready MCP error."""
    if resolution.outcome is WorkspaceResolutionOutcome.AMBIGUOUS:
        candidates = [_workspace_choice(workspace) for workspace in resolution.workspace_candidates]
        boundary_candidates = [_boundary_choice(boundary) for boundary in resolution.boundary_candidates]
        unregistered_roots = [str(root) for root in resolution.unregistered_candidates]
        return ToolError(
            code="WORKSPACE_AMBIGUOUS",
            message="Dolphin cannot choose one workspace without an explicit workspace ID.",
            retryable=False,
            details={
                "candidates": candidates,
                "boundary_candidates": boundary_candidates,
                "unregistered_roots": unregistered_roots,
                "candidates_truncated": resolution.candidates_truncated,
                "next_action": {"tool": "repo_list", "arguments": {"cursor": None}},
            },
        )
    if resolution.outcome is WorkspaceResolutionOutcome.MISSING:
        return ToolError(
            code="WORKSPACE_MISSING",
            message="The selected Dolphin workspace is unavailable.",
            retryable=False,
            details={"next_action": {"tool": "repo_list", "arguments": {"cursor": None}}},
        )
    if resolution.outcome is WorkspaceResolutionOutcome.UNAVAILABLE:
        return ToolError(
            code="WORKSPACE_RESOLUTION_UNAVAILABLE",
            message="Dolphin could not safely inspect the client workspace roots.",
            retryable=True,
            details={"next_action": {"tool": "status", "arguments": {}}},
        )
    if resolution.boundary is not None:
        boundary = resolution.boundary.boundary
        if boundary.kind is RepositoryBoundaryKind.SUBMODULE and boundary.state in {
            RepositoryBoundaryState.UNINITIALIZED,
            RepositoryBoundaryState.MISSING,
        }:
            return ToolError(
                code="SUBMODULE_UNINITIALIZED",
                message="The requested path is inside a submodule without a usable checkout.",
                retryable=False,
                details={"path": resolution.boundary.root},
            )
        if boundary.state in {RepositoryBoundaryState.INVALID, RepositoryBoundaryState.CONFLICTED}:
            return ToolError(
                code="REPOSITORY_BOUNDARY_INVALID",
                message="The requested path is inside an invalid repository boundary.",
                retryable=False,
                details={"path": resolution.boundary.root, "state": boundary.state.value},
            )
    details: dict[str, Any] = {"next_action": {"tool": "status", "arguments": {}}}
    if resolution.unregistered_root is not None:
        details["path"] = str(resolution.unregistered_root)
    return ToolError(
        code="WORKSPACE_REQUIRED",
        message=f"Dolphin needs an explicit registered workspace before {tool_name} can run.",
        retryable=False,
        details=details,
    )


def _resolved(workspace: WorkspaceSnapshot, source: WorkspaceResolutionSource) -> WorkspaceResolution:
    return WorkspaceResolution(
        outcome=WorkspaceResolutionOutcome.RESOLVED,
        source=source,
        workspace=workspace,
    )


def _workspace_choice(workspace: WorkspaceSnapshot) -> dict[str, str | None]:
    return {
        "workspace_id": workspace.workspace_id,
        "display_name": workspace.workspace_display_name,
        "root": workspace.root,
        "branch": workspace.branch,
        "head_commit": workspace.head_commit,
    }


def _boundary_choice(boundary: BoundaryPathMatch) -> dict[str, str | None]:
    return {
        "root": boundary.root,
        "kind": boundary.boundary.kind.value,
        "state": boundary.boundary.state.value,
        "workspace_id": boundary.boundary.workspace_id,
    }


def _resolution_key(resolution: WorkspaceResolution) -> tuple[str, str]:
    if resolution.workspace is not None:
        return "workspace", resolution.workspace.workspace_id
    if resolution.boundary is not None:
        return "boundary", resolution.boundary.root
    if resolution.unregistered_root is not None:
        return "unregistered", str(resolution.unregistered_root)
    raise ValueError("workspace resolution has no stable candidate key")


def _is_bounded_absolute_path(path: Path) -> bool:
    encoded = str(path)
    return (
        path.is_absolute() and 0 < len(encoded) <= 4_096 and not any(marker in encoded for marker in ("\0", "\n", "\r"))
    )
