"""Centralized retrieval hyperparameters.

All constants are tuned via A/B testing and documented with rationale.
Last tuned: 2025-11-13
"""

from dataclasses import dataclass


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

    # Score Adjustments
    CONFIG_FILE_SCORE_PENALTY: float = 0.5
    """Reduce config file scores by 50%.

    Rationale: Config files (JSON/TOML/YAML) frequently dominate results
    due to high chunk count but low semantic value. 50% penalty balances
    this while still allowing config files when highly relevant.
    A/B test: EXP-2024-10-15
    """

    # BM25 Normalization
    BM25_SCORE_NORMALIZATION_FACTOR: float = 10.0
    """Sigmoid normalization parameter for BM25 scores.

    Rationale: BM25 scores range [0, 50+] while vector scores are [0, 1].
    Dividing by 10 before sigmoid maps typical BM25 scores (1-20) to
    [0.27, 0.95] which aligns well with vector score distribution.

    NOTE: This is suboptimal. Future work will implement min-max
    normalization based on actual BM25 score distributions per dataset.
    See WP4.1 for improved normalization implementation.

    A/B test: EXP-2024-09-20 (scheduled for replacement)
    """

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
