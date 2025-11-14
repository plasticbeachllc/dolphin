"""Unit tests for adaptive batching."""

import pytest

from kb.embeddings.adaptive_batching import (
    AdaptiveBatcher,
    create_adaptive_batches,
)


class TestAdaptiveBatcher:
    """Unit tests for AdaptiveBatcher class."""

    def test_create_empty_batches(self):
        """Test creating batches from empty input."""
        batcher = AdaptiveBatcher()
        batches = list(batcher.create_batches([]))
        assert batches == []

    def test_single_text_batch(self):
        """Test batching a single text."""
        batcher = AdaptiveBatcher(min_batch_size=1, max_batch_size=10)
        batches = list(batcher.create_batches(["test text"]))

        assert len(batches) == 1
        assert batches[0] == ["test text"]

    def test_respects_min_batch_size(self):
        """Test that minimum batch size is respected."""
        texts = ["text"] * 5

        batcher = AdaptiveBatcher(
            min_batch_size=3,
            max_batch_size=10,
            target_tokens=10000,
        )

        batches = list(batcher.create_batches(texts))

        # All batches except possibly the last should be >= min_batch_size
        for batch in batches[:-1]:
            assert len(batch) >= 3

    def test_respects_max_batch_size(self):
        """Test that maximum batch size is respected."""
        texts = ["text"] * 100

        batcher = AdaptiveBatcher(
            min_batch_size=1,
            max_batch_size=20,
            target_tokens=100000,  # Very high to test max constraint
        )

        batches = list(batcher.create_batches(texts))

        # No batch should exceed max_batch_size
        for batch in batches:
            assert len(batch) <= 20

    def test_all_texts_included(self):
        """Test that all texts are included in batches."""
        texts = ["text"] * 47  # Odd number to test edge cases

        batcher = AdaptiveBatcher(min_batch_size=5, max_batch_size=15)
        batches = list(batcher.create_batches(texts))

        total_texts = sum(len(batch) for batch in batches)
        assert total_texts == len(texts)

    def test_batch_size_estimation(self):
        """Test batch size estimation based on token count."""
        # Create texts of known size
        short_texts = ["a"] * 100  # Very short
        long_texts = ["word " * 200] * 100  # Long

        short_batcher = AdaptiveBatcher(target_tokens=1000)
        short_batches = list(short_batcher.create_batches(short_texts))

        long_batcher = AdaptiveBatcher(target_tokens=1000)
        long_batches = list(long_batcher.create_batches(long_texts))

        # Short texts should produce larger batches
        # Long texts should produce smaller batches
        avg_short_batch_size = sum(len(b) for b in short_batches) / len(short_batches)
        avg_long_batch_size = sum(len(b) for b in long_batches) / len(long_batches)

        # This is a rough heuristic - exact values depend on tokenizer
        assert avg_short_batch_size > avg_long_batch_size

    def test_recent_metrics_tracking(self):
        """Test that recent metrics are tracked."""
        batcher = AdaptiveBatcher()
        texts = ["text"] * 50

        batches = list(batcher.create_batches(texts))

        # Should have metrics for created batches
        assert len(batcher._recent_metrics) > 0
        assert len(batcher._recent_metrics) <= 10  # maxlen=10

    def test_get_stats(self):
        """Test statistics retrieval."""
        batcher = AdaptiveBatcher()
        texts = ["text"] * 30

        # Before batching
        stats = batcher.get_stats()
        assert stats["batches_processed"] == 0

        # After batching
        batches = list(batcher.create_batches(texts))
        stats = batcher.get_stats()

        assert stats["batches_processed"] > 0
        assert stats["avg_batch_size"] > 0
        assert stats["avg_tokens_per_batch"] > 0

    def test_record_batch_time(self):
        """Test recording batch processing time."""
        batcher = AdaptiveBatcher()
        texts = ["text"] * 20

        batches = list(batcher.create_batches(texts))
        first_batch_size = len(batches[0])

        # Record time for first batch
        batcher.record_batch_time(first_batch_size, 1.5)

        stats = batcher.get_stats()
        # Should have processing time recorded
        assert "avg_processing_time" in stats


class TestCreateAdaptiveBatches:
    """Unit tests for create_adaptive_batches convenience function."""

    def test_convenience_function(self):
        """Test that convenience function works."""
        texts = ["text"] * 50

        batches = create_adaptive_batches(
            texts,
            model="small",
            target_tokens=5000,
            min_batch_size=5,
            max_batch_size=25,
        )

        # Should create batches
        assert len(batches) > 0

        # All texts should be included
        total = sum(len(b) for b in batches)
        assert total == len(texts)

        # Should respect constraints
        for batch in batches:
            assert len(batch) <= 25

    def test_different_models(self):
        """Test batching with different models."""
        texts = ["test text"] * 20

        small_batches = create_adaptive_batches(texts, model="small")
        large_batches = create_adaptive_batches(texts, model="large")

        # Both should work
        assert len(small_batches) > 0
        assert len(large_batches) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
