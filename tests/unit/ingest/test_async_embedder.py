"""Unit tests for kb.ingest.async_embedder module.

Tests the async embedding queue and rate-limited embedder:
- RateLimitedEmbedder RPM/TPM enforcement
- Backoff logic on rate-limit errors
- EmbeddingQueue worker pool processing
- Batch dispatching and future resolution
- Error handling and retry behavior
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from kb.ingest.async_embedder import EmbeddingBatch, EmbeddingQueue, RateLimitedEmbedder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_vectors(texts: list[str]) -> list[list[float]]:
    """Return deterministic fake embeddings (one per text)."""
    return [[float(i)] * 8 for i in range(len(texts))]


# ---------------------------------------------------------------------------
# RateLimitedEmbedder — initialisation
# ---------------------------------------------------------------------------


class TestRateLimitedEmbedderInit:
    """Test RateLimitedEmbedder construction and defaults."""

    def test_default_limits(self):
        embedder = RateLimitedEmbedder()
        assert embedder.rpm_limit == 3000
        assert embedder.tpm_limit == 200_000
        assert embedder.max_concurrent == 10
        assert embedder.model == "small"

    def test_custom_limits(self):
        embedder = RateLimitedEmbedder(
            provider_model="large",
            initial_rpm=100,
            initial_tpm=50_000,
            max_concurrent=5,
        )
        assert embedder.rpm_limit == 100
        assert embedder.tpm_limit == 50_000
        assert embedder.max_concurrent == 5
        assert embedder.model == "large"

    def test_empty_rolling_windows(self):
        embedder = RateLimitedEmbedder()
        assert len(embedder.request_times) == 0
        assert len(embedder.token_usage) == 0
        assert embedder.backoff_until == 0.0


# ---------------------------------------------------------------------------
# RateLimitedEmbedder — embed_batch
# ---------------------------------------------------------------------------


class TestRateLimitedEmbedderEmbedBatch:
    """Test embed_batch behaviour with mocked provider."""

    @pytest.mark.asyncio
    async def test_embed_batch_empty_returns_empty(self):
        """Passing an empty list should return [] immediately."""
        embedder = RateLimitedEmbedder()
        result = await embedder.embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=100)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_embed_batch_returns_vectors(self, mock_embed, mock_tokens):
        """embed_batch should return vectors from the underlying provider."""
        embedder = RateLimitedEmbedder()
        texts = ["hello", "world"]
        result = await embedder.embed_batch(texts)

        assert len(result) == 2
        assert result[0] == [0.0] * 8
        assert result[1] == [1.0] * 8

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=50)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_embed_batch_records_usage(self, mock_embed, mock_tokens):
        """After a successful call, RPM and TPM rolling windows are updated."""
        embedder = RateLimitedEmbedder()
        await embedder.embed_batch(["a"])

        assert len(embedder.request_times) == 1
        assert len(embedder.token_usage) == 1
        # Token count stored should match the estimate
        _, recorded_tokens = embedder.token_usage[0]
        assert recorded_tokens == 50

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_embed_batch_respects_semaphore(self, mock_embed, mock_tokens):
        """Concurrent calls should be limited by max_concurrent."""
        max_conc = 2
        embedder = RateLimitedEmbedder(max_concurrent=max_conc)

        active = 0
        peak_active = 0

        original_embed = mock_embed.side_effect

        def tracking_embed(model, texts):
            nonlocal active, peak_active
            active += 1
            peak_active = max(peak_active, active)
            result = original_embed(model, texts)
            active -= 1
            return result

        mock_embed.side_effect = tracking_embed

        tasks = [embedder.embed_batch([f"text {i}"]) for i in range(6)]
        await asyncio.gather(*tasks)

        assert peak_active <= max_conc


# ---------------------------------------------------------------------------
# RateLimitedEmbedder — RPM/TPM enforcement
# ---------------------------------------------------------------------------


class TestRateLimitedEmbedderRateLimits:
    """Test that RPM and TPM limits are enforced."""

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_rpm_limit_tracked(self, mock_embed, mock_tokens):
        """After N requests within 60s, request_times contains N entries."""
        embedder = RateLimitedEmbedder(initial_rpm=5000)
        for _ in range(5):
            await embedder.embed_batch(["a"])
        assert len(embedder.request_times) == 5

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=100)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_tpm_accumulates(self, mock_embed, mock_tokens):
        """Token usage should accumulate across calls."""
        embedder = RateLimitedEmbedder(initial_tpm=500_000)
        for _ in range(3):
            await embedder.embed_batch(["a"])
        total_tokens = sum(k for _, k in embedder.token_usage)
        assert total_tokens == 300  # 3 * 100

    @pytest.mark.asyncio
    async def test_enforce_limits_passes_when_under(self):
        """_enforce_limits returns immediately when under limits."""
        embedder = RateLimitedEmbedder(initial_rpm=100, initial_tpm=100_000)
        # No requests recorded, should return immediately
        start = time.monotonic()
        await embedder._enforce_limits(50)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_enforce_limits_waits_when_rpm_exceeded(self):
        """_enforce_limits should sleep when RPM is at the limit."""
        embedder = RateLimitedEmbedder(initial_rpm=2, initial_tpm=100_000)
        now = time.time()
        # Simulate 2 recent requests (at the limit)
        embedder.request_times.extend([now, now])

        # Patch asyncio.sleep so we don't actually wait
        with patch("kb.ingest.async_embedder.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # After the first sleep call, clear the request_times to break the loop
            async def clear_and_sleep(seconds):
                embedder.request_times.clear()

            mock_sleep.side_effect = clear_and_sleep
            await embedder._enforce_limits(10)
            mock_sleep.assert_called_once_with(0.5)

    @pytest.mark.asyncio
    async def test_enforce_limits_waits_when_tpm_exceeded(self):
        """_enforce_limits should sleep when TPM is at the limit."""
        embedder = RateLimitedEmbedder(initial_rpm=10000, initial_tpm=100)
        now = time.time()
        # Simulate token usage that fills the limit
        embedder.token_usage.extend([(now, 90)])

        with patch("kb.ingest.async_embedder.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:

            async def clear_and_sleep(seconds):
                embedder.token_usage.clear()

            mock_sleep.side_effect = clear_and_sleep
            # Requesting 20 tokens: 90 + 20 = 110 > 100 limit
            await embedder._enforce_limits(20)
            mock_sleep.assert_called_once_with(0.5)

    @pytest.mark.asyncio
    async def test_enforce_limits_evicts_old_entries(self):
        """Entries older than 60 seconds should be evicted."""
        embedder = RateLimitedEmbedder(initial_rpm=2, initial_tpm=100_000)
        old_time = time.time() - 61  # More than 60 seconds ago
        embedder.request_times.extend([old_time, old_time])
        embedder.token_usage.extend([(old_time, 50), (old_time, 50)])

        # Should pass immediately because old entries are pruned
        start = time.monotonic()
        await embedder._enforce_limits(10)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1
        # Old entries should have been evicted
        assert len(embedder.request_times) == 0
        assert len(embedder.token_usage) == 0


# ---------------------------------------------------------------------------
# RateLimitedEmbedder — backoff logic
# ---------------------------------------------------------------------------


class TestRateLimitedEmbedderBackoff:
    """Test backoff trigger and adaptive limit reduction."""

    def test_trigger_backoff_sets_future_time(self):
        """_trigger_backoff should set backoff_until to ~10s in the future."""
        embedder = RateLimitedEmbedder(initial_rpm=100)
        before = time.time()
        embedder._trigger_backoff()
        after = time.time()

        assert embedder.backoff_until >= before + 9.0
        assert embedder.backoff_until <= after + 11.0

    def test_trigger_backoff_halves_rpm(self):
        """_trigger_backoff should reduce RPM limit by 50%."""
        embedder = RateLimitedEmbedder(initial_rpm=100)
        embedder._trigger_backoff()
        assert embedder.rpm_limit == 50

    def test_trigger_backoff_minimum_rpm(self):
        """RPM limit should not go below 1."""
        embedder = RateLimitedEmbedder(initial_rpm=1)
        embedder._trigger_backoff()
        assert embedder.rpm_limit >= 1

    def test_repeated_backoff_reduces_progressively(self):
        """Multiple backoffs should keep halving."""
        embedder = RateLimitedEmbedder(initial_rpm=200)
        embedder._trigger_backoff()
        assert embedder.rpm_limit == 100
        embedder._trigger_backoff()
        assert embedder.rpm_limit == 50
        embedder._trigger_backoff()
        assert embedder.rpm_limit == 25

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=Exception("429 Too Many Requests"))
    async def test_rate_limit_error_triggers_backoff(self, mock_embed, mock_tokens):
        """A 429-like error should trigger backoff and re-raise."""
        embedder = RateLimitedEmbedder(initial_rpm=100)
        original_rpm = embedder.rpm_limit

        with pytest.raises(Exception, match="429"):
            await embedder.embed_batch(["hello"])

        assert embedder.rpm_limit < original_rpm
        assert embedder.backoff_until > time.time()

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=Exception("Rate limit exceeded"))
    async def test_rate_limit_string_triggers_backoff(self, mock_embed, mock_tokens):
        """An error containing 'Rate limit' should also trigger backoff."""
        embedder = RateLimitedEmbedder(initial_rpm=100)

        with pytest.raises(Exception, match="Rate limit"):
            await embedder.embed_batch(["hello"])

        assert embedder.rpm_limit == 50

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=ValueError("something else"))
    async def test_non_rate_limit_error_does_not_trigger_backoff(self, mock_embed, mock_tokens):
        """Non-rate-limit errors should not trigger backoff."""
        embedder = RateLimitedEmbedder(initial_rpm=100)

        with pytest.raises(ValueError, match="something else"):
            await embedder.embed_batch(["hello"])

        assert embedder.rpm_limit == 100
        assert embedder.backoff_until == 0.0

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_backoff_delays_next_request(self, mock_embed, mock_tokens):
        """When backoff is active, embed_batch should wait before proceeding."""
        embedder = RateLimitedEmbedder()
        embedder.backoff_until = time.time() + 5.0  # 5 seconds from now

        with patch("kb.ingest.async_embedder.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await embedder.embed_batch(["hello"])
            # Should have slept for approximately 5 seconds
            mock_sleep.assert_called_once()
            sleep_time = mock_sleep.call_args[0][0]
            assert 4.0 <= sleep_time <= 6.0


# ---------------------------------------------------------------------------
# RateLimitedEmbedder — _record_usage
# ---------------------------------------------------------------------------


class TestRateLimitedEmbedderRecordUsage:
    """Test usage recording."""

    def test_record_usage_appends(self):
        embedder = RateLimitedEmbedder()
        embedder._record_usage(42)
        assert len(embedder.request_times) == 1
        assert len(embedder.token_usage) == 1
        _, tokens = embedder.token_usage[0]
        assert tokens == 42

    def test_record_usage_multiple(self):
        embedder = RateLimitedEmbedder()
        embedder._record_usage(10)
        embedder._record_usage(20)
        embedder._record_usage(30)
        assert len(embedder.request_times) == 3
        total = sum(k for _, k in embedder.token_usage)
        assert total == 60


# ---------------------------------------------------------------------------
# EmbeddingBatch dataclass
# ---------------------------------------------------------------------------


class TestEmbeddingBatch:
    """Test the EmbeddingBatch dataclass."""

    def test_batch_creation(self):
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        batch = EmbeddingBatch(texts=["a", "b"], metadata={"file_id": 1}, future=future)
        assert batch.texts == ["a", "b"]
        assert batch.metadata == {"file_id": 1}
        assert batch.future is future
        loop.close()


# ---------------------------------------------------------------------------
# EmbeddingQueue — worker pool
# ---------------------------------------------------------------------------


class TestEmbeddingQueueWorkerPool:
    """Test EmbeddingQueue worker management."""

    @pytest.mark.asyncio
    async def test_start_creates_workers(self):
        """start() should create the requested number of worker tasks."""
        embedder = RateLimitedEmbedder()
        queue = EmbeddingQueue(embedder, batch_size=10)
        queue.start(num_workers=4)

        assert len(queue.workers) == 4
        assert all(isinstance(w, asyncio.Task) for w in queue.workers)

        await queue.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_workers(self):
        """stop() should cancel all worker tasks."""
        embedder = RateLimitedEmbedder()
        queue = EmbeddingQueue(embedder, batch_size=10)
        queue.start(num_workers=2)

        await queue.stop()
        assert queue._shutdown is True
        for w in queue.workers:
            assert w.cancelled() or w.done()

    @pytest.mark.asyncio
    async def test_default_batch_size(self):
        embedder = RateLimitedEmbedder()
        queue = EmbeddingQueue(embedder)
        assert queue.batch_size == 100


# ---------------------------------------------------------------------------
# EmbeddingQueue — submit and processing
# ---------------------------------------------------------------------------


class TestEmbeddingQueueSubmit:
    """Test submitting work to the EmbeddingQueue."""

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_submit_returns_vectors(self, mock_embed, mock_tokens):
        """submit() should return embeddings via the future."""
        embedder = RateLimitedEmbedder()
        queue = EmbeddingQueue(embedder, batch_size=50)
        queue.start(num_workers=1)

        try:
            result = await asyncio.wait_for(
                queue.submit(["hello", "world"], metadata={"file_id": 42}),
                timeout=5.0,
            )
            assert len(result) == 2
            assert result[0] == [0.0] * 8
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_submit_multiple_batches(self, mock_embed, mock_tokens):
        """Multiple submit() calls should all resolve correctly."""
        embedder = RateLimitedEmbedder()
        queue = EmbeddingQueue(embedder, batch_size=50)
        queue.start(num_workers=2)

        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    queue.submit(["a"], metadata={"id": 1}),
                    queue.submit(["b", "c"], metadata={"id": 2}),
                    queue.submit(["d", "e", "f"], metadata={"id": 3}),
                ),
                timeout=5.0,
            )
            assert len(results) == 3
            assert len(results[0]) == 1
            assert len(results[1]) == 2
            assert len(results[2]) == 3
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=RuntimeError("API down"))
    async def test_submit_propagates_error(self, mock_embed, mock_tokens):
        """Errors in the embedder should propagate to the caller via the future."""
        embedder = RateLimitedEmbedder()
        queue = EmbeddingQueue(embedder, batch_size=50)
        queue.start(num_workers=1)

        try:
            with pytest.raises(RuntimeError, match="API down"):
                await asyncio.wait_for(
                    queue.submit(["hello"], metadata={}),
                    timeout=5.0,
                )
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_submit_metadata_passthrough(self, mock_embed, mock_tokens):
        """Metadata should be stored on the batch (pass-through for caller use)."""
        embedder = RateLimitedEmbedder()
        queue = EmbeddingQueue(embedder, batch_size=50)

        # Intercept the worker to inspect the batch
        batches_seen: list[EmbeddingBatch] = []

        async def tracking_worker():
            while True:
                batch = await queue.queue.get()
                batches_seen.append(batch)
                try:
                    vectors = await embedder.embed_batch(batch.texts)
                    if not batch.future.done():
                        batch.future.set_result(vectors)
                except Exception as e:
                    if not batch.future.done():
                        batch.future.set_exception(e)
                finally:
                    queue.queue.task_done()

        queue.workers.append(asyncio.create_task(tracking_worker()))

        try:
            await asyncio.wait_for(
                queue.submit(["text"], metadata={"file_id": 99, "chunk": "abc"}),
                timeout=5.0,
            )
            assert len(batches_seen) == 1
            assert batches_seen[0].metadata == {"file_id": 99, "chunk": "abc"}
        finally:
            await queue.stop()


# ---------------------------------------------------------------------------
# EmbeddingQueue — error handling
# ---------------------------------------------------------------------------


class TestEmbeddingQueueErrorHandling:
    """Test error handling within the queue worker loop."""

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    async def test_worker_continues_after_error(self, mock_tokens):
        """A worker should keep processing after one batch fails."""
        call_count = 0

        def embed_side_effect(model, texts):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")
            return _make_fake_vectors(texts)

        with patch(
            "kb.ingest.async_embedder.embed_texts_with_retry",
            side_effect=embed_side_effect,
        ):
            embedder = RateLimitedEmbedder()
            queue = EmbeddingQueue(embedder, batch_size=50)
            queue.start(num_workers=1)

            try:
                # First submission should fail
                with pytest.raises(RuntimeError, match="transient failure"):
                    await asyncio.wait_for(
                        queue.submit(["fail"], metadata={}),
                        timeout=5.0,
                    )

                # Second submission should succeed (worker is still alive)
                result = await asyncio.wait_for(
                    queue.submit(["succeed"], metadata={}),
                    timeout=5.0,
                )
                assert len(result) == 1
            finally:
                await queue.stop()

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_task_done_called_on_success(self, mock_embed, mock_tokens):
        """queue.task_done() should be called after successful processing."""
        embedder = RateLimitedEmbedder()
        queue = EmbeddingQueue(embedder, batch_size=50)
        queue.start(num_workers=1)

        try:
            await asyncio.wait_for(
                queue.submit(["hello"], metadata={}),
                timeout=5.0,
            )
            # If task_done was not called, queue.join() would hang
            await asyncio.wait_for(queue.queue.join(), timeout=2.0)
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=RuntimeError("boom"))
    async def test_task_done_called_on_error(self, mock_embed, mock_tokens):
        """queue.task_done() should be called even when processing fails."""
        embedder = RateLimitedEmbedder()
        queue = EmbeddingQueue(embedder, batch_size=50)
        queue.start(num_workers=1)

        try:
            with pytest.raises(RuntimeError, match="boom"):
                await asyncio.wait_for(
                    queue.submit(["hello"], metadata={}),
                    timeout=5.0,
                )
            # If task_done was not called on error, this would hang
            await asyncio.wait_for(queue.queue.join(), timeout=2.0)
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=10)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_future_not_set_twice(self, mock_embed, mock_tokens):
        """Worker should not set result on an already-done future."""
        embedder = RateLimitedEmbedder()
        queue = EmbeddingQueue(embedder, batch_size=50)

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        # Pre-set the future to simulate a race condition
        future.set_result([[0.0]])

        batch = EmbeddingBatch(texts=["a"], metadata={}, future=future)
        await queue.queue.put(batch)

        queue.start(num_workers=1)
        try:
            await asyncio.wait_for(queue.queue.join(), timeout=5.0)
            # Future should still have the original result, not overwritten
            assert future.result() == [[0.0]]
        finally:
            await queue.stop()


# ---------------------------------------------------------------------------
# Integration-style: RateLimitedEmbedder + EmbeddingQueue together
# ---------------------------------------------------------------------------


class TestEmbedderQueueIntegration:
    """Test RateLimitedEmbedder and EmbeddingQueue working together."""

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=5)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_concurrent_submissions(self, mock_embed, mock_tokens):
        """Multiple concurrent submissions through the queue should all resolve."""
        embedder = RateLimitedEmbedder(max_concurrent=3)
        queue = EmbeddingQueue(embedder, batch_size=50)
        queue.start(num_workers=3)

        try:
            tasks = [queue.submit([f"text_{i}"], metadata={"idx": i}) for i in range(10)]
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10.0)

            assert len(results) == 10
            for r in results:
                assert len(r) == 1
        finally:
            await queue.stop()

    @pytest.mark.asyncio
    @patch("kb.ingest.async_embedder.estimate_tokens_batch", return_value=5)
    @patch("kb.ingest.async_embedder.embed_texts_with_retry", side_effect=lambda m, t: _make_fake_vectors(t))
    async def test_queue_drains_before_stop(self, mock_embed, mock_tokens):
        """stop() should wait for the queue to drain before cancelling workers."""
        embedder = RateLimitedEmbedder()
        queue = EmbeddingQueue(embedder, batch_size=50)
        queue.start(num_workers=2)

        futures = []
        for i in range(5):
            f = queue.submit([f"item_{i}"], metadata={})
            futures.append(f)

        results = await asyncio.wait_for(asyncio.gather(*futures), timeout=10.0)
        assert len(results) == 5

        await queue.stop()
        assert queue.queue.empty()
