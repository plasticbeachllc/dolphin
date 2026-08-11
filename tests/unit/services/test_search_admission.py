"""Tests for all-or-nothing search coverage admission."""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore, Event
from typing import cast

import pytest

from kb.generation import (
    GenerationCoordinatorError,
    GenerationReadLease,
    GenerationReadLeaseUnavailable,
    PublishedSnapshot,
)
from kb.search_admission import (
    SearchAdmissionInvalid,
    SearchAdmissionUnavailable,
    SearchIndexBuilding,
    SearchOperationFailed,
    SearchScopeFuseTripped,
    SearchWorkspaceMissing,
    SearchWorkspaceResolutionFailed,
)
from kb.services import search_admission as search_admission_module
from kb.services.search_admission import SearchCoverageService
from kb.services.workspace_registry import (
    OperationCountersSnapshot,
    OperationPauseReason,
    OperationSnapshot,
    OperationState,
    WorkspaceEffectiveState,
    WorkspaceSnapshot,
)
from kb.services.workspace_resolution import WorkspaceResolution, WorkspaceResolutionOutcome

_NOW = datetime(2026, 8, 10, tzinfo=UTC)


def test_published_workspace_is_admitted_while_newer_indexing_continues() -> None:
    workspace = _workspace("ws_ready", state="indexing")
    coordinator = _Coordinator({workspace.workspace_id: _published(workspace.workspace_id)})
    registry = _Registry(
        {workspace.workspace_id: workspace},
        {workspace.workspace_id: _operation(workspace.workspace_id, OperationState.RUNNING)},
    )
    service = SearchCoverageService(registry, coordinator)

    with service.admit([workspace.workspace_id]) as coverage:
        assert coverage.workspace_ids == (workspace.workspace_id,)
        assert coverage.snapshots == (_published(workspace.workspace_id),)
        service.validate(coverage)
        assert coordinator.released == []

    assert registry.operation_calls == []
    assert coordinator.acquired == [workspace.workspace_id]
    assert coordinator.validated == ["read_ws_ready", "read_ws_ready"]
    assert coordinator.released == ["read_ws_ready"]


def test_incomplete_multi_workspace_scope_returns_every_blocker_before_acquiring_reads() -> None:
    ready = _workspace("ws_ready", state="ready")
    queued = _workspace("ws_queued", state="indexing")
    paused = _workspace("ws_paused", state="indexing")
    coordinator = _Coordinator(
        {
            ready.workspace_id: _published(ready.workspace_id),
            queued.workspace_id: None,
            paused.workspace_id: None,
        }
    )
    registry = _Registry(
        {item.workspace_id: item for item in (ready, queued, paused)},
        {
            queued.workspace_id: _operation(queued.workspace_id, OperationState.QUEUED),
            paused.workspace_id: _operation(paused.workspace_id, OperationState.PAUSED, pause_reason="disk_pressure"),
        },
    )

    with pytest.raises(SearchIndexBuilding) as failure:
        with SearchCoverageService(registry, coordinator).admit(
            [ready.workspace_id, queued.workspace_id, paused.workspace_id]
        ):
            raise AssertionError("incomplete coverage must not enter the search body")

    assert [detail.workspace_id for detail in failure.value.details] == ["ws_paused", "ws_queued"]
    assert failure.value.details[0].pause_reason == "disk_pressure"
    assert coordinator.acquired == []


def test_scope_fuse_takes_precedence_over_ordinary_index_building() -> None:
    approval = _workspace("ws_approval", state="indexing")
    queued = _workspace("ws_queued", state="indexing")
    registry = _Registry(
        {item.workspace_id: item for item in (approval, queued)},
        {
            approval.workspace_id: _operation(approval.workspace_id, OperationState.AWAITING_APPROVAL),
            queued.workspace_id: _operation(queued.workspace_id, OperationState.QUEUED),
        },
    )
    coordinator = _Coordinator({approval.workspace_id: None, queued.workspace_id: None})

    with pytest.raises(SearchScopeFuseTripped) as failure:
        with SearchCoverageService(registry, coordinator).admit([queued.workspace_id, approval.workspace_id]):
            raise AssertionError("approval-blocked coverage must not enter the search body")

    assert failure.value.detail.workspace_id == approval.workspace_id
    assert coordinator.acquired == []


@pytest.mark.parametrize("state", [OperationState.FAILED, OperationState.CANCELLED, OperationState.SUCCEEDED])
def test_terminal_operation_without_a_publication_fails_closed(state: OperationState) -> None:
    workspace = _workspace("ws_terminal", state="failed")
    registry = _Registry(
        {workspace.workspace_id: workspace},
        {workspace.workspace_id: _operation(workspace.workspace_id, state)},
    )
    coordinator = _Coordinator({workspace.workspace_id: None})

    with pytest.raises(SearchOperationFailed) as failure:
        with SearchCoverageService(registry, coordinator).admit([workspace.workspace_id]):
            raise AssertionError("terminal incomplete coverage must not be admitted")

    assert failure.value.details[0].operation_state is state
    assert coordinator.acquired == []


def test_missing_duplicate_empty_and_unresolved_scopes_fail_before_lease_work() -> None:
    coordinator = _Coordinator({})
    service = SearchCoverageService(_Registry({}, {}), coordinator)

    with pytest.raises(SearchWorkspaceMissing) as missing:
        with service.admit(["ws_missing"]):
            raise AssertionError
    assert missing.value.workspace_ids == ("ws_missing",)

    for invalid in ([], ["ws_same", "ws_same"], [f"ws_{index}" for index in range(33)]):
        with pytest.raises(SearchAdmissionInvalid):
            with service.admit(invalid):
                raise AssertionError

    for invalid_container in ("ws_ready", cast(Sequence[str], iter(["ws_ready"]))):
        with pytest.raises(SearchAdmissionInvalid, match="bounded sequence"):
            with service.admit(invalid_container):
                raise AssertionError

    with pytest.raises(SearchWorkspaceResolutionFailed):
        with service.admit(None, current_resolution=WorkspaceResolution(outcome=WorkspaceResolutionOutcome.REQUIRED)):
            raise AssertionError
    assert coordinator.acquired == []


def test_null_scope_uses_one_already_resolved_current_workspace() -> None:
    workspace = _workspace("ws_current", state="ready")
    registry = _Registry({workspace.workspace_id: workspace}, {})
    coordinator = _Coordinator({workspace.workspace_id: _published(workspace.workspace_id)})
    resolution = WorkspaceResolution(outcome=WorkspaceResolutionOutcome.RESOLVED, workspace=workspace)

    with SearchCoverageService(registry, coordinator).admit(None, current_resolution=resolution) as coverage:
        assert coverage.workspace_ids == (workspace.workspace_id,)

    assert coordinator.released == ["read_ws_current"]


def test_partial_acquisition_failure_releases_every_prior_lease() -> None:
    first = _workspace("ws_first", state="ready")
    second = _workspace("ws_second", state="ready")
    registry = _Registry({item.workspace_id: item for item in (first, second)}, {})
    coordinator = _Coordinator(
        {
            first.workspace_id: _published(first.workspace_id),
            second.workspace_id: _published(second.workspace_id),
        },
        acquire_error_for=second.workspace_id,
    )

    with pytest.raises(SearchAdmissionUnavailable, match="pin complete"):
        with SearchCoverageService(registry, coordinator).admit([second.workspace_id, first.workspace_id]):
            raise AssertionError

    assert coordinator.acquired == [first.workspace_id, second.workspace_id]
    assert coordinator.released == ["read_ws_first"]


def test_invalid_lease_authority_is_released_before_admission_fails() -> None:
    workspace = _workspace("ws_expected", state="ready")
    registry = _Registry({workspace.workspace_id: workspace}, {})
    coordinator = _Coordinator(
        {workspace.workspace_id: _published(workspace.workspace_id)},
        acquired_snapshot_override=_published("ws_other"),
    )

    with pytest.raises(SearchAdmissionUnavailable, match="invalid workspace authority"):
        with SearchCoverageService(registry, coordinator).admit([workspace.workspace_id]):
            raise AssertionError

    assert coordinator.released == ["read_ws_expected"]


def test_release_failure_does_not_mask_partial_acquisition_failure() -> None:
    first = _workspace("ws_first", state="ready")
    second = _workspace("ws_second", state="ready")
    registry = _Registry({item.workspace_id: item for item in (first, second)}, {})
    coordinator = _Coordinator(
        {
            first.workspace_id: _published(first.workspace_id),
            second.workspace_id: _published(second.workspace_id),
        },
        acquire_error_for=second.workspace_id,
        release_error=True,
    )

    with pytest.raises(SearchAdmissionUnavailable, match="pin complete"):
        with SearchCoverageService(registry, coordinator).admit([first.workspace_id, second.workspace_id]):
            raise AssertionError

    assert coordinator.released == ["read_ws_first"]


def test_unexpected_release_failure_releases_remaining_leases_and_admission_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_admission_module, "_SEARCH_ADMISSION_CAPACITY", BoundedSemaphore(1))
    first = _workspace("ws_first", state="ready")
    second = _workspace("ws_second", state="ready")
    third = _workspace("ws_third", state="ready")
    workspaces = {item.workspace_id: item for item in (first, second, third)}
    snapshots = {workspace_id: _published(workspace_id) for workspace_id in workspaces}
    failing_coordinator = _Coordinator(
        snapshots,
        acquire_error_for=third.workspace_id,
        raw_release_error_for="read_ws_second",
    )

    with pytest.raises(SearchAdmissionUnavailable, match="pin complete"):
        with SearchCoverageService(_Registry(workspaces, {}), failing_coordinator).admit(tuple(workspaces)):
            raise AssertionError

    assert failing_coordinator.released == ["read_ws_second", "read_ws_first"]

    recovery_coordinator = _Coordinator({first.workspace_id: _published(first.workspace_id)})
    with SearchCoverageService(
        _Registry({first.workspace_id: first}, {}),
        recovery_coordinator,
    ).admit([first.workspace_id]):
        pass


def test_validation_fails_closed_when_any_retained_snapshot_changes() -> None:
    workspace = _workspace("ws_ready", state="ready")
    registry = _Registry({workspace.workspace_id: workspace}, {})
    coordinator = _Coordinator({workspace.workspace_id: _published(workspace.workspace_id)})
    service = SearchCoverageService(registry, coordinator)

    with service.admit([workspace.workspace_id]) as coverage:
        coordinator.validation_override = _published(workspace.workspace_id, revision=2)
        with pytest.raises(SearchAdmissionUnavailable, match="changed"):
            service.validate(coverage)
        coordinator.validation_override = None

    assert coordinator.released == ["read_ws_ready"]


def test_unexpected_final_validation_error_still_closes_the_keeper() -> None:
    workspace = _workspace("ws_ready", state="ready")
    coordinator = _Coordinator(
        {workspace.workspace_id: _published(workspace.workspace_id)},
        validation_error=ValueError("raw backend exception"),
    )

    with pytest.raises(SearchAdmissionUnavailable, match="validation failed unexpectedly"):
        with SearchCoverageService(_Registry({workspace.workspace_id: workspace}, {}), coordinator).admit(
            [workspace.workspace_id]
        ):
            pass

    assert coordinator.released == ["read_ws_ready"]


def test_slow_multi_workspace_work_renews_the_complete_lease_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_admission_module, "_SEARCH_READ_LEASE_RENEW_INTERVAL_SECONDS", 0.01)
    first = _workspace("ws_first", state="ready")
    second = _workspace("ws_second", state="ready")
    registry = _Registry({item.workspace_id: item for item in (first, second)}, {})
    coordinator = _Coordinator(
        {
            first.workspace_id: _published(first.workspace_id),
            second.workspace_id: _published(second.workspace_id),
        }
    )

    with SearchCoverageService(registry, coordinator).admit([first.workspace_id, second.workspace_id]):
        time.sleep(0.035)

    assert coordinator.renewed
    assert all(renewed == ("read_ws_first", "read_ws_second") for renewed in coordinator.renewed)
    assert coordinator.released == ["read_ws_second", "read_ws_first"]


def test_unexpected_lease_keeper_failure_fails_the_request_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_admission_module, "_SEARCH_READ_LEASE_RENEW_INTERVAL_SECONDS", 0.01)
    workspace = _workspace("ws_ready", state="ready")
    coordinator = _Coordinator(
        {workspace.workspace_id: _published(workspace.workspace_id)},
        renew_error=ValueError("unexpected backend exception"),
    )

    with pytest.raises(SearchAdmissionUnavailable, match="renewal failed unexpectedly"):
        with SearchCoverageService(_Registry({workspace.workspace_id: workspace}, {}), coordinator).admit(
            [workspace.workspace_id]
        ):
            time.sleep(0.025)

    assert coordinator.released == ["read_ws_ready"]


def test_search_admission_has_a_bounded_global_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_admission_module, "_SEARCH_ADMISSION_CAPACITY", BoundedSemaphore(1))
    first = _workspace("ws_first", state="ready")
    second = _workspace("ws_second", state="ready")
    first_service = SearchCoverageService(
        _Registry({first.workspace_id: first}, {}),
        _Coordinator({first.workspace_id: _published(first.workspace_id)}),
    )
    second_service = SearchCoverageService(
        _Registry({second.workspace_id: second}, {}),
        _Coordinator({second.workspace_id: _published(second.workspace_id)}),
    )

    with first_service.admit([first.workspace_id]):
        with pytest.raises(SearchAdmissionUnavailable, match="bounded capacity"):
            with second_service.admit([second.workspace_id]):
                raise AssertionError

    with second_service.admit([second.workspace_id]):
        pass


def test_keeper_deadline_stops_renewal_and_releases_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_admission_module, "_SEARCH_CALL_DEADLINE_SECONDS", 0.03)
    monkeypatch.setattr(search_admission_module, "_SEARCH_READ_LEASE_RENEW_INTERVAL_SECONDS", 0.01)
    workspace = _workspace("ws_ready", state="ready")
    coordinator = _Coordinator({workspace.workspace_id: _published(workspace.workspace_id)})

    with pytest.raises(SearchAdmissionUnavailable, match="bounded read deadline"):
        with SearchCoverageService(_Registry({workspace.workspace_id: workspace}, {}), coordinator).admit(
            [workspace.workspace_id]
        ):
            time.sleep(0.05)

    assert coordinator.released == ["read_ws_ready"]


def test_close_immediately_after_fixed_deadline_cannot_bypass_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    current = [10.0]
    monkeypatch.setattr(search_admission_module, "monotonic", lambda: current[0])
    monkeypatch.setattr(search_admission_module, "_SEARCH_CALL_DEADLINE_SECONDS", 30.0)
    workspace = _workspace("ws_ready", state="ready")
    coordinator = _Coordinator({workspace.workspace_id: _published(workspace.workspace_id)})

    with pytest.raises(SearchAdmissionUnavailable, match="bounded read deadline"):
        with SearchCoverageService(_Registry({workspace.workspace_id: workspace}, {}), coordinator).admit(
            [workspace.workspace_id]
        ):
            current[0] = 40.0

    assert coordinator.released == ["read_ws_ready"]


def test_keeper_owns_delayed_cleanup_after_close_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_admission_module, "_SEARCH_READ_LEASE_RENEW_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(search_admission_module, "_SEARCH_READ_LEASE_KEEPER_STOP_SECONDS", 0.01)
    renew_started = Event()
    allow_renewal = Event()
    workspace = _workspace("ws_ready", state="ready")
    coordinator = _Coordinator(
        {workspace.workspace_id: _published(workspace.workspace_id)},
        renew_blocker=(renew_started, allow_renewal),
    )

    try:
        with pytest.raises(SearchAdmissionUnavailable, match="cleanup is still completing safely"):
            with SearchCoverageService(_Registry({workspace.workspace_id: workspace}, {}), coordinator).admit(
                [workspace.workspace_id]
            ):
                assert renew_started.wait(timeout=1)
        assert coordinator.released == []
    finally:
        allow_renewal.set()

    assert coordinator.release_completed.wait(timeout=1)
    assert coordinator.released == ["read_ws_ready"]


def test_keeper_retries_transient_release_failure() -> None:
    workspace = _workspace("ws_ready", state="ready")
    coordinator = _Coordinator(
        {workspace.workspace_id: _published(workspace.workspace_id)},
        release_failures=1,
    )

    with SearchCoverageService(_Registry({workspace.workspace_id: workspace}, {}), coordinator).admit(
        [workspace.workspace_id]
    ):
        pass

    assert coordinator.released == ["read_ws_ready", "read_ws_ready"]


class _Registry:
    def __init__(
        self,
        workspaces: dict[str, WorkspaceSnapshot],
        operations: dict[str, OperationSnapshot],
    ) -> None:
        self.workspaces = workspaces
        self.operations = operations
        self.operation_calls: list[str] = []

    def inspect_workspace(self, workspace_id: str) -> WorkspaceSnapshot | None:
        return self.workspaces.get(workspace_id)

    def inspect_latest_workspace_operation(self, workspace_id: str) -> OperationSnapshot | None:
        self.operation_calls.append(workspace_id)
        return self.operations.get(workspace_id)


class _Coordinator:
    def __init__(
        self,
        snapshots: dict[str, PublishedSnapshot | None],
        *,
        acquire_error_for: str | None = None,
        acquired_snapshot_override: PublishedSnapshot | None = None,
        release_error: bool = False,
        renew_error: Exception | None = None,
        renew_blocker: tuple[Event, Event] | None = None,
        release_failures: int = 0,
        raw_release_error_for: str | None = None,
        validation_error: Exception | None = None,
    ) -> None:
        self.snapshots = snapshots
        self.acquire_error_for = acquire_error_for
        self.acquired_snapshot_override = acquired_snapshot_override
        self.release_error = release_error
        self.renew_error = renew_error
        self.renew_blocker = renew_blocker
        self.release_failures = release_failures
        self.raw_release_error_for = raw_release_error_for
        self.validation_error = validation_error
        self.acquired: list[str] = []
        self.released: list[str] = []
        self.validated: list[str] = []
        self.renewed: list[tuple[str, ...]] = []
        self.validation_override: PublishedSnapshot | None = None
        self.release_completed = Event()

    def current_snapshot(self, workspace_id: str) -> PublishedSnapshot | None:
        return self.snapshots[workspace_id]

    def acquire_read(self, workspace_id: str, *, lease_duration: timedelta) -> GenerationReadLease:
        assert lease_duration == timedelta(seconds=30)
        self.acquired.append(workspace_id)
        if workspace_id == self.acquire_error_for:
            raise GenerationReadLeaseUnavailable("changed")
        snapshot = self.snapshots[workspace_id]
        assert snapshot is not None
        return GenerationReadLease(
            lease_id=f"read_{workspace_id}",
            snapshot=self.acquired_snapshot_override or snapshot,
            acquired_at=_NOW,
            expires_at=_NOW + lease_duration,
        )

    def snapshot_for_lease(self, lease_id: str) -> PublishedSnapshot:
        self.validated.append(lease_id)
        if self.validation_error is not None:
            raise self.validation_error
        if self.validation_override is not None:
            return self.validation_override
        workspace_id = lease_id.removeprefix("read_")
        snapshot = self.snapshots[workspace_id]
        assert snapshot is not None
        return snapshot

    def renew_reads(
        self,
        leases: Sequence[GenerationReadLease],
        *,
        lease_duration: timedelta,
    ) -> None:
        assert lease_duration == timedelta(seconds=30)
        self.renewed.append(tuple(lease.lease_id for lease in leases))
        if self.renew_blocker is not None:
            started, allowed = self.renew_blocker
            started.set()
            if not allowed.wait(timeout=1):
                raise GenerationCoordinatorError("test renewal remained blocked")
        if self.renew_error is not None:
            raise self.renew_error

    def release_read(self, lease: GenerationReadLease) -> None:
        self.released.append(lease.lease_id)
        if lease.lease_id == self.raw_release_error_for:
            raise RuntimeError("unexpected release failure")
        if self.release_failures:
            self.release_failures -= 1
            raise GenerationCoordinatorError("transient release failure")
        if self.release_error:
            raise GenerationCoordinatorError("release failed")
        self.release_completed.set()


def _workspace(workspace_id: str, *, state: WorkspaceEffectiveState) -> WorkspaceSnapshot:
    return WorkspaceSnapshot(
        workspace_id=workspace_id,
        repository_id=f"repo_{workspace_id}",
        repository_display_name=workspace_id,
        workspace_display_name=workspace_id,
        root=f"/repos/{workspace_id}",
        branch="main",
        head_commit="a" * 40,
        state=state,
    )


def _operation(
    workspace_id: str,
    state: OperationState,
    *,
    pause_reason: OperationPauseReason | None = None,
) -> OperationSnapshot:
    return OperationSnapshot(
        operation_id=f"op_{workspace_id}",
        workspace_id=workspace_id,
        kind="initial_index",
        state=state,
        target_head_commit="a" * 40,
        attempt=1,
        created_at=_NOW,
        updated_at=_NOW,
        terminal_at=_NOW
        if state in {OperationState.SUCCEEDED, OperationState.FAILED, OperationState.CANCELLED}
        else None,
        phase="preflight",
        counters=OperationCountersSnapshot(known_eligible_files=10, processed_files=2),
        pause_reason=pause_reason,
        pipeline_key="pipeline-v1",
    )


def _published(workspace_id: str, *, revision: int = 1) -> PublishedSnapshot:
    return PublishedSnapshot(
        publication_id=f"publication_{workspace_id}_{revision}",
        generation_id=f"generation_{workspace_id}_{revision}",
        workspace_id=workspace_id,
        operation_id=f"op_{workspace_id}",
        target_fingerprint="a" * 64,
        pipeline_key="pipeline-v1",
        manifest_id=f"manifest_{workspace_id}",
        manifest_digest="b" * 64,
        vector_commit_token=f"vector-{workspace_id}",
        vector_digest="c" * 64,
        vector_row_count=1,
        vector_provider="openai",
        vector_model="text-embedding-3-small",
        vector_dimensions=1_536,
        embedding_contract_version=1,
        metadata_item_count=1,
        keyword_item_count=1,
        revision=revision,
        published_at=_NOW,
    )
