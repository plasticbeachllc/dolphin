"""Transport-independent application services for Dolphin 0.3.0."""

from kb.services.mcp_application import default_mcp_handlers
from kb.services.repo_add import RepoAddService, RepoAddSubmission
from kb.services.status import StatusResult, StatusService
from kb.services.workspace_registry import (
    OperationState,
    WorkspaceOperation,
    WorkspaceRegistration,
    WorkspaceRegistry,
    WorkspaceRegistryError,
)
from kb.services.worktree import (
    GitWorktree,
    WorktreeDiscoveryError,
    discover_git_worktree,
    validate_git_worktree_snapshot,
)

__all__ = [
    "GitWorktree",
    "OperationState",
    "RepoAddService",
    "RepoAddSubmission",
    "StatusResult",
    "StatusService",
    "WorktreeDiscoveryError",
    "WorkspaceRegistration",
    "WorkspaceOperation",
    "WorkspaceRegistry",
    "WorkspaceRegistryError",
    "default_mcp_handlers",
    "discover_git_worktree",
    "validate_git_worktree_snapshot",
]
