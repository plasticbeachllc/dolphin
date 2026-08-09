"""Process-bound ownership and renewable execution leases for durable operations."""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from kb.services.workspace_registry import (
    OperationCheckpoint,
    OperationLease,
    OperationPauseReason,
    OperationState,
    RuntimeMode,
    RuntimeOwner,
    WorkspaceOperation,
    WorkspaceRegistry,
    WorkspaceRegistryError,
)

RUNTIME_LEASE_SECONDS = 15
RUNTIME_HEARTBEAT_SECONDS = 5
GRACEFUL_SHUTDOWN_SECONDS = 5
PROCESS_PROBE_TIMEOUT_SECONDS = 1
PROCESS_PROBE_CONCURRENCY = 4


class OperationRuntimeError(RuntimeError):
    """A foreground runtime cannot safely own or advance durable work."""


@dataclass(frozen=True, slots=True)
class ProcessStartProbe:
    """Bounded result of inspecting one PID without treating uncertainty as staleness."""

    available: bool
    identity: str | None


type Clock = Callable[[], datetime]
type ProcessProbe = Callable[[int], ProcessStartProbe]


def probe_process_start_identity(pid: int) -> ProcessStartProbe:
    """Read the macOS process start identity used to distinguish PID reuse."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return ProcessStartProbe(available=False, identity=None)
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            check=False,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            text=True,
            timeout=PROCESS_PROBE_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ProcessStartProbe(available=False, identity=None)
    if result.returncode == 1 and not result.stdout and not result.stderr:
        return ProcessStartProbe(available=True, identity=None)
    identity = result.stdout.strip()
    if result.returncode != 0 or not identity or "\x00" in identity or len(identity) > 256:
        return ProcessStartProbe(available=False, identity=None)
    return ProcessStartProbe(available=True, identity=identity)


class OperationRuntime:
    """Own one visible process lifetime and its renewable operation leases."""

    def __init__(
        self,
        registry: WorkspaceRegistry,
        *,
        mode: RuntimeMode,
        operation_capable: bool,
        pipeline_key: str = "dolphin-pipeline-v1",
        pid: int | None = None,
        clock: Clock | None = None,
        process_probe: ProcessProbe = probe_process_start_identity,
        start_heartbeat: bool = True,
    ) -> None:
        self._registry = registry
        self._mode = mode
        self._operation_capable = operation_capable
        self._pipeline_key = pipeline_key
        self._pid = pid or os.getpid()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._process_probe = process_probe
        self._start_heartbeat = start_heartbeat
        self._owner: RuntimeOwner | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def owner(self) -> RuntimeOwner:
        if not self.ownership_available or self._owner is None:
            raise OperationRuntimeError("Dolphin operation runtime ownership is unavailable")
        return self._owner

    @property
    def ownership_available(self) -> bool:
        """Report whether this process still has a supervised runtime owner."""
        if self._owner is None or self._closed:
            return False
        heartbeat = self._heartbeat_task
        return heartbeat is None or not heartbeat.done()

    async def start(self) -> RuntimeOwner:
        """Reconcile stale owners, prove this process identity, and register it."""
        if self._closed:
            raise OperationRuntimeError("Dolphin operation runtime is already closed")
        if self._owner is not None:
            return self._owner

        reconciliation_time = self._now()
        try:
            owners = (
                await asyncio.to_thread(self._registry.list_runtime_owners)
                if await asyncio.to_thread(self._registry.database_exists)
                else ()
            )
            owner_probes: list[ProcessStartProbe] = []
            for offset in range(0, len(owners), PROCESS_PROBE_CONCURRENCY):
                batch = owners[offset : offset + PROCESS_PROBE_CONCURRENCY]
                owner_probes.extend(
                    await asyncio.gather(*(asyncio.to_thread(self._process_probe, owner.pid) for owner in batch))
                )
            for owner, probe in zip(owners, owner_probes, strict=True):
                stale_identity_proven = probe.available and probe.identity != owner.process_start_identity
                await asyncio.to_thread(
                    self._registry.reconcile_stale_runtime,
                    runtime_id=owner.runtime_id,
                    process_start_identity=owner.process_start_identity,
                    observed_at=reconciliation_time,
                    stale_identity_proven=stale_identity_proven,
                )

            own_probe = await asyncio.to_thread(self._process_probe, self._pid)
            if not own_probe.available or own_probe.identity is None:
                raise OperationRuntimeError("Dolphin cannot prove this process start identity")
            registration_time = self._now()
            runtime_id = f"runtime_{uuid.uuid4().hex}"
            self._owner = await asyncio.to_thread(
                self._registry.register_runtime,
                runtime_id=runtime_id,
                pid=self._pid,
                process_start_identity=own_probe.identity,
                mode=self._mode,
                operation_capable=self._operation_capable,
                pipeline_key=self._pipeline_key if self._operation_capable else None,
                now=registration_time,
                expires_at=registration_time + timedelta(seconds=RUNTIME_LEASE_SECONDS),
            )
        except WorkspaceRegistryError as exc:
            raise OperationRuntimeError("Dolphin could not establish runtime ownership") from exc

        if self._start_heartbeat:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        return self._owner

    async def heartbeat_once(self) -> RuntimeOwner:
        """Renew this process record and all execution leases it owns."""
        owner = self.owner
        now = self._now()
        try:
            self._owner = await asyncio.to_thread(
                self._registry.heartbeat_runtime,
                runtime_id=owner.runtime_id,
                process_start_identity=owner.process_start_identity,
                now=now,
                expires_at=now + timedelta(seconds=RUNTIME_LEASE_SECONDS),
            )
        except WorkspaceRegistryError as exc:
            raise OperationRuntimeError("Dolphin lost runtime ownership") from exc
        return self._owner

    async def claim_next(self) -> OperationLease | None:
        """Claim the oldest compatible operation when this runtime is capable."""
        owner = self.owner
        if not owner.operation_capable:
            raise OperationRuntimeError("Dolphin runtime is not configured to execute operations")
        now = self._now()
        try:
            return await asyncio.to_thread(
                self._registry.claim_next_operation,
                runtime_id=owner.runtime_id,
                process_start_identity=owner.process_start_identity,
                pipeline_key=self._pipeline_key,
                now=now,
                expires_at=now + timedelta(seconds=RUNTIME_LEASE_SECONDS),
            )
        except WorkspaceRegistryError as exc:
            raise OperationRuntimeError("Dolphin could not claim durable operation work") from exc

    async def checkpoint(self, lease: OperationLease, checkpoint: OperationCheckpoint) -> OperationCheckpoint:
        """Persist monotonic bounded progress under an active execution lease."""
        try:
            return await asyncio.to_thread(
                self._registry.checkpoint_operation,
                lease,
                checkpoint,
                observed_at=self._now(),
            )
        except WorkspaceRegistryError as exc:
            raise OperationRuntimeError("Dolphin could not persist operation progress") from exc

    async def finish(self, lease: OperationLease, state: OperationState) -> WorkspaceOperation:
        """Commit one terminal outcome under an active execution lease."""
        try:
            return await asyncio.to_thread(
                self._registry.finish_operation,
                lease,
                state,
                observed_at=self._now(),
            )
        except WorkspaceRegistryError as exc:
            raise OperationRuntimeError("Dolphin could not finish the operation safely") from exc

    async def pause(self, lease: OperationLease, reason: OperationPauseReason) -> WorkspaceOperation:
        """Persist a blocked state and make the operation safely unowned."""
        try:
            return await asyncio.to_thread(
                self._registry.pause_operation,
                lease,
                reason,
                observed_at=self._now(),
            )
        except WorkspaceRegistryError as exc:
            raise OperationRuntimeError("Dolphin could not pause the operation safely") from exc

    async def close(self) -> None:
        """Stop heartbeats and release owned work within the shutdown budget."""
        if self._closed:
            return
        heartbeat = self._heartbeat_task
        self._heartbeat_task = None
        heartbeat_error: OperationRuntimeError | None = None
        if heartbeat is not None:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
            except OperationRuntimeError as exc:
                heartbeat_error = exc
        if self._owner is None:
            self._closed = True
            if heartbeat_error is not None:
                raise heartbeat_error
            return
        owner = self._owner
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    self._registry.drain_runtime,
                    runtime_id=owner.runtime_id,
                    process_start_identity=owner.process_start_identity,
                    observed_at=self._now(),
                ),
                timeout=GRACEFUL_SHUTDOWN_SECONDS,
            )
        except (TimeoutError, WorkspaceRegistryError) as exc:
            raise OperationRuntimeError("Dolphin could not release runtime ownership cleanly") from exc
        self._closed = True
        if heartbeat_error is not None:
            raise heartbeat_error

    async def __aenter__(self) -> OperationRuntime:
        await self.start()
        return self

    async def __aexit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        await self.close()

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise OperationRuntimeError("Dolphin runtime clock must return timezone-aware timestamps")
        return value.astimezone(UTC)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(RUNTIME_HEARTBEAT_SECONDS)
            await self.heartbeat_once()
