"""Dynamic worker pool for parallel processing.

This module provides an adaptive process pool that scales the number of workers
based on system load and available resources.
"""

from __future__ import annotations

import logging
import math
import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import ClassVar

from kb.ingest._helpers import worker_ignore_sigint

logger = logging.getLogger(__name__)

# Try to import psutil for advanced resource monitoring
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


@dataclass
class SystemResources:
    """Snapshot of system resource usage."""

    cpu_percent: float
    memory_percent: float
    load_avg_1min: float
    available_memory_mb: float


def get_system_resources() -> SystemResources:
    """Get current system resource usage."""
    if HAS_PSUTIL:
        # Use psutil for detailed metrics
        cpu_pct = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()

        # Load avg (Unix only)
        try:
            load_avg = os.getloadavg()[0]
        except (AttributeError, OSError):
            load_avg = 0.0

        return SystemResources(
            cpu_percent=cpu_pct,
            memory_percent=mem.percent,
            load_avg_1min=load_avg,
            available_memory_mb=mem.available / (1024 * 1024),
        )
    else:
        # Fallback for standard library
        try:
            load_avg = os.getloadavg()[0]
        except (AttributeError, OSError):
            load_avg = 0.0

        return SystemResources(
            cpu_percent=0.0,  # Unknown
            memory_percent=0.0,  # Unknown
            load_avg_1min=load_avg,
            available_memory_mb=1024.0,  # Assume 1GB free conservatively
        )


class DynamicWorkerPool:
    """Adaptive process pool that scales based on system load."""

    # Defaults
    MIN_WORKERS: ClassVar[int] = 2
    MAX_WORKERS_CAP: ClassVar[int] = 32  # Hard cap

    def __init__(
        self,
        max_workers: int | None = None,
        min_workers: int | None = None,
        target_cpu_utilization: float = 0.8,
        memory_headroom_mb: int = 2048,  # Leave 2GB free
    ):
        """Initialize dynamic worker pool.

        Args:
            max_workers: Maximum number of workers (default: CPU count)
            min_workers: Minimum number of workers (default: 2)
            target_cpu_utilization: Target CPU usage (0.0 - 1.0)
            memory_headroom_mb: Minimum memory to keep free in MB
        """
        self.cpu_count = mp.cpu_count()
        # Ensure max_workers is an int or None (guard against typer.OptionInfo)
        if max_workers is not None:
            self.max_workers = int(max_workers)
        else:
            self.max_workers = self.cpu_count
        self.max_workers = min(self.max_workers, self.MAX_WORKERS_CAP)

        if min_workers is not None:
            self.min_workers = int(min_workers)
        else:
            self.min_workers = self.MIN_WORKERS
        self.min_workers = min(self.min_workers, self.max_workers)

        self.target_cpu_utilization = target_cpu_utilization
        self.memory_headroom_mb = memory_headroom_mb

        # Determine initial optimal worker count
        self._optimal_workers = self._calculate_optimal_workers()

        logger.info(
            f"Initialized DynamicWorkerPool: "
            f"min={self.min_workers}, max={self.max_workers}, "
            f"using={self._optimal_workers} workers"
        )

        # Create executor — workers ignore SIGINT so only the main process handles Ctrl-C
        self._executor = ProcessPoolExecutor(max_workers=self._optimal_workers, initializer=worker_ignore_sigint)

    def _calculate_optimal_workers(self) -> int:
        """Calculate optimal number of workers based on current system state."""
        resources = get_system_resources()

        # 1. CPU-based calculation
        # If load matches CPUs, we are fully utilized
        current_load = resources.load_avg_1min
        max(0, self.cpu_count * self.target_cpu_utilization - current_load)

        # Allow at least 1 worker per free core-equivalent, but be conservative
        cpu_workers = max(self.min_workers, int(self.cpu_count * self.target_cpu_utilization))

        # If system is already heavily loaded, throttle back
        if current_load > self.cpu_count:
            cpu_workers = self.min_workers

        # 2. Memory-based calculation
        # Estimate per-worker memory usage (conservative 500MB for Python processes + deps)
        PER_WORKER_MEM_MB = 500
        available_mem_slots = int(max(0, resources.available_memory_mb - self.memory_headroom_mb) / PER_WORKER_MEM_MB)

        # 3. Combine constraints
        optimal = min(cpu_workers, available_mem_slots)

        # Apply bounds
        optimal = max(self.min_workers, optimal)
        optimal = min(self.max_workers, optimal)

        if HAS_PSUTIL:
            logger.debug(
                f"Worker calculation: CPU load={resources.load_avg_1min:.2f}/{self.cpu_count}, "
                f"Avail Mem={resources.available_memory_mb:.0f}MB -> "
                f"Optimal={optimal} (Bounds: {self.min_workers}-{self.max_workers})"
            )

        return optimal

    @property
    def executor(self) -> ProcessPoolExecutor:
        """Get the underlying executor."""
        return self._executor

    def __enter__(self) -> ProcessPoolExecutor:
        return self._executor

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._executor.shutdown(wait=True)


class WorkloadEstimator:
    """Helper to estimate workload size and batching strategy."""

    @staticmethod
    def estimate_batch_size(total_items: int, worker_count: int, min_batch: int = 10, max_batch: int = 100) -> int:
        """Estimate optimal batch size for parallel processing.

        Aim for enough batches to keep all workers busy but not too many
        to cause overhead.
        """
        if total_items == 0:
            return min_batch

        # Target 4 batches per worker minimum to allow load balancing
        target_batches = worker_count * 4

        batch_size = math.ceil(total_items / target_batches)

        # Clamp to reasonable limits
        return max(min_batch, min(max_batch, batch_size))
