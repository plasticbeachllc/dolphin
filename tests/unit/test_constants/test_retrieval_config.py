"""Tests for retrieval configuration constants."""

import pytest

from kb.constants.retrieval_config import RETRIEVAL_PARAMS, RetrievalConstants


class TestRetrievalConstants:
    """Test suite for RetrievalConstants."""

    def test_candidate_multiplier(self):
        """Test CANDIDATE_MULTIPLIER constant."""
        assert RETRIEVAL_PARAMS.CANDIDATE_MULTIPLIER == 4
        assert isinstance(RETRIEVAL_PARAMS.CANDIDATE_MULTIPLIER, int)
        assert RETRIEVAL_PARAMS.CANDIDATE_MULTIPLIER > 0

    def test_config_file_score_penalty(self):
        """Test CONFIG_FILE_SCORE_PENALTY constant."""
        assert RETRIEVAL_PARAMS.CONFIG_FILE_SCORE_PENALTY == 0.5
        assert isinstance(RETRIEVAL_PARAMS.CONFIG_FILE_SCORE_PENALTY, float)
        assert 0.0 <= RETRIEVAL_PARAMS.CONFIG_FILE_SCORE_PENALTY <= 1.0

    def test_bm25_score_normalization_factor(self):
        """Test BM25_SCORE_NORMALIZATION_FACTOR constant."""
        assert RETRIEVAL_PARAMS.BM25_SCORE_NORMALIZATION_FACTOR == 10.0
        assert isinstance(RETRIEVAL_PARAMS.BM25_SCORE_NORMALIZATION_FACTOR, float)
        assert RETRIEVAL_PARAMS.BM25_SCORE_NORMALIZATION_FACTOR > 0

    def test_rrf_k(self):
        """Test RRF_K constant."""
        assert RETRIEVAL_PARAMS.RRF_K == 60
        assert isinstance(RETRIEVAL_PARAMS.RRF_K, int)
        assert RETRIEVAL_PARAMS.RRF_K > 0

    def test_mmr_lambda_default(self):
        """Test MMR_LAMBDA_DEFAULT constant."""
        assert RETRIEVAL_PARAMS.MMR_LAMBDA_DEFAULT == 0.7
        assert isinstance(RETRIEVAL_PARAMS.MMR_LAMBDA_DEFAULT, float)
        assert 0.0 <= RETRIEVAL_PARAMS.MMR_LAMBDA_DEFAULT <= 1.0

    def test_search_timeout_seconds(self):
        """Test SEARCH_TIMEOUT_SECONDS constant."""
        assert RETRIEVAL_PARAMS.SEARCH_TIMEOUT_SECONDS == 30.0
        assert isinstance(RETRIEVAL_PARAMS.SEARCH_TIMEOUT_SECONDS, float)
        assert RETRIEVAL_PARAMS.SEARCH_TIMEOUT_SECONDS > 0

    def test_embedding_timeout_seconds(self):
        """Test EMBEDDING_TIMEOUT_SECONDS constant."""
        assert RETRIEVAL_PARAMS.EMBEDDING_TIMEOUT_SECONDS == 10.0
        assert isinstance(RETRIEVAL_PARAMS.EMBEDDING_TIMEOUT_SECONDS, float)
        assert RETRIEVAL_PARAMS.EMBEDDING_TIMEOUT_SECONDS > 0

    def test_result_cache_ttl_seconds(self):
        """Test RESULT_CACHE_TTL_SECONDS constant."""
        assert RETRIEVAL_PARAMS.RESULT_CACHE_TTL_SECONDS == 3600
        assert isinstance(RETRIEVAL_PARAMS.RESULT_CACHE_TTL_SECONDS, int)
        assert RETRIEVAL_PARAMS.RESULT_CACHE_TTL_SECONDS > 0

    def test_constants_are_frozen(self):
        """Test that RetrievalConstants is immutable (frozen dataclass)."""
        with pytest.raises(AttributeError):
            RETRIEVAL_PARAMS.CANDIDATE_MULTIPLIER = 10

    def test_global_singleton_instance(self):
        """Test that RETRIEVAL_PARAMS is a RetrievalConstants instance."""
        assert isinstance(RETRIEVAL_PARAMS, RetrievalConstants)

    def test_all_constants_have_values(self):
        """Test that all constant fields have non-None values."""
        assert RETRIEVAL_PARAMS.CANDIDATE_MULTIPLIER is not None
        assert RETRIEVAL_PARAMS.CONFIG_FILE_SCORE_PENALTY is not None
        assert RETRIEVAL_PARAMS.BM25_SCORE_NORMALIZATION_FACTOR is not None
        assert RETRIEVAL_PARAMS.RRF_K is not None
        assert RETRIEVAL_PARAMS.MMR_LAMBDA_DEFAULT is not None
        assert RETRIEVAL_PARAMS.SEARCH_TIMEOUT_SECONDS is not None
        assert RETRIEVAL_PARAMS.EMBEDDING_TIMEOUT_SECONDS is not None
        assert RETRIEVAL_PARAMS.RESULT_CACHE_TTL_SECONDS is not None

    def test_constant_value_ranges(self):
        """Test that constants are within reasonable ranges."""
        # Multipliers should be >= 1
        assert RETRIEVAL_PARAMS.CANDIDATE_MULTIPLIER >= 1

        # Penalties should be 0-1
        assert 0.0 <= RETRIEVAL_PARAMS.CONFIG_FILE_SCORE_PENALTY <= 1.0

        # Lambda should be 0-1
        assert 0.0 <= RETRIEVAL_PARAMS.MMR_LAMBDA_DEFAULT <= 1.0

        # Timeouts should be positive
        assert RETRIEVAL_PARAMS.SEARCH_TIMEOUT_SECONDS > 0
        assert RETRIEVAL_PARAMS.EMBEDDING_TIMEOUT_SECONDS > 0

        # TTL should be positive
        assert RETRIEVAL_PARAMS.RESULT_CACHE_TTL_SECONDS > 0

    def test_bm25_normalization_factor_reasonable(self):
        """Test that BM25 normalization factor is reasonable for sigmoid."""
        # For sigmoid normalization, factor should typically be 1-100
        assert 1.0 <= RETRIEVAL_PARAMS.BM25_SCORE_NORMALIZATION_FACTOR <= 100.0

    def test_rrf_k_reasonable(self):
        """Test that RRF K is within typical range from literature."""
        # K typically ranges from 10-100 in RRF literature
        assert 10 <= RETRIEVAL_PARAMS.RRF_K <= 100

    def test_timeout_hierarchy(self):
        """Test that search timeout is longer than embedding timeout."""
        # Search timeout should be longer since it includes embeddings + search
        assert RETRIEVAL_PARAMS.SEARCH_TIMEOUT_SECONDS > RETRIEVAL_PARAMS.EMBEDDING_TIMEOUT_SECONDS

    def test_create_new_instance(self):
        """Test creating a new RetrievalConstants instance with custom values."""
        custom = RetrievalConstants(
            CANDIDATE_MULTIPLIER=8,
            CONFIG_FILE_SCORE_PENALTY=0.3,
            BM25_SCORE_NORMALIZATION_FACTOR=15.0,
            RRF_K=50,
            MMR_LAMBDA_DEFAULT=0.8,
            SEARCH_TIMEOUT_SECONDS=60.0,
            EMBEDDING_TIMEOUT_SECONDS=15.0,
            RESULT_CACHE_TTL_SECONDS=7200,
        )

        assert custom.CANDIDATE_MULTIPLIER == 8
        assert custom.CONFIG_FILE_SCORE_PENALTY == 0.3
        assert custom.BM25_SCORE_NORMALIZATION_FACTOR == 15.0
        assert custom.RRF_K == 50
        assert custom.MMR_LAMBDA_DEFAULT == 0.8
        assert custom.SEARCH_TIMEOUT_SECONDS == 60.0
        assert custom.EMBEDDING_TIMEOUT_SECONDS == 15.0
        assert custom.RESULT_CACHE_TTL_SECONDS == 7200

    def test_constants_import_from_config_module(self):
        """Test that constants can be imported from kb.config."""
        from kb.constants import RETRIEVAL_PARAMS as imported_params, RetrievalConstants as imported_class

        assert imported_params is RETRIEVAL_PARAMS
        assert imported_class is RetrievalConstants
