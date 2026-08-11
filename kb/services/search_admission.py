"""All-or-nothing workspace coverage and reader-lease admission for search."""

from __future__ import annotations

import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import timedelta
from threading import Event, Thread
from typing import Protocol

from kb.generation import GenerationCoordinatorError, GenerationReadLease, PublishedSnapshot
from kb.lifecycle_limits import ENTITY_ID_MAX_LENGTH
from kb.search_admission import (
    AdmittedSearchWorkspace,
    SearchAdmissionInvalid,
    SearchAdmissionUnavailable,
    SearchCoverage,
    SearchIndexBuilding,
    SearchIndexBuildingDetail,
    SearchOperationFailed,
    SearchOperationFailureDetail,
    SearchScopeFuseDetail,
    SearchScopeFuseTripped,
    SearchWorkspaceMissing,
    SearchWorkspaceResolutionFailed,
)
from kb.services.workspace_registry import (
    OperationCountersSnapshot,
    OperationSnapshot,
    OperationState,
    WorkspaceRegistryError,
    WorkspaceSnapshot,
)
from kb.services.workspace_resolution import WorkspaceResolution, WorkspaceResolutionOutcome

_SEARCH_READ_LEASE_DURATION = timedelta(seconds=30)
_SEARCH_READ_LEASE_RENEW_INTERVAL_SECONDS = 5.0
_SEARCH_READ_LEASE_KEEPER_STOP_SECONDS = 5.0
_MAX_SEARCH_SCOPE_WORKSPACES = 32


class _WorkspaceCoverageRegistry(Protocol):
    def inspect_workspace(self, workspace_id: str) -> WorkspaceSnapshot | None: ...

    def inspect_latest_workspace_operation(self, workspace_id: str) -> OperationSnapshot | None: ...


class _SearchCoverageCoordinator(Protocol):
    def current_snapshot(self, workspace_id: str) -> PublishedSnapshot | None: ...

    def acquire_read(self, workspace_id: str, *, lease_duration: timedelta) -> GenerationReadLease: ...

    def snapshot_for_lease(self, lease_id: str) -> PublishedSnapshot: ...

    def renew_reads(
        self,
        leases: Sequence[GenerationReadLease],
        *,
        lease_duration: timedelta,
    ) -> None: ...

    def release_read(self, lease: GenerationReadLease) -> None: ...


class _CoverageLeaseKeeper:
    """Renew one admitted lease set as a unit until the search call exits."""

    def __init__(
        self,
        coordinator: _SearchCoverageCoordinator,
        coverage: SearchCoverage,
    ) -> None:
        self._coordinator = coordinator
        self._leases = tuple(item.read_lease for item in coverage.workspaces)
        self._stop = Event()
        self._failed = Event()
        self._thread = Thread(target=self._run, name="dolphin-search-lease-keeper", daemon=True)
        self._started = False

    def start(self) -> None:
        self._thread.start()
        self._started = True

    def stop(self) -> bool:
        if not self._started:
            return True
        self._stop.set()
        self._thread.join(timeout=_SEARCH_READ_LEASE_KEEPER_STOP_SECONDS)
        return not self._thread.is_alive()

    @property
    def failed(self) -> bool:
        return self._failed.is_set()

    def _run(self) -> None:
        while not self._stop.wait(_SEARCH_READ_LEASE_RENEW_INTERVAL_SECONDS):
            try:
                self._coordinator.renew_reads(
                    self._leases,
                    lease_duration=_SEARCH_READ_LEASE_DURATION,
                )
            except GenerationCoordinatorError:
                # A transient missed renewal is safe while the existing authority is
                # live. Later renewals may recover; final validation fails closed if not.
                continue
            except Exception:
                # Coordinator implementations must normalize backend failures. Record
                # any contract violation so this request fails clearly at its boundary.
                self._failed.set()
                return


class SearchCoverageService:
    """Pin complete coverage for every workspace before any query work begins."""

    def __init__(
        self,
        registry: _WorkspaceCoverageRegistry,
        coordinator: _SearchCoverageCoordinator,
    ) -> None:
        self._registry = registry
        self._coordinator = coordinator

    @contextmanager
    def admit(
        self,
        workspace_ids: Sequence[str] | None,
        *,
        current_resolution: WorkspaceResolution | None = None,
    ) -> Iterator[SearchCoverage]:
        """Yield exact reader leases, releasing every acquired lease on every outcome."""

        scope = self._resolve_scope(workspace_ids, current_resolution=current_resolution)
        workspaces = self._require_complete_preflight(scope)
        admitted: list[AdmittedSearchWorkspace] = []
        try:
            for workspace in workspaces:
                lease = self._coordinator.acquire_read(
                    workspace.workspace_id,
                    lease_duration=_SEARCH_READ_LEASE_DURATION,
                )
                admitted.append(AdmittedSearchWorkspace(workspace=workspace, read_lease=lease))
                if lease.snapshot.workspace_id != workspace.workspace_id:
                    raise SearchAdmissionUnavailable("Dolphin search reader lease has invalid workspace authority")
        except (WorkspaceRegistryError, GenerationCoordinatorError) as exc:
            self._release_after_failed_admission(admitted)
            raise SearchAdmissionUnavailable("Dolphin could not pin complete search coverage") from exc
        except Exception:
            self._release_after_failed_admission(admitted)
            raise

        coverage = SearchCoverage(workspaces=tuple(admitted))
        keeper = _CoverageLeaseKeeper(self._coordinator, coverage)
        try:
            keeper.start()
            yield coverage
        finally:
            primary_failure = sys.exception()
            completion_failure: SearchAdmissionUnavailable | None = None
            if not keeper.stop() and primary_failure is None:
                completion_failure = SearchAdmissionUnavailable("Dolphin search lease keeper did not stop safely")
            if keeper.failed and primary_failure is None:
                completion_failure = SearchAdmissionUnavailable("Dolphin search lease renewal failed unexpectedly")
            if primary_failure is None and completion_failure is None:
                try:
                    self.validate(coverage)
                except SearchAdmissionUnavailable as exc:
                    completion_failure = exc
            try:
                self._release_all(coverage)
            except SearchAdmissionUnavailable:
                if primary_failure is None and completion_failure is None:
                    raise
            if primary_failure is None and completion_failure is not None:
                raise completion_failure

    def validate(self, coverage: SearchCoverage) -> None:
        """Fail closed if any retained lease expired or changed before serialization."""

        try:
            for item in coverage.workspaces:
                if self._coordinator.snapshot_for_lease(item.read_lease.lease_id) != item.snapshot:
                    raise SearchAdmissionUnavailable("Dolphin search coverage changed during the admitted read")
        except SearchAdmissionUnavailable:
            raise
        except GenerationCoordinatorError as exc:
            raise SearchAdmissionUnavailable("Dolphin search coverage is no longer available") from exc

    def _resolve_scope(
        self,
        workspace_ids: Sequence[str] | None,
        *,
        current_resolution: WorkspaceResolution | None,
    ) -> tuple[str, ...]:
        if workspace_ids is None:
            if (
                current_resolution is None
                or current_resolution.outcome is not WorkspaceResolutionOutcome.RESOLVED
                or current_resolution.workspace is None
            ):
                raise SearchWorkspaceResolutionFailed(current_resolution)
            values = (current_resolution.workspace.workspace_id,)
        else:
            values = tuple(workspace_ids)
        if not 1 <= len(values) <= _MAX_SEARCH_SCOPE_WORKSPACES:
            raise SearchAdmissionInvalid("Dolphin search workspace scope is empty or too large")
        if any(
            not isinstance(workspace_id, str) or not 1 <= len(workspace_id) <= ENTITY_ID_MAX_LENGTH
            for workspace_id in values
        ):
            raise SearchAdmissionInvalid("Dolphin search workspace scope contains an invalid ID")
        if len(set(values)) != len(values):
            raise SearchAdmissionInvalid("Dolphin search workspace scope contains duplicate IDs")
        return tuple(sorted(values))

    def _require_complete_preflight(self, workspace_ids: tuple[str, ...]) -> tuple[WorkspaceSnapshot, ...]:
        workspaces: list[WorkspaceSnapshot] = []
        missing: list[str] = []
        incomplete: list[tuple[WorkspaceSnapshot, OperationSnapshot | None]] = []
        try:
            for workspace_id in workspace_ids:
                workspace = self._registry.inspect_workspace(workspace_id)
                if workspace is None:
                    missing.append(workspace_id)
                    continue
                workspaces.append(workspace)
                if self._coordinator.current_snapshot(workspace_id) is None:
                    incomplete.append((workspace, self._registry.inspect_latest_workspace_operation(workspace_id)))
        except (WorkspaceRegistryError, GenerationCoordinatorError) as exc:
            raise SearchAdmissionUnavailable("Dolphin could not inspect search coverage") from exc

        if missing:
            raise SearchWorkspaceMissing(tuple(missing))
        self._raise_incomplete(incomplete)
        return tuple(workspaces)

    @staticmethod
    def _raise_incomplete(incomplete: list[tuple[WorkspaceSnapshot, OperationSnapshot | None]]) -> None:
        approval = next(
            (
                (workspace, operation)
                for workspace, operation in incomplete
                if operation is not None and operation.state is OperationState.AWAITING_APPROVAL
            ),
            None,
        )
        if approval is not None:
            workspace, operation = approval
            raise SearchScopeFuseTripped(
                SearchScopeFuseDetail(
                    workspace_id=workspace.workspace_id,
                    operation_id=operation.operation_id,
                    last_progress_at=operation.updated_at.isoformat(),
                )
            )

        failures = tuple(
            SearchOperationFailureDetail(
                workspace_id=workspace.workspace_id,
                operation_id=operation.operation_id,
                operation_state=operation.state,
                last_progress_at=operation.updated_at.isoformat(),
            )
            for workspace, operation in incomplete
            if operation is not None
            and operation.state in {OperationState.FAILED, OperationState.CANCELLED, OperationState.SUCCEEDED}
        )
        if failures:
            raise SearchOperationFailed(failures)

        if any(operation is None for _workspace, operation in incomplete):
            raise SearchAdmissionUnavailable("Dolphin incomplete search coverage has no durable operation")

        details = tuple(
            SearchIndexBuildingDetail(
                workspace_id=workspace.workspace_id,
                operation_id=operation.operation_id,
                operation_state=operation.state,
                phase=operation.phase,
                pause_reason=operation.pause_reason,
                counters=operation.counters or OperationCountersSnapshot(),
                last_progress_at=operation.updated_at.isoformat(),
            )
            for workspace, operation in incomplete
            if operation is not None
            and operation.state in {OperationState.QUEUED, OperationState.RUNNING, OperationState.PAUSED}
        )
        if len(details) != len(incomplete):
            raise SearchAdmissionUnavailable("Dolphin incomplete search coverage state is invalid")
        if details:
            raise SearchIndexBuilding(details)

    def _release_after_failed_admission(self, admitted: list[AdmittedSearchWorkspace]) -> None:
        if not admitted:
            return
        try:
            self._release_all(SearchCoverage(workspaces=tuple(admitted)))
        except SearchAdmissionUnavailable:
            # Admission already has a primary failure. Cleanup is best-effort here so
            # a secondary release error cannot replace the actionable root cause.
            pass

    def _release_all(self, coverage: SearchCoverage) -> None:
        first_failure: GenerationCoordinatorError | None = None
        for item in reversed(coverage.workspaces):
            try:
                self._coordinator.release_read(item.read_lease)
            except GenerationCoordinatorError as exc:
                if first_failure is None:
                    first_failure = exc
        if first_failure is not None:
            raise SearchAdmissionUnavailable("Dolphin search reader leases could not be released") from first_failure
