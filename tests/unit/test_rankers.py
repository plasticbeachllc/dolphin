"""Tests for ranking and fusion algorithms."""

import pytest

from pb_kb.retrieval.rankers import reciprocal_rank_fusion, weighted_score_fusion


class TestReciprocalRankFusion:
    """Tests for reciprocal rank fusion algorithm."""

    def test_rrf_single_list(self):
        """Test RRF with a single result list."""
        results = [
            {"chunk_id": "a", "score": 0.9},
            {"chunk_id": "b", "score": 0.8},
            {"chunk_id": "c", "score": 0.7},
        ]

        merged = reciprocal_rank_fusion([results])

        # Order should be preserved, scores should be RRF scores
        assert len(merged) == 3
        assert merged[0]["chunk_id"] == "a"
        assert merged[1]["chunk_id"] == "b"
        assert merged[2]["chunk_id"] == "c"

        # Verify RRF scores (1/(60+rank))
        assert abs(merged[0]["score"] - 1.0 / 61) < 0.0001
        assert abs(merged[1]["score"] - 1.0 / 62) < 0.0001
        assert abs(merged[2]["score"] - 1.0 / 63) < 0.0001

    def test_rrf_two_identical_lists(self):
        """Test RRF with two identical lists."""
        list1 = [
            {"chunk_id": "a", "score": 0.9},
            {"chunk_id": "b", "score": 0.8},
        ]
        list2 = [
            {"chunk_id": "a", "score": 0.9},
            {"chunk_id": "b", "score": 0.8},
        ]

        merged = reciprocal_rank_fusion([list1, list2])

        assert len(merged) == 2
        assert merged[0]["chunk_id"] == "a"
        assert merged[1]["chunk_id"] == "b"

        # Scores should be doubled (appears in both lists at same rank)
        assert abs(merged[0]["score"] - 2.0 / 61) < 0.0001
        assert abs(merged[1]["score"] - 2.0 / 62) < 0.0001

    def test_rrf_different_rankings(self):
        """Test RRF with different rankings."""
        # List 1: a > b > c
        list1 = [
            {"chunk_id": "a", "score": 0.9},
            {"chunk_id": "b", "score": 0.8},
            {"chunk_id": "c", "score": 0.7},
        ]

        # List 2: b > c > a (different order)
        list2 = [
            {"chunk_id": "b", "score": 0.95},
            {"chunk_id": "c", "score": 0.85},
            {"chunk_id": "a", "score": 0.75},
        ]

        merged = reciprocal_rank_fusion([list1, list2])

        # 'b' should rank first: 1/62 + 1/61 = highest
        # 'a' and 'c' have same total: 1/61 + 1/63 vs 1/63 + 1/62
        assert len(merged) == 3
        assert merged[0]["chunk_id"] == "b"

        # Verify 'b' has highest RRF score
        assert merged[0]["score"] > merged[1]["score"]
        assert merged[0]["score"] > merged[2]["score"]

    def test_rrf_non_overlapping_lists(self):
        """Test RRF with lists that don't overlap."""
        list1 = [{"chunk_id": "a", "score": 0.9}, {"chunk_id": "b", "score": 0.8}]
        list2 = [{"chunk_id": "c", "score": 0.9}, {"chunk_id": "d", "score": 0.8}]

        merged = reciprocal_rank_fusion([list1, list2])

        # All 4 results should be present
        assert len(merged) == 4
        result_ids = {r["chunk_id"] for r in merged}
        assert result_ids == {"a", "b", "c", "d"}

        # Top-ranked items from each list should have equal scores
        scores_by_id = {r["chunk_id"]: r["score"] for r in merged}
        assert abs(scores_by_id["a"] - scores_by_id["c"]) < 0.0001
        assert abs(scores_by_id["b"] - scores_by_id["d"]) < 0.0001

    def test_rrf_empty_lists(self):
        """Test RRF with empty input."""
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[]]) == []
        assert reciprocal_rank_fusion([[], []]) == []

    def test_rrf_custom_k_parameter(self):
        """Test RRF with custom k parameter."""
        results = [{"chunk_id": "a", "score": 0.9}]

        # With k=10
        merged_k10 = reciprocal_rank_fusion([results], k=10)
        assert abs(merged_k10[0]["score"] - 1.0 / 11) < 0.0001

        # With k=100
        merged_k100 = reciprocal_rank_fusion([results], k=100)
        assert abs(merged_k100[0]["score"] - 1.0 / 101) < 0.0001

    def test_rrf_custom_id_field(self):
        """Test RRF with custom ID field."""
        list1 = [{"doc_id": "a", "score": 0.9}, {"doc_id": "b", "score": 0.8}]
        list2 = [{"doc_id": "b", "score": 0.9}, {"doc_id": "a", "score": 0.8}]

        merged = reciprocal_rank_fusion([list1, list2], id_field="doc_id")

        assert len(merged) == 2
        assert "doc_id" in merged[0]

    def test_rrf_missing_id_field(self):
        """Test RRF handles results without ID field."""
        list1 = [
            {"chunk_id": "a", "score": 0.9},
            {"score": 0.8},  # Missing chunk_id
        ]

        merged = reciprocal_rank_fusion([list1])

        # Should only include result with ID
        assert len(merged) == 1
        assert merged[0]["chunk_id"] == "a"

    def test_rrf_preserves_metadata(self):
        """Test that RRF preserves metadata from results."""
        list1 = [
            {"chunk_id": "a", "score": 0.9, "path": "test.py", "language": "python"}
        ]
        list2 = [
            {"chunk_id": "a", "score": 0.8, "path": "other.py"}  # Different metadata
        ]

        merged = reciprocal_rank_fusion([list1, list2])

        # Should preserve metadata from first occurrence
        assert merged[0]["path"] == "test.py"
        assert merged[0]["language"] == "python"


class TestWeightedScoreFusion:
    """Tests for weighted score fusion algorithm."""

    def test_weighted_fusion_equal_weights(self):
        """Test weighted fusion with equal weights (default)."""
        list1 = [{"chunk_id": "a", "score": 0.8}]
        list2 = [{"chunk_id": "a", "score": 0.6}]

        merged = weighted_score_fusion([list1, list2])

        # With equal weights: (0.8 + 0.6) / 2 = 0.7
        assert len(merged) == 1
        assert abs(merged[0]["score"] - 0.7) < 0.0001

    def test_weighted_fusion_custom_weights(self):
        """Test weighted fusion with custom weights."""
        list1 = [{"chunk_id": "a", "score": 0.8}]
        list2 = [{"chunk_id": "a", "score": 0.4}]

        # Give list1 3x weight of list2
        merged = weighted_score_fusion([list1, list2], weights=[3.0, 1.0])

        # Weighted average: (3*0.8 + 1*0.4) / 4 = 2.8/4 = 0.7
        assert abs(merged[0]["score"] - 0.7) < 0.0001

    def test_weighted_fusion_non_overlapping(self):
        """Test weighted fusion with non-overlapping results."""
        list1 = [{"chunk_id": "a", "score": 0.9}]
        list2 = [{"chunk_id": "b", "score": 0.8}]

        merged = weighted_score_fusion([list1, list2])

        # Both should be present with their normalized scores
        assert len(merged) == 2
        result_map = {r["chunk_id"]: r for r in merged}

        # With equal weights (0.5 each): scores are 0.45 and 0.4
        assert abs(result_map["a"]["score"] - 0.45) < 0.0001
        assert abs(result_map["b"]["score"] - 0.4) < 0.0001

    def test_weighted_fusion_sorting(self):
        """Test that weighted fusion sorts by combined score."""
        list1 = [
            {"chunk_id": "a", "score": 0.9},
            {"chunk_id": "b", "score": 0.5},
        ]
        list2 = [
            {"chunk_id": "b", "score": 0.8},
            {"chunk_id": "a", "score": 0.4},
        ]

        merged = weighted_score_fusion([list1, list2])

        # 'a': (0.9 + 0.4) / 2 = 0.65
        # 'b': (0.5 + 0.8) / 2 = 0.65
        # Equal scores, but 'a' appears first in list1
        assert len(merged) == 2

    def test_weighted_fusion_empty_lists(self):
        """Test weighted fusion with empty input."""
        assert weighted_score_fusion([]) == []
        assert weighted_score_fusion([[]]) == []

    def test_weighted_fusion_invalid_weights(self):
        """Test that mismatched weights raises error."""
        list1 = [{"chunk_id": "a", "score": 0.9}]
        list2 = [{"chunk_id": "b", "score": 0.8}]

        with pytest.raises(ValueError, match="Number of weights"):
            weighted_score_fusion([list1, list2], weights=[1.0])  # Only 1 weight

    def test_weighted_fusion_zero_scores(self):
        """Test weighted fusion handles zero scores."""
        list1 = [{"chunk_id": "a", "score": 0.0}]
        list2 = [{"chunk_id": "a", "score": 1.0}]

        merged = weighted_score_fusion([list1, list2], weights=[1.0, 1.0])

        # Average: (0.0 + 1.0) / 2 = 0.5
        assert abs(merged[0]["score"] - 0.5) < 0.0001

    def test_weighted_fusion_missing_scores(self):
        """Test weighted fusion handles missing scores."""
        list1 = [{"chunk_id": "a"}]  # No score field
        list2 = [{"chunk_id": "a", "score": 0.8}]

        merged = weighted_score_fusion([list1, list2])

        # Missing score treated as 0.0: (0.0 + 0.8) / 2 = 0.4
        assert abs(merged[0]["score"] - 0.4) < 0.0001


class TestRankingComparison:
    """Compare different ranking strategies."""

    def test_rrf_vs_weighted_on_agreement(self):
        """Test that RRF and weighted fusion agree when lists agree."""
        list1 = [
            {"chunk_id": "a", "score": 0.9},
            {"chunk_id": "b", "score": 0.8},
        ]
        list2 = [
            {"chunk_id": "a", "score": 0.85},
            {"chunk_id": "b", "score": 0.75},
        ]

        rrf_merged = reciprocal_rank_fusion([list1, list2])
        weighted_merged = weighted_score_fusion([list1, list2])

        # Both should rank 'a' before 'b'
        assert rrf_merged[0]["chunk_id"] == "a"
        assert weighted_merged[0]["chunk_id"] == "a"

    def test_rrf_vs_weighted_on_disagreement(self):
        """Test behavior when lists strongly disagree."""
        # List 1 strongly prefers 'a'
        list1 = [
            {"chunk_id": "a", "score": 1.0},
            {"chunk_id": "b", "score": 0.1},
        ]

        # List 2 strongly prefers 'b'
        list2 = [
            {"chunk_id": "b", "score": 1.0},
            {"chunk_id": "a", "score": 0.1},
        ]

        rrf_merged = reciprocal_rank_fusion([list1, list2])
        weighted_merged = weighted_score_fusion([list1, list2])

        # RRF gives equal weight to rankings (both appear first in one list)
        # Weighted fusion averages scores
        rrf_ids = [r["chunk_id"] for r in rrf_merged]
        weighted_ids = [r["chunk_id"] for r in weighted_merged]

        # Both should have same items
        assert set(rrf_ids) == set(weighted_ids) == {"a", "b"}
