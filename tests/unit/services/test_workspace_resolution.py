"""Tests for deterministic current-workspace scope resolution."""

from __future__ import annotations

import base64
import hashlib
import subprocess
from pathlib import Path

import pytest

from kb.runtime.storage import macos_storage_layout
from kb.services.repo_add import RepoAddService
from kb.services.repository_boundaries import RepositoryBoundary, RepositoryBoundaryKind, RepositoryBoundaryState
from kb.services.workspace_registry import BoundaryPathMatch, WorkspaceRegistry
from kb.services.workspace_resolution import (
    MCPRootSnapshot,
    WorkspaceResolution,
    WorkspaceResolutionOutcome,
    WorkspaceResolutionSource,
    WorkspaceResolver,
    WorkspaceSessionScope,
    workspace_resolution_error,
)
from kb.services.worktree import discover_git_worktree_sync


def test_registry_path_resolution_prefers_a_registered_nested_worktree(tmp_path: Path) -> None:
    parent = _commit_repository(tmp_path / "parent")
    child = _commit_repository(parent / "child")
    registry = _registry(tmp_path)
    parent_submission = _submit(registry, parent, "parent")

    parent_match = registry.resolve_workspace_path(parent / "src" / "module.py")
    unregistered_child = registry.resolve_workspace_path(child / "src" / "child.py")

    assert parent_match.workspace is not None
    assert parent_match.workspace.workspace_id == parent_submission.registration.workspace_id
    assert unregistered_child.workspace is None
    assert unregistered_child.boundary is not None
    assert unregistered_child.boundary.root == str(child)
    assert unregistered_child.boundary.boundary.state is RepositoryBoundaryState.ENROLLABLE

    child_submission = _submit(registry, child, "child")
    registered_child = registry.resolve_workspace_path(child / "src" / "child.py")
    refreshed_parent = registry.inspect_workspace(parent_submission.registration.workspace_id)

    assert registered_child.workspace is not None
    assert registered_child.workspace.workspace_id == child_submission.registration.workspace_id
    assert registered_child.boundary is None
    assert refreshed_parent is not None
    assert refreshed_parent.repository_boundaries[0].workspace_id == child_submission.registration.workspace_id


def test_resolver_applies_explicit_root_session_and_cwd_precedence(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    first = _register(registry, _commit_repository(tmp_path / "first"), "first")
    second = _register(registry, _commit_repository(tmp_path / "second"), "second")
    third = _register(registry, _commit_repository(tmp_path / "third"), "third")
    session = WorkspaceSessionScope(third.workspace_id)
    resolver = WorkspaceResolver(registry, session_scope=session)

    explicit = resolver.resolve(
        explicit_workspace_id=first.workspace_id,
        mcp_roots=(_mcp_root(Path(second.root)),),
        cwd=Path(third.root),
        cwd_worktree_root=Path(third.root),
    )
    assert explicit.workspace is not None
    assert explicit.workspace.workspace_id == first.workspace_id
    assert explicit.source is WorkspaceResolutionSource.EXPLICIT
    assert session.workspace_id == first.workspace_id

    session.select(third.workspace_id)
    rooted = resolver.resolve(
        mcp_roots=(_mcp_root(Path(second.root) / "src", worktree_root=Path(second.root)),),
        cwd=Path(first.root),
        cwd_worktree_root=Path(first.root),
    )
    assert rooted.workspace is not None
    assert rooted.workspace.workspace_id == second.workspace_id
    assert rooted.source is WorkspaceResolutionSource.MCP_ROOT
    assert session.workspace_id == third.workspace_id

    session_selected = resolver.resolve(cwd=Path(first.root), cwd_worktree_root=Path(first.root))
    assert session_selected.workspace is not None
    assert session_selected.workspace.workspace_id == third.workspace_id
    assert session_selected.source is WorkspaceResolutionSource.SESSION

    session.clear()
    cwd_selected = resolver.resolve(cwd=Path(first.root) / "src", cwd_worktree_root=Path(first.root))
    assert cwd_selected.workspace is not None
    assert cwd_selected.workspace.workspace_id == first.workspace_id
    assert cwd_selected.source is WorkspaceResolutionSource.CWD


def test_resolver_never_guesses_between_distinct_mcp_roots(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    first = _register(registry, _commit_repository(tmp_path / "first"), "first")
    second = _register(registry, _commit_repository(tmp_path / "second"), "second")

    result = WorkspaceResolver(registry).resolve(mcp_roots=(_mcp_root(Path(first.root)), _mcp_root(Path(second.root))))

    assert result.outcome is WorkspaceResolutionOutcome.AMBIGUOUS
    assert result.source is WorkspaceResolutionSource.MCP_ROOT
    assert {candidate.workspace_id for candidate in result.workspace_candidates} == {
        first.workspace_id,
        second.workspace_id,
    }
    assert workspace_resolution_error(result, tool_name="search").code == "WORKSPACE_AMBIGUOUS"


def test_resolver_fails_closed_when_any_mcp_root_probe_is_unavailable(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registered = _register(registry, _commit_repository(tmp_path / "registered"), "registered")
    session = WorkspaceSessionScope(registered.workspace_id)

    result = WorkspaceResolver(registry, session_scope=session).resolve(
        mcp_roots=(
            _mcp_root(Path(registered.root)),
            MCPRootSnapshot(path=tmp_path / "unavailable", worktree_root=None, probe_available=False),
        ),
        cwd=Path(registered.root),
        cwd_worktree_root=Path(registered.root),
    )

    assert result.outcome is WorkspaceResolutionOutcome.UNAVAILABLE
    assert result.source is WorkspaceResolutionSource.MCP_ROOT
    assert workspace_resolution_error(result, tool_name="search").code == "WORKSPACE_RESOLUTION_UNAVAILABLE"


def test_one_registered_mcp_root_wins_when_other_roots_are_known_unregistered(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registered = _register(registry, _commit_repository(tmp_path / "registered"), "registered")
    unregistered = _commit_repository(tmp_path / "unregistered")

    result = WorkspaceResolver(registry).resolve(mcp_roots=(_mcp_root(Path(registered.root)), _mcp_root(unregistered)))

    assert result.outcome is WorkspaceResolutionOutcome.RESOLVED
    assert result.workspace is not None
    assert result.workspace.workspace_id == registered.workspace_id


def test_missing_session_scope_does_not_fall_back_to_cwd(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registered = _register(registry, _commit_repository(tmp_path / "registered"), "registered")
    session = WorkspaceSessionScope("ws_missing")

    result = WorkspaceResolver(registry, session_scope=session).resolve(
        cwd=Path(registered.root),
        cwd_worktree_root=Path(registered.root),
    )

    assert result.outcome is WorkspaceResolutionOutcome.MISSING
    assert result.source is WorkspaceResolutionSource.SESSION
    assert result.workspace is None
    assert workspace_resolution_error(result, tool_name="search").code == "WORKSPACE_MISSING"


def test_new_nested_worktree_never_falls_back_to_its_registered_parent(tmp_path: Path) -> None:
    parent = _commit_repository(tmp_path / "parent")
    registry = _registry(tmp_path)
    _register(registry, parent, "parent")
    child = _commit_repository(parent / "created-later")

    result = WorkspaceResolver(registry).resolve(
        cwd=child,
        cwd_worktree_root=child,
    )

    assert result.outcome is WorkspaceResolutionOutcome.UNREGISTERED
    assert result.workspace is None
    assert result.unregistered_root == child

    client_root_result = WorkspaceResolver(registry).resolve(mcp_roots=(_mcp_root(child),))

    assert client_root_result.outcome is WorkspaceResolutionOutcome.UNREGISTERED
    assert client_root_result.workspace is None
    assert client_root_result.unregistered_root == child


def test_connection_local_scopes_do_not_leak(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registered = _register(registry, _commit_repository(tmp_path / "registered"), "registered")
    first = WorkspaceSessionScope()
    second = WorkspaceSessionScope()

    WorkspaceResolver(registry, session_scope=first).resolve(explicit_workspace_id=registered.workspace_id)

    assert first.workspace_id == registered.workspace_id
    assert second.workspace_id is None


@pytest.mark.asyncio
async def test_repo_add_establishes_only_its_connection_local_scope(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    root = _commit_repository(tmp_path / "registered")
    first = WorkspaceSessionScope()
    second = WorkspaceSessionScope()

    submission = await RepoAddService(registry, session_scope=first).submit(root, _cleanup_receipt("registered"))

    assert first.workspace_id == submission.registration.workspace_id
    assert second.workspace_id is None


def test_boundary_failures_map_to_typed_errors(tmp_path: Path) -> None:
    uninitialized = WorkspaceResolution(
        outcome=WorkspaceResolutionOutcome.UNREGISTERED,
        boundary=BoundaryPathMatch(
            parent_workspace_id="ws_parent",
            root=str(tmp_path / "submodule"),
            boundary=RepositoryBoundary(
                kind=RepositoryBoundaryKind.SUBMODULE,
                relative_path="submodule",
                state=RepositoryBoundaryState.UNINITIALIZED,
                workspace_id="ws_submodule",
            ),
        ),
    )
    invalid = WorkspaceResolution(
        outcome=WorkspaceResolutionOutcome.UNREGISTERED,
        boundary=BoundaryPathMatch(
            parent_workspace_id="ws_parent",
            root=str(tmp_path / "nested"),
            boundary=RepositoryBoundary(
                kind=RepositoryBoundaryKind.NESTED_GIT,
                relative_path="nested",
                state=RepositoryBoundaryState.INVALID,
            ),
        ),
    )

    assert workspace_resolution_error(uninitialized, tool_name="search").code == "SUBMODULE_UNINITIALIZED"
    assert workspace_resolution_error(invalid, tool_name="search").code == "REPOSITORY_BOUNDARY_INVALID"
    assert uninitialized.boundary is not None
    assert invalid.boundary is not None
    ambiguous = WorkspaceResolution(
        outcome=WorkspaceResolutionOutcome.AMBIGUOUS,
        source=WorkspaceResolutionSource.MCP_ROOT,
        boundary_candidates=(uninitialized.boundary, invalid.boundary),
    )

    assert workspace_resolution_error(ambiguous, tool_name="search").details["boundary_candidates"] == [
        {
            "root": str(tmp_path / "submodule"),
            "kind": "submodule",
            "state": "uninitialized",
            "workspace_id": "ws_submodule",
        },
        {
            "root": str(tmp_path / "nested"),
            "kind": "nested_git",
            "state": "invalid",
            "workspace_id": None,
        },
    ]


def _registry(tmp_path: Path) -> WorkspaceRegistry:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return WorkspaceRegistry(macos_storage_layout(home=home))


def _register(registry: WorkspaceRegistry, root: Path, label: str):
    return registry.register(
        discover_git_worktree_sync(root),
        cleanup_receipt=_cleanup_receipt(label),
    )


def _submit(registry: WorkspaceRegistry, root: Path, label: str):
    import asyncio

    return asyncio.run(RepoAddService(registry).submit(root, _cleanup_receipt(label)))


def _commit_repository(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "dolphin-tests@example.invalid")
    _git(path, "config", "user.name", "Dolphin Tests")
    (path / "README.md").write_text(f"# {path.name}\n")
    _git(path, "add", "-f", "README.md")
    _git(path, "commit", "-qm", "Initial commit")
    return path


def _git(path: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(path), *arguments], check=True, capture_output=True, text=True)


def _cleanup_receipt(label: str) -> str:
    payload = hashlib.sha256(label.encode("utf-8")).digest()
    return "dolphin-cleanup-v1_" + base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _mcp_root(path: Path, *, worktree_root: Path | None = None) -> MCPRootSnapshot:
    return MCPRootSnapshot(
        path=path,
        worktree_root=worktree_root or path,
        probe_available=True,
    )
