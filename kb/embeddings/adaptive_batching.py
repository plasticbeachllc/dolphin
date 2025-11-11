"""Adaptive batch sizing for embedding API calls.

This module provides intelligent batching that adjusts batch size based on
chunk token counts to optimize throughput while respecting API limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Iterator
from collections import deque

from ..chunkers.token_utils import count_tokens


@dataclass
class BatchMetrics:
    """Metrics for a batch of texts."""
    batch_size: int
    total_tokens: int
    avg_tokens: float
    processing_time: float | None = None


class AdaptiveBatcher:
    """Adaptive batcher that adjusts batch size based on content.

    This batcher aims to maximize throughput by:
    1. Targeting a specific total token count per batch
    2. Respecting min/max batch size constraints
    3. Learning from recent batch performance
    """

    def __init__(
        self,
        target_tokens: int = 8000,
        min_batch_size: int = 10,
        max_batch_size: int = 500,
        model: str = "small",
    ):
        """Initialize adaptive batcher.

        Args:
            target_tokens: Target total tokens per batch (default: 8000)
            min_batch_size: Minimum texts per batch (default: 10)
            max_batch_size: Maximum texts per batch (default: 500)
            model: Embedding model name for token counting
        """
        self.target_tokens = target_tokens
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.model = model

        # Track recent batches for adaptive sizing
        self._recent_metrics: deque[BatchMetrics] = deque(maxlen=10)
        self._current_batch_size = min_batch_size

    def create_batches(self, texts: List[str]) -> Iterator[List[str]]:
        """Create optimally-sized batches from texts.

        Args:
            texts: List of texts to batch

        Yields:
            Batches of texts
        """
        if not texts:
            return

        i = 0
        while i < len(texts):
            # Determine batch size for this batch
            batch_size = self._estimate_batch_size(texts[i:min(i + 100, len(texts))])
            batch_size = max(self.min_batch_size, min(batch_size, self.max_batch_size))

            # Don't exceed remaining texts
            batch_size = min(batch_size, len(texts) - i)

            # Extract batch
            batch = texts[i:i + batch_size]

            # Calculate metrics
            total_tokens = sum(count_tokens(text, self.model) for text in batch)
            metrics = BatchMetrics(
                batch_size=len(batch),
                total_tokens=total_tokens,
                avg_tokens=total_tokens / len(batch) if batch else 0,
            )
            self._recent_metrics.append(metrics)

            yield batch
            i += batch_size

    def _estimate_batch_size(self, sample_texts: List[str]) -> int:
        """Estimate optimal batch size based on sample texts.

        Args:
            sample_texts: Sample of upcoming texts (up to 100)

        Returns:
            Estimated optimal batch size
        """
        if not sample_texts:
            return self.min_batch_size

        # Sample first few texts to estimate average token count
        sample_size = min(10, len(sample_texts))
        sample = sample_texts[:sample_size]

        # Count tokens in sample
        token_counts = [count_tokens(text, self.model) for text in sample]
        avg_tokens = sum(token_counts) / len(token_counts) if token_counts else 400

        # Estimate batch size to hit target tokens
        if avg_tokens > 0:
            estimated_size = int(self.target_tokens / avg_tokens)
        else:
            estimated_size = self.max_batch_size

        # Apply constraints
        estimated_size = max(self.min_batch_size, min(estimated_size, self.max_batch_size))

        # Adjust based on recent performance
        if self._recent_metrics:
            recent_avg = sum(m.avg_tokens for m in self._recent_metrics) / len(self._recent_metrics)
            if recent_avg > 0:
                adjusted_size = int(self.target_tokens / recent_avg)
                # Blend estimate with adjusted size
                estimated_size = int(0.7 * estimated_size + 0.3 * adjusted_size)

        return max(self.min_batch_size, min(estimated_size, self.max_batch_size))

    def record_batch_time(self, batch_size: int, processing_time: float) -> None:
        """Record processing time for a batch.

        Args:
            batch_size: Size of the processed batch
            processing_time: Time taken to process batch (seconds)
        """
        # Update most recent batch with timing info
        if self._recent_metrics and self._recent_metrics[-1].batch_size == batch_size:
            metrics = self._recent_metrics[-1]
            metrics.processing_time = processing_time

    def get_stats(self) -> dict:
        """Get statistics about recent batches.

        Returns:
            Dictionary with batch statistics
        """
        if not self._recent_metrics:
            return {
                'batches_processed': 0,
                'avg_batch_size': 0,
                'avg_tokens_per_batch': 0,
                'avg_processing_time': 0,
            }

        avg_batch_size = sum(m.batch_size for m in self._recent_metrics) / len(self._recent_metrics)
        avg_tokens = sum(m.total_tokens for m in self._recent_metrics) / len(self._recent_metrics)

        times = [m.processing_time for m in self._recent_metrics if m.processing_time]
        avg_time = sum(times) / len(times) if times else 0

        return {
            'batches_processed': len(self._recent_metrics),
            'avg_batch_size': avg_batch_size,
            'avg_tokens_per_batch': avg_tokens,
            'avg_processing_time': avg_time,
        }


def create_adaptive_batches(
    texts: List[str],
    model: str = "small",
    target_tokens: int = 8000,
    min_batch_size: int = 10,
    max_batch_size: int = 500,
) -> List[List[str]]:
    """Create adaptively-sized batches from texts (convenience function).

    Args:
        texts: List of texts to batch
        model: Embedding model name
        target_tokens: Target tokens per batch
        min_batch_size: Minimum batch size
        max_batch_size: Maximum batch size

    Returns:
        List of batches
    """
    batcher = AdaptiveBatcher(
        target_tokens=target_tokens,
        min_batch_size=min_batch_size,
        max_batch_size=max_batch_size,
        model=model,
    )

    return list(batcher.create_batches(texts))
