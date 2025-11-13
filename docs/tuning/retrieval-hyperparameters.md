# Retrieval Hyperparameter Tuning

**Last Updated**: 2025-11-13
**Owner**: Search Team

## Methodology

All retrieval hyperparameters are tuned via A/B testing with statistical significance testing (p<0.05).

## Test Dataset

- **Size**: 1,000 hand-labeled queries from production logs
- **Relevance Judgments**: 3 independent annotators (majority vote)
- **Stratification**: Queries stratified by type
  - Identifier queries (e.g., "UserController class")
  - Concept queries (e.g., "authentication flow")
  - Example queries (e.g., "how to implement OAuth")

## Metrics

### Primary Metric
- **NDCG@10** (Normalized Discounted Cumulative Gain)
  - Measures ranking quality with position-based discounting
  - Range: [0, 1], higher is better
  - Threshold for significance: >5% relative improvement

### Secondary Metrics
- **MRR** (Mean Reciprocal Rank)
  - Average of reciprocal ranks of first relevant result
  - Sensitive to top-1 accuracy
- **Recall@5**
  - Fraction of relevant results in top 5
  - Measures coverage

## Active Experiments

### EXP-2024-09-20: BM25 Sigmoid Normalization (BASELINE)

**Status**: Active baseline (scheduled for replacement)

**Configuration**:
```python
BM25_SCORE_NORMALIZATION_FACTOR = 10.0
normalized_score = 1 / (1 + exp(-bm25_score / 10.0))
```

**Results**:
- NDCG@10: 0.72
- MRR: 0.68
- Recall@5: 0.85

**Known Issues**:
- Squashes scores into narrow range [0.27, 0.73]
- Factor=10 is arbitrary, not data-driven
- Loses discriminative power for very high/low scores

### EXP-2024-10-15: Config File Score Penalty

**Status**: Active production

**Hypothesis**: Config files dominate results due to high chunk count but provide low semantic value.

**Configuration**:
```python
CONFIG_FILE_SCORE_PENALTY = 0.5
```

**Results**:
- **Treatment** (50% penalty): NDCG@10 = 0.74 (+2.8%, p=0.003)
- **Control** (no penalty): NDCG@10 = 0.72

**Decision**: Deployed to production 2024-10-20

### EXP-2024-10-30: MMR Lambda Tuning

**Status**: Active production

**Hypothesis**: Too much diversity hurts code search UX where users expect similar results.

**Variants Tested**:
- λ=0.5 (50% diversity): NDCG@10 = 0.71
- λ=0.7 (30% diversity): NDCG@10 = 0.74 ✓
- λ=0.9 (10% diversity): NDCG@10 = 0.73

**Results**: λ=0.7 optimal, deployed to production 2024-11-05

### EXP-2024-11-01: Reranking Candidate Multiplier

**Status**: Active production

**Hypothesis**: Fetching more candidates for cross-encoder reranking improves precision.

**Variants Tested**:
- 1x candidates: NDCG@10 = 0.68
- 2x candidates: NDCG@10 = 0.72 (+5.9%, p<0.01)
- 4x candidates: NDCG@10 = 0.74 (+8.8%, p<0.01) ✓
- 8x candidates: NDCG@10 = 0.75 (+10.3%, p<0.01, but 2.3x latency)

**Decision**: 4x multiplier provides best precision/latency tradeoff

**Deployed**: 2024-11-10

## Planned Experiments

### EXP-2025-01: Min-Max BM25 Normalization

**Status**: Planned (Q1 2025)

**Hypothesis**: Min-max normalization preserves BM25 score distribution better than sigmoid.

**Variants**:
- **Control**: Sigmoid with factor=10
- **Treatment**: Min-max with p95 clipping

**Implementation Plan**:
1. Collect BM25 score statistics during indexing (100K+ samples)
2. Compute percentiles (p5, p25, p50, p75, p95, p99)
3. Implement min-max normalizer with p95 clipping
4. A/B test with 50/50 split, 10K queries

**Expected Completion**: 2025-02-15

See `kb/retrieval/bm25_normalizer.py` for implementation.

## Statistical Testing

### Sample Size Calculation

Minimum sample size for 80% power, α=0.05:
```
n = (2 * σ² * (z_α/2 + z_β)²) / δ²
```

Where:
- σ = baseline standard deviation (~0.15 for NDCG@10)
- δ = minimum detectable effect (0.05 = 5% relative improvement)
- z_α/2 = 1.96 (two-tailed, α=0.05)
- z_β = 0.84 (β=0.20, power=80%)

**Result**: n ≈ 900 queries per variant

### Significance Testing

Use Welch's t-test (unequal variances) for NDCG comparisons:
```python
from scipy import stats
t_stat, p_value = stats.ttest_ind(treatment, control, equal_var=False)
```

**Significance threshold**: p < 0.05

## Rollout Strategy

### Phase 1: Validation (10%)
- Deploy to 10% of traffic
- Monitor for 48 hours
- Check for regressions in latency, error rate

### Phase 2: Ramp (50%)
- Increase to 50% of traffic
- Monitor for 1 week
- Validate NDCG improvement holds

### Phase 3: Full Rollout (100%)
- Deploy to 100% of traffic
- Update baseline metrics
- Document in `kb/config/retrieval_config.py`

## References

1. Cormack, G. V., et al. (2009). "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods"
2. Carbonell, J., & Goldstein, J. (1998). "The use of MMR, diversity-based reranking for reordering documents and producing summaries"
3. Nogueira, R., & Cho, K. (2019). "Passage Re-ranking with BERT" (cross-encoder reranking)

## Contact

For questions about hyperparameter tuning:
- Search Team: search-team@example.com
- Metrics Discussion: #search-metrics Slack channel
