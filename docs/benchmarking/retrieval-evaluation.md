# Retrieval Evaluation

Systematic methodology for evaluating retrieval quality using golden scenarios and information retrieval metrics.

## Table of Contents

- [Overview](#overview)
- [Evaluation Process](#evaluation-process)
- [Running Evaluations](#running-evaluations)
- [Interpreting Results](#interpreting-results)
- [Configuration Testing](#configuration-testing)
- [Failure Analysis](#failure-analysis)
- [Continuous Evaluation](#continuous-evaluation)

---

## Overview

### What is Retrieval Evaluation?

Retrieval evaluation measures **how well the system finds relevant results** for queries. Unlike performance benchmarks (speed), retrieval evaluation focuses on **quality** (accuracy, relevance, ranking).

### Key Questions

- Does the system find the right results?
- Are the most relevant results ranked highest?
- How often does it miss important results?
- How many irrelevant results appear in top-K?

### Metrics Used

| Metric | What it measures | Target |
|--------|------------------|--------|
| **MRR** | Ranking quality (position of first relevant result) | > 0.85 |
| **P@5** | Precision (fraction of top-5 that are relevant) | > 0.80 |
| **P@10** | Precision (fraction of top-10 that are relevant) | > 0.70 |
| **R@10** | Recall (fraction of relevant results found) | > 0.90 |
| **MAP** | Overall ranking quality (all relevant results) | > 0.80 |

See [Metrics Reference](./metrics.md) for detailed definitions.

---

## Evaluation Process

### Step 1: Prepare Golden Scenarios

Golden scenarios define expected behavior for test queries.

```bash
# Scenario structure
golden-scenarios/
├── code-search/
│   ├── exact-match/
│   │   └── lancedb-store.json
│   └── description-based/
│       └── parse-markdown.json
├── semantic-search/
│   └── architecture/
│       └── authentication.json
└── hybrid-search/
    └── framework-specific/
        └── fastapi-endpoints.json
```

See [Golden Scenarios](./golden-scenarios.md) for format specification.

### Step 2: Index Test Repository

Ensure the knowledge base is up-to-date:

```bash
# Index the repository under test
dolphin index /path/to/repo

# Verify index status
dolphin kb status
```

### Step 3: Run Evaluation

Execute the evaluation script against golden scenarios:

```bash
# Evaluate all scenarios
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/ \
  --output results/eval.json

# Evaluate specific category
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/code-search/ \
  --output results/code_search_eval.json

# Verbose mode (show per-query results)
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/ \
  --verbose
```

### Step 4: Analyze Results

Review the evaluation report:

```bash
# View JSON results
cat results/eval.json | jq '.summary'

# Generate HTML report
python scripts/generate_eval_report.py \
  results/eval.json \
  --output results/eval_report.html

# Open in browser
open results/eval_report.html
```

---

## Running Evaluations

### Basic Evaluation

```bash
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/ \
  --output results/eval.json
```

**Expected output**:
```
==================================================
RETRIEVAL EVALUATION
==================================================

Loading scenarios: golden-scenarios/
Found 52 scenarios across 4 categories

Indexing repository...
Index complete: 10,234 chunks from 245 files

Running evaluation...
[████████████████████████████████████████] 52/52

==================================================
SUMMARY
==================================================

Total scenarios: 52
Passed: 48 (92.3%)
Failed: 4 (7.7%)

Overall metrics:
  MRR:      0.872  ✓ (target: 0.85)
  P@5:      0.804  ✓ (target: 0.80)
  P@10:     0.712  ✓ (target: 0.70)
  R@10:     0.934  ✓ (target: 0.90)
  MAP:      0.823  ✓ (target: 0.80)

By category:
  code-search:      MRR 0.91, P@5 0.85  ✓
  semantic-search:  MRR 0.82, P@5 0.76  ⚠ (below target)
  hybrid-search:    MRR 0.88, P@5 0.81  ✓
  navigation:       MRR 0.78, P@5 0.70  ⚠ (below target)

Status: PASS (overall targets met)

Failures:
  1. semantic-search-ambiguous-query
  2. navigation-cross-repo-usage
  3. semantic-search-rare-concept
  4. code-search-nested-class

See results/eval.json for details.
```

### Detailed Evaluation

```bash
# Verbose mode - show per-query results
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/ \
  --verbose
```

**Per-query output**:
```
──────────────────────────────────────────────────
Query: "function to parse markdown tables"
ID: code-search-parse-markdown
Category: code-search | Difficulty: medium
──────────────────────────────────────────────────

Expected results (3):
  1. kb/parsers/markdown.py::parse_table (relevance: 1.0)
  2. kb/parsers/markdown.py::extract_table_rows (relevance: 0.8)
  3. tests/unit/parsers/test_markdown.py::test_parse_table (relevance: 0.6)

Actual results (top 5):
  1. kb/parsers/markdown.py::parse_table ✓ (score: 0.95)
  2. kb/parsers/markdown.py::extract_table_rows ✓ (score: 0.87)
  3. kb/parsers/utils.py::split_table_cells (score: 0.72)
  4. tests/unit/parsers/test_markdown.py::test_parse_table ✓ (score: 0.68)
  5. kb/parsers/base.py::Parser (score: 0.55)

Metrics:
  MRR:   1.00  (first result at rank 1) ✓
  P@5:   0.60  (3/5 expected results found)
  R@10:  1.00  (all expected results found)

Status: PASS
```

### Configuration-Specific Evaluation

Test different retrieval configurations:

```bash
# Test with specific ANN parameters
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/ \
  --nprobes 10 \
  --refine-factor 5 \
  --output results/eval_default.json

# Test with speed-optimized config
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/ \
  --nprobes 5 \
  --refine-factor 3 \
  --output results/eval_fast.json

# Test with accuracy-optimized config
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/ \
  --nprobes 20 \
  --refine-factor 10 \
  --output results/eval_accurate.json

# Compare configurations
python scripts/compare_eval.py \
  results/eval_default.json \
  results/eval_fast.json \
  results/eval_accurate.json
```

### Reranking Evaluation

Test with and without reranking:

```bash
# Without reranking
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/ \
  --no-rerank \
  --output results/eval_no_rerank.json

# With reranking (default)
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/ \
  --output results/eval_with_rerank.json

# Compare impact of reranking
python scripts/compare_eval.py \
  results/eval_no_rerank.json \
  results/eval_with_rerank.json
```

---

## Interpreting Results

### Summary Metrics

```json
{
  "summary": {
    "total_scenarios": 52,
    "passed": 48,
    "failed": 4,
    "pass_rate": 0.923,
    "metrics": {
      "mrr": 0.872,
      "map": 0.823,
      "p@5": 0.804,
      "p@10": 0.712,
      "r@10": 0.934
    }
  }
}
```

**Interpretation**:
- **Pass rate: 92.3%** - Most scenarios pass
- **MRR: 0.872** - First relevant result typically at rank 1-2
- **P@5: 0.804** - About 4 out of 5 top results are relevant
- **R@10: 0.934** - System finds 93% of relevant results in top-10

**Status**: PASS (all metrics exceed targets)

### Per-Category Breakdown

```json
{
  "by_category": {
    "code-search": {
      "count": 24,
      "metrics": {
        "mrr": 0.912,
        "p@5": 0.850
      },
      "status": "pass"
    },
    "semantic-search": {
      "count": 16,
      "metrics": {
        "mrr": 0.821,
        "p@5": 0.756
      },
      "status": "warning"
    }
  }
}
```

**Interpretation**:
- **Code search**: Excellent performance (MRR 0.91)
- **Semantic search**: Acceptable but below target (P@5 0.76)

**Action**: Investigate semantic search failures.

### Per-Difficulty Breakdown

```json
{
  "by_difficulty": {
    "easy": {
      "count": 26,
      "metrics": {"mrr": 0.981},
      "pass_rate": 1.00
    },
    "medium": {
      "count": 18,
      "metrics": {"mrr": 0.854},
      "pass_rate": 0.944
    },
    "hard": {
      "count": 8,
      "metrics": {"mrr": 0.612},
      "pass_rate": 0.625
    }
  }
}
```

**Interpretation**:
- **Easy**: Near-perfect (MRR 0.98)
- **Medium**: Good (MRR 0.85)
- **Hard**: Poor (MRR 0.61, only 62.5% pass)

**Action**: Focus on improving hard scenarios.

---

## Configuration Testing

### Comparing Configurations

Test different settings to find optimal configuration:

```bash
# Generate comparison report
python scripts/eval_configs.py \
  --scenarios golden-scenarios/ \
  --configs configs/eval_configs.yaml \
  --output results/config_comparison.json
```

**configs/eval_configs.yaml**:
```yaml
configurations:
  - name: default
    nprobes: 10
    refine_factor: 5
    rerank: true

  - name: fast
    nprobes: 5
    refine_factor: 3
    rerank: false

  - name: accurate
    nprobes: 20
    refine_factor: 10
    rerank: true

  - name: balanced
    nprobes: 12
    refine_factor: 6
    rerank: true
```

**Comparison output**:
```
==================================================
CONFIGURATION COMPARISON
==================================================

Configuration           MRR    P@5    R@10   Latency
──────────────────────────────────────────────────────
default (baseline)     0.872  0.804  0.934   42 ms
fast                   0.834  0.756  0.901   18 ms  📉 quality, 📈 speed
accurate               0.891  0.823  0.956   78 ms  📈 quality, 📉 speed
balanced               0.881  0.812  0.945   52 ms  slight improvement

Recommendation: Use 'balanced' for best quality/latency trade-off
  - 1% MRR improvement over default
  - 1% P@5 improvement over default
  - Only 10ms latency increase
```

### Quality vs Speed Trade-off

Visualize the efficiency frontier:

```bash
python scripts/plot_quality_vs_speed.py \
  results/config_comparison.json \
  --output results/quality_speed_tradeoff.png
```

Expected plot:
```
MRR
0.90 ┤                    ●accurate
0.88 ┤              ●balanced
0.87 ┤         ●default
0.85 ┤
0.83 ┤   ●fast
     └────────────────────────────> Latency
      0ms   20ms  40ms  60ms  80ms

Optimal: 'balanced' at the knee of the curve
```

---

## Failure Analysis

### Identifying Failures

```bash
# List failed scenarios
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/ \
  --show-failures
```

**Output**:
```
==================================================
FAILED SCENARIOS (4)
==================================================

1. semantic-search-ambiguous-query
   Query: "store"
   Expected: kb/store/lancedb_store.py::LanceDBStore at rank 1
   Actual: kb/store/sqlite_meta.py::SQLiteMetadataStore at rank 1
   MRR: 0.50 (expected at rank 2)
   Issue: Ambiguous query - multiple valid interpretations

2. navigation-cross-repo-usage
   Query: "find all usages of ANNParams"
   Expected: 5 files
   Found: 3 files in top-10
   R@10: 0.60 (below 0.90 target)
   Issue: Missing usages in test files

3. semantic-search-rare-concept
   Query: "code that implements exponential backoff"
   Expected: kb/utils/retry.py::exponential_backoff
   Actual: Not found in top-10
   MRR: 0.00
   Issue: Rare terminology not well represented

4. code-search-nested-class
   Query: "NestedIterator class"
   Expected: kb/parsers/base.py::Parser.NestedIterator
   Actual: Not found in top-10
   MRR: 0.00
   Issue: Nested class not chunked properly
```

### Categorizing Failures

**Failure types**:

| Type | Description | Fix |
|------|-------------|-----|
| **Ambiguous query** | Multiple valid interpretations | Add context to query or accept lower MRR |
| **Missing result** | Expected result not in index | Check chunking and indexing |
| **Poor ranking** | Expected result present but low rank | Tune ANN params or reranking |
| **Incomplete coverage** | Missing usages/references | Improve code graph extraction |
| **Rare terms** | Low-frequency concepts not well represented | Increase training data or use keyword fallback |

### Debugging Individual Scenarios

```bash
# Debug specific scenario
python scripts/debug_scenario.py \
  --scenario golden-scenarios/semantic-search/rare-concept.json \
  --top-k 20 \
  --explain
```

**Debug output**:
```
==================================================
SCENARIO DEBUG
==================================================

Query: "code that implements exponential backoff"
ID: semantic-search-rare-concept

Query embedding (top terms):
  - "exponential": 0.85
  - "backoff": 0.82
  - "implements": 0.71
  - "code": 0.65

Expected result:
  File: kb/utils/retry.py
  Symbol: exponential_backoff
  Chunk: "def exponential_backoff(attempt, base=2, max_delay=60)..."

Chunk embedding (top terms):
  - "retry": 0.88
  - "delay": 0.84
  - "attempt": 0.79
  - "sleep": 0.75
  - "exponential": 0.68  ⚠ lower than expected

Similarity: 0.67 (rank: 12)

Analysis:
  - Chunk uses "retry" and "delay" terminology
  - Query uses "exponential backoff"
  - Semantic gap between terminology
  - Suggestion: Add keyword boosting for exact term matches
```

---

## Continuous Evaluation

### Evaluation in CI

Run evaluations automatically on every PR:

```yaml
# .github/workflows/eval.yml
name: Retrieval Evaluation

on: [pull_request]

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup environment
        run: |
          pip install -e .
          # Setup test index

      - name: Run evaluation
        run: |
          python scripts/eval_retrieval.py \
            --scenarios golden-scenarios/ \
            --output results/eval.json

      - name: Compare to baseline
        run: |
          python scripts/compare_eval.py \
            baseline/eval.json \
            results/eval.json \
            --threshold 0.05 \
            --fail-on-regression

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: eval-results
          path: results/eval.json
```

### Regression Detection

```bash
# Compare to baseline
python scripts/compare_eval.py \
  baseline/eval.json \
  results/current.json \
  --threshold 0.05
```

**Output**:
```
==================================================
EVALUATION COMPARISON
==================================================

Baseline: baseline/eval.json (2025-11-01)
Current:  results/current.json (2025-11-11)

Overall metrics:
  MRR:  0.872 → 0.854  (📉 2.1% regression) ⚠
  P@5:  0.804 → 0.798  (📉 0.7% regression)
  P@10: 0.712 → 0.725  (📈 1.8% improvement) ✓
  R@10: 0.934 → 0.945  (📈 1.2% improvement) ✓

Status: ⚠ WARNING - MRR regression

New failures (2):
  - code-search-async-function
  - semantic-search-error-handling

Newly passing (1):
  + navigation-import-tracking

Recommendation: Investigate MRR regression before merging
```

### Trend Tracking

Track metrics over time:

```bash
# Collect historical results
python scripts/track_eval_trends.py \
  --results-dir results/history/ \
  --output results/trends.json

# Visualize trends
python scripts/plot_eval_trends.py \
  results/trends.json \
  --output results/trends.png
```

Expected trend plot:
```
MRR
0.90 ┤                          ●
0.88 ┤                    ●   ●
0.86 ┤              ●   ●
0.84 ┤         ●  ●
0.82 ┤    ●  ●
0.80 ┤  ●
     └──────────────────────────────> Time
     Jan  Feb  Mar  Apr  May  Jun

Target: 0.85 (dashed line)
Trend: +2.3% per month (improving)
```

---

## Best Practices

### Creating Scenarios

1. **Start small**: Begin with 10-20 core scenarios
2. **Cover variety**: Include easy, medium, and hard cases
3. **Use real queries**: Base scenarios on actual user searches
4. **Update regularly**: Add scenarios for new features and bug fixes

### Running Evaluations

1. **Baseline first**: Establish baseline before making changes
2. **Evaluate frequently**: Run on every significant change
3. **Test configurations**: Compare multiple settings
4. **Analyze failures**: Don't just count failures - understand why

### Interpreting Results

1. **Look at trends**: Single-run variance is normal
2. **Consider trade-offs**: Perfect metrics aren't always necessary
3. **Prioritize by impact**: Focus on high-frequency query types
4. **Use thresholds wisely**: Set realistic, achievable targets

---

## Evaluation Checklist

Before merging changes:

- [ ] Run full evaluation against all golden scenarios
- [ ] Compare to baseline (< 5% regression)
- [ ] Analyze any new failures
- [ ] Update scenarios if behavior intentionally changed
- [ ] Document trade-offs (if quality decreased for speed)
- [ ] Update baseline if improvements are significant

---

## Tools and Scripts

| Script | Purpose |
|--------|---------|
| `scripts/eval_retrieval.py` | Main evaluation runner |
| `scripts/compare_eval.py` | Compare evaluation results |
| `scripts/eval_configs.py` | Test multiple configurations |
| `scripts/debug_scenario.py` | Debug individual scenarios |
| `scripts/generate_eval_report.py` | Generate HTML reports |
| `scripts/track_eval_trends.py` | Track metrics over time |
| `scripts/plot_quality_vs_speed.py` | Visualize trade-offs |

---

## Summary

**Retrieval evaluation measures quality**:
- MRR: Ranking of first relevant result
- P@K: Precision (relevance of top-K)
- R@K: Recall (coverage of relevant results)

**Process**:
1. Create golden scenarios
2. Run evaluation
3. Analyze results
4. Fix failures or accept trade-offs
5. Update baseline

**Continuous evaluation**:
- Run on every PR
- Track trends over time
- Alert on regressions
- Update scenarios as code evolves

**Next**: See [CI Integration](./ci-integration.md) for automation.
