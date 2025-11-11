# Performance Benchmarking

Guide to measuring and optimizing latency, throughput, and resource utilization in Dolphin.

## Table of Contents

- [Overview](#overview)
- [Latency Benchmarks](#latency-benchmarks)
- [Throughput Benchmarks](#throughput-benchmarks)
- [ANN Parameter Tuning](#ann-parameter-tuning)
- [Resource Benchmarks](#resource-benchmarks)
- [Regression Testing](#regression-testing)
- [Optimization Guide](#optimization-guide)

---

## Overview

### What We Measure

**Latency**: How fast individual operations complete
**Throughput**: How many operations we can handle concurrently
**Resources**: Memory, CPU, and I/O utilization
**Scalability**: Performance as data size grows

### Why It Matters

- **User experience**: Fast queries feel responsive
- **Scalability**: Handle more users and data
- **Cost**: Efficiency reduces infrastructure costs
- **Reliability**: Consistent performance builds trust

### Target Metrics

| Metric | Target | Stretch Goal |
|--------|--------|--------------|
| Query p50 latency | < 50ms | < 30ms |
| Query p95 latency | < 150ms | < 100ms |
| Query p99 latency | < 300ms | < 200ms |
| Throughput (1 user) | > 20 QPS | > 50 QPS |
| Throughput (10 users) | > 100 QPS | > 200 QPS |
| Index throughput | > 100 files/sec | > 200 files/sec |
| Memory (10K files) | < 2GB | < 1GB |

---

## Latency Benchmarks

### Query Latency

Measure end-to-end query response time including vector search, reranking, and result formatting.

#### Running the Benchmark

```bash
# Quick benchmark (10 queries, 10 iterations each)
python scripts/benchmark_query.py --queries 10 --iterations 10

# Thorough benchmark (100 queries, 100 iterations each)
python scripts/benchmark_query.py --queries 100 --iterations 100 --output results/latency.json

# With specific ANN parameters
python scripts/benchmark_query.py \
  --queries 50 \
  --nprobes 10 \
  --refine-factor 5
```

#### Expected Output

```
==================================================
QUERY LATENCY BENCHMARK
==================================================

Configuration:
  Queries: 100
  Iterations per query: 100
  Vector dimension: 1536
  Top-K: 10
  ANN params: nprobes=10, refine_factor=5

Results:
  p50 latency:   42.3 ms
  p95 latency:   89.7 ms
  p99 latency:  156.2 ms
  Mean latency:  51.8 ms
  Std dev:       28.4 ms
  Min:           18.3 ms
  Max:          234.1 ms

Status: PASS (p50 < 50ms, p95 < 150ms)
```

#### Breakdown by Component

```bash
# Detailed profiling
python scripts/benchmark_query.py --profile --queries 20
```

Expected breakdown:
```
Component breakdown (average):
  Vector embedding:     5.2 ms  (10%)
  ANN search:          28.1 ms  (54%)
  Reranking:           12.3 ms  (24%)
  Result formatting:    4.2 ms   (8%)
  Overhead:             2.1 ms   (4%)
  ─────────────────────────────────────
  Total:               51.9 ms  (100%)
```

### Indexing Latency

Measure time to index files including chunking, embedding, and vector storage.

#### Running the Benchmark

```bash
# Index benchmark on fixture repo
python scripts/benchmark_index.py --repo tests/fixtures/test_repo

# Index benchmark on large corpus
python scripts/benchmark_index.py \
  --repo /path/to/large/repo \
  --file-count 1000 \
  --output results/index_latency.json
```

#### Expected Output

```
==================================================
INDEXING LATENCY BENCHMARK
==================================================

Repository: tests/fixtures/test_repo
Files: 50 Python files
Total size: 250 KB

Results:
  Total time:       12.3 seconds
  Files per second: 4.06 files/sec
  Throughput:       20.3 KB/sec

Per-file breakdown:
  p50: 180 ms
  p95: 420 ms
  p99: 680 ms

Per-component (average per file):
  File reading:     12 ms   (7%)
  Chunking:         35 ms  (19%)
  Embedding:       115 ms  (64%)
  Vector storage:   18 ms  (10%)
  ───────────────────────────────
  Total:           180 ms (100%)
```

---

## Throughput Benchmarks

### Concurrent Query Throughput

Measure queries per second with multiple concurrent users.

#### Running the Benchmark

```bash
# Single user throughput
python scripts/benchmark_throughput.py --users 1 --duration 60

# Multi-user throughput
python scripts/benchmark_throughput.py --users 10 --duration 60

# Load test
python scripts/benchmark_throughput.py \
  --users 50 \
  --duration 300 \
  --ramp-up 30 \
  --output results/load_test.json
```

#### Expected Output

```
==================================================
THROUGHPUT BENCHMARK
==================================================

Configuration:
  Concurrent users: 10
  Duration: 60 seconds
  Ramp-up: 10 seconds

Results:
  Total queries:     6,543
  Successful:        6,540 (99.95%)
  Failed:                3 (0.05%)

  Throughput:        109.0 QPS

  Latency distribution:
    p50:   52 ms
    p95:  198 ms
    p99:  367 ms

  Per-user metrics:
    Avg queries/user: 654
    Avg QPS/user: 10.9

Status: PASS (> 100 QPS target)
```

#### Scaling Analysis

```bash
# Test scaling from 1 to 100 users
python scripts/benchmark_scaling.py \
  --min-users 1 \
  --max-users 100 \
  --step 10 \
  --duration 30
```

Expected analysis:
```
User count vs Throughput:
   1 user:    22 QPS  (100% of linear)
   5 users:   95 QPS   (86% of linear)
  10 users:  172 QPS   (78% of linear)
  25 users:  380 QPS   (69% of linear)
  50 users:  650 QPS   (59% of linear)
 100 users: 1020 QPS   (46% of linear)

Bottleneck analysis:
  1-10 users:   CPU-bound (vector operations)
  10-50 users:  Balanced (CPU + I/O)
  50+ users:    I/O-bound (embedding API rate limits)
```

### Batch Indexing Throughput

Measure sustained indexing performance.

#### Running the Benchmark

```bash
# Generate synthetic test data
python scripts/generate_test_repo.py \
  --files 10000 \
  --output /tmp/test_repo_10k

# Benchmark indexing throughput
python scripts/benchmark_index_throughput.py \
  --repo /tmp/test_repo_10k \
  --batch-size 100 \
  --output results/index_throughput.json
```

#### Expected Output

```
==================================================
INDEXING THROUGHPUT BENCHMARK
==================================================

Repository: /tmp/test_repo_10k
Files: 10,000
Total size: 50 MB

Results:
  Total time:       620 seconds (10.3 minutes)
  Files per second: 16.1 files/sec
  Throughput:       82.6 KB/sec

  Chunks created:   125,430
  Vectors stored:   125,430

  Phase breakdown:
    Scanning:         12 sec   (2%)
    Chunking:        185 sec  (30%)
    Embedding:       380 sec  (61%)
    Storage:          43 sec   (7%)

  Resource usage:
    Peak memory:     1.8 GB
    Avg CPU:         65%
    Disk writes:     2.1 GB
```

---

## ANN Parameter Tuning

Optimize ANN parameters for the best latency/recall trade-off.

### Running ANN Benchmarks

```bash
# Use existing benchmark script
python scripts/benchmark_ann.py \
  --store-path ~/.dolphin/knowledge_store \
  --queries 50 \
  --iterations 100 \
  --output results/ann_benchmark.json
```

### Understanding Results

The benchmark tests multiple ANN configurations:

```
==================================================
ANN PARAMETER BENCHMARKING
==================================================

Configuration                  p50 (ms)  p95 (ms)  Recall  Speedup
────────────────────────────────────────────────────────────────────
default (nprobes=10, refine=5)   28.3      62.1     0.96    8.2x
speed (nprobes=5, refine=3)      15.7      34.2     0.91   15.1x
accuracy (nprobes=20, refine=10) 52.8     118.4     0.99    4.3x
custom_fast (nprobes=5, refine=3)15.9      35.1     0.91   14.8x
custom_balanced (nprobes=15, refine=8) 38.2  84.7   0.97    6.1x
────────────────────────────────────────────────────────────────────

Recommendation: Use 'default' for balanced performance/accuracy
```

### Choosing Configuration

**Decision matrix**:

| Use case | Configuration | Rationale |
|----------|--------------|-----------|
| **Interactive search** | `default` (nprobes=10) | Best balance of speed and accuracy |
| **Batch processing** | `accuracy` (nprobes=20) | Quality over speed |
| **High QPS** | `speed` (nprobes=5) | Maximize throughput |
| **Production** | `default` or custom | Tune based on actual query patterns |

### Custom Tuning

Create custom configurations:

```python
from kb.retrieval.ann_tuning import ANNParams

# Start with defaults
params = ANNParams()  # nprobes=10, refine_factor=5

# Tune for lower latency (sacrifice some recall)
fast_params = ANNParams(nprobes=7, refine_factor=4)

# Tune for higher accuracy (accept higher latency)
accurate_params = ANNParams(nprobes=15, refine_factor=8)

# Benchmark your custom config
python scripts/benchmark_ann.py --nprobes 7 --refine-factor 4
```

### Efficiency Frontier

Plot recall vs latency to find the optimal point:

```bash
# Generate efficiency frontier data
python scripts/ann_efficiency_frontier.py \
  --output results/efficiency_frontier.json

# Visualize
python scripts/plot_efficiency_frontier.py \
  results/efficiency_frontier.json \
  --output results/efficiency_frontier.png
```

Expected plot:
```
Recall
 1.00 ┤                              ●accuracy
 0.98 ┤                        ●balanced
 0.96 ┤                  ●default
 0.94 ┤            ●
 0.92 ┤      ●speed
 0.90 ┤●
      └────────────────────────────────────> Latency (ms)
       0    20    40    60    80   100  120

Recommendation: Operate at the "knee" of the curve
                (default: 0.96 recall @ 28ms)
```

---

## Resource Benchmarks

### Memory Profiling

Track memory usage during indexing and querying.

#### Running Memory Benchmarks

```bash
# Memory profile during indexing
python scripts/benchmark_memory.py \
  --operation index \
  --repo /path/to/repo \
  --output results/memory_index.json

# Memory profile during queries
python scripts/benchmark_memory.py \
  --operation query \
  --queries 1000 \
  --output results/memory_query.json
```

#### Expected Output

```
==================================================
MEMORY BENCHMARK
==================================================

Operation: Indexing
Repository: 10,000 files (50 MB)

Memory usage:
  Baseline:        120 MB  (before indexing)
  Peak:          1,950 MB  (during embedding)
  Final:           340 MB  (after completion)

  Peak by phase:
    Scanning:      145 MB
    Chunking:      580 MB
    Embedding:   1,950 MB  (peak)
    Storage:       820 MB

  Per-file average: 195 KB

Warnings:
  - Peak memory during embedding phase
  - Consider batch size tuning to reduce peak
```

### CPU Profiling

Identify CPU bottlenecks.

#### Running CPU Benchmarks

```bash
# CPU profile with py-spy
py-spy record -o results/cpu_profile.svg -- \
  python scripts/benchmark_query.py --queries 100

# View flame graph
open results/cpu_profile.svg
```

Expected hotspots:
- `lancedb_store.query`: 35% (vector search)
- `reranker.rerank`: 25% (reranking)
- `embeddings.embed_texts`: 20% (embedding generation)
- `json.loads/dumps`: 10% (serialization)
- Other: 10%

### I/O Profiling

Monitor disk and network I/O.

```bash
# Monitor I/O during benchmark
iostat -x 1 > results/iostat.log &
python scripts/benchmark_index.py --repo /path/to/repo
kill %1

# Analyze I/O patterns
python scripts/analyze_iostat.py results/iostat.log
```

---

## Regression Testing

### Baseline Establishment

Establish performance baselines for regression detection.

```bash
# Run full benchmark suite
python scripts/benchmark_suite.py --output results/baseline.json

# Tag baseline
git tag perf-baseline-v1.0
```

### Continuous Benchmarking

Run benchmarks on every significant change:

```bash
# Run lightweight benchmark (< 30 seconds)
just benchmark-quick

# Run full benchmark (5-10 minutes)
just benchmark-full

# Compare to baseline
python scripts/compare_benchmarks.py \
  results/baseline.json \
  results/current.json \
  --threshold 10  # Fail if > 10% regression
```

### Regression Detection

Expected output:
```
==================================================
BENCHMARK COMPARISON
==================================================

Comparing:
  Baseline: results/baseline.json (2025-11-01)
  Current:  results/current.json  (2025-11-10)

Query latency:
  p50:  42.3ms → 38.1ms  (📉 9.9% improvement) ✓
  p95:  89.7ms → 96.2ms  (📈 7.2% regression)  ⚠
  p99: 156.2ms → 168.4ms (📈 7.8% regression)  ⚠

Throughput:
  QPS:  109 → 115  (📈 5.5% improvement) ✓

Status: ⚠ WARNING - p95 regression detected

Recommendations:
  - Investigate p95/p99 regressions
  - Check for new I/O or locking contention
  - Review recent changes to query path
```

### Automated Alerts

Configure CI to fail on regressions:

```yaml
# .github/workflows/benchmark.yml
- name: Run benchmarks
  run: just benchmark-full

- name: Compare to baseline
  run: |
    python scripts/compare_benchmarks.py \
      results/baseline.json \
      results/current.json \
      --threshold 10 \
      --fail-on-regression
```

---

## Optimization Guide

### Query Optimization

**If p50 is high**:
1. Reduce `nprobes` (faster ANN search)
2. Disable reranking for simple queries
3. Cache frequent query results
4. Optimize vector normalization

**If p95/p99 are high**:
1. Identify outliers with profiling
2. Check for GC pauses (tune heap size)
3. Look for I/O spikes (buffer/cache tuning)
4. Reduce concurrent load

**If throughput is low**:
1. Enable connection pooling
2. Batch embedding API calls
3. Parallelize independent operations
4. Reduce serialization overhead

### Indexing Optimization

**If indexing is slow**:
1. Increase batch size (more chunks per API call)
2. Parallelize file scanning and chunking
3. Use faster embedding model (e.g., small vs large)
4. Optimize chunking algorithm

**If memory usage is high**:
1. Reduce batch size
2. Stream processing instead of batching
3. Clear intermediate data structures
4. Use memory-mapped files for large vectors

### ANN Optimization

**If recall is low**:
1. Increase `nprobes` (search more partitions)
2. Increase `refine_factor` (better reranking)
3. Ensure vectors are properly normalized
4. Check index is properly built

**If latency is high**:
1. Decrease `nprobes` (search fewer partitions)
2. Decrease `refine_factor` (less reranking)
3. Use IVF_PQ quantization for large datasets
4. Optimize distance computation

---

## Benchmark Checklist

Before releasing changes:

- [ ] Run query latency benchmark (p50, p95, p99 within targets)
- [ ] Run throughput benchmark (QPS meets targets)
- [ ] Run ANN parameter sweep (optimal configuration identified)
- [ ] Compare to baseline (< 10% regression)
- [ ] Profile resource usage (memory, CPU within bounds)
- [ ] Test under load (no degradation with concurrent users)
- [ ] Document any performance trade-offs

---

## Tools and Scripts

| Script | Purpose |
|--------|---------|
| `scripts/benchmark_ann.py` | ANN parameter tuning (existing) |
| `scripts/benchmark_query.py` | Query latency measurement |
| `scripts/benchmark_throughput.py` | Concurrent throughput testing |
| `scripts/benchmark_index.py` | Indexing performance |
| `scripts/benchmark_memory.py` | Memory profiling |
| `scripts/benchmark_suite.py` | Full benchmark suite |
| `scripts/compare_benchmarks.py` | Regression detection |

---

## Summary

**Key practices**:
1. **Establish baselines** before optimization
2. **Measure continuously** to catch regressions
3. **Profile before optimizing** to find real bottlenecks
4. **Test under load** to reveal scaling issues
5. **Compare configurations** objectively

**Targets to remember**:
- p50 < 50ms, p95 < 150ms
- Throughput > 100 QPS (10 users)
- Recall > 95%
- Memory < 2GB (10K files)

**Next**: See [Retrieval Evaluation](./retrieval-evaluation.md) for quality metrics.
