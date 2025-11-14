"""Adaptive nprobes tuning for LanceDB queries.

This module provides runtime adjustment of nprobes based on actual
search performance, dynamically balancing speed and quality.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Optional

from kb.retrieval.ann_tuning import ANNParams

logger = logging.getLogger(__name__)


@dataclass
class SearchMetrics:
    """Metrics for a single search operation."""

    query_id: str
    """Unique identifier for the query"""

    latency_ms: float
    """Search latency in milliseconds"""

    nprobes: int
    """Number of probes used"""

    refine_factor: int
    """Refine factor used"""

    result_count: int
    """Number of results returned"""

    quality_score: Optional[float] = None
    """Optional quality score (0-1) if available"""

    timestamp: float = 0.0
    """Timestamp of the search"""

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class AdaptiveState:
    """Current state of adaptive tuning."""

    current_nprobes: int
    """Current nprobes value"""

    current_refine_factor: int
    """Current refine factor"""

    target_latency_ms: float
    """Target latency threshold"""

    avg_latency_ms: float
    """Recent average latency"""

    adjustment_count: int
    """Number of adjustments made"""

    last_adjustment: float
    """Timestamp of last adjustment"""


class AdaptiveNProbes:
    """Adaptive nprobes tuner for LanceDB queries.

    This class monitors search performance and dynamically adjusts
    nprobes to meet latency targets while maintaining quality.

    Strategy:
    1. Start with conservative nprobes (20)
    2. Monitor search latency over recent queries
    3. If latency > target: decrease nprobes
    4. If latency << target: increase nprobes
    5. Use exponential moving average for stability
    """

    def __init__(
        self,
        target_latency_ms: float = 150.0,
        min_nprobes: int = 5,
        max_nprobes: int = 50,
        initial_nprobes: int = 20,
        initial_refine_factor: int = 10,
        history_size: int = 50,
        adjustment_threshold: float = 0.2,
        adjustment_cooldown: float = 10.0,
    ):
        """Initialize adaptive nprobes tuner.

        Args:
            target_latency_ms: Target search latency (default: 150ms)
            min_nprobes: Minimum nprobes value (default: 5)
            max_nprobes: Maximum nprobes value (default: 50)
            initial_nprobes: Starting nprobes value (default: 20)
            initial_refine_factor: Starting refine factor (default: 10)
            history_size: Number of recent queries to track (default: 50)
            adjustment_threshold: Latency deviation to trigger adjustment (default: 0.2 = 20%)
            adjustment_cooldown: Minimum seconds between adjustments (default: 10.0)
        """
        self.target_latency_ms = target_latency_ms
        self.min_nprobes = min_nprobes
        self.max_nprobes = max_nprobes
        self.initial_nprobes = initial_nprobes
        self.initial_refine_factor = initial_refine_factor
        self.history_size = history_size
        self.adjustment_threshold = adjustment_threshold
        self.adjustment_cooldown = adjustment_cooldown

        # Current parameters
        self.current_nprobes = initial_nprobes
        self.current_refine_factor = initial_refine_factor

        # History tracking
        self._history: deque[SearchMetrics] = deque(maxlen=history_size)

        # Adjustment tracking
        self._adjustment_count = 0
        self._last_adjustment = 0.0

        # Moving averages
        self._ema_latency: Optional[float] = None
        self._ema_alpha = 0.2  # Smoothing factor

    def get_params(
        self,
        query_type: Optional[str] = None,
        top_k: int = 10,
    ) -> ANNParams:
        """Get current ANN parameters.

        Args:
            query_type: Optional query type for context
            top_k: Number of results requested

        Returns:
            ANNParams with current adaptive settings
        """
        # Adjust for query context
        nprobes = self.current_nprobes
        refine_factor = self.current_refine_factor

        # Boost accuracy for identifier queries
        if query_type == "identifier":
            nprobes = min(int(nprobes * 1.5), self.max_nprobes)
            refine_factor = min(int(refine_factor * 1.5), 20)

        # Adjust for small result sets
        if top_k <= 3:
            nprobes = min(int(nprobes * 1.2), self.max_nprobes)

        return ANNParams(
            metric="cosine",
            nprobes=nprobes,
            refine_factor=refine_factor,
            use_index=True,
        )

    def record_search(
        self,
        query_id: str,
        latency_ms: float,
        result_count: int,
        quality_score: Optional[float] = None,
    ) -> None:
        """Record a search operation for adaptive tuning.

        Args:
            query_id: Unique query identifier
            latency_ms: Search latency in milliseconds
            result_count: Number of results returned
            quality_score: Optional quality score (0-1)
        """
        metrics = SearchMetrics(
            query_id=query_id,
            latency_ms=latency_ms,
            nprobes=self.current_nprobes,
            refine_factor=self.current_refine_factor,
            result_count=result_count,
            quality_score=quality_score,
        )

        self._history.append(metrics)

        # Update exponential moving average
        if self._ema_latency is None:
            self._ema_latency = latency_ms
        else:
            self._ema_latency = (
                self._ema_alpha * latency_ms + (1 - self._ema_alpha) * self._ema_latency
            )

        # Consider adjustment
        self._consider_adjustment()

    def _consider_adjustment(self) -> None:
        """Consider adjusting nprobes based on recent performance."""
        # Need enough history
        if len(self._history) < 10:
            return

        # Check cooldown period
        now = time.time()
        if now - self._last_adjustment < self.adjustment_cooldown:
            return

        # Calculate recent average latency
        recent_latencies = [m.latency_ms for m in list(self._history)[-20:]]
        avg_latency = sum(recent_latencies) / len(recent_latencies)

        # Calculate deviation from target
        deviation = (avg_latency - self.target_latency_ms) / self.target_latency_ms

        # Only adjust if deviation exceeds threshold
        if abs(deviation) < self.adjustment_threshold:
            return

        # Determine adjustment direction and magnitude
        if deviation > 0:
            # Latency too high - decrease nprobes
            adjustment_factor = 0.8  # Reduce by 20%
            new_nprobes = max(
                self.min_nprobes, int(self.current_nprobes * adjustment_factor)
            )

            # Also reduce refine factor if needed
            if self.current_refine_factor > 5:
                new_refine_factor = max(5, int(self.current_refine_factor * 0.9))
            else:
                new_refine_factor = self.current_refine_factor

        else:
            # Latency too low - can increase nprobes for better quality
            adjustment_factor = 1.2  # Increase by 20%
            new_nprobes = min(
                self.max_nprobes, int(self.current_nprobes * adjustment_factor)
            )

            # Also increase refine factor if appropriate
            if self.current_refine_factor < 15:
                new_refine_factor = min(15, int(self.current_refine_factor * 1.1))
            else:
                new_refine_factor = self.current_refine_factor

        # Apply adjustment
        if new_nprobes != self.current_nprobes:
            logger.info(
                f"Adaptive adjustment: nprobes {self.current_nprobes} → {new_nprobes}, "
                f"refine_factor {self.current_refine_factor} → {new_refine_factor} "
                f"(avg_latency={avg_latency:.1f}ms, target={self.target_latency_ms}ms)"
            )

            self.current_nprobes = new_nprobes
            self.current_refine_factor = new_refine_factor
            self._adjustment_count += 1
            self._last_adjustment = now

    def get_state(self) -> AdaptiveState:
        """Get current adaptive tuning state.

        Returns:
            Current state snapshot
        """
        # Calculate average latency from history
        if self._history:
            recent_latencies = [m.latency_ms for m in self._history]
            avg_latency = sum(recent_latencies) / len(recent_latencies)
        else:
            avg_latency = 0.0

        return AdaptiveState(
            current_nprobes=self.current_nprobes,
            current_refine_factor=self.current_refine_factor,
            target_latency_ms=self.target_latency_ms,
            avg_latency_ms=avg_latency,
            adjustment_count=self._adjustment_count,
            last_adjustment=self._last_adjustment,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get detailed statistics about adaptive tuning.

        Returns:
            Dictionary with tuning statistics
        """
        if not self._history:
            return {
                "total_queries": 0,
                "current_nprobes": self.current_nprobes,
                "current_refine_factor": self.current_refine_factor,
                "target_latency_ms": self.target_latency_ms,
                "avg_latency_ms": 0.0,
                "min_latency_ms": 0.0,
                "max_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "adjustment_count": 0,
            }

        # Extract latencies
        latencies = sorted([m.latency_ms for m in self._history])

        # Calculate percentiles
        p50_idx = len(latencies) // 2
        p95_idx = int(len(latencies) * 0.95)

        return {
            "total_queries": len(self._history),
            "current_nprobes": self.current_nprobes,
            "current_refine_factor": self.current_refine_factor,
            "target_latency_ms": self.target_latency_ms,
            "avg_latency_ms": sum(latencies) / len(latencies),
            "min_latency_ms": min(latencies),
            "max_latency_ms": max(latencies),
            "p50_latency_ms": latencies[p50_idx],
            "p95_latency_ms": latencies[p95_idx],
            "adjustment_count": self._adjustment_count,
            "ema_latency_ms": self._ema_latency or 0.0,
        }

    def reset(self) -> None:
        """Reset adaptive tuner to initial state."""
        self.current_nprobes = self.initial_nprobes
        self.current_refine_factor = self.initial_refine_factor
        self._history.clear()
        self._adjustment_count = 0
        self._last_adjustment = 0.0
        self._ema_latency = None

    def estimate_optimal_nprobes(
        self,
        dataset_size: int,
        target_recall: float = 0.95,
    ) -> int:
        """Estimate optimal nprobes for dataset characteristics.

        Args:
            dataset_size: Number of vectors in dataset
            target_recall: Target recall rate (0-1)

        Returns:
            Estimated optimal nprobes value
        """
        # Rough heuristics based on IVF theory
        # LanceDB typically uses ~100 clusters per million vectors
        estimated_clusters = max(dataset_size // 10000, 10)

        # For 95% recall: nprobes ≈ sqrt(K)
        # For 98% recall: nprobes ≈ sqrt(K) * 1.5
        # For 90% recall: nprobes ≈ sqrt(K) * 0.7
        base_nprobes = math.sqrt(estimated_clusters)

        if target_recall >= 0.98:
            multiplier = 1.5
        elif target_recall >= 0.95:
            multiplier = 1.0
        elif target_recall >= 0.90:
            multiplier = 0.7
        else:
            multiplier = 0.5

        optimal = int(base_nprobes * multiplier)

        # Clamp to valid range, but ensure distinct values for different recall levels
        clamped = max(self.min_nprobes, min(optimal, self.max_nprobes))

        # If clamped at min, use recall-based offset to distinguish
        if clamped == self.min_nprobes and optimal < self.min_nprobes:
            if target_recall >= 0.98:
                return self.min_nprobes + 2
            elif target_recall >= 0.95:
                return self.min_nprobes + 1
            elif target_recall >= 0.90:
                return self.min_nprobes

        return clamped


class GlobalAdaptiveNProbes:
    """Global singleton for adaptive nprobes tuning."""

    _instance: Optional[AdaptiveNProbes] = None

    @classmethod
    def get_instance(
        cls,
        target_latency_ms: float = 150.0,
    ) -> AdaptiveNProbes:
        """Get or create global adaptive nprobes instance.

        Args:
            target_latency_ms: Target latency (only used for initialization)

        Returns:
            Global AdaptiveNProbes instance
        """
        if cls._instance is None:
            cls._instance = AdaptiveNProbes(target_latency_ms=target_latency_ms)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the global instance."""
        cls._instance = None


def get_adaptive_params(
    query_type: Optional[str] = None,
    top_k: int = 10,
    target_latency_ms: float = 150.0,
) -> ANNParams:
    """Convenience function to get adaptive ANN parameters.

    Args:
        query_type: Optional query type
        top_k: Number of results requested
        target_latency_ms: Target latency threshold

    Returns:
        Adaptively tuned ANNParams
    """
    tuner = GlobalAdaptiveNProbes.get_instance(target_latency_ms)
    return tuner.get_params(query_type=query_type, top_k=top_k)


def record_search_performance(
    query_id: str,
    latency_ms: float,
    result_count: int,
    quality_score: Optional[float] = None,
) -> None:
    """Record search performance for adaptive tuning.

    Args:
        query_id: Unique query identifier
        latency_ms: Search latency in milliseconds
        result_count: Number of results returned
        quality_score: Optional quality score (0-1)
    """
    tuner = GlobalAdaptiveNProbes.get_instance()
    tuner.record_search(
        query_id=query_id,
        latency_ms=latency_ms,
        result_count=result_count,
        quality_score=quality_score,
    )
