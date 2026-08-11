"""All-or-nothing workspace coverage and reader-lease admission for search."""

from __future__ import annotations

import asyncio
import queue
import sys
from collections.abc import Callable, Coroutine, Iterator, Sequence
from concurrent.futures import Future as ConcurrentFuture
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from threading import BoundedSemaphore, Event, Lock, Thread
from time import monotonic
from typing import Protocol, TypeVar

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
_SEARCH_READ_LEASE_RENEW_TIMEOUT_SECONDS = 2.0
_SEARCH_READ_LEASE_KEEPER_STOP_SECONDS = 5.0
_SEARCH_CALL_DEADLINE_SECONDS = 30.0
_SEARCH_CALL_DRAIN_SECONDS = 12.0
_SEARCH_ADMISSION_CAPACITY = BoundedSemaphore(8)
_MAX_SEARCH_SCOPE_WORKSPACES = 32
_LEASE_RELEASE_ATTEMPTS = 3
_MAX_CONCURRENT_RENEWAL_CALLS = 8
_ResultT = TypeVar("_ResultT")


class _CoordinatorDeadlineRunner:
    """Bound coordinator workers while retaining one isolated recovery lane."""

    def __init__(self, *, capacity: int = _MAX_CONCURRENT_RENEWAL_CALLS) -> None:
        self._slots = BoundedSemaphore(capacity)
        self._recovery_slot = BoundedSemaphore(1)

    def call(self, operation: Callable[[], None], *, timeout: float) -> None:
        started_at = monotonic()
        slot = self._slots if self._slots.acquire(blocking=False) else self._recovery_slot
        if slot is self._recovery_slot and not slot.acquire(timeout=timeout):
            raise TimeoutError("Dolphin search renewal workers are occupied")
        completed: queue.Queue[BaseException | None] = queue.Queue(maxsize=1)

        def run() -> None:
            try:
                try:
                    operation()
                except BaseException as exc:
                    completed.put(exc)
                else:
                    completed.put(None)
            finally:
                slot.release()

        try:
            Thread(target=run, name="dolphin-search-renewal", daemon=True).start()
        except RuntimeError:
            slot.release()
            raise

        remaining = timeout - (monotonic() - started_at)
        if remaining <= 0:
            raise TimeoutError("Dolphin search reader lease renewal exceeded its deadline")
        try:
            failure = completed.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError("Dolphin search reader lease renewal exceeded its deadline") from exc
        if failure is not None:
            raise failure


_COORDINATOR_DEADLINES = _CoordinatorDeadlineRunner()


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
        admitted: Sequence[AdmittedSearchWorkspace],
        admission_capacity: BoundedSemaphore,
    ) -> None:
        self._coordinator = coordinator
        self._admission_capacity = admission_capacity
        self._leases = tuple(item.read_lease for item in admitted)
        self._stop = Event()
        self._done = Event()
        self._failed = Event()
        self._deadline_exceeded = Event()
        self._cleanup_failed = Event()
        self._deadline = monotonic() + _SEARCH_CALL_DEADLINE_SECONDS
        self._thread = Thread(target=self._run, name="dolphin-search-lease-keeper", daemon=True)
        self._started = False

    def start(self) -> None:
        self._thread.start()
        self._started = True

    def close(self) -> bool:
        if not self._started:
            return True
        self.deadline_exceeded()
        self._stop.set()
        return self._done.wait(timeout=_SEARCH_READ_LEASE_KEEPER_STOP_SECONDS)

    @property
    def failed(self) -> bool:
        return self._failed.is_set()

    def deadline_exceeded(self) -> bool:
        if monotonic() >= self._deadline:
            self._deadline_exceeded.set()
        return self._deadline_exceeded.is_set()

    def authority_unavailable(self) -> bool:
        return self.failed or self.deadline_exceeded()

    @property
    def cleanup_failed(self) -> bool:
        return self._cleanup_failed.is_set()

    def _run(self) -> None:
        try:
            while True:
                remaining = self._deadline - monotonic()
                if remaining <= 0:
                    self._deadline_exceeded.set()
                    self._stop.wait(_SEARCH_CALL_DRAIN_SECONDS)
                    return
                if self._stop.wait(min(_SEARCH_READ_LEASE_RENEW_INTERVAL_SECONDS, remaining)):
                    return
                try:
                    _COORDINATOR_DEADLINES.call(
                        lambda: self._coordinator.renew_reads(
                            self._leases,
                            lease_duration=_SEARCH_READ_LEASE_DURATION,
                        ),
                        timeout=_SEARCH_READ_LEASE_RENEW_TIMEOUT_SECONDS,
                    )
                except TimeoutError:
                    self._failed.set()
                    self._stop.wait(_SEARCH_CALL_DRAIN_SECONDS)
                    return
                except GenerationCoordinatorError:
                    # A transient missed renewal is safe while the existing authority is
                    # live. Later renewals may recover; final validation fails closed if not.
                    continue
                except Exception:
                    # Coordinator implementations must normalize backend failures. Record
                    # any contract violation so this request fails clearly at its boundary.
                    self._failed.set()
                    self._stop.wait(_SEARCH_CALL_DRAIN_SECONDS)
                    return
        finally:
            self._admission_capacity.release()
            try:
                self._release_leases()
            finally:
                self._done.set()

    def _release_leases(self) -> None:
        for _attempt in range(_LEASE_RELEASE_ATTEMPTS):
            failed = False
            for lease in reversed(self._leases):
                try:
                    self._coordinator.release_read(lease)
                except Exception:
                    failed = True
            if not failed:
                return
        self._cleanup_failed.set()


class SearchCoverageService:
    """Pin complete coverage for every workspace before any query work begins."""

    def __init__(
        self,
        registry: _WorkspaceCoverageRegistry,
        coordinator: _SearchCoverageCoordinator,
    ) -> None:
        self._registry = registry
        self._coordinator = coordinator

    def execute(
        self,
        workspace_ids: Sequence[str] | None,
        operation: Callable[[SearchCoverage], _ResultT],
        *,
        current_resolution: WorkspaceResolution | None = None,
    ) -> _ResultT:
        """Return a materialized result only after its exact coverage validates."""

        with self._admit(workspace_ids, current_resolution=current_resolution) as coverage:
            return operation(coverage)

    async def execute_async(
        self,
        workspace_ids: Sequence[str] | None,
        operation: Callable[[SearchCoverage], Coroutine[object, object, _ResultT]],
        *,
        current_resolution: WorkspaceResolution | None = None,
    ) -> _ResultT:
        """Run one async operation while blocking admission work stays off the event loop."""

        loop = asyncio.get_running_loop()
        cancellation_requested = Event()
        future_guard = Lock()
        operation_future: list[ConcurrentFuture[_ResultT]] = []

        def invoke(coverage: SearchCoverage) -> _ResultT:
            future = asyncio.run_coroutine_threadsafe(operation(coverage), loop)
            with future_guard:
                operation_future.append(future)
                if cancellation_requested.is_set():
                    future.cancel()
            return future.result()

        def execute_sync() -> _ResultT:
            with self._admit(workspace_ids, current_resolution=current_resolution) as coverage:
                return invoke(coverage)

        worker = asyncio.create_task(
            asyncio.to_thread(execute_sync),
            name="dolphin-search-coverage",
        )
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancellation_requested.set()
            with future_guard:
                if operation_future:
                    operation_future[0].cancel()
            try:
                await asyncio.shield(worker)
            except BaseException:
                pass
            raise

    @contextmanager
    def _admit(
        self,
        workspace_ids: Sequence[str] | None,
        *,
        current_resolution: WorkspaceResolution | None = None,
    ) -> Iterator[SearchCoverage]:
        """Yield exact reader leases, releasing every acquired lease on every outcome."""

        scope = self._resolve_scope(workspace_ids, current_resolution=current_resolution)
        admission_capacity = _SEARCH_ADMISSION_CAPACITY
        if not admission_capacity.acquire(blocking=False):
            raise SearchAdmissionUnavailable("Dolphin search admission is at bounded capacity")
        admitted: list[AdmittedSearchWorkspace] = []
        try:
            workspaces = self._require_complete_preflight(scope)
            for workspace in workspaces:
                lease = self._coordinator.acquire_read(
                    workspace.workspace_id,
                    lease_duration=_SEARCH_READ_LEASE_DURATION,
                )
                admitted.append(AdmittedSearchWorkspace(workspace=workspace, read_lease=lease))
                if lease.snapshot.workspace_id != workspace.workspace_id:
                    raise SearchAdmissionUnavailable("Dolphin search reader lease has invalid workspace authority")
        except (WorkspaceRegistryError, GenerationCoordinatorError) as exc:
            try:
                self._release_after_failed_admission(admitted)
            finally:
                admission_capacity.release()
            raise SearchAdmissionUnavailable("Dolphin could not pin complete search coverage") from exc
        except Exception:
            try:
                self._release_after_failed_admission(admitted)
            finally:
                admission_capacity.release()
            raise

        keeper = _CoverageLeaseKeeper(self._coordinator, admitted, admission_capacity)
        coverage = SearchCoverage(
            workspaces=tuple(replace(item, deadline_exceeded=keeper.authority_unavailable) for item in admitted)
        )
        try:
            keeper.start()
        except Exception:
            try:
                self._release_after_failed_admission(admitted)
            finally:
                admission_capacity.release()
            raise

        try:
            yield coverage
        finally:
            primary_failure = sys.exception()
            completion_failure: SearchAdmissionUnavailable | None = None
            if keeper.deadline_exceeded() and primary_failure is None:
                completion_failure = SearchAdmissionUnavailable("Dolphin search exceeded its bounded read deadline")
            elif keeper.failed and primary_failure is None:
                completion_failure = SearchAdmissionUnavailable("Dolphin search lease renewal failed unexpectedly")
            if primary_failure is None and completion_failure is None:
                try:
                    self.validate(coverage)
                except SearchAdmissionUnavailable as exc:
                    completion_failure = exc
            if not keeper.close() and primary_failure is None:
                completion_failure = SearchAdmissionUnavailable(
                    "Dolphin search lease cleanup is still completing safely"
                )
            elif keeper.deadline_exceeded() and primary_failure is None:
                completion_failure = SearchAdmissionUnavailable("Dolphin search exceeded its bounded read deadline")
            elif keeper.failed and primary_failure is None:
                completion_failure = SearchAdmissionUnavailable("Dolphin search lease renewal failed unexpectedly")
            elif keeper.cleanup_failed and primary_failure is None:
                completion_failure = SearchAdmissionUnavailable("Dolphin search reader leases could not be released")
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
        except Exception as exc:
            raise SearchAdmissionUnavailable("Dolphin search coverage validation failed unexpectedly") from exc

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
            if isinstance(workspace_ids, (str, bytes)) or not isinstance(workspace_ids, Sequence):
                raise SearchAdmissionInvalid("Dolphin search workspace scope must be a bounded sequence of IDs")
            if not 1 <= len(workspace_ids) <= _MAX_SEARCH_SCOPE_WORKSPACES:
                raise SearchAdmissionInvalid("Dolphin search workspace scope is empty or too large")
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
        first_failure: Exception | None = None
        for item in reversed(coverage.workspaces):
            try:
                self._coordinator.release_read(item.read_lease)
            except Exception as exc:
                if first_failure is None:
                    first_failure = exc
        if first_failure is not None:
            raise SearchAdmissionUnavailable("Dolphin search reader leases could not be released") from first_failure
