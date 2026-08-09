"""Async application service for explicit repository enrollment and index submission."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from kb.services.repository_boundaries import ParentScanPlan, plan_parent_scan
from kb.services.workspace_registry import WorkspaceOperation, WorkspaceRegistration, WorkspaceRegistry
from kb.services.workspace_resolution import WorkspaceSessionScope
from kb.services.worktree import GitWorktree, discover_git_worktree


@dataclass(frozen=True, slots=True)
class RepoAddSubmission:
    """The internal, transport-neutral result of one `repo_add` lifecycle request."""

    worktree: GitWorktree
    parent_scan: ParentScanPlan
    registration: WorkspaceRegistration
    operation: WorkspaceOperation


class RepoAddService:
    """Coordinate discovery, registration, and exactly-once initial-index submission."""

    def __init__(
        self,
        registry: WorkspaceRegistry,
        *,
        session_scope: WorkspaceSessionScope | None = None,
    ) -> None:
        self._registry = registry
        self._session_scope = session_scope

    async def submit(self, path: Path, cleanup_receipt: str) -> RepoAddSubmission:
        """Register an explicit worktree and durably submit or reuse its initial index operation."""
        worktree = await discover_git_worktree(path)
        parent_scan = await asyncio.to_thread(plan_parent_scan, worktree)
        registration, operation = await asyncio.to_thread(
            self._registry.register_and_submit_initial_index,
            worktree,
            cleanup_receipt=cleanup_receipt,
            parent_scan=parent_scan,
        )
        if self._session_scope is not None:
            self._session_scope.select(registration.workspace_id)
        return RepoAddSubmission(
            worktree=worktree,
            parent_scan=parent_scan,
            registration=registration,
            operation=operation,
        )
