"""Tests for process-bound runtime ownership and durable operation execution leases."""

from __future__ import annotations

import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kb.mcp.contracts import OperationStatusInput
from kb.runtime.storage import macos_storage_layout
from kb.services import operation_runtime as operation_runtime_module
from kb.services.lifecycle_read import OperationStatusService
from kb.services.operation_runtime import OperationRuntime, OperationRuntimeError, ProcessStartProbe
from kb.services.workspace_registry import (
    OperationCountersSnapshot,
    OperationPauseReason,
    OperationState,
    WorkspaceOperation,
    WorkspaceRegistry,
    WorkspaceRegistryError,
)
from kb.services.worktree import GitWorktree


def test_two_runtimes_can_claim_one_operation_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    first = _register_runtime(registry, "first", now)
    second = _register_runtime(registry, "second", now)

    def claim(runtime_id: str, identity: str):
        return registry.claim_next_operation(
            runtime_id=runtime_id,
            process_start_identity=identity,
            pipeline_key="pipeline-v1",
            now=now,
            expires_at=now + timedelta(seconds=15),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(
            executor.map(
                lambda owner: claim(owner.runtime_id, owner.process_start_identity),
                (first, second),
            )
        )

    leases = [claim for claim in claims if claim is not None]
    assert len(leases) == 1
    assert leases[0].operation.operation_id == operation.operation_id
    assert leases[0].operation.state is OperationState.RUNNING
    assert leases[0].checkpoint.phase == "preflight"
    assert leases[0].checkpoint.target_fingerprint == f"git-head-v1:{operation.target_head_commit}"
    stored = registry.get_operation(operation.operation_id)
    assert stored is not None
    assert stored.state is OperationState.RUNNING


def test_checkpoint_progress_is_monotonic_and_visible_to_operation_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    owner = _register_runtime(registry, "worker", now)
    lease = registry.claim_next_operation(
        runtime_id=owner.runtime_id,
        process_start_identity=owner.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=15),
    )
    assert lease is not None
    checkpoint = replace(
        lease.checkpoint,
        phase="chunk",
        counters=OperationCountersSnapshot(
            known_eligible_files=10,
            processed_files=6,
            parsed_files=4,
            reused_chunks=3,
        ),
    )

    persisted = registry.checkpoint_operation(lease, checkpoint, observed_at=now + timedelta(seconds=1))
    snapshot = registry.inspect_operation(operation.operation_id)

    assert persisted.checkpointed_at == now + timedelta(seconds=1)
    assert snapshot is not None
    assert snapshot.phase == "chunk"
    assert snapshot.counters is not None
    assert snapshot.counters.processed_files == 6
    assert snapshot.counters.reused_chunks == 3

    with pytest.raises(WorkspaceRegistryError, match="cannot regress"):
        registry.checkpoint_operation(
            lease,
            replace(checkpoint, phase="scan"),
            observed_at=now + timedelta(seconds=2),
        )


@pytest.mark.asyncio
async def test_operation_status_projects_checkpoint_and_live_executor_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime.now(UTC)
    owner = _register_runtime(registry, "worker", now)
    lease = registry.claim_next_operation(
        runtime_id=owner.runtime_id,
        process_start_identity=owner.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=15),
    )
    assert lease is not None
    registry.checkpoint_operation(
        lease,
        replace(
            lease.checkpoint,
            phase="scan",
            counters=OperationCountersSnapshot(known_eligible_files=12, processed_files=3),
        ),
        observed_at=now + timedelta(seconds=1),
    )

    result = await OperationStatusService(registry)(OperationStatusInput(operation_id=operation.operation_id))

    assert result.state is OperationState.RUNNING
    assert result.phase == "scan"
    assert result.counters.known_eligible_files == 12
    assert result.counters.processed_files == 3
    assert result.pause_reason is None


def test_heartbeat_renews_runtime_and_owned_operation_lease(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, _operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    owner = _register_runtime(registry, "worker", now, lifetime=5)
    lease = registry.claim_next_operation(
        runtime_id=owner.runtime_id,
        process_start_identity=owner.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=5),
    )
    assert lease is not None

    renewed = registry.heartbeat_runtime(
        runtime_id=owner.runtime_id,
        process_start_identity=owner.process_start_identity,
        now=now + timedelta(seconds=4),
        expires_at=now + timedelta(seconds=19),
    )
    finished = registry.finish_operation(
        lease,
        OperationState.SUCCEEDED,
        observed_at=now + timedelta(seconds=10),
    )

    assert renewed.expires_at == now + timedelta(seconds=19)
    assert finished.state is OperationState.SUCCEEDED


def test_expired_runtime_cannot_revive_itself_with_a_late_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, _operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    owner = _register_runtime(registry, "worker", now, lifetime=5)

    with pytest.raises(WorkspaceRegistryError, match="no longer matches"):
        registry.heartbeat_runtime(
            runtime_id=owner.runtime_id,
            process_start_identity=owner.process_start_identity,
            now=now + timedelta(seconds=5),
            expires_at=now + timedelta(seconds=20),
        )


def test_graceful_shutdown_pauses_and_hands_off_checkpointed_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    first = _register_runtime(registry, "first", now)
    lease = registry.claim_next_operation(
        runtime_id=first.runtime_id,
        process_start_identity=first.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=15),
    )
    assert lease is not None
    registry.checkpoint_operation(
        lease,
        replace(
            lease.checkpoint,
            phase="embed",
            counters=OperationCountersSnapshot(processed_files=8, parsed_files=8, embedded_chunks=5),
        ),
        observed_at=now + timedelta(seconds=1),
    )

    paused = registry.drain_runtime(
        runtime_id=first.runtime_id,
        process_start_identity=first.process_start_identity,
        observed_at=now + timedelta(seconds=2),
    )
    snapshot = registry.inspect_operation(operation.operation_id)
    second = _register_runtime(registry, "second", now + timedelta(seconds=2))
    resumed = registry.claim_next_operation(
        runtime_id=second.runtime_id,
        process_start_identity=second.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now + timedelta(seconds=2),
        expires_at=now + timedelta(seconds=17),
    )

    assert paused == 1
    assert snapshot is not None
    assert snapshot.state is OperationState.PAUSED
    assert snapshot.pause_reason == "shutdown"
    assert resumed is not None
    assert resumed.operation.operation_id == operation.operation_id
    assert resumed.checkpoint.phase == "embed"
    assert resumed.checkpoint.counters.embedded_chunks == 5
    assert resumed.checkpoint.pause_reason is None
    assert resumed.checkpoint.resume_count == 1


def test_pid_reuse_proof_retires_owner_but_probe_uncertainty_does_not(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    owner = _register_runtime(registry, "worker", now)
    lease = registry.claim_next_operation(
        runtime_id=owner.runtime_id,
        process_start_identity=owner.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=15),
    )
    assert lease is not None

    untouched = registry.reconcile_stale_runtime(
        runtime_id=owner.runtime_id,
        process_start_identity=owner.process_start_identity,
        observed_at=now + timedelta(seconds=1),
        stale_identity_proven=False,
    )
    paused = registry.reconcile_stale_runtime(
        runtime_id=owner.runtime_id,
        process_start_identity=owner.process_start_identity,
        observed_at=now + timedelta(seconds=2),
        stale_identity_proven=True,
    )
    snapshot = registry.inspect_operation(operation.operation_id)

    assert untouched == 0
    assert paused == 1
    assert snapshot is not None
    assert snapshot.state is OperationState.PAUSED
    assert snapshot.pause_reason == "runtime_absent"


def test_expired_lease_is_reconciled_before_compatible_peer_takeover(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    first = _register_runtime(registry, "first", now, lifetime=5)
    claimed = registry.claim_next_operation(
        runtime_id=first.runtime_id,
        process_start_identity=first.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=5),
    )
    assert claimed is not None
    second = _register_runtime(registry, "second", now + timedelta(seconds=6))

    takeover = registry.claim_next_operation(
        runtime_id=second.runtime_id,
        process_start_identity=second.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now + timedelta(seconds=6),
        expires_at=now + timedelta(seconds=21),
    )

    assert takeover is not None
    assert takeover.operation.operation_id == operation.operation_id
    assert takeover.checkpoint.resume_count == 1


def test_incompatible_pipeline_cannot_resume_a_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, _operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    first = _register_runtime(registry, "first", now)
    lease = registry.claim_next_operation(
        runtime_id=first.runtime_id,
        process_start_identity=first.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=15),
    )
    assert lease is not None
    registry.drain_runtime(
        runtime_id=first.runtime_id,
        process_start_identity=first.process_start_identity,
        observed_at=now + timedelta(seconds=1),
    )
    second = _register_runtime(registry, "second", now + timedelta(seconds=1))

    incompatible = registry.claim_next_operation(
        runtime_id=second.runtime_id,
        process_start_identity=second.process_start_identity,
        pipeline_key="pipeline-v2",
        now=now + timedelta(seconds=1),
        expires_at=now + timedelta(seconds=16),
    )

    assert incompatible is None


@pytest.mark.parametrize(
    ("reason", "expected_state"),
    [
        ("credential_missing", OperationState.PAUSED),
        ("disk_pressure", OperationState.PAUSED),
        ("awaiting_approval", OperationState.AWAITING_APPROVAL),
    ],
)
def test_blocked_operations_release_their_lease_without_automatic_resume(
    reason: OperationPauseReason,
    expected_state: OperationState,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    first = _register_runtime(registry, "first", now)
    lease = registry.claim_next_operation(
        runtime_id=first.runtime_id,
        process_start_identity=first.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=15),
    )
    assert lease is not None

    paused = registry.pause_operation(lease, reason, observed_at=now + timedelta(seconds=1))
    second = _register_runtime(registry, "second", now + timedelta(seconds=1))
    resumed = registry.claim_next_operation(
        runtime_id=second.runtime_id,
        process_start_identity=second.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now + timedelta(seconds=1),
        expires_at=now + timedelta(seconds=16),
    )
    snapshot = registry.inspect_operation(operation.operation_id)

    assert paused.state is expected_state
    assert resumed is None
    assert snapshot is not None
    assert snapshot.pause_reason == reason


def test_expired_lease_cannot_checkpoint_or_complete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, _operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    owner = _register_runtime(registry, "worker", now, lifetime=5)
    lease = registry.claim_next_operation(
        runtime_id=owner.runtime_id,
        process_start_identity=owner.process_start_identity,
        pipeline_key="pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=5),
    )
    assert lease is not None

    with pytest.raises(WorkspaceRegistryError, match="expired"):
        registry.checkpoint_operation(
            lease,
            lease.checkpoint,
            observed_at=now + timedelta(seconds=5),
        )
    with pytest.raises(WorkspaceRegistryError, match="expired"):
        registry.finish_operation(
            lease,
            OperationState.SUCCEEDED,
            observed_at=now + timedelta(seconds=5),
        )


@pytest.mark.asyncio
async def test_operation_runtime_context_registers_and_drains_without_background_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    probe = lambda pid: ProcessStartProbe(available=True, identity=f"start-{pid}")  # noqa: E731
    runtime = OperationRuntime(
        registry,
        mode="mcp",
        operation_capable=True,
        pid=42,
        clock=lambda: now,
        process_probe=probe,
        start_heartbeat=False,
    )

    await runtime.start()
    lease = await runtime.claim_next()
    assert lease is not None
    assert registry.read_runtime_status(now=now).operation_executors == 1

    await runtime.close()
    snapshot = registry.inspect_operation(operation.operation_id)

    assert registry.read_runtime_status(now=now).active_processes == 0
    assert snapshot is not None
    assert snapshot.state is OperationState.PAUSED
    assert snapshot.pause_reason == "shutdown"


@pytest.mark.asyncio
async def test_runtime_start_reconciles_pid_reuse_before_resuming_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    prior = registry.register_runtime(
        runtime_id="runtime_prior",
        pid=42,
        process_start_identity="old-start",
        mode="mcp",
        operation_capable=True,
        now=now,
        expires_at=now + timedelta(seconds=15),
    )
    original_lease = registry.claim_next_operation(
        runtime_id=prior.runtime_id,
        process_start_identity=prior.process_start_identity,
        pipeline_key="dolphin-pipeline-v1",
        now=now,
        expires_at=now + timedelta(seconds=15),
    )
    assert original_lease is not None
    runtime = OperationRuntime(
        registry,
        mode="mcp",
        operation_capable=True,
        pid=42,
        clock=lambda: now + timedelta(seconds=1),
        process_probe=lambda _pid: ProcessStartProbe(available=True, identity="new-start"),
        start_heartbeat=False,
    )

    await runtime.start()
    resumed = await runtime.claim_next()

    assert resumed is not None
    assert resumed.operation.operation_id == operation.operation_id
    assert resumed.checkpoint.resume_count == 1
    await runtime.close()


@pytest.mark.asyncio
async def test_non_executing_runtime_cannot_claim_operations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry, _operation = _registry_with_operation(monkeypatch, tmp_path)
    now = datetime(2026, 8, 9, 12, tzinfo=UTC)
    runtime = OperationRuntime(
        registry,
        mode="mcp",
        operation_capable=False,
        pid=42,
        clock=lambda: now,
        process_probe=lambda pid: ProcessStartProbe(available=True, identity=f"start-{pid}"),
        start_heartbeat=False,
    )
    await runtime.start()

    with pytest.raises(OperationRuntimeError, match="not configured"):
        await runtime.claim_next()

    await runtime.close()


def test_process_start_probe_distinguishes_absence_from_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operation_runtime_module.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, stdout="", stderr=""),
    )
    absent = operation_runtime_module.probe_process_start_identity(123)

    def timeout(*_args: object, **_kwargs: object):
        raise subprocess.TimeoutExpired(["ps"], 1)

    monkeypatch.setattr(operation_runtime_module.subprocess, "run", timeout)
    unavailable = operation_runtime_module.probe_process_start_identity(123)

    assert absent == ProcessStartProbe(available=True, identity=None)
    assert unavailable == ProcessStartProbe(available=False, identity=None)


def _registry_with_operation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[WorkspaceRegistry, WorkspaceOperation]:
    root = tmp_path / "repository"
    root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    registry = WorkspaceRegistry(macos_storage_layout(home=home))
    monkeypatch.setattr("kb.services.workspace_registry.validate_git_worktree_snapshot", lambda _worktree: None)
    _registration, operation = registry.register_and_submit_initial_index(
        GitWorktree(
            root=root,
            common_git_dir=root / ".git",
            common_git_dir_identity="common-identity",
            worktree_git_dir=root / ".git",
            worktree_git_dir_identity="worktree-identity",
            head_commit="a" * 40,
            branch="develop",
        ),
        cleanup_receipt=_cleanup_receipt("operation-runtime"),
    )
    return registry, operation


def _register_runtime(
    registry: WorkspaceRegistry,
    label: str,
    now: datetime,
    *,
    lifetime: int = 15,
):
    return registry.register_runtime(
        runtime_id=f"runtime_{label}",
        pid=100 + len(label),
        process_start_identity=f"start-{label}",
        mode="mcp",
        operation_capable=True,
        now=now,
        expires_at=now + timedelta(seconds=lifetime),
    )


def _cleanup_receipt(seed: str) -> str:
    token = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:43]
    return f"dolphin-cleanup-v1_{token}"
