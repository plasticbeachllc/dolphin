"""Transport-independent application services for Dolphin 0.3.0."""

from kb.services.mcp_application import default_mcp_handlers
from kb.services.operation_runtime import (
    OperationRuntime,
    OperationRuntimeError,
    ProcessStartProbe,
    probe_process_start_identity,
)
from kb.services.repo_add import RepoAddService, RepoAddSubmission
from kb.services.repository_boundaries import (
    ParentScanPlan,
    RepositoryBoundary,
    RepositoryBoundaryError,
    RepositoryBoundaryKind,
    RepositoryBoundaryState,
    plan_parent_scan,
)
from kb.services.status import StatusResult, StatusService
from kb.services.workspace_registry import (
    OperationCheckpoint,
    OperationCountersSnapshot,
    OperationLease,
    OperationState,
    RuntimeOwner,
    RuntimeStatusSnapshot,
    WorkspaceOperation,
    WorkspaceRegistration,
    WorkspaceRegistry,
    WorkspaceRegistryError,
)
from kb.services.workspace_resolution import (
    MCPRootSnapshot,
    WorkspaceResolution,
    WorkspaceResolutionOutcome,
    WorkspaceResolutionSource,
    WorkspaceResolver,
    WorkspaceSessionScope,
)
from kb.services.worktree import (
    GitWorktree,
    WorktreeDiscoveryError,
    discover_git_worktree,
    validate_git_worktree_snapshot,
)

__all__ = [
    "GitWorktree",
    "MCPRootSnapshot",
    "OperationCheckpoint",
    "OperationCountersSnapshot",
    "OperationLease",
    "OperationRuntime",
    "OperationRuntimeError",
    "OperationState",
    "ParentScanPlan",
    "RepoAddService",
    "RepoAddSubmission",
    "RepositoryBoundary",
    "RepositoryBoundaryError",
    "RepositoryBoundaryKind",
    "RepositoryBoundaryState",
    "ProcessStartProbe",
    "RuntimeOwner",
    "RuntimeStatusSnapshot",
    "StatusResult",
    "StatusService",
    "WorktreeDiscoveryError",
    "WorkspaceRegistration",
    "WorkspaceResolution",
    "WorkspaceResolutionOutcome",
    "WorkspaceResolutionSource",
    "WorkspaceResolver",
    "WorkspaceOperation",
    "WorkspaceRegistry",
    "WorkspaceRegistryError",
    "WorkspaceSessionScope",
    "default_mcp_handlers",
    "discover_git_worktree",
    "plan_parent_scan",
    "probe_process_start_identity",
    "validate_git_worktree_snapshot",
]
