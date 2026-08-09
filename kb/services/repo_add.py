"""Async application service for explicit repository enrollment and index submission."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from kb.services.workspace_registry import WorkspaceOperation, WorkspaceRegistration, WorkspaceRegistry
from kb.services.worktree import GitWorktree, discover_git_worktree


@dataclass(frozen=True, slots=True)
class RepoAddSubmission:
    """The internal, transport-neutral result of one `repo_add` lifecycle request."""

    worktree: GitWorktree
    registration: WorkspaceRegistration
    operation: WorkspaceOperation


class RepoAddService:
    """Coordinate discovery, registration, and exactly-once initial-index submission."""

    def __init__(self, registry: WorkspaceRegistry) -> None:
        self._registry = registry

    async def submit(self, path: Path) -> RepoAddSubmission:
        """Register an explicit worktree and durably submit or reuse its initial index operation."""
        worktree = await discover_git_worktree(path)
        registration = await asyncio.to_thread(self._registry.register, worktree)
        operation = await asyncio.to_thread(self._registry.submit_initial_index, registration)
        return RepoAddSubmission(worktree=worktree, registration=registration, operation=operation)
