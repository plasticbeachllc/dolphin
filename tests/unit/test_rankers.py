"""Unit tests for ranking algorithms (RRF, Weighted Fusion, MMR)."""

import pytest

from kb.retrieval.rankers import (
    create_fusion_function,
    maximal_marginal_relevance,
    reciprocal_rank_fusion,
    weighted_fusion,
)


class TestReciprocalRankFusion:
    """Test Reciprocal Rank Fusion algorithm."""

    def test_empty_input(self):
        """Test with empty input lists."""
        result = reciprocal_rank_fusion([])
        assert result == []

    def test_single_result_list(self):
        """Test with single result list."""
        results = [[{"chunk_id": "A", "score": 0.9}]]
        fused = reciprocal_rank_fusion(results)
        assert len(fused) == 1
        assert fused[0]["chunk_id"] == "A"
        assert fused[0]["rrf_score"] > 0

    def test_two_result_lists(self):
        """Test with two result lists containing overlapping documents."""
        vector_results = [
            {"chunk_id": "A", "score": 0.9, "repo": "repo1"},
            {"chunk_id": "B", "score": 0.8, "repo": "repo1"},
        ]
        bm25_results = [
            {"chunk_id": "B", "score": 0.95, "repo": "repo1"},
            {"chunk_id": "A", "score": 0.75, "repo": "repo1"},
        ]

        fused = reciprocal_rank_fusion([vector_results, bm25_results])

        # Should have 2 documents
        assert len(fused) == 2

        # Both documents should have appearances in both lists
        doc_a = next(doc for doc in fused if doc["chunk_id"] == "A")
        doc_b = next(doc for doc in fused if doc["chunk_id"] == "B")

        assert doc_a["appearances"] == 2
        assert doc_b["appearances"] == 2

        # RRF scores should be calculated correctly
        assert doc_a["rrf_score"] > 0
        assert doc_b["rrf_score"] > 0

    def test_non_overlapping_documents(self):
        """Test with non-overlapping documents."""
        list1 = [
            {"chunk_id": "A", "score": 0.9},
            {"chunk_id": "B", "score": 0.8},
        ]
        list2 = [
            {"chunk_id": "C", "score": 0.95},
            {"chunk_id": "D", "score": 0.75},
        ]

        fused = reciprocal_rank_fusion([list1, list2])

        # Should have 4 documents
        assert len(fused) == 4

        # All documents should appear once
        for doc in fused:
            assert doc["appearances"] == 1

    def test_custom_parameters(self):
        """Test with custom parameters."""
        results = [[{"chunk_id": "A", "score": 0.9}]]

        # Test custom k value
        fused_k30 = reciprocal_rank_fusion(results, k=30)
        fused_k60 = reciprocal_rank_fusion(results, k=60)

        # Both should have the same chunk_id but different scores
        assert fused_k30[0]["chunk_id"] == fused_k60[0]["chunk_id"]
        assert fused_k30[0]["rrf_score"] != fused_k60[0]["rrf_score"]

    def test_different_id_field(self):
        """Test with custom ID field."""
        results = [[{"document_id": "A", "score": 0.9}]]

        fused = reciprocal_rank_fusion(results, id_field="document_id")
        assert fused[0]["document_id"] == "A"
        assert "chunk_id" not in fused[0]


class TestWeightedFusion:
    """Test weighted fusion algorithm."""

    def test_invalid_weights(self):
        """Test that invalid weights raise errors."""
        results = [[{"chunk_id": "A", "score": 0.9}]]

        # Weights don't sum to 1.0
        with pytest.raises(ValueError):
            weighted_fusion(results, [0.3, 0.7])  # Wrong number of lists

        with pytest.raises(ValueError):
            weighted_fusion(results, [0.4, 0.4])  # Don't sum to 1.0

    def test_valid_weights(self):
        """Test with valid weights."""
        list1 = [
            {"chunk_id": "A", "score": 0.9},
            {"chunk_id": "B", "score": 0.7},
        ]
        list2 = [
            {"chunk_id": "B", "score": 0.95},
            {"chunk_id": "A", "score": 0.6},
        ]

        fused = weighted_fusion([list1, list2], [0.5, 0.5])

        assert len(fused) == 2
        doc_a = next(doc for doc in fused if doc["chunk_id"] == "A")
        doc_b = next(doc for doc in fused if doc["chunk_id"] == "B")

        # Both documents should have contributions
        assert doc_a["contributions"] == 2
        assert doc_b["contributions"] == 2

        # Fused scores should be calculated
        assert doc_a["fused_score"] > 0
        assert doc_b["fused_score"] > 0

    def test_normalization(self):
        """Test score normalization."""
        list1 = [{"chunk_id": "A", "score": 0.1}]  # Very low scores
        list2 = [{"chunk_id": "A", "score": 0.01}]

        fused_normalized = weighted_fusion([list1, list2], [0.5, 0.5], normalize=True)
        fused_unnormalized = weighted_fusion(
            [list1, list2], [0.5, 0.5], normalize=False
        )

        # Should have different results due to normalization
        assert (
            fused_normalized[0]["fused_score"] != fused_unnormalized[0]["fused_score"]
        )

    def test_missing_scores(self):
        """Test handling of missing scores."""
        list1 = [{"chunk_id": "A"}, {"chunk_id": "B", "score": 0.8}]
        list2 = [{"chunk_id": "B"}, {"chunk_id": "C", "score": 0.9}]

        fused = weighted_fusion([list1, list2], [0.5, 0.5])

        # Should handle missing scores gracefully
        doc_a = next((doc for doc in fused if doc["chunk_id"] == "A"), None)
        doc_b = next((doc for doc in fused if doc["chunk_id"] == "B"), None)
        doc_c = next((doc for doc in fused if doc["chunk_id"] == "C"), None)

        assert doc_a is not None
        assert doc_b is not None
        assert doc_c is not None


class TestMaximalMarginalRelevance:
    """Test MMR algorithm for diverse results."""

    def test_empty_candidates(self):
        """Test with empty candidates."""
        result = maximal_marginal_relevance([0.1, 0.2, 0.3], [])
        assert result == []

    def test_single_candidate(self):
        """Test with single candidate."""
        candidates = [{"chunk_id": "A", "score": 0.9}]
        result = maximal_marginal_relevance([0.1, 0.2, 0.3], candidates)

        assert len(result) == 1
        assert result[0]["chunk_id"] == "A"
        assert "mmr_score" in result[0]

    def test_diversification(self):
        """Test that MMR provides diverse results."""
        # Create similar candidates (high cosine similarity)
        query_vector = [0.1, 0.2, 0.3]
        candidates = [
            {"chunk_id": "A", "score": 0.9, "query_vector": query_vector},
            {
                "chunk_id": "B",
                "score": 0.85,
                "query_vector": query_vector,
            },  # Very similar
            {
                "chunk_id": "C",
                "score": 0.8,
                "query_vector": [-0.1, -0.2, -0.3],
            },  # Different
        ]

        result = maximal_marginal_relevance(
            query_vector, candidates, top_k=2, lambda_param=0.7
        )

        assert len(result) == 2

        # Should prefer diverse results when lambda is reasonable
        # C should be selected over B if they compete for second spot
        ids = {doc["chunk_id"] for doc in result}
        assert "C" in ids  # Diverse document should be included

    def test_lambda_parameter(self):
        """Test different lambda values."""
        query_vector = [0.1, 0.2, 0.3]
        candidates = [
            {"chunk_id": "A", "score": 0.95, "query_vector": query_vector},
            {
                "chunk_id": "B",
                "score": 0.80,
                "query_vector": query_vector,
            },  # Same as A, high relevance
            {
                "chunk_id": "C",
                "score": 0.50,
                "query_vector": [-0.1, -0.2, -0.3],
            },  # Low score but very diverse
            {
                "chunk_id": "D",
                "score": 0.45,
                "query_vector": [0.1, 0.2, 0.3],
            },  # Medium score, same vector as A
        ]

        # High lambda = prioritize relevance
        result_relevance = maximal_marginal_relevance(
            query_vector, candidates, lambda_param=0.9
        )

        # Low lambda = prioritize diversity
        result_diversity = maximal_marginal_relevance(
            query_vector, candidates, lambda_param=0.1
        )

        # Results should be different with different lambda values
        assert len(result_relevance) >= 2
        assert len(result_diversity) >= 2

        # First result should be A (highest score)
        assert result_relevance[0]["chunk_id"] == "A"
        assert result_diversity[0]["chunk_id"] == "A"

        # Test different scenarios based on lambda
        # Instead of asserting specific order, verify that different lambdas produce different MMR scores

        # Check that MMR scores are calculated correctly
        assert all("mmr_score" in doc for doc in result_relevance)
        assert all("mmr_score" in doc for doc in result_diversity)

        # Verify that the lambda parameter affects the selection process
        # This is demonstrated by the different MMR scores for similar documents
        relevance_scores = [r["mmr_score"] for r in result_relevance]
        diversity_scores = [r["mmr_score"] for r in result_diversity]

        # Should have different score distributions
        assert (
            relevance_scores != diversity_scores
        ), "Different lambda values should produce different MMR scores"

    def test_top_k_limit(self):
        """Test top_k parameter limits results."""
        query_vector = [0.1, 0.2, 0.3]
        candidates = [
            {"chunk_id": str(i), "score": 0.9 - i * 0.1, "query_vector": query_vector}
            for i in range(10)
        ]

        result = maximal_marginal_relevance(query_vector, candidates, top_k=3)

        assert len(result) == 3

    def test_missing_query_vector(self):
        """Test handling of candidates without query_vector."""
        query_vector = [0.1, 0.2, 0.3]
        candidates = [
            {"chunk_id": "A", "score": 0.9},  # No query_vector
            {"chunk_id": "B", "score": 0.8, "query_vector": query_vector},
        ]

        # Should not crash, will use query_vector for all calculations
        result = maximal_marginal_relevance(query_vector, candidates, top_k=2)

        assert len(result) == 2
        assert all("mmr_score" in doc for doc in result)


class TestFusionFactory:
    """Test fusion function factory."""

    def test_rrf_factory(self):
        """Test RRF function creation."""
        fusion_func = create_fusion_function(method="rrf", k=50)

        results = [[{"chunk_id": "A", "score": 0.9}]]
        fused = fusion_func(results)

        assert len(fused) == 1
        assert fused[0]["chunk_id"] == "A"
        assert fused[0]["rrf_score"] > 0

    def test_weighted_factory(self):
        """Test weighted fusion function creation."""
        fusion_func = create_fusion_function(method="weighted", weights=[0.5, 0.5])

        list1 = [{"chunk_id": "A", "score": 0.9}]
        list2 = [{"chunk_id": "B", "score": 0.8}]
        fused = fusion_func([list1, list2])

        assert len(fused) == 2
        assert all("fused_score" in doc for doc in fused)

    def test_invalid_method(self):
        """Test invalid method raises error."""
        with pytest.raises(ValueError):
            create_fusion_function(method="invalid")

    def test_missing_weights(self):
        """Test missing weights for weighted fusion."""
        fusion_func = create_fusion_function(method="weighted")

        with pytest.raises(ValueError):
            fusion_func([[{"chunk_id": "A", "score": 0.9}]])


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_none_values(self):
        """Test handling of None values."""
        results = [[{"chunk_id": "A", "score": None}]]
        fused = reciprocal_rank_fusion(results)

        assert len(fused) == 1
        assert fused[0]["chunk_id"] == "A"

    def test_missing_id_field(self):
        """Test handling when ID field is missing."""
        results = [[{"score": 0.9}]]  # No chunk_id
        fused = reciprocal_rank_fusion(results)

        # Should skip documents without ID
        assert len(fused) == 0

    def test_duplicate_documents_in_same_list(self):
        """Test handling of duplicates within same list."""
        results = [
            [
                {"chunk_id": "A", "score": 0.9},
                {"chunk_id": "A", "score": 0.8},  # Duplicate
            ]
        ]
        fused = reciprocal_rank_fusion(results)

        # Should handle duplicates gracefully
        assert len(fused) >= 1

    def test_large_result_sets(self):
        """Test with large result sets."""
        # Create large result sets
        list1 = [{"chunk_id": str(i), "score": 0.9 - i * 0.001} for i in range(100)]
        list2 = [
            {"chunk_id": str(i + 50), "score": 0.9 - i * 0.001} for i in range(100)
        ]

        fused = reciprocal_rank_fusion([list1, list2])

        # Should process efficiently
        assert len(fused) == 150  # Some overlap

        # Results should be sorted
        scores = [doc["rrf_score"] for doc in fused]
        assert scores == sorted(scores, reverse=True)
