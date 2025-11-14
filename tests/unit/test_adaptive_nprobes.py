"""Unit tests for adaptive nprobes tuning."""

import pytest

from kb.retrieval.ann_tuning import ANNParams
from kb.search.adaptive_nprobes import (
    AdaptiveNProbes,
    AdaptiveState,
    GlobalAdaptiveNProbes,
    SearchMetrics,
    get_adaptive_params,
    record_search_performance,
)


class TestSearchMetrics:
    """Unit tests for SearchMetrics dataclass."""

    def test_metrics_creation(self):
        """Test creating search metrics."""
        metrics = SearchMetrics(
            query_id="q1",
            latency_ms=50.0,
            nprobes=20,
            refine_factor=10,
            result_count=10,
        )

        assert metrics.query_id == "q1"
        assert metrics.latency_ms == 50.0
        assert metrics.nprobes == 20
        assert metrics.refine_factor == 10
        assert metrics.result_count == 10

    def test_metrics_with_quality_score(self):
        """Test metrics with quality score."""
        metrics = SearchMetrics(
            query_id="q1",
            latency_ms=50.0,
            nprobes=20,
            refine_factor=10,
            result_count=10,
            quality_score=0.95,
        )

        assert metrics.quality_score == 0.95

    def test_metrics_timestamp(self):
        """Test that timestamp is set automatically."""
        metrics = SearchMetrics(
            query_id="q1",
            latency_ms=50.0,
            nprobes=20,
            refine_factor=10,
            result_count=10,
        )

        assert metrics.timestamp > 0


class TestAdaptiveNProbes:
    """Unit tests for AdaptiveNProbes class."""

    def test_initialization(self):
        """Test adaptive tuner initialization."""
        tuner = AdaptiveNProbes(
            target_latency_ms=150.0,
            min_nprobes=5,
            max_nprobes=50,
            initial_nprobes=20,
        )

        assert tuner.target_latency_ms == 150.0
        assert tuner.min_nprobes == 5
        assert tuner.max_nprobes == 50
        assert tuner.current_nprobes == 20

    def test_get_params_default(self):
        """Test getting default ANN parameters."""
        tuner = AdaptiveNProbes(initial_nprobes=20)

        params = tuner.get_params()

        assert isinstance(params, ANNParams)
        assert params.nprobes == 20
        assert params.metric == "cosine"

    def test_get_params_identifier_query(self):
        """Test parameter adjustment for identifier queries."""
        tuner = AdaptiveNProbes(initial_nprobes=20, max_nprobes=50)

        params = tuner.get_params(query_type="identifier")

        # Should boost nprobes for identifier queries
        assert params.nprobes > 20

    def test_get_params_small_top_k(self):
        """Test parameter adjustment for small result sets."""
        tuner = AdaptiveNProbes(initial_nprobes=20, max_nprobes=50)

        params = tuner.get_params(top_k=3)

        # Should increase nprobes for small result sets
        assert params.nprobes >= 20

    def test_record_search_basic(self):
        """Test recording search metrics."""
        tuner = AdaptiveNProbes()

        tuner.record_search(
            query_id="q1",
            latency_ms=100.0,
            result_count=10,
        )

        stats = tuner.get_stats()
        assert stats["total_queries"] == 1
        assert stats["avg_latency_ms"] == 100.0

    def test_record_multiple_searches(self):
        """Test recording multiple searches."""
        tuner = AdaptiveNProbes()

        for i in range(5):
            tuner.record_search(
                query_id=f"q{i}",
                latency_ms=100.0 + i * 10,
                result_count=10,
            )

        stats = tuner.get_stats()
        assert stats["total_queries"] == 5
        assert stats["avg_latency_ms"] > 100.0

    def test_adjustment_high_latency(self):
        """Test automatic adjustment when latency is too high."""
        tuner = AdaptiveNProbes(
            target_latency_ms=100.0,
            initial_nprobes=30,
            adjustment_cooldown=0.0,  # No cooldown for testing
        )

        initial_nprobes = tuner.current_nprobes

        # Record many high-latency searches
        for i in range(15):
            tuner.record_search(
                query_id=f"q{i}",
                latency_ms=200.0,  # Above target
                result_count=10,
            )

        # Should have decreased nprobes
        assert tuner.current_nprobes < initial_nprobes

    def test_adjustment_low_latency(self):
        """Test automatic adjustment when latency is too low."""
        tuner = AdaptiveNProbes(
            target_latency_ms=150.0,
            initial_nprobes=10,
            max_nprobes=50,
            adjustment_cooldown=0.0,  # No cooldown for testing
        )

        initial_nprobes = tuner.current_nprobes

        # Record many low-latency searches
        for i in range(15):
            tuner.record_search(
                query_id=f"q{i}",
                latency_ms=50.0,  # Well below target
                result_count=10,
            )

        # Should have increased nprobes
        assert tuner.current_nprobes > initial_nprobes

    def test_adjustment_respects_min_max(self):
        """Test that adjustments respect min/max bounds."""
        tuner = AdaptiveNProbes(
            target_latency_ms=100.0,
            min_nprobes=5,
            max_nprobes=50,
            initial_nprobes=5,
            adjustment_cooldown=0.0,
        )

        # Try to force adjustment below min
        for i in range(20):
            tuner.record_search(
                query_id=f"q{i}",
                latency_ms=300.0,  # Very high
                result_count=10,
            )

        # Should not go below min
        assert tuner.current_nprobes >= tuner.min_nprobes

        # Reset and test max
        tuner.current_nprobes = 50
        for i in range(20):
            tuner.record_search(
                query_id=f"q{i}",
                latency_ms=10.0,  # Very low
                result_count=10,
            )

        # Should not go above max
        assert tuner.current_nprobes <= tuner.max_nprobes

    def test_adjustment_cooldown(self):
        """Test adjustment cooldown period."""
        tuner = AdaptiveNProbes(
            target_latency_ms=100.0,
            initial_nprobes=20,
            adjustment_cooldown=10.0,  # 10 second cooldown
        )

        initial_nprobes = tuner.current_nprobes

        # Record high latency searches
        for i in range(15):
            tuner.record_search(
                query_id=f"q{i}",
                latency_ms=200.0,
                result_count=10,
            )

        first_adjustment = tuner.current_nprobes

        # Should have adjusted once
        assert first_adjustment != initial_nprobes

        # More searches immediately after
        for i in range(15):
            tuner.record_search(
                query_id=f"q{i}_2",
                latency_ms=200.0,
                result_count=10,
            )

        # Should not adjust again due to cooldown
        assert tuner.current_nprobes == first_adjustment

    def test_get_state(self):
        """Test getting current state."""
        tuner = AdaptiveNProbes(
            target_latency_ms=150.0,
            initial_nprobes=20,
        )

        tuner.record_search("q1", 100.0, 10)

        state = tuner.get_state()

        assert isinstance(state, AdaptiveState)
        assert state.current_nprobes == 20
        assert state.target_latency_ms == 150.0
        assert state.avg_latency_ms > 0

    def test_get_stats(self):
        """Test statistics retrieval."""
        tuner = AdaptiveNProbes()

        for i in range(10):
            tuner.record_search(f"q{i}", 100.0 + i * 5, 10)

        stats = tuner.get_stats()

        assert stats["total_queries"] == 10
        assert stats["current_nprobes"] > 0
        assert stats["avg_latency_ms"] > 0
        assert stats["min_latency_ms"] > 0
        assert stats["max_latency_ms"] > 0
        assert stats["p50_latency_ms"] > 0
        assert stats["p95_latency_ms"] > 0
        assert "ema_latency_ms" in stats

    def test_reset(self):
        """Test resetting tuner state."""
        tuner = AdaptiveNProbes(initial_nprobes=20)

        # Record some searches
        for i in range(5):
            tuner.record_search(f"q{i}", 100.0, 10)

        # Modify state
        tuner.current_nprobes = 30

        stats_before = tuner.get_stats()
        assert stats_before["total_queries"] > 0

        # Reset
        tuner.reset()

        stats_after = tuner.get_stats()
        assert stats_after["total_queries"] == 0
        assert tuner.current_nprobes == 20

    def test_estimate_optimal_nprobes(self):
        """Test optimal nprobes estimation."""
        tuner = AdaptiveNProbes(min_nprobes=5, max_nprobes=50)

        # Small dataset
        optimal_small = tuner.estimate_optimal_nprobes(
            dataset_size=10000,
            target_recall=0.95,
        )

        # Large dataset
        optimal_large = tuner.estimate_optimal_nprobes(
            dataset_size=1000000,
            target_recall=0.95,
        )

        # Larger dataset should need more probes
        assert optimal_large > optimal_small

        # Should respect bounds
        assert optimal_small >= tuner.min_nprobes
        assert optimal_large <= tuner.max_nprobes

    def test_estimate_optimal_nprobes_recall_levels(self):
        """Test estimation with different recall targets."""
        tuner = AdaptiveNProbes()

        nprobes_90 = tuner.estimate_optimal_nprobes(100000, target_recall=0.90)
        nprobes_95 = tuner.estimate_optimal_nprobes(100000, target_recall=0.95)
        nprobes_98 = tuner.estimate_optimal_nprobes(100000, target_recall=0.98)

        # Higher recall should require more probes
        assert nprobes_90 < nprobes_95 < nprobes_98

    def test_exponential_moving_average(self):
        """Test that EMA is calculated correctly."""
        tuner = AdaptiveNProbes()

        # Record several searches
        tuner.record_search("q1", 100.0, 10)
        tuner.record_search("q2", 200.0, 10)
        tuner.record_search("q3", 150.0, 10)

        stats = tuner.get_stats()

        # EMA should be somewhere between min and max
        assert (
            stats["min_latency_ms"]
            <= stats["ema_latency_ms"]
            <= stats["max_latency_ms"]
        )


class TestGlobalAdaptiveNProbes:
    """Unit tests for GlobalAdaptiveNProbes singleton."""

    def test_get_instance(self):
        """Test getting global instance."""
        GlobalAdaptiveNProbes.reset_instance()

        instance1 = GlobalAdaptiveNProbes.get_instance()
        instance2 = GlobalAdaptiveNProbes.get_instance()

        # Should return same instance
        assert instance1 is instance2

    def test_reset_instance(self):
        """Test resetting global instance."""
        instance1 = GlobalAdaptiveNProbes.get_instance()

        GlobalAdaptiveNProbes.reset_instance()

        instance2 = GlobalAdaptiveNProbes.get_instance()

        # Should be different instance
        assert instance1 is not instance2

    def test_get_adaptive_params(self):
        """Test convenience function for getting params."""
        GlobalAdaptiveNProbes.reset_instance()

        params = get_adaptive_params(top_k=10)

        assert isinstance(params, ANNParams)
        assert params.nprobes > 0

    def test_record_search_performance(self):
        """Test convenience function for recording performance."""
        GlobalAdaptiveNProbes.reset_instance()

        record_search_performance(
            query_id="test",
            latency_ms=100.0,
            result_count=10,
        )

        tuner = GlobalAdaptiveNProbes.get_instance()
        stats = tuner.get_stats()

        assert stats["total_queries"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
