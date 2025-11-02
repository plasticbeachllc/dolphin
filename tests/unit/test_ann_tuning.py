"""Unit tests for ANN parameter tuning module."""

import pytest
from kb.retrieval.ann_tuning import ANNParams


class TestANNParamsValidation:
    """Test parameter validation."""

    def test_valid_default_params(self):
        """Test default parameters are valid."""
        params = ANNParams()
        assert params.metric == "cosine"
        assert params.nprobes == 20
        assert params.refine_factor == 10
        assert params.use_index is True

    def test_invalid_nprobes(self):
        """Test nprobes validation."""
        with pytest.raises(ValueError, match="nprobes must be >= 1"):
            ANNParams(nprobes=0)
        
        with pytest.raises(ValueError, match="nprobes must be >= 1"):
            ANNParams(nprobes=-1)

    def test_invalid_refine_factor(self):
        """Test refine_factor validation."""
        with pytest.raises(ValueError, match="refine_factor must be >= 1"):
            ANNParams(refine_factor=0)
        
        with pytest.raises(ValueError, match="refine_factor must be >= 1"):
            ANNParams(refine_factor=-1)

    def test_valid_custom_params(self):
        """Test custom parameters are accepted."""
        params = ANNParams(
            metric="L2",
            nprobes=15,
            refine_factor=5,
            use_index=False
        )
        assert params.metric == "L2"
        assert params.nprobes == 15
        assert params.refine_factor == 5
        assert params.use_index is False


class TestANNParamsPresets:
    """Test preset configurations."""

    def test_speed_preset(self):
        """Test speed-optimized configuration."""
        params = ANNParams.for_speed()
        assert params.metric == "cosine"
        assert params.nprobes == 10
        assert params.refine_factor == 5
        assert params.use_index is True
        
        # Should be faster than default
        speedup = params.estimated_speedup()
        assert speedup >= 2.0, f"Expected speedup >= 2.0x, got {speedup:.2f}x"

    def test_accuracy_preset(self):
        """Test accuracy-optimized configuration."""
        params = ANNParams.for_accuracy()
        assert params.metric == "cosine"
        assert params.nprobes == 30
        assert params.refine_factor == 20
        assert params.use_index is True
        
        # Should be slower than default
        speedup = params.estimated_speedup()
        assert speedup < 1.0, f"Expected speedup < 1.0x, got {speedup:.2f}x"

    def test_development_preset(self):
        """Test development/debugging configuration."""
        params = ANNParams.for_development()
        assert params.metric == "cosine"
        assert params.nprobes == 1000
        assert params.refine_factor == 100
        assert params.use_index is False  # Brute force


class TestANNParamsAdaptive:
    """Test adaptive parameter selection."""

    def test_identifier_query_high_precision(self):
        """Test identifier query needs high precision."""
        params = ANNParams.adaptive(
            query_type="identifier",
            top_k=5,
            dataset_size=100000
        )
        assert params.nprobes >= 20, "Identifier queries need high precision"
        assert params.refine_factor >= 15, "Identifier queries need refinement"

    def test_concept_query_small_topk(self):
        """Test concept query with small top_k can afford accuracy."""
        params = ANNParams.adaptive(
            query_type="concept",
            top_k=5,
            dataset_size=100000
        )
        # Small top_k allows balanced parameters
        assert 10 <= params.nprobes <= 50
        assert params.refine_factor >= 5

    def test_concept_query_large_topk(self):
        """Test concept query with large top_k prioritizes speed."""
        params = ANNParams.adaptive(
            query_type="concept",
            top_k=20,
            dataset_size=100000
        )
        # Large top_k prioritizes speed
        assert params.nprobes <= 20
        assert params.refine_factor <= 10

    def test_adaptive_scales_with_dataset_size(self):
        """Test adaptive parameters scale with dataset size."""
        # Small dataset
        params_small = ANNParams.adaptive(
            query_type="concept",
            top_k=10,
            dataset_size=10000
        )
        
        # Large dataset
        params_large = ANNParams.adaptive(
            query_type="concept",
            top_k=10,
            dataset_size=1000000
        )
        
        # Larger datasets should use more nprobes (more clusters)
        assert params_large.nprobes >= params_small.nprobes


class TestANNParamsUtilities:
    """Test utility methods."""

    def test_estimated_speedup_calculation(self):
        """Test speedup estimation."""
        # Baseline (default)
        baseline = ANNParams(nprobes=20, refine_factor=10)
        assert baseline.estimated_speedup() == pytest.approx(1.0, rel=0.01)
        
        # Faster config
        fast = ANNParams(nprobes=10, refine_factor=5)
        assert fast.estimated_speedup() >= 2.0
        
        # Slower config
        slow = ANNParams(nprobes=40, refine_factor=20)
        assert slow.estimated_speedup() < 1.0

    def test_to_lancedb_params(self):
        """Test conversion to LanceDB parameters."""
        params = ANNParams(
            metric="cosine",
            nprobes=15,
            refine_factor=8,
            use_index=True
        )
        
        lance_params = params.to_lancedb_params()
        
        assert lance_params["metric"] == "cosine"
        assert lance_params["nprobes"] == 15
        assert lance_params["refine_factor"] == 8
        assert lance_params["use_index"] is True

    def test_to_lancedb_params_all_metrics(self):
        """Test all metric types convert properly."""
        for metric in ["cosine", "L2", "dot"]:
            params = ANNParams(metric=metric)
            lance_params = params.to_lancedb_params()
            assert lance_params["metric"] == metric


class TestANNParamsEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_minimum_valid_nprobes(self):
        """Test minimum valid nprobes value."""
        params = ANNParams(nprobes=1)
        assert params.nprobes == 1

    def test_large_nprobes(self):
        """Test large nprobes values."""
        params = ANNParams(nprobes=1000)
        assert params.nprobes == 1000

    def test_minimum_valid_refine_factor(self):
        """Test minimum valid refine_factor value."""
        params = ANNParams(refine_factor=1)
        assert params.refine_factor == 1

    def test_large_refine_factor(self):
        """Test large refine_factor values."""
        params = ANNParams(refine_factor=500)
        assert params.refine_factor == 500

    def test_zero_dataset_size_adaptive(self):
        """Test adaptive with zero/small dataset size."""
        params = ANNParams.adaptive(dataset_size=0)
        # Should use minimum valid parameters
        assert params.nprobes >= 10

    def test_example_query_type(self):
        """Test example query type uses concept defaults."""
        params = ANNParams.adaptive(query_type="example", top_k=10)
        # Example queries behave like concept queries
        assert params.nprobes >= 5
        assert params.use_index is True