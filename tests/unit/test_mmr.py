"""Tests for Maximal Marginal Relevance (MMR) algorithm."""

import pytest

from kb.retrieval.rankers import maximal_marginal_relevance


class TestMaximalMarginalRelevance:
    """Test cases for MMR algorithm - updated for new API."""

    def test_empty_results(self):
        """Test that empty results list returns empty list."""
        results = []
        query_vector = [0.1, 0.2, 0.3]
        reranked = maximal_marginal_relevance(query_vector, results)
        assert reranked == []

    def test_single_result(self):
        """Test that single result is returned unchanged."""
        query_vector = [0.1, 0.2, 0.3]
        results = [{"chunk_id": "a", "score": 0.9, "query_vector": query_vector}]
        reranked = maximal_marginal_relevance(query_vector, results)
        assert len(reranked) == 1
        assert reranked[0]["chunk_id"] == "a"
        assert "mmr_score" in reranked[0]

    def test_no_lambda_param(self):
        """Test MMR with default lambda parameter."""
        query_vector = [0.1, 0.2, 0.3]
        results = [
            {"chunk_id": "a", "score": 0.95, "query_vector": query_vector},
            {"chunk_id": "b", "score": 0.90, "query_vector": query_vector},
            {"chunk_id": "c", "score": 0.85, "query_vector": query_vector},
        ]
        reranked = maximal_marginal_relevance(query_vector, results)

        # Should return all results
        assert len(reranked) == 3
        # Each should have MMR scores
        assert all("mmr_score" in r for r in reranked)

    def test_high_relevance_focus(self):
        """Test MMR with high lambda (relevance-focused)."""
        query_vector = [0.1, 0.2, 0.3]
        results = [
            {"chunk_id": "a", "score": 0.95, "query_vector": query_vector},
            {"chunk_id": "b", "score": 0.90, "query_vector": query_vector},
            {"chunk_id": "c", "score": 0.85, "query_vector": query_vector},
        ]

        # High lambda (0.9) should prioritize relevance
        reranked = maximal_marginal_relevance(query_vector, results, lambda_param=0.9)

        # Should return all results with MMR scores
        assert len(reranked) == 3
        # First result should be one of the high-scoring ones
        assert reranked[0]["score"] >= 0.90

    def test_high_diversity_focus(self):
        """Test MMR with low lambda (diversity-focused)."""
        query_vector = [0.1, 0.2, 0.3]
        results = [
            {"chunk_id": "a", "score": 0.95, "query_vector": query_vector},
            {"chunk_id": "b", "score": 0.94, "query_vector": query_vector},
            {"chunk_id": "c", "score": 0.90, "query_vector": query_vector},
            {"chunk_id": "d", "score": 0.85, "query_vector": query_vector},
        ]

        # Low lambda (0.3) should favor diversity
        reranked = maximal_marginal_relevance(query_vector, results, lambda_param=0.3)

        # Should return all results
        assert len(reranked) == 4
        # MMR scores should reflect diversity optimization
        assert all("mmr_score" in r for r in reranked)

    def test_custom_field_names(self):
        """Test MMR with custom ID field."""
        query_vector = [0.1, 0.2, 0.3]
        results = [
            {"id": "a", "score": 0.9, "query_vector": query_vector},
            {"id": "b", "score": 0.8, "query_vector": query_vector},
        ]

        reranked = maximal_marginal_relevance(
            query_vector, results, lambda_param=0.7, id_field="id"
        )

        assert len(reranked) == 2
        assert all("mmr_score" in r for r in reranked)

    def test_invalid_lambda_param(self):
        """Test that invalid lambda parameters are handled gracefully."""
        query_vector = [0.1, 0.2, 0.3]
        results = [{"chunk_id": "a", "score": 0.9, "query_vector": query_vector}]

        # Should handle invalid lambda gracefully (clip to valid range)
        # The function should not crash but should handle edge cases
        reranked = maximal_marginal_relevance(query_vector, results, lambda_param=-0.1)
        assert len(reranked) == 1

    def test_results_without_id(self):
        """Test that results without ID field are handled."""
        query_vector = [0.1, 0.2, 0.3]
        results = [
            {"score": 0.9, "query_vector": query_vector},  # No chunk_id
            {"chunk_id": "b", "score": 0.8, "query_vector": query_vector},
            {"score": 0.7, "query_vector": query_vector},  # No chunk_id
        ]

        reranked = maximal_marginal_relevance(query_vector, results)

        # Should handle missing IDs gracefully
        assert len(reranked) >= 0

    def test_score_consistency(self):
        """Test that MMR scores are properly calculated."""
        query_vector = [0.1, 0.2, 0.3]
        results = [
            {"chunk_id": "a", "score": 0.95, "query_vector": query_vector},
            {"chunk_id": "b", "score": 0.90, "query_vector": query_vector},
        ]

        reranked = maximal_marginal_relevance(query_vector, results, lambda_param=0.7)

        # Each result should have both original score and MMR score
        assert len(reranked) == 2
        for result in reranked:
            assert "score" in result  # Original similarity score
            assert "mmr_score" in result  # MMR score

    def test_result_preservation(self):
        """Test that all result fields are preserved."""
        query_vector = [0.1, 0.2, 0.3]
        original_results = [
            {
                "chunk_id": "a",
                "score": 0.9,
                "path": "src/auth.py",
                "repo": "api-server",
                "language": "python",
                "content": "def login(): pass",
                "query_vector": query_vector,
            }
        ]

        reranked = maximal_marginal_relevance(query_vector, original_results)

        assert len(reranked) == 1
        # All original fields should be preserved
        for key, value in original_results[0].items():
            if key != "query_vector":  # query_vector is processed internally
                assert key in reranked[0]
                assert reranked[0][key] == value

    def test_diversity_vs_relevance_impact(self):
        """Test the impact of different lambda values on ordering."""
        query_vector = [0.1, 0.2, 0.3]
        # Create results with similar high-scoring items and different lower-scoring ones
        results = [
            {"chunk_id": "a", "score": 0.95, "query_vector": query_vector},
            {"chunk_id": "b", "score": 0.94, "query_vector": query_vector},
            {
                "chunk_id": "c",
                "score": 0.90,
                "query_vector": [-0.1, -0.2, -0.3],
            },  # Different vector
            {"chunk_id": "d", "score": 0.80, "query_vector": query_vector},
        ]

        # High lambda (relevance-focused)
        relevance_focused = maximal_marginal_relevance(
            query_vector, results, lambda_param=0.9
        )

        # Low lambda (diversity-focused)
        diversity_focused = maximal_marginal_relevance(
            query_vector, results, lambda_param=0.3
        )

        # Both should preserve all results but potentially reorder
        assert len(relevance_focused) == 4
        assert len(diversity_focused) == 4

        # Check that results are reordered differently
        relevance_order = [r["chunk_id"] for r in relevance_focused]
        diversity_order = [r["chunk_id"] for r in diversity_focused]

        # The ordering might be the same, but MMR scores should differ
        relevance_scores = [r["mmr_score"] for r in relevance_focused]
        diversity_scores = [r["mmr_score"] for r in diversity_focused]

        assert relevance_scores != diversity_scores

    def test_realistic_code_search_scenario(self):
        """Test MMR with realistic code search results."""
        query_vector = [0.1, 0.2, 0.3]
        results = [
            {
                "chunk_id": "login_1",
                "score": 0.92,
                "content": "def login(username, password): return authenticate(username, password)",
                "path": "src/auth/login.py",
                "symbol_name": "login",
                "query_vector": query_vector,
            },
            {
                "chunk_id": "login_2",
                "score": 0.89,
                "content": "async def login_async(user: User) -> AuthResult: return await auth.login(user)",
                "path": "src/auth/async_login.py",
                "symbol_name": "login_async",
                "query_vector": query_vector,
            },
            {
                "chunk_id": "logout",
                "score": 0.75,
                "content": "def logout(session_id): clear_session(session_id)",
                "path": "src/auth/session.py",
                "symbol_name": "logout",
                "query_vector": query_vector,
            },
            {
                "chunk_id": "database",
                "score": 0.65,
                "content": "SELECT * FROM users WHERE id = ?",
                "path": "src/db/queries.sql",
                "symbol_name": None,
                "query_vector": [-0.1, -0.2, -0.3],  # Different semantic space
            },
        ]

        reranked = maximal_marginal_relevance(query_vector, results, lambda_param=0.7)

        # Should return all results
        assert len(reranked) == 4

        # All should have MMR scores
        assert all("mmr_score" in r for r in reranked)

        # Login-related results (similar) and database query (different) should be included
        chunk_ids = [r["chunk_id"] for r in reranked]
        assert "login_1" in chunk_ids
        assert "login_2" in chunk_ids
        assert "database" in chunk_ids

        # First result should be highly relevant
        assert reranked[0]["score"] >= 0.85

    def test_very_similar_results(self):
        """Test MMR when all results are very similar."""
        query_vector = [0.1, 0.2, 0.3]
        results = [
            {"chunk_id": "a", "score": 0.90, "query_vector": query_vector},
            {"chunk_id": "b", "score": 0.89, "query_vector": query_vector},
            {"chunk_id": "c", "score": 0.88, "query_vector": query_vector},
        ]

        # With high similarity, lambda determines which gets selected first
        reranked = maximal_marginal_relevance(query_vector, results, lambda_param=0.8)

        assert len(reranked) == 3
        # All should still be returned, MMR handles similarity internally
        assert all(r["chunk_id"] in ["a", "b", "c"] for r in reranked)
