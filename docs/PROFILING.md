# Profiling Guide - EP-6 Performance Optimization

**Document Version**: 1.0
**Last Updated**: 2025-11-11
**Status**: Phase 1 - Profiling Infrastructure

---

## Overview

This guide provides instructions for profiling Dolphin's performance using the tools and scripts set up for EP-6. The profiling infrastructure enables systematic measurement of indexing, search, storage, and runtime performance.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Profiling Tools](#profiling-tools)
3. [Quick Start](#quick-start)
4. [Profiling Indexing](#profiling-indexing)
5. [Profiling Search](#profiling-search)
6. [Monitoring Dashboard](#monitoring-dashboard)
7. [Analyzing Results](#analyzing-results)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools

**Python Profiling**:

```bash
# Install py-spy globally (recommended for profiling tools that need sudo)
pipx install py-spy
# or: pip install --user py-spy

# Verify installation
py-spy --version
```

**Node/Bun Profiling**:

```bash
# Install clinic.js for Node/Bun profiling
bun install -g clinic

# Verify installation
bun run clinic --version
```

**Monitoring Stack** (Optional but recommended):

```bash
# Requires Docker
docker --version

# Setup monitoring (Prometheus + Grafana)
./scripts/setup_monitoring.sh
```

### Test Repositories

Set up test repositories of various sizes for consistent benchmarking:

```bash
# Set environment variables pointing to test repos
export TEST_REPO_SMALL="$HOME/test-repos/small"    # ~1,000 files
export TEST_REPO_MEDIUM="$HOME/test-repos/medium"  # ~10,000 files
export TEST_REPO_LARGE="$HOME/test-repos/large"    # ~50,000 files

# Example: Clone sample repos
mkdir -p ~/test-repos
cd ~/test-repos

# Small repo (~1K files)
git clone https://github.com/expressjs/express small

# Medium repo (~10K files)
git clone https://github.com/django/django medium

# Large repo (~50K files) - use a large monorepo or the Linux kernel
git clone --depth 1 https://github.com/torvalds/linux large
```

---

## Profiling Tools

### py-spy

**Purpose**: CPU profiling for Python (Knowledge Bank backend)

**Key Features**:

- Low-overhead sampling profiler
- No code modification required
- Generates flame graphs and speedscope format
- Supports multiprocessing

**Usage**:

```bash
# Record profiling data
py-spy record --format speedscope --output profile.json --rate 100 -- uv run python -m kb.cli index /path/to/repo

# Generate flame graph
py-spy record --format flamegraph --output flamegraph.svg --rate 100 -- uv run python -m kb.cli index /path/to/repo
```

### clinic.js

**Purpose**: Performance profiling for Node.js/Bun (Agent Core, Extension)

**Key Features**:

- Doctor: Detects performance issues
- Bubbleprof: Async operations visualization
- Flame: CPU flame graphs

**Usage**:

```bash
# Profile extension activation
clinic doctor -- node extension/dist/extension.js

# Profile with flame graph
clinic flame -- bun run agent-core/src/main.ts
```

### Prometheus + Grafana

**Purpose**: Real-time metrics collection and visualization

**Key Features**:

- Time-series metrics database
- Pre-built dashboard for EP-6 metrics
- Alerting on performance regressions

**Setup**:

```bash
# Start monitoring stack
./scripts/setup_monitoring.sh

# Access Grafana
open http://localhost:3001
# Username: admin
# Password: admin
```

---

## Quick Start

### 1. Profile Indexing Pipeline

```bash
# Small repo (~1K files)
./scripts/profile_indexing.sh small

# Medium repo (~10K files)
./scripts/profile_indexing.sh medium

# Large repo (~50K files)
./scripts/profile_indexing.sh large
```

Results saved to: `profiling_results/indexing/`

### 2. Profile Search Queries

```bash
# Cold cache (first-time searches)
./scripts/profile_search.sh cold

# Warm cache (repeated searches)
./scripts/profile_search.sh warm

# Concurrent users (10 simultaneous)
./scripts/profile_search.sh concurrent
```

Results saved to: `profiling_results/search/`

### 3. View Results

**Flame Graphs**:

1. Visit https://speedscope.app
2. Upload `profiling_results/*/*.json` files
3. Analyze CPU hotspots

**Monitoring Dashboard**:

1. Open http://localhost:3001
2. Add Prometheus data source (http://host.docker.internal:9090)
3. Import dashboard from `monitoring/grafana/ep6-dashboard.json`

---

## Profiling Indexing

### Metrics to Collect

1. **Throughput**: Files indexed per minute
2. **Latency Distribution**: Time per file (p50, p95, p99)
3. **CPU Hotspots**: Functions consuming most CPU time
4. **Memory Usage**: Peak and average memory consumption
5. **I/O Patterns**: Disk reads/writes during indexing

### Step-by-Step Process

#### Step 1: Prepare Test Repository

```bash
# Ensure clean git state
cd $TEST_REPO_SMALL
git reset --hard HEAD
git clean -fd

# Note repository stats
find . -type f | wc -l  # File count
du -sh .                # Repository size
```

#### Step 2: Clear Previous Index

```bash
# Remove existing KB database for this repo
uv run python -m kb.cli drop-repo "$TEST_REPO_SMALL"
```

#### Step 3: Run Profiling

```bash
# Profile with py-spy
./scripts/profile_indexing.sh small

# Alternatively, manual profiling:
py-spy record \
  --format speedscope \
  --output indexing_small.json \
  --rate 100 \
  --subprocesses \
  -- uv run python -m kb.cli index "$TEST_REPO_SMALL"
```

#### Step 4: Extract Metrics

From the log output, record:

- Total time (seconds)
- Files processed
- Throughput (files/min)
- Any errors or warnings

#### Step 5: Analyze Flame Graph

1. Upload `indexing_small.json` to https://speedscope.app
2. Identify top 10 functions by time
3. Look for:
   - Sequential processing bottlenecks
   - Repeated parsing/hashing
   - Inefficient I/O operations
   - Unnecessary allocations

### Example Analysis

```
Top CPU consumers in indexing:
1. tree_sitter.parse()          - 35% (parsing files)
2. openai.embed()               - 25% (embedding API calls)
3. lancedb.insert()             - 15% (vector insertion)
4. sqlite3.execute()            - 10% (metadata insertion)
5. hash_text()                  - 8%  (content hashing)
6. os.walk() / git ls-files     - 5%  (file scanning)
7. Other                        - 2%
```

**Optimization Opportunities**:

- Parallelize tree_sitter.parse() (35% → ~3.5% with 10 workers)
- Batch openai.embed() calls (25% → ~10% with adaptive batching)
- Cache parsed ASTs (8% reduction in parse time)

---

## Profiling Search

### Metrics to Collect

1. **Query Latency**: Time from request to response (p50, p95, p99)
2. **Cache Hit Rate**: % of queries served from cache
3. **Vector Search Time**: LanceDB query latency
4. **BM25 Search Time**: SQLite FTS query latency
5. **Result Fusion Time**: Time to merge vector + BM25 results
6. **Concurrent Performance**: Latency under load (10+ users)

### Step-by-Step Process

#### Step 1: Start KB API Server

```bash
# Start the Knowledge Bank API
uv run python -m kb.api.server

# Verify it's running
curl http://localhost:8420/health
```

#### Step 2: Warm Up (Optional)

```bash
# Pre-load models and establish connections
curl -X POST http://localhost:8420/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "warmup", "top_k": 1}'
```

#### Step 3: Profile Cold Cache Queries

```bash
# Clear cache to measure cold performance
curl -X DELETE http://localhost:8420/api/cache

# Run cold cache profiling
./scripts/profile_search.sh cold
```

#### Step 4: Profile Warm Cache Queries

```bash
# Pre-warm the cache
curl -X POST http://localhost:8420/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication", "top_k": 10}'

# Run warm cache profiling
./scripts/profile_search.sh warm
```

#### Step 5: Profile Concurrent Queries

```bash
# Simulate 10 concurrent users
./scripts/profile_search.sh concurrent
```

#### Step 6: Analyze Results

Review `profiling_results/search/*.log`:

```bash
# Calculate average latency
grep "Latency:" profiling_results/search/search_cold_*.log | \
  awk '{sum+=$2; count++} END {print "Average: " sum/count "ms"}'

# Calculate p95 latency
grep "Latency:" profiling_results/search/search_cold_*.log | \
  awk '{print $2}' | sort -n | awk 'BEGIN{c=0} {latencies[c++]=$1} END{print "p95: " latencies[int(c*0.95)] "ms"}'
```

### Example Analysis

```
Cold Cache Performance:
- Average latency: 320ms
- p50: 300ms
- p95: 450ms
- p99: 850ms

Warm Cache Performance:
- Average latency: 50ms
- p50: 45ms
- p95: 80ms
- p99: 120ms
- Cache hit rate: 0% (not yet implemented)

Breakdown (cold):
- Vector search (LanceDB): 180ms (56%)
- BM25 search (SQLite FTS): 80ms (25%)
- Result fusion: 40ms (13%)
- Metadata hydration: 20ms (6%)
```

**Optimization Opportunities**:

- Implement query caching (expect 70%+ hit rate → 50% avg latency reduction)
- Pre-filter vector search by repo (180ms → ~80ms)
- Parallelize vector + BM25 (260ms → ~180ms)
- Connection pooling for SQLite (20ms → ~5ms)

---

## Monitoring Dashboard

### Setting Up Metrics

#### 1. Add Prometheus Instrumentation

**KB API** (`kb/api/server.py`):

```python
from prometheus_client import Counter, Histogram, Gauge

# Metrics
indexing_files_total = Counter('kb_indexing_files_total', 'Total files indexed')
search_duration = Histogram('kb_search_duration_seconds', 'Search query duration')
cache_hits = Counter('kb_cache_hits_total', 'Cache hits')
cache_misses = Counter('kb_cache_misses_total', 'Cache misses')
database_size = Gauge('kb_database_size_bytes', 'Database size in bytes')

# Usage
@app.post("/api/search")
async def search(request: SearchRequest):
    with search_duration.time():
        # ... search logic ...
        if cache_hit:
            cache_hits.inc()
        else:
            cache_misses.inc()
```

**Agent Core** (`agent-core/src/main.ts`):

```typescript
import { register, Counter, Histogram } from "prom-client";

// Metrics
const extensionActivationDuration = new Histogram({
  name: "extension_activation_duration_seconds",
  help: "Extension activation time",
});

// Usage
const start = Date.now();
await activateExtension();
const duration = (Date.now() - start) / 1000;
extensionActivationDuration.observe(duration);
```

#### 2. Expose Metrics Endpoints

**KB API**:

```python
from prometheus_client import generate_latest

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

**Agent Core**:

```typescript
app.get("/metrics", (req, res) => {
  res.set("Content-Type", register.contentType);
  res.end(register.metrics());
});
```

#### 3. Import Dashboard

1. Open Grafana: http://localhost:3001
2. Go to Dashboards → Import
3. Upload `monitoring/grafana/ep6-dashboard.json`
4. Select Prometheus data source
5. Click Import

### Dashboard Panels

The EP-6 dashboard includes:

1. **Indexing Throughput**: Real-time files/min rate
2. **Search Latency**: p50, p95, p99 over time
3. **Cache Hit Rate**: Percentage of cached queries
4. **Database Size**: Storage growth tracking
5. **Extension Activation**: Startup time monitoring
6. **Resource Usage**: CPU and memory utilization

---

## Analyzing Results

### Identifying Bottlenecks

#### 1. CPU-Bound Operations

**Indicators**:

- High % in flame graph for specific functions
- Low I/O wait time
- All cores at 100% utilization

**Common Culprits**:

- tree-sitter parsing (synchronous, CPU-intensive)
- Text embedding (if done locally)
- Vector similarity calculations

**Solutions**:

- Parallelize across multiple processes
- Use Rust/C++ extensions for hot paths
- Cache expensive computations

#### 2. I/O-Bound Operations

**Indicators**:

- High disk read/write time
- Low CPU utilization
- Long wait times in flame graph

**Common Culprits**:

- Sequential file reading
- Synchronous database operations
- Network API calls (embeddings)

**Solutions**:

- Async I/O with asyncio/tokio
- Batch database operations
- Connection pooling
- Parallel file processing

#### 3. Memory Bottlenecks

**Indicators**:

- High memory allocation rate
- Frequent garbage collection
- Out-of-memory errors

**Common Culprits**:

- Loading entire files into memory
- Large intermediate data structures
- Memory leaks in loops

**Solutions**:

- Streaming/chunked processing
- Clear references explicitly
- Use generators instead of lists
- Profile with memory_profiler

### Calculating ROI

For each optimization, calculate:

**Impact**: Expected improvement (% or absolute)
**Complexity**: Implementation difficulty (1-5 scale)
**ROI**: Impact / Complexity

**Example**:

```
Optimization: Parallelize file scanning
Impact: 8x throughput improvement = 800%
Complexity: 2 (moderate - multiprocessing)
ROI: 800 / 2 = 400

Optimization: Implement query caching
Impact: 50% latency reduction at 70% hit rate = 35% avg improvement
Complexity: 2 (moderate - LRU cache)
ROI: 35 / 2 = 17.5
```

**Prioritization**: Sort by ROI descending

---

## Troubleshooting

### py-spy Not Working

**Issue**: Permission denied when profiling

**Solution**:

```bash
# Run with sudo (Linux)
sudo py-spy record --pid <pid> --output profile.json

# Or use ptrace capability (Linux)
sudo setcap cap_sys_ptrace=eip $(which py-spy)
```

### clinic.js Errors

**Issue**: "Cannot find module"

**Solution**:

```bash
# Reinstall clinic globally
npm uninstall -g clinic
npm install -g clinic

# Verify installation
clinic --version
```

### Prometheus Not Scraping

**Issue**: Targets down in Prometheus UI

**Solution**:

```bash
# Check if KB API is exposing metrics
curl http://localhost:8420/metrics

# Check Prometheus config
cat monitoring/prometheus/prometheus.yml

# Restart Prometheus
docker restart ep6-prometheus
```

### Test Repository Too Large

**Issue**: Profiling takes too long or crashes

**Solution**:

```bash
# Use a subset of the repository
git clone --depth 1 --single-branch <repo-url>

# Or create a synthetic test repo
uv run python scripts/generate_test_repo.py --size 1000
```

### Inconsistent Results

**Issue**: Profiling results vary significantly between runs

**Solution**:

```bash
# Warm up system before profiling
echo 3 > /proc/sys/vm/drop_caches  # Clear caches (Linux, requires sudo)

# Close other applications
# Run multiple times and take average

# Use fixed test data
export TEST_REPO_SMALL="$HOME/test-repos/small"
```

---

## Best Practices

### 1. Consistent Test Environment

- Use the same test repositories for all measurements
- Close unnecessary applications
- Disable background indexing/antivirus
- Use consistent network conditions (for API calls)

### 2. Multiple Runs

- Profile each scenario 3-5 times
- Calculate average and standard deviation
- Discard outliers (±2σ)

### 3. Incremental Optimization

- Optimize highest ROI items first
- Re-profile after each optimization
- Verify gains match predictions
- Watch for performance regressions

### 4. Document Assumptions

- Record hardware specs
- Note software versions (Python, Node, DB)
- Document test data characteristics
- Explain profiling methodology

### 5. Version Control Results

```bash
# Commit profiling results for reference
git add profiling_results/
git commit -m "chore: add baseline profiling results"
```

---

## Next Steps

After completing profiling and baseline measurement:

1. **Review Results**: Analyze flame graphs and metrics
2. **Identify Top 10 Bottlenecks**: Quantify impact of each
3. **Calculate ROI**: Prioritize optimizations
4. **Create Baseline Report**: Document findings in `baseline-performance-report.md`
5. **Begin Phase 2**: Start implementing optimizations

---

## References

- [py-spy Documentation](https://github.com/benfred/py-spy)
- [clinic.js Documentation](https://clinicjs.org/documentation/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Speedscope Flame Graph Viewer](https://speedscope.app)

---

**Document Status**: Complete ✅
**Next**: Generate baseline performance report
**Owner**: EP-6 Lead Engineer
