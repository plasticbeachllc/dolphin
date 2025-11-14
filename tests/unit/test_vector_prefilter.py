"""Unit tests for vector search pre-filtering."""

import pytest
from unittest.mock import Mock
from kb.search.vector_prefilter import (
    VectorPreFilter,
    FilterCriteria,
    create_repo_filter,
    create_language_filter,
    create_symbol_filter,
    combine_filters,
)


class TestFilterCriteria:
    """Unit tests for FilterCriteria dataclass."""

    def test_empty_criteria(self):
        """Test empty filter criteria."""
        criteria = FilterCriteria()

        assert criteria.repos is None
        assert criteria.languages is None
        assert criteria.file_patterns is None

    def test_repo_criteria(self):
        """Test repository filter criteria."""
        criteria = FilterCriteria(repos=["repo1", "repo2"])

        assert criteria.repos == ["repo1", "repo2"]

    def test_language_criteria(self):
        """Test language filter criteria."""
        criteria = FilterCriteria(languages=["python", "javascript"])

        assert criteria.languages == ["python", "javascript"]

    def test_token_count_criteria(self):
        """Test token count filter criteria."""
        criteria = FilterCriteria(
            min_token_count=100,
            max_token_count=500,
        )

        assert criteria.min_token_count == 100
        assert criteria.max_token_count == 500


class TestVectorPreFilter:
    """Unit tests for VectorPreFilter class."""

    def test_prefilter_initialization(self):
        """Test pre-filter initialization."""
        prefilter = VectorPreFilter(
            enable_stats=True,
            cache_filter_expressions=True,
        )

        assert prefilter.enable_stats is True
        assert prefilter.cache_filter_expressions is True

    def test_build_repo_filter_single(self):
        """Test building single repository filter."""
        prefilter = VectorPreFilter()
        criteria = FilterCriteria(repos=["repo1"])

        expr = prefilter.build_filter_expression(criteria)

        assert expr == "repo = 'repo1'"

    def test_build_repo_filter_multiple(self):
        """Test building multiple repository filter."""
        prefilter = VectorPreFilter()
        criteria = FilterCriteria(repos=["repo1", "repo2"])

        expr = prefilter.build_filter_expression(criteria)

        assert "IN" in expr
        assert "repo1" in expr
        assert "repo2" in expr

    def test_build_language_filter(self):
        """Test building language filter."""
        prefilter = VectorPreFilter()
        criteria = FilterCriteria(languages=["python"])

        expr = prefilter.build_filter_expression(criteria)

        assert "language = 'python'" in expr

    def test_build_symbol_kind_filter(self):
        """Test building symbol kind filter."""
        prefilter = VectorPreFilter()
        criteria = FilterCriteria(symbol_kinds=["function", "class"])

        expr = prefilter.build_filter_expression(criteria)

        assert "symbol_kind" in expr
        assert "function" in expr
        assert "class" in expr

    def test_build_token_count_filter(self):
        """Test building token count filter."""
        prefilter = VectorPreFilter()
        criteria = FilterCriteria(
            min_token_count=100,
            max_token_count=500,
        )

        expr = prefilter.build_filter_expression(criteria)

        assert "token_count >= 100" in expr
        assert "token_count <= 500" in expr

    def test_build_exclude_paths_filter(self):
        """Test building path exclusion filter."""
        prefilter = VectorPreFilter()
        criteria = FilterCriteria(exclude_paths=["test/", "vendor/"])

        expr = prefilter.build_filter_expression(criteria)

        assert "NOT LIKE" in expr

    def test_build_file_patterns_filter(self):
        """Test building file pattern filter."""
        prefilter = VectorPreFilter()
        criteria = FilterCriteria(file_patterns=["*.py", "*.js"])

        expr = prefilter.build_filter_expression(criteria)

        assert "LIKE" in expr
        assert ".py" in expr or ".js" in expr

    def test_build_combined_filter(self):
        """Test building combined filter with multiple criteria."""
        prefilter = VectorPreFilter()
        criteria = FilterCriteria(
            repos=["repo1"],
            languages=["python"],
            min_token_count=100,
        )

        expr = prefilter.build_filter_expression(criteria)

        assert "repo = 'repo1'" in expr
        assert "language = 'python'" in expr
        assert "token_count >= 100" in expr
        assert " AND " in expr

    def test_build_filter_caching(self):
        """Test filter expression caching."""
        prefilter = VectorPreFilter(cache_filter_expressions=True)
        criteria = FilterCriteria(repos=["repo1"])

        # Build expression twice
        expr1 = prefilter.build_filter_expression(criteria)
        expr2 = prefilter.build_filter_expression(criteria)

        # Should return same expression
        assert expr1 == expr2

        # Cache should have entry
        stats = prefilter.get_stats()
        assert stats["cache_size"] > 0

    def test_apply_prefilter(self):
        """Test applying pre-filter to search query."""
        prefilter = VectorPreFilter(enable_stats=True)
        criteria = FilterCriteria(repos=["repo1"])

        # Mock search query
        mock_query = Mock()
        mock_query.where = Mock(return_value=mock_query)

        filtered_query, stats = prefilter.apply_prefilter(
            mock_query,
            criteria,
            estimate_total=1000,
        )

        # Should have called where()
        mock_query.where.assert_called_once()

        # Should have stats
        assert stats is not None
        assert stats.total_candidates == 1000
        assert stats.reduction_pct > 0

    def test_apply_prefilter_no_criteria(self):
        """Test applying pre-filter with no criteria."""
        prefilter = VectorPreFilter()
        criteria = FilterCriteria()  # Empty

        mock_query = Mock()

        filtered_query, stats = prefilter.apply_prefilter(
            mock_query,
            criteria,
            estimate_total=1000,
        )

        # Should not modify query
        assert filtered_query == mock_query
        assert stats is None

    def test_estimate_reduction_repo_filter(self):
        """Test search space reduction estimation for repo filter."""
        prefilter = VectorPreFilter()
        criteria = FilterCriteria(repos=["repo1"])

        reduction = prefilter._estimate_reduction(criteria, 10000)

        # Single repo should give high reduction
        assert reduction >= 70.0

    def test_estimate_reduction_language_filter(self):
        """Test search space reduction estimation for language filter."""
        prefilter = VectorPreFilter()
        criteria = FilterCriteria(languages=["python"])

        reduction = prefilter._estimate_reduction(criteria, 10000)

        # Language filter should give moderate reduction
        assert reduction >= 30.0

    def test_get_stats(self):
        """Test statistics retrieval."""
        prefilter = VectorPreFilter(enable_stats=True)
        criteria = FilterCriteria(repos=["repo1"])

        mock_query = Mock()
        mock_query.where = Mock(return_value=mock_query)

        # Apply some filters
        prefilter.apply_prefilter(mock_query, criteria, estimate_total=1000)
        prefilter.apply_prefilter(mock_query, criteria, estimate_total=2000)

        stats = prefilter.get_stats()

        assert stats["total_filters_applied"] == 2
        assert stats["avg_reduction_pct"] > 0
        assert "cache_size" in stats

    def test_clear_cache(self):
        """Test cache clearing."""
        prefilter = VectorPreFilter(cache_filter_expressions=True)
        criteria = FilterCriteria(repos=["repo1"])

        # Build expression to populate cache
        prefilter.build_filter_expression(criteria)

        stats = prefilter.get_stats()
        assert stats["cache_size"] > 0

        # Clear cache
        prefilter.clear_cache()

        stats = prefilter.get_stats()
        assert stats["cache_size"] == 0

    def test_cache_key_generation(self):
        """Test cache key generation."""
        prefilter = VectorPreFilter()

        # Different criteria should generate different keys
        key1 = prefilter._make_cache_key(FilterCriteria(repos=["repo1"]))
        key2 = prefilter._make_cache_key(FilterCriteria(repos=["repo2"]))
        key3 = prefilter._make_cache_key(FilterCriteria(languages=["python"]))

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    def test_param_order_independence(self):
        """Test that parameter order doesn't affect cache key."""
        prefilter = VectorPreFilter()

        criteria1 = FilterCriteria(
            repos=["repo1", "repo2"],
            languages=["python", "javascript"],
        )

        criteria2 = FilterCriteria(
            repos=["repo2", "repo1"],  # Different order
            languages=["javascript", "python"],  # Different order
        )

        # Should generate same cache key (after sorting)
        key1 = prefilter._make_cache_key(criteria1)
        key2 = prefilter._make_cache_key(criteria2)

        assert key1 == key2


class TestConvenienceFunctions:
    """Unit tests for convenience functions."""

    def test_create_repo_filter(self):
        """Test repo filter creation."""
        criteria = create_repo_filter(["repo1", "repo2"])

        assert criteria.repos == ["repo1", "repo2"]

    def test_create_language_filter(self):
        """Test language filter creation."""
        criteria = create_language_filter(["python", "javascript"])

        assert criteria.languages == ["python", "javascript"]

    def test_create_symbol_filter(self):
        """Test symbol filter creation."""
        criteria = create_symbol_filter(["function", "class"])

        assert criteria.symbol_kinds == ["function", "class"]

    def test_combine_filters_repos(self):
        """Test combining repository filters."""
        filter1 = create_repo_filter(["repo1"])
        filter2 = create_repo_filter(["repo2"])

        combined = combine_filters(filter1, filter2)

        assert set(combined.repos) == {"repo1", "repo2"}

    def test_combine_filters_multiple_types(self):
        """Test combining different filter types."""
        filter1 = create_repo_filter(["repo1"])
        filter2 = create_language_filter(["python"])
        filter3 = FilterCriteria(min_token_count=100)

        combined = combine_filters(filter1, filter2, filter3)

        assert combined.repos == ["repo1"]
        assert combined.languages == ["python"]
        assert combined.min_token_count == 100

    def test_combine_filters_token_counts(self):
        """Test combining token count filters (most restrictive)."""
        filter1 = FilterCriteria(min_token_count=100, max_token_count=500)
        filter2 = FilterCriteria(min_token_count=150, max_token_count=400)

        combined = combine_filters(filter1, filter2)

        # Should use most restrictive (highest min, lowest max)
        assert combined.min_token_count == 150
        assert combined.max_token_count == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
