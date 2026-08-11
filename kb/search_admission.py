"""Typed internal outcomes for all-or-nothing search coverage admission."""

from __future__ import annotations

from dataclasses import dataclass

from kb.generation import GenerationReadLease, PublishedSnapshot
from kb.services.workspace_registry import (
    OperationCountersSnapshot,
    OperationPauseReason,
    OperationPhase,
    OperationState,
    WorkspaceSnapshot,
)
from kb.services.workspace_resolution import WorkspaceResolution


class SearchAdmissionError(RuntimeError):
    """Search cannot safely begin against the requested workspace scope."""


class SearchAdmissionInvalid(SearchAdmissionError):
    """The requested internal workspace scope is malformed or unbounded."""


class SearchAdmissionUnavailable(SearchAdmissionError):
    """Coverage or read-lease state could not be proven safely."""


class SearchWorkspaceMissing(SearchAdmissionError):
    """One or more explicitly requested workspaces are unavailable."""

    def __init__(self, workspace_ids: tuple[str, ...]) -> None:
        super().__init__("Dolphin search workspace scope is unavailable")
        self.workspace_ids = workspace_ids


class SearchWorkspaceResolutionFailed(SearchAdmissionError):
    """A null workspace scope could not resolve to one current workspace."""

    def __init__(self, resolution: WorkspaceResolution | None) -> None:
        super().__init__("Dolphin could not resolve one current workspace for search")
        self.resolution = resolution


@dataclass(frozen=True, slots=True)
class SearchIndexBuildingDetail:
    """Bounded source-free progress for one workspace without a publication."""

    workspace_id: str
    operation_id: str
    operation_state: OperationState
    phase: OperationPhase | None
    pause_reason: OperationPauseReason | None
    counters: OperationCountersSnapshot
    last_progress_at: str


class SearchIndexBuilding(SearchAdmissionError):
    """Every requested workspace exists, but at least one lacks complete coverage."""

    def __init__(self, details: tuple[SearchIndexBuildingDetail, ...]) -> None:
        super().__init__("Dolphin is still building complete search coverage")
        self.details = details


@dataclass(frozen=True, slots=True)
class SearchScopeFuseDetail:
    """Minimal internal approval blocker pending the full public fuse authority."""

    workspace_id: str
    operation_id: str
    last_progress_at: str


class SearchScopeFuseTripped(SearchAdmissionError):
    """Exceptional indexing approval blocks this complete requested scope."""

    def __init__(self, detail: SearchScopeFuseDetail) -> None:
        super().__init__("Dolphin search coverage awaits exceptional human approval")
        self.detail = detail


@dataclass(frozen=True, slots=True)
class SearchOperationFailureDetail:
    workspace_id: str
    operation_id: str
    operation_state: OperationState
    last_progress_at: str


class SearchOperationFailed(SearchAdmissionError):
    """A terminal operation left a workspace without a complete publication."""

    def __init__(self, details: tuple[SearchOperationFailureDetail, ...]) -> None:
        super().__init__("Dolphin indexing did not produce complete search coverage")
        self.details = details


@dataclass(frozen=True, slots=True)
class AdmittedSearchWorkspace:
    workspace: WorkspaceSnapshot
    read_lease: GenerationReadLease

    @property
    def snapshot(self) -> PublishedSnapshot:
        return self.read_lease.snapshot


@dataclass(frozen=True, slots=True)
class SearchCoverage:
    """Exact publications pinned for one all-or-nothing search call."""

    workspaces: tuple[AdmittedSearchWorkspace, ...]

    @property
    def workspace_ids(self) -> tuple[str, ...]:
        return tuple(item.workspace.workspace_id for item in self.workspaces)

    @property
    def snapshots(self) -> tuple[PublishedSnapshot, ...]:
        return tuple(item.snapshot for item in self.workspaces)
