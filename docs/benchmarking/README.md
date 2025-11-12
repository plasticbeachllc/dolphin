# Dolphin Benchmarking Framework

Comprehensive benchmarking and evaluation framework for the Dolphin knowledge base system.

## Overview

This framework provides systematic measurement of Dolphin's performance across two key dimensions:

1. **Performance Benchmarks** - Latency, throughput, and resource utilization
2. **Retrieval Quality** - Accuracy metrics (MRR, Precision@K, Recall@K)

## Quick Start

### Running Performance Benchmarks

```bash
# Benchmark ANN parameters (latency, recall, speedup)
uv run scripts/benchmark_ann.py --iterations 100 --output results/ann_benchmark.json

# Run full performance suite
just benchmark-performance
```

### Running Retrieval Evaluation

```bash
# Evaluate retrieval quality against golden scenarios
uv run scripts/eval_retrieval.py --scenarios golden-scenarios/ --output results/eval.json

# Run full evaluation suite
just eval
```

## Documentation Structure

- **[Metrics Reference](./metrics.md)** - Detailed definitions of all metrics (MRR, P@K, R@K, latency)
- **[Golden Scenarios](./golden-scenarios.md)** - Format specification and creation guide
- **[Performance Benchmarks](./performance-benchmarks.md)** - Latency and throughput testing
- **[Retrieval Evaluation](./retrieval-evaluation.md)** - Quality assessment methodology
- **[CI Integration](./ci-integration.md)** - Automated benchmarking in CI/CD pipelines
- **[Best Practices](./best-practices.md)** - Guidelines for reliable benchmarking

## Why Benchmark?

### Regression Prevention

- Gate changes that degrade performance or quality
- Track metrics over time to catch regressions early
- Enforce quality SLAs before merging

### Informed Optimization

- Identify bottlenecks with data
- Compare configurations objectively
- Validate optimization hypotheses

### Transparency

- Communicate system capabilities clearly
- Set realistic user expectations
- Track progress toward goals

## Key Metrics

### Performance Metrics

| Metric          | Definition                         | Target    |
| --------------- | ---------------------------------- | --------- |
| **p50 latency** | Median query response time         | < 50ms    |
| **p95 latency** | 95th percentile response time      | < 150ms   |
| **p99 latency** | 99th percentile response time      | < 300ms   |
| **Throughput**  | Queries per second                 | > 100 QPS |
| **Recall@10**   | Fraction of relevant results found | > 95%     |

### Quality Metrics

| Metric   | Definition              | Target |
| -------- | ----------------------- | ------ |
| **MRR**  | Mean Reciprocal Rank    | > 0.85 |
| **P@5**  | Precision at 5 results  | > 0.80 |
| **P@10** | Precision at 10 results | > 0.70 |
| **R@10** | Recall at 10 results    | > 0.90 |

See [Metrics Reference](./metrics.md) for detailed definitions.

## Golden Scenarios

Golden scenarios are curated test cases that capture expected retrieval behavior:

```json
{
  "id": "python-function-search",
  "query": "function to parse markdown tables",
  "repo": "dolphin",
  "expected_results": [
    {
      "file": "kb/parsers/markdown.py",
      "symbol": "parse_table",
      "rank": 1
    }
  ],
  "metadata": {
    "category": "code-search",
    "difficulty": "medium"
  }
}
```

See [Golden Scenarios](./golden-scenarios.md) for the complete specification.

## Continuous Benchmarking

Benchmarks run automatically in CI:

- **Every PR** - Fast smoke tests (< 30s)
- **Daily** - Full benchmark suite with reports
- **Weekly** - Comprehensive evaluation with trend analysis

Results are published as artifacts and tracked over time.

See [CI Integration](./ci-integration.md) for implementation details.

## Architecture

```
docs/benchmarking/          # Documentation (you are here)
scripts/
  ├── benchmark_ann.py      # ANN parameter benchmarking
  ├── eval_retrieval.py     # Retrieval quality evaluation
  └── benchmark_suite.py    # Comprehensive benchmark runner
golden-scenarios/           # Test scenarios for evaluation
  ├── code-search/         # Code search scenarios
  ├── semantic-search/     # Semantic search scenarios
  └── hybrid-search/       # Hybrid search scenarios
results/                    # Benchmark outputs (gitignored)
  ├── ann_benchmark.json
  ├── eval_report.json
  └── trends/              # Historical tracking
```

## Contributing

When adding features or optimizations:

1. **Establish baseline** - Run benchmarks before changes
2. **Make changes** - Implement your feature/optimization
3. **Measure impact** - Run benchmarks after changes
4. **Compare results** - Analyze differences
5. **Update scenarios** - Add golden scenarios for new capabilities

See [Best Practices](./best-practices.md) for detailed guidelines.

## Next Steps

- Read [Metrics Reference](./metrics.md) to understand what we measure
- Review [Golden Scenarios](./golden-scenarios.md) to create test cases
- Check [Performance Benchmarks](./performance-benchmarks.md) for latency testing
- Explore [Retrieval Evaluation](./retrieval-evaluation.md) for quality assessment
- Learn [CI Integration](./ci-integration.md) to automate benchmarking

## Resources

- **Existing benchmarks**: `scripts/benchmark_ann.py`
- **Integration tests**: `tests/integration/test_kb_search.py`
- **Improvement proposals**: `docs/repo-improvements.md` (item #5)
- **Performance guide**: `docs/GUIDE.md` (Performance Benchmarking section)
