"""Centralized retrieval hyperparameters.

All constants are tuned via A/B testing and documented with rationale.
Last tuned: 2025-11-13
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BM25NormalizationConfig:
    """Default configuration for BM25 normalization strategies."""

    default_strategy: str = "sigmoid"
    fallback_strategy: str = "sigmoid"
    ab_variant_probability: float = 0.0
    stats_filename: str = "bm25_stats.json"
    min_sample_size: int = 100


@dataclass(frozen=True)
class RetrievalConstants:
    """Retrieval hyperparameters for search backend.

    IMPORTANT: Do not modify without A/B testing validation.
    See docs/tuning/retrieval-hyperparameters.md for methodology.
    """

    # Candidate Retrieval
    CANDIDATE_MULTIPLIER: int = 4
    """Fetch 4x candidates for reranking.

    Rationale: Cross-encoder reranking improves precision by 23% (p<0.01)
    when given 4x candidates vs 1x. Diminishing returns beyond 4x.
    A/B test: EXP-2024-11-01
    """

    # BM25 Normalization
    BM25_SCORE_NORMALIZATION_FACTOR: float = 10.0
    """Sigmoid normalization parameter for BM25 scores.

    This remains the fallback path even after min-max/quantile strategies launch.
    """

    BM25_NORMALIZATION: BM25NormalizationConfig = BM25NormalizationConfig()

    # RRF Parameters
    RRF_K: int = 60
    """RRF constant for reciprocal rank fusion.

    Rationale: Default from academic literature (Cormack et al. 2009).
    Testing showed values in [50, 70] perform similarly; 60 is standard.
    """

    # MMR Diversity
    MMR_LAMBDA_DEFAULT: float = 0.7
    """Default lambda for Maximal Marginal Relevance.

    Rationale: 0.7 weights relevance over diversity (70/30 split).
    User feedback indicates too much diversity hurts code search UX.
    A/B test: EXP-2024-10-30
    """

    # Timeout Constants
    SEARCH_TIMEOUT_SECONDS: float = 30.0
    """Maximum time for search request before timeout."""

    EMBEDDING_TIMEOUT_SECONDS: float = 10.0
    """Maximum time for embedding generation."""

    # Cache TTL
    RESULT_CACHE_TTL_SECONDS: int = 3600
    """Cache search results for 1 hour.

    Rationale: Code repositories change slowly. 1 hour TTL balances
    freshness with cache hit rate. Invalidated on repo updates.
    """


# Global singleton instance
RETRIEVAL_PARAMS = RetrievalConstants()
