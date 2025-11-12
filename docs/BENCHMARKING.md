# Benchmarking Guide

**Version**: 1.0.0  
**Last Updated**: 2025-11-12  
**Status**: Production Ready

---

## Overview

This guide provides benchmarking procedures and performance baselines for Dolphin's semantic code search and knowledge management system. Use these benchmarks to validate performance and detect regressions.

For detailed profiling procedures, see [PROFILING.md](PROFILING.md).

---

## Table of Contents

1. [Performance Targets](#performance-targets)
2. [Baseline Benchmarks](#baseline-benchmarks)
3. [Benchmarking Procedures](#benchmarking-procedures)
4. [Interpreting Results](#interpreting-results)
5. [Performance Optimization](#performance-optimization)

---

## Performance Targets

### Search Latency

| Metric | Target | Current (v1.0.0) | Status |
|--------|--------|------------------|--------|
| p50 (median) | ≤ 600ms | ~300ms | ✅ 2x better |
| p95 | ≤ 2s | ~800ms | ✅ 2.5x better |
| p99 | ≤ 5s | ~2s | ✅ 2.5x better |

### Throughput

| Metric | Target | Current (v1.0.0) | Status |
|--------|--------|------------------|--------|
| Single-user QPS | 10-20 | 10-20 | ✅ |
| Concurrent queries | 8 parallel | 8 parallel | ✅ |

### Resource Usage

| Metric | Target | Current (v1.0.0) | Status |
|--------|--------|------------------|--------|
| Baseline memory | ~200 MB | ~200 MB | ✅ |
| Under load (8 queries) | ~500 MB | ~500 MB | ✅ |
| Embedding latency | - | ~150ms avg | ✅ |
| Vector search latency | - | ~50ms avg | ✅ |

---

## Baseline Benchmarks

### Repository Sizes

| Size | Files | Chunks | LanceDB | SQLite | Status |
|------|-------|--------|---------|--------|--------|
| Small | ~1K | ~50K | ~100 MB | ~5 MB | ✅ |
| Medium | ~10K | ~500K | ~1 GB | ~50 MB | ✅ |
| Large | ~100K | ~5M | ~10 GB | ~500 MB | ✅ |

### Search Quality Metrics

#### Hybrid Search (BM25 + Vector)

- **Precision improvement**: 40% better on code identifier searches vs. vector-only
- **Configurable parameters**:
  - BM25 k1 and b parameters
  - Fusion k parameter (default: 60)

#### Cross-Encoder Reranking (Optional)

- **MRR improvement**: 20-30% over baseline
- **Trade-off**: 2-3x slower searches
- **Install size**: ~2GB additional (PyTorch + sentence-transformers)
- **Model**: ms-marco-MiniLM-L-6-v2

#### Maximal Marginal Relevance (MMR)

- **Purpose**: Balance relevance and diversity in results
- **Effect**: Prevents redundant/similar results
- **Lambda parameter**: 0.7 (default)

#### Adaptive ANN Tuning

- **Performance gain**: ~40% faster searches with adaptive parameters vs. static
- **Strategies**: speed, accuracy, development
- **Automatic query-type detection**: identifier, concept, example-based

---

## Benchmarking Procedures

### Prerequisites

Set up test repositories:

```bash
export TEST_REPO_SMALL="$HOME/test-repos/small"    # ~1,000 files
export TEST_REPO_MEDIUM="$HOME/test-repos/medium"  # ~10,000 files
export TEST_REPO_LARGE="$HOME/test-repos/large"    # ~50,000 files
```

### 1. Indexing Performance

```bash
# Small repository
uv run dolphin kb add-repo test-small "$TEST_REPO_SMALL"
time uv run dolphin kb index test-small --full --force

# Medium repository
uv run dolphin kb add-repo test-medium "$TEST_REPO_MEDIUM"
time uv run dolphin kb index test-medium --full --force

# Large repository (incremental recommended)
uv run dolphin kb add-repo test-large "$TEST_REPO_LARGE"
time uv run dolphin kb index test-large
```

**Expected Results**:
- Small: < 5 minutes
- Medium: 10-30 minutes
- Large: Varies by size (incremental indexing recommended)

### 2. Search Latency

Start the API server:

```bash
uv run dolphin serve
```

Run benchmark queries:

```bash
# Cold cache (first-time search)
curl -w "\nTime: %{time_total}s\n" -X POST http://127.0.0.1:7777/search \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication logic", "top_k": 10}'

# Warm cache (repeated search)
curl -w "\nTime: %{time_total}s\n" -X POST http://127.0.0.1:7777/search \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication logic", "top_k": 10}'
```

**Expected Results**:
- Cold cache: 300-600ms
- Warm cache: 50-200ms

### 3. Concurrent Performance

```bash
# Simulate 8 concurrent users
for i in {1..8}; do
  curl -X POST http://127.0.0.1:7777/search \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"test query $i\", \"top_k\": 5}" &
done
wait
```

**Expected Results**:
- All queries complete in < 2s
- No significant latency increase

### 4. Hybrid Search Quality

Use the provided benchmark script:

```bash
uv run python scripts/test_hybrid_search_performance.py
```

**Metrics tracked**:
- Precision@5
- Precision@10
- Mean Reciprocal Rank (MRR)
- Latency (mean, median, p95, p99)

### 5. ANN Parameter Tuning

```bash
uv run python scripts/benchmark_ann.py --repo test-medium --queries 50
```

**Expected Results**:
- Speed strategy: Fastest, good precision
- Accuracy strategy: Slower, best precision
- Adaptive strategy: Balanced (recommended)

---

## Interpreting Results

### Search Latency Breakdown

Typical cold cache search (300ms total):

1. **Vector search (LanceDB)**: 180ms (60%)
2. **BM25 search (SQLite FTS)**: 80ms (27%)
3. **Result fusion**: 20ms (7%)
4. **Metadata hydration**: 20ms (7%)

### Optimization Opportunities

If performance doesn't meet targets:

1. **High vector search time (>200ms)**:
   - Enable adaptive ANN tuning
   - Use pre-filtering by repo
   - Reduce top_k parameter

2. **High BM25 search time (>100ms)**:
   - Check FTS5 index integrity
   - Optimize SQLite connection pooling
   - Consider in-memory database

3. **High result fusion time (>50ms)**:
   - Parallelize vector + BM25 searches
   - Optimize RRF implementation

4. **High memory usage (>500MB idle)**:
   - Reduce LanceDB cache size
   - Check for memory leaks in long-running servers

---

## Performance Optimization

### 1. Embedding Model Selection

```bash
# Faster, cheaper (recommended)
uv run dolphin kb add-repo my-repo /path --default-embed-model small

# More accurate, slower
uv run dolphin kb add-repo my-repo /path --default-embed-model large
```

**Trade-offs**:
- Small (1536d): Faster, lower cost, good for most use cases
- Large (3072d): Better precision, use for critical repos

### 2. Chunk Size Configuration

Edit `.dolphin/config.toml`:

```toml
[chunking]
max_chunk_tokens = 256  # Smaller = more chunks, better precision
overlap_tokens = 64     # Balance context and duplication
```

**Trade-offs**:
- Smaller chunks (256): Better precision, more API calls, higher cost
- Larger chunks (512): Better context, fewer chunks, lower cost

### 3. Search Optimization

Filter searches to reduce latency:

```bash
# Filter by repository
KB_REPOS=api-server uv run dolphin search "auth"

# Filter by path prefix (API)
curl -X POST http://127.0.0.1:7777/search \
  -d '{"query": "auth", "repos": ["api-server"], "path_prefix": ["src/"]}'
```

### 4. Incremental Indexing

```bash
# Fast: Only index changed files
uv run dolphin kb index my-repo

# Slow: Full reindex (only when needed)
uv run dolphin kb index my-repo --full --force
```

### 5. Caching Strategy

Leverage content deduplication:
- SHA256 hashing prevents re-embedding unchanged code
- Git-aware indexing only processes changed files
- Reindexing same code is nearly free

---

## Regression Testing

### Continuous Monitoring

Track key metrics over time:

1. **Search latency** (p50, p95, p99)
2. **Indexing throughput** (files/min)
3. **Memory usage** (idle, under load)
4. **Cache hit rate** (when implemented)
5. **Search quality** (Precision@5, MRR)

### Alerting Thresholds

Set up alerts for:
- p95 latency > 2s
- Memory usage > 1GB
- Indexing failures
- Search quality degradation > 10%

---

## References

- [PROFILING.md](PROFILING.md) - Detailed profiling procedures
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture and design
- [AGENTS.md](../AGENTS.md) - Development guidelines
- [scripts/benchmark_ann.py](../scripts/benchmark_ann.py) - ANN benchmarking tool
- [scripts/test_hybrid_search_performance.py](../scripts/test_hybrid_search_performance.py) - Search quality metrics

---

**Version**: 1.0.0  
**Last Updated**: 2025-11-12  
**Status**: Production Ready