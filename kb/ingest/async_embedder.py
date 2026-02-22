"""Async embedding queue and rate limiting.

This module provides a concurrent dispatcher for embedding requests with
adaptive rate limiting to handle API constraints.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from ..embeddings.provider import embed_texts_with_retry

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingBatch:
    """A batch of texts to start embedding."""

    texts: list[str]
    metadata: dict[str, Any]  # Pass-through metadata (e.g. file_id, chunk info)
    future: asyncio.Future  # Future to set result on


class RateLimitedEmbedder:
    """Async embedder with adaptive rate limiting."""

    def __init__(
        self,
        provider_model: str = "small",
        initial_rpm: int = 3000,
        initial_tpm: int = 200_000,
        max_concurrent: int = 10,
    ):
        """Initialize rate limited embedder.

        Args:
            provider_model: Embedding model name
            initial_rpm: Initial Requests Per Minute limit
            initial_tpm: Initial Tokens Per Minute limit
            max_concurrent: Maximum concurrent in-flight requests
        """
        self.model = provider_model

        # Limits
        self.rpm_limit = initial_rpm
        self.tpm_limit = initial_tpm
        self.max_concurrent = max_concurrent

        # State
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.last_request_time = 0.0
        # Bounded deques prevent unbounded growth; maxlen caps at the RPM limit so
        # the oldest entries are evicted automatically if pruning ever falls behind.
        self.request_times: deque[float] = deque(maxlen=initial_rpm)  # Rolling window for RPM
        self.token_usage: deque[tuple[float, float]] = deque(maxlen=initial_rpm)  # Rolling window for TPM
        self.backoff_until = 0.0

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts respecting rate limits."""
        if not texts:
            return []

        # Estimate token count (rough heuristic: 1 word ~ 1.3 tokens)
        est_tokens = sum(len(t.split()) * 1.3 for t in texts)

        async with self.semaphore:
            # Check backoff
            now = time.time()
            if now < self.backoff_until:
                wait_time = self.backoff_until - now
                logger.warning(f"Rate limited, backing off for {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

            # Enforce RPM/TPM
            await self._enforce_limits(est_tokens)

            try:
                # We use the existing retry logic but run it in a thread executor
                # since the underlying provider might be sync-blocking or
                # we want to ensure we don't block the event loop.
                # Currently embed_texts_with_retry wraps embed_texts which is sync in base,
                # but providers may implement async.
                # For safety, run in executor.
                loop = asyncio.get_running_loop()

                # Note: `embed_texts_with_retry` is our robust entry point
                vectors = await loop.run_in_executor(None, embed_texts_with_retry, self.model, texts)

                # Record usage
                self._record_usage(est_tokens)
                return vectors

            except Exception as e:
                # If we hit a rate limit error that wasn't caught by retry logic
                if "429" in str(e) or "Rate limit" in str(e):
                    self._trigger_backoff()
                    # Raising to caller allows them to decide (retry or fail)
                    # But ideally the retry wrapper handles this.
                    # If it bubbles up, it's a hard failure after retries.
                    pass
                raise e

    async def _enforce_limits(self, tokens: float):
        """Sleep if limits are exceeded."""
        while True:
            now = time.time()

            # Evict entries older than the 1-minute rolling window from the left
            # (deques are ordered oldest-first since entries are appended on the right).
            while self.request_times and now - self.request_times[0] >= 60:
                self.request_times.popleft()
            while self.token_usage and now - self.token_usage[0][0] >= 60:
                self.token_usage.popleft()

            current_rpm = len(self.request_times)
            current_tpm = sum(k for _, k in self.token_usage)

            if current_rpm < self.rpm_limit and current_tpm + tokens < self.tpm_limit:
                break

            # Wait a bit
            await asyncio.sleep(0.5)

    def _record_usage(self, tokens: float):
        now = time.time()
        self.request_times.append(now)
        self.token_usage.append((now, tokens))

    def _trigger_backoff(self):
        """Trigger adaptive backoff."""
        self.backoff_until = time.time() + 10.0  # 10s cooldown
        # Reduce limits temporarily
        self.rpm_limit = max(1, int(self.rpm_limit * 0.5))
        logger.info(f"Rate limit hit. Reducing RPM to {self.rpm_limit}")


class EmbeddingQueue:
    """Async queue for buffering and dispatching embedding jobs."""

    def __init__(self, embedder: RateLimitedEmbedder, batch_size: int = 100):
        self.embedder = embedder
        self.batch_size = batch_size
        self.queue: asyncio.Queue[EmbeddingBatch] = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        self._shutdown = False

    def start(self, num_workers: int = 3):
        """Start background workers."""
        for _ in range(num_workers):
            self.workers.append(asyncio.create_task(self._worker_loop()))

    async def stop(self):
        """Stop workers and wait for queue to drain."""
        self._shutdown = True
        await self.queue.join()
        for w in self.workers:
            w.cancel()
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)

    async def submit(self, texts: list[str], metadata: dict[str, Any]) -> list[list[float]]:
        """Submit texts for embedding and wait for result."""
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        batch = EmbeddingBatch(texts, metadata, future)
        await self.queue.put(batch)

        return await future

    async def _worker_loop(self):
        """Worker loop to process queue."""
        while True:
            batch = await self.queue.get()
            try:
                vectors = await self.embedder.embed_batch(batch.texts)
                if not batch.future.done():
                    batch.future.set_result(vectors)
            except Exception as e:
                if not batch.future.done():
                    batch.future.set_exception(e)
            finally:
                self.queue.task_done()
