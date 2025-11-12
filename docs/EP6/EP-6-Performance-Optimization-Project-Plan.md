# EP-6: Performance Optimization Suite - Project Plan

**Project ID**: EP-6  
**Category**: Foundation  
**Priority**: Medium  
**Duration**: 5-7 weeks  
**Status**: Planning  
**Last Updated**: 2025-11-11

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [Project Objectives](#project-objectives)
- [Success Criteria](#success-criteria)
- [Architecture Context](#architecture-context)
- [Implementation Phases](#implementation-phases)
- [Detailed Task Breakdown](#detailed-task-breakdown)
- [Timeline and Schedule](#timeline-and-schedule)
- [Resource Requirements](#resource-requirements)
- [Risk Management](#risk-management)
- [Testing Strategy](#testing-strategy)
- [Deliverables](#deliverables)
- [Dependencies](#dependencies)
- [Post-Implementation](#post-implementation)

---

## Executive Summary

### Problem Statement

Dolphin's current performance limits its scalability and user experience:
- Indexing speed: ~500 files/min (target: 2,500 files/min)
- Search latency: 300ms p50 (target: 150ms p50)
- Extension activation: 5s (target: <2s)
- Repository scale: Limited to 1K-50K files (target: 100K+ files)
- Embedding costs: High due to inefficient batching

### Solution Overview

Implement a comprehensive performance optimization suite across five key areas:
1. **Indexing Pipeline**: Parallel processing, incremental updates, batch optimization
2. **Search Queries**: Caching, vector search optimization, connection pooling
3. **Storage**: Compression, compaction, database tuning
4. **Runtime**: Lazy loading, webview optimization, IPC improvements
5. **Observability**: Continuous profiling, load testing, performance budgets

### Expected Impact

| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| Indexing throughput | 500 files/min | 2,500 files/min | 5x |
| Search latency (p50) | 300ms | 150ms | 50% reduction |
| Search latency (p95) | 1,000ms | <1,000ms | Maintain |
| Extension activation | 5s | <2s | 60% reduction |
| Database size | Baseline | -50% | Compression |
| Cache hit rate | 0% | 70%+ | New capability |
| Max QPS sustained | ~5 | 20 | 4x |

### Investment and ROI

**Time Investment**: 5-7 weeks (1 FTE)  
**Expected Benefits**:
- **User Experience**: Sub-second search enables flow state programming
- **Scale**: Support enterprise repositories (100K+ files)
- **Cost**: 50% reduction in embedding API costs
- **Developer Velocity**: 5x faster indexing enables rapid iteration
- **Competitive**: Matches/exceeds performance of commercial tools

---

## Project Objectives

### Primary Objectives

1. **Achieve 5x indexing throughput improvement** (500 → 2,500 files/min)
2. **Reduce search latency by 50%** (300ms → 150ms p50)
3. **Enable 100K+ file repository support** with acceptable performance
4. **Reduce extension activation time by 60%** (5s → <2s)
5. **Implement comprehensive performance monitoring** and alerting

### Secondary Objectives

1. Reduce embedding costs by 50% through intelligent batching
2. Achieve 70%+ cache hit rate for repeated queries
3. Reduce database storage by 50% through compression
4. Sustain 20 QPS with <1s p95 latency
5. Establish performance regression testing in CI

### Non-Goals

- ❌ Rewriting core architecture (maintain backward compatibility)
- ❌ Migrating from LanceDB to alternative vector databases
- ❌ Implementing distributed/multi-node architecture
- ❌ Supporting repositories >500K files in v1
- ❌ Real-time collaborative indexing

---

## Success Criteria

### Quantitative Metrics

**Indexing Performance**:
- [ ] Throughput: ≥2,500 files/min (5x improvement)
- [ ] Incremental reindex: <10% time of full reindex
- [ ] Parse time: 40% reduction via AST caching
- [ ] Batch efficiency: 30% improvement in embedding throughput

**Search Performance**:
- [ ] Query latency p50: ≤150ms (50% reduction)
- [ ] Query latency p95: ≤1,000ms (maintained)
- [ ] Cache hit rate: ≥70% for repeated queries
- [ ] Concurrent users: Support 10 simultaneous users
- [ ] Hybrid search: 50% latency reduction vs sequential

**Storage Efficiency**:
- [ ] Database size: 50% reduction with compression
- [ ] LanceDB compaction: 30% storage reduction
- [ ] Query speed post-compaction: 15% improvement

**Runtime Performance**:
- [ ] Extension activation: <2s (60% reduction)
- [ ] Webview load time: <1s
- [ ] IPC overhead: 40% reduction via MessagePack
- [ ] Memory usage: No increase vs baseline

**Load Testing**:
- [ ] Sustained QPS: 20 requests/sec for 5 minutes
- [ ] Latency under load: <1s p95 at 20 QPS
- [ ] Error rate: <0.1% under load
- [ ] Resource usage: CPU <80%, Memory <4GB

### Qualitative Metrics

- [ ] Zero breaking changes to public APIs
- [ ] All optimizations configurable (opt-in for risky changes)
- [ ] Performance monitoring dashboard operational
- [ ] Documentation updated with optimization guide
- [ ] Load test suite integrated into CI
- [ ] Flame graphs available for profiling

---

## Architecture Context

### Current System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  VSCode Extension                       │
│               (Node.js/TypeScript)                      │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Webview   │  │ Extension    │  │  Settings    │  │
│  │  (Svelte)   │  │   Host       │  │              │  │
│  └──────┬──────┘  └──────┬───────┘  └──────────────┘  │
└─────────┼────────────────┼──────────────────────────────┘
          │                │
          │ JSON-RPC       │ JSON-RPC
          â–¼                â–¼
┌─────────────────────────────────────────────────────────┐
│                    Agent Core                           │
│                     (Bun)                               │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │ Orchestrator │  │  KB Manager  │  │   Planner   │  │
│  │              │  │              │  │             │  │
│  └──────┬───────┘  └──────┬───────┘  └─────────────┘  │
└─────────┼────────────────┼──────────────────────────────┘
          │                │
          │ HTTP           │ HTTP
          â–¼                â–¼
┌─────────────────────────────────────────────────────────┐
│              Knowledge Bank (Python/FastAPI)            │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐   │
│  │ Scanner  │→│ Chunker  │→│  Embedder          │   │
│  └──────────┘  └──────────┘  └──────────┬─────────┘   │
│                                          │             │
│  ┌──────────────────────────────────────▼─────────┐   │
│  │           Storage Layer                        │   │
│  │  ┌─────────────┐  ┌──────────────┐           │   │
│  │  │  SQLite     │  │  LanceDB     │           │   │
│  │  │ (metadata)  │  │  (vectors)   │           │   │
│  │  └─────────────┘  └──────────────┘           │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Performance Bottlenecks Identified

**Indexing Pipeline** (`kb/ingest/`):
1. **Sequential processing**: `scanner.py` processes files one at a time
2. **Full re-embedding**: `embedder.py` re-embeds all chunks on reindex
3. **Fixed batch size**: `BATCH_SIZE=100` regardless of chunk size
4. **No AST caching**: `chunker.py` reparses files every index

**Search Queries** (`kb/search/`):
1. **No query caching**: Every search hits vector DB
2. **Fixed nprobes**: LanceDB KNN uses static probe count
3. **New connections**: SQLite connection per request
4. **Sequential hybrid**: Vector and BM25 searches run sequentially

**Storage** (`kb/storage/`):
1. **No compaction**: LanceDB grows unbounded with updates
2. **Unoptimized SQLite**: No WAL mode, missing indexes
3. **Uncompressed text**: Full chunk text stored in SQLite
4. **Large database**: No cleanup of stale entries

**Runtime** (`vscode-extension/`, `agent-core/`):
1. **Eager loading**: Embedding models load on startup
2. **Webview bloat**: All components load immediately
3. **JSON serialization**: IPC uses verbose JSON format
4. **No code splitting**: All JS bundled together

---

## Implementation Phases

### Phase 1: Profiling & Baseline (Week 1)

**Objective**: Establish performance baselines and identify top bottlenecks

**Activities**:
- Set up profiling infrastructure
- Profile indexing pipeline end-to-end
- Profile search queries (cold and warm cache)
- Analyze storage size and growth patterns
- Measure extension activation and runtime metrics
- Document top 10 bottlenecks with evidence

**Deliverables**:
- Baseline performance report
- Profiling infrastructure (integrated into repo)
- Flame graphs for indexing and search
- Bottleneck analysis document
- Performance dashboard (initial version)

**Success Criteria**:
- Comprehensive baseline metrics collected
- Profiling tools working in development environment
- Top 10 bottlenecks identified with quantified impact
- Team aligned on optimization priorities

---

### Phase 2: Indexing Optimization (Weeks 2-3)

**Objective**: Achieve 5x throughput improvement in indexing pipeline

**Week 2: Parallel Processing**

**Tasks**:
1. Implement multiprocessing for file scanning
   - Worker pool with 8-16 processes
   - Queue-based work distribution
   - Progress tracking across workers
2. Parallelize tree-sitter parsing
   - Separate process pool for CPU-bound parsing
   - Share parsed ASTs across workers
3. Implement incremental embedding
   - Detect changed chunks via SHA256
   - Skip unchanged chunks
   - Update vector table incrementally
4. Add progress bars and telemetry

**Week 3: Batch Optimization & Caching**

**Tasks**:
1. Implement adaptive batch sizing
   - Measure throughput at various batch sizes
   - Auto-tune based on chunk size and API latency
   - Monitor embedding API rate limits
2. Add tree-sitter AST caching
   - LRU cache with pickle serialization
   - Cache key: file_path + content_hash
   - Size limit: 1000 files
3. Optimize chunking algorithm
   - Profile chunker performance
   - Reduce allocations and copies
   - Consider Rust/C++ extension for hot path
4. Integration testing with large repos

**Deliverables**:
- Parallel indexing implementation
- Incremental embedding system
- Adaptive batch sizing
- AST cache implementation
- Performance comparison report
- Updated documentation

**Success Criteria**:
- Indexing throughput: ≥2,500 files/min
- Incremental reindex: <10% time of full reindex
- Parse time: 40% reduction
- Batch efficiency: 30% improvement
- Zero data corruption or race conditions

---

### Phase 3: Search Optimization (Weeks 4-5)

**Objective**: Reduce search latency by 50% and achieve 70% cache hit rate

**Week 4: Query Caching & Vector Search**

**Tasks**:
1. Implement query result caching
   - In-memory LRU cache (Python `functools.lru_cache`)
   - Cache key: query_hash + repo_filter + top_k
   - TTL: 5 minutes for exact, 1 hour for similar
   - Cache invalidation on index updates
2. Optimize LanceDB vector search
   - Pre-filter by repo before KNN
   - Implement adaptive nprobes
   - Profile different distance metrics
   - Consider IVF_PQ index if beneficial
3. Add query analytics
   - Track cache hit rate
   - Log slow queries (>500ms)
   - Identify common query patterns
4. Benchmark and tune

**Week 5: Connection Pooling & Hybrid Search**

**Tasks**:
1. Implement SQLite connection pooling
   - Pool size: 10-20 connections
   - Use aiosqlite or SQLAlchemy
   - Handle connection lifecycle
2. Parallelize hybrid search
   - Run vector and BM25 queries concurrently
   - Use `asyncio.gather()`
   - Merge results asynchronously
3. Optimize metadata queries
   - Add missing indexes (EXPLAIN QUERY PLAN)
   - Denormalize frequently joined tables
   - Consider materialized views for common queries
4. Load testing with concurrent users

**Deliverables**:
- Query caching system
- Optimized vector search
- Connection pooling
- Parallelized hybrid search
- Query analytics dashboard
- Performance comparison report

**Success Criteria**:
- Search latency p50: ≤150ms
- Search latency p95: ≤1,000ms
- Cache hit rate: ≥70%
- Concurrent users: 10 simultaneous searches
- Hybrid search: 50% latency reduction
- Zero cache coherence issues

---

### Phase 4: Storage & Runtime Optimization (Week 6)

**Objective**: Reduce storage by 50% and improve runtime performance

**Storage Optimization**:

**Tasks**:
1. LanceDB compaction
   - Implement periodic compaction (weekly)
   - Compact after N% new data threshold
   - Monitor compaction impact on queries
2. SQLite optimization
   - Enable WAL mode for concurrency
   - Run PRAGMA optimize after bulk ops
   - Add missing indexes from query analysis
   - Schedule periodic VACUUM
3. Content compression
   - Implement zstd compression for chunk_content.content
   - Benchmark compression ratio and overhead
   - Make compression configurable
   - Update decompression in search path
4. Implement storage monitoring

**Runtime Optimization**:

**Tasks**:
1. Lazy initialization
   - Defer embedding model loading until first use
   - Singleton pattern with lazy initialization
   - Measure activation time improvement
2. Webview optimization
   - Implement code splitting (dynamic imports)
   - Add virtual scrolling for message history
   - Debounce search input (300ms)
   - Memoize rendered components
3. IPC optimization
   - Replace JSON with MessagePack
   - Benchmark serialization overhead
   - Implement in both extension and agent-core
4. Profile and iterate

**Deliverables**:
- LanceDB compaction scheduler
- SQLite optimizations applied
- Content compression system
- Lazy initialization implementation
- Optimized webview
- MessagePack IPC
- Storage and runtime monitoring

**Success Criteria**:
- Database size: 50% reduction
- LanceDB compaction: 30% storage reduction
- Query speed post-compaction: 15% improvement
- Extension activation: <2s
- Webview load: <1s
- IPC overhead: 40% reduction
- Memory usage: No regression

---

### Phase 5: Load Testing & Documentation (Week 7)

**Objective**: Validate performance under load and document optimizations

**Week 7: Load Testing & Refinement**

**Tasks**:
1. Build load test suite
   - Concurrent search scenario (10 users)
   - Indexing during search scenario
   - Large result set scenario (100+ results)
   - Stress test (100 QPS for 5 minutes)
2. Implement load testing tools
   - HTTP load testing: Locust or k6
   - CLI operations: Custom Python scripts
   - Monitor latency, error rate, resource usage
3. Run comprehensive tests
   - Execute all load test scenarios
   - Collect metrics (latency, throughput, errors)
   - Identify bottlenecks under load
4. Performance regression tests
   - Integrate into CI pipeline
   - Compare against baseline
   - Fail builds on >10% regression
5. Generate performance report
   - Before/after comparisons
   - Flame graphs and profiling data
   - Recommendations for further optimization
6. Update documentation
   - Performance optimization guide
   - Configuration tuning guide
   - Troubleshooting performance issues
   - Best practices for large repos

**Deliverables**:
- Load test suite
- CI integration for performance tests
- Comprehensive performance report
- Flame graphs and profiling visualizations
- Updated documentation
- Performance tuning guide

**Success Criteria**:
- Sustained QPS: 20 requests/sec for 5 minutes
- Latency under load: <1s p95 at 20 QPS
- Error rate: <0.1% under load
- Resource usage: CPU <80%, Memory <4GB
- CI performance tests passing
- Documentation complete and reviewed

---

## Detailed Task Breakdown

### Phase 1: Profiling & Baseline (Week 1)

#### Day 1-2: Setup Profiling Infrastructure

**Tasks**:
- [ ] Set up py-spy for Python profiling
  - Install: `pip install py-spy`
  - Create profiling script: `scripts/profile_indexing.sh`
  - Test with small repo (1K files)
- [ ] Set up clinic.js for Node/Bun profiling
  - Install: `npm install -g clinic`
  - Create profiling script: `scripts/profile_extension.sh`
  - Test with extension activation
- [ ] Set up Prometheus metrics collection
  - Add instrumentation to KB API endpoints
  - Add instrumentation to Agent Core
  - Create Grafana dashboard template
- [ ] Document profiling process
  - Create `docs/profiling-guide.md`
  - Add runbook for common scenarios

**Deliverables**:
- Profiling scripts in `scripts/`
- Prometheus metrics configured
- Grafana dashboard template
- Profiling guide documentation

**Estimated Time**: 2 days

---

#### Day 3-4: Collect Baseline Metrics

**Tasks**:
- [ ] Profile indexing pipeline
  - Small repo (1K files): `scripts/profile_indexing.sh small`
  - Medium repo (10K files): `scripts/profile_indexing.sh medium`
  - Large repo (50K files): `scripts/profile_indexing.sh large`
  - Generate flame graphs with speedscope.app
- [ ] Profile search queries
  - Cold cache: First-time searches
  - Warm cache: Repeated searches
  - Various query types (semantic, keyword, hybrid)
  - Concurrent searches (2, 5, 10 users)
- [ ] Measure storage metrics
  - SQLite database size over time
  - LanceDB table size and fragmentation
  - Disk I/O patterns
- [ ] Measure runtime metrics
  - Extension activation time
  - Webview initial render time
  - IPC message latency
  - Memory usage over time

**Deliverables**:
- Baseline performance report (`docs/baseline-performance.md`)
- Flame graphs for all major operations
- Storage growth analysis
- Runtime metrics dashboard

**Estimated Time**: 2 days

---

#### Day 5: Analyze and Prioritize

**Tasks**:
- [ ] Analyze profiling results
  - Identify CPU hotspots
  - Identify I/O bottlenecks
  - Identify memory allocations
  - Identify slow queries
- [ ] Quantify impact of each bottleneck
  - % of total time spent
  - Projected improvement if optimized
  - Implementation complexity (1-5 scale)
- [ ] Create prioritized bottleneck list
  - Top 10 bottlenecks with impact analysis
  - ROI calculation (impact / complexity)
  - Dependencies between optimizations
- [ ] Team review and alignment
  - Present findings to team
  - Validate optimization priorities
  - Adjust phase 2-5 plans if needed

**Deliverables**:
- Bottleneck analysis document
- Prioritized optimization list
- Updated project plan (if needed)
- Team sign-off on priorities

**Estimated Time**: 1 day

---

### Phase 2: Indexing Optimization (Weeks 2-3)

#### Week 2: Parallel Processing

**Day 1-2: Parallel File Scanning**

**Tasks**:
- [ ] Design parallel scanner architecture
  - Worker pool with 8-16 processes
  - Queue-based work distribution
  - Error handling and retry logic
- [ ] Implement `ParallelScanner` class
  - `multiprocessing.Pool` for workers
  - Chunk work by directory
  - Progress tracking with `tqdm`
- [ ] Test with various repo sizes
  - 1K files: Expect 5-8x speedup
  - 10K files: Expect 8-10x speedup
  - 50K files: Expect 10-12x speedup
- [ ] Handle edge cases
  - Large files (>10MB)
  - Binary files
  - Symlinks and circular references

**Deliverables**:
- `kb/ingest/parallel_scanner.py`
- Unit tests: `tests/test_parallel_scanner.py`
- Performance comparison: sequential vs parallel
- Documentation update

**Estimated Time**: 2 days

---

**Day 3-4: Parallel Tree-Sitter Parsing**

**Tasks**:
- [ ] Extract parsing logic to separate module
  - Create `kb/ingest/parallel_parser.py`
  - Separate process pool from scanner
- [ ] Implement parallel parsing
  - Use `multiprocessing.Pool.map()`
  - Parse AST for each file
  - Return parsed chunks
- [ ] Optimize memory usage
  - Limit worker memory
  - Clear AST cache between batches
  - Monitor memory consumption
- [ ] Integration with parallel scanner
  - Scanner → Parser → Chunker pipeline
  - Pass parsed ASTs to chunker
  - Avoid reparsing

**Deliverables**:
- `kb/ingest/parallel_parser.py`
- Unit tests: `tests/test_parallel_parser.py`
- Memory profiling results
- Integration tests

**Estimated Time**: 2 days

---

**Day 5: Incremental Embedding**

**Tasks**:
- [ ] Implement change detection
  - SHA256 hash comparison (already exists)
  - Query existing chunks by hash
  - Filter unchanged chunks
- [ ] Implement incremental update
  - Identify new, modified, deleted chunks
  - Embed only new/modified chunks
  - Update vector table incrementally
  - Delete stale chunks
- [ ] Test incremental reindex
  - Modify 1% of files: Expect 90%+ time reduction
  - Modify 10% of files: Expect 80%+ time reduction
  - Verify vector table consistency
- [ ] Add telemetry
  - Track % chunks skipped
  - Track time saved
  - Log incremental update stats

**Deliverables**:
- Incremental embedding implementation
- Integration tests
- Telemetry and logging
- Performance comparison report

**Estimated Time**: 1 day

---

#### Week 3: Batch Optimization & Caching

**Day 1-2: Adaptive Batch Sizing**

**Tasks**:
- [ ] Implement batch size tuning
  - Measure throughput at batch sizes: 10, 50, 100, 200, 500
  - Measure latency distribution for each batch size
  - Consider chunk text length in batch size
- [ ] Implement adaptive algorithm
  - Start with batch_size = 100
  - Measure throughput for last N batches
  - Adjust batch size if throughput decreases
  - Respect API rate limits (e.g., 500 req/min)
- [ ] Add configuration options
  - `min_batch_size`, `max_batch_size`
  - `batch_size_adjustment_factor`
  - `auto_tune_batch_size` (enable/disable)
- [ ] Test with various workloads
  - Small chunks (avg 200 tokens)
  - Large chunks (avg 1000 tokens)
  - Mixed chunk sizes
  - Verify 30%+ throughput improvement

**Deliverables**:
- Adaptive batching implementation
- Configuration options
- Performance benchmark results
- Documentation update

**Estimated Time**: 2 days

---

**Day 3-4: Tree-Sitter AST Caching**

**Tasks**:
- [ ] Design AST cache
  - LRU cache with size limit (1000 files)
  - Cache key: `(file_path, content_hash)`
  - Pickle serialization for AST
- [ ] Implement caching layer
  - Check cache before parsing
  - Store parsed AST in cache
  - Handle cache eviction
- [ ] Measure impact
  - Cache hit rate during reindex
  - Time saved per cache hit
  - Memory usage of cache
  - Verify 40%+ parse time reduction
- [ ] Handle cache invalidation
  - Clear cache on file modification
  - Option to disable cache (development)

**Deliverables**:
- AST caching implementation
- Cache hit rate metrics
- Performance comparison
- Configuration options

**Estimated Time**: 2 days

---

**Day 5: Integration Testing**

**Tasks**:
- [ ] End-to-end indexing tests
  - Test with large repos (50K+ files)
  - Verify correctness of parallel processing
  - Check for race conditions
  - Validate vector table integrity
- [ ] Performance regression tests
  - Baseline: Sequential indexing
  - Optimized: Parallel + incremental + adaptive
  - Measure 5x improvement
  - Generate performance report
- [ ] Edge case testing
  - Empty repo
  - Single file repo
  - Repo with no code files
  - Very large files (>50MB)
- [ ] Update documentation
  - Indexing performance guide
  - Configuration tuning guide
  - Troubleshooting common issues

**Deliverables**:
- Integration test suite
- Performance report (Phase 2)
- Edge case test results
- Updated documentation

**Estimated Time**: 1 day

---

### Phase 3: Search Optimization (Weeks 4-5)

#### Week 4: Query Caching & Vector Search

**Day 1-2: Query Result Caching**

**Tasks**:
- [ ] Design caching strategy
  - Cache key: `hash(query + repo_filter + top_k)`
  - TTL: 5 minutes for exact matches
  - Similar query detection (embedding similarity)
- [ ] Implement in-memory cache
  - Use `functools.lru_cache` decorator
  - Max size: 1000 queries
  - Thread-safe implementation
- [ ] Implement cache invalidation
  - Track last_indexed_at per repo
  - Invalidate cache entries for modified repos
  - Manual cache clear endpoint
- [ ] Add cache analytics
  - Track hit rate, miss rate
  - Track cache size and memory usage
  - Log slow queries (>500ms)
- [ ] Test caching behavior
  - Identical queries: Expect instant response
  - Similar queries: Expect cache hit
  - Modified repo: Expect cache miss
  - Verify 70%+ cache hit rate

**Deliverables**:
- Query caching implementation
- Cache invalidation logic
- Analytics and metrics
- Unit and integration tests

**Estimated Time**: 2 days

---

**Day 3-4: Vector Search Optimization**

**Tasks**:
- [ ] Pre-filter by repository
  - Apply repo filter before KNN search
  - Reduce search space by 90%+ for single-repo queries
  - Measure latency improvement
- [ ] Implement adaptive nprobes
  - Start with nprobes = 10
  - Increase if result quality is low
  - Decrease if latency is high
  - Track nprobes adjustments
- [ ] Profile LanceDB queries
  - Measure KNN search time
  - Identify slow queries (>200ms)
  - Experiment with IVF_PQ index
- [ ] Consider alternative optimizations
  - Approximate filtering with refinement
  - Parallel search across repos
  - Pre-compute embeddings for common queries
- [ ] Benchmark and tune
  - Test various nprobes values (5, 10, 20, 50)
  - Measure latency vs result quality trade-off
  - Verify 40%+ latency reduction

**Deliverables**:
- Pre-filtering implementation
- Adaptive nprobes algorithm
- LanceDB profiling results
- Performance benchmark

**Estimated Time**: 2 days

---

**Day 5: Query Analytics Dashboard**

**Tasks**:
- [ ] Implement query logging
  - Log all queries with metadata
  - Include latency, cache status, result count
  - Store in SQLite or time-series DB
- [ ] Create analytics queries
  - Top 10 slowest queries
  - Cache hit rate over time
  - Query patterns (common terms)
  - Latency distribution (p50, p95, p99)
- [ ] Build Grafana dashboard
  - Query latency chart
  - Cache hit rate gauge
  - Top slow queries table
  - Search volume over time
- [ ] Set up alerts
  - Alert if p95 latency >1s
  - Alert if cache hit rate <50%
  - Alert if error rate >1%

**Deliverables**:
- Query logging system
- Analytics queries
- Grafana dashboard
- Alerting rules

**Estimated Time**: 1 day

---

#### Week 5: Connection Pooling & Hybrid Search

**Day 1-2: SQLite Connection Pooling**

**Tasks**:
- [ ] Evaluate pooling libraries
  - `aiosqlite` (async)
  - `SQLAlchemy` (sync + pool)
  - Benchmark both approaches
- [ ] Implement connection pool
  - Pool size: 10-20 connections
  - Connection timeout: 30s
  - Max overflow: 5 connections
- [ ] Update database access layer
  - Replace direct `sqlite3.connect()` calls
  - Use pool.acquire() / pool.release()
  - Handle connection errors gracefully
- [ ] Test concurrent access
  - 10 simultaneous queries
  - 20 simultaneous queries
  - Verify no deadlocks or timeouts
  - Measure 30%+ metadata query improvement

**Deliverables**:
- Connection pooling implementation
- Updated database layer
- Concurrency tests
- Performance comparison

**Estimated Time**: 2 days

---

**Day 3-4: Parallelize Hybrid Search**

**Tasks**:
- [ ] Refactor hybrid search
  - Separate vector and BM25 functions
  - Make both async compatible
  - Return results with scores
- [ ] Implement parallel execution
  - Use `asyncio.gather()` for concurrent queries
  - Merge results with fusion algorithm
  - Normalize scores across search types
- [ ] Handle errors gracefully
  - If vector search fails, fall back to BM25
  - If BM25 fails, fall back to vector
  - Log failures and alert
- [ ] Benchmark parallel vs sequential
  - Measure latency reduction
  - Verify result quality maintained
  - Test with various query types
  - Verify 50%+ latency reduction

**Deliverables**:
- Parallelized hybrid search
- Error handling and fallbacks
- Performance benchmark
- Integration tests

**Estimated Time**: 2 days

---

**Day 5: Load Testing (Concurrent Users)**

**Tasks**:
- [ ] Build load test script
  - Use Locust or k6
  - Simulate 10 concurrent users
  - Execute realistic search queries
- [ ] Run load tests
  - Ramp up: 1 → 10 users over 1 min
  - Sustained: 10 users for 5 min
  - Ramp down: 10 → 0 users over 1 min
- [ ] Collect metrics
  - Latency (p50, p95, p99)
  - Throughput (QPS)
  - Error rate
  - Resource usage (CPU, memory)
- [ ] Analyze results
  - Identify bottlenecks under load
  - Check for connection pool exhaustion
  - Verify cache effectiveness
- [ ] Generate load test report

**Deliverables**:
- Load test script
- Load test results
- Bottleneck analysis
- Recommendations for tuning

**Estimated Time**: 1 day

---

### Phase 4: Storage & Runtime Optimization (Week 6)

#### Day 1-2: Storage Optimization

**LanceDB Compaction**:

**Tasks**:
- [ ] Implement compaction scheduler
  - Trigger: Weekly OR after 20% new data
  - Use LanceDB `compact()` API
  - Run during low-traffic hours
- [ ] Test compaction impact
  - Measure storage reduction (expect 30%)
  - Measure query speedup (expect 15%)
  - Verify data integrity post-compaction
- [ ] Add monitoring
  - Track compaction duration
  - Track storage before/after
  - Alert if compaction fails

**SQLite Optimization**:

**Tasks**:
- [ ] Enable WAL mode
  - Set `PRAGMA journal_mode=WAL`
  - Verify concurrent read/write performance
  - Test with connection pool
- [ ] Add missing indexes
  - Run `EXPLAIN QUERY PLAN` on slow queries
  - Create indexes for frequently filtered columns
  - Measure query speedup
- [ ] Implement PRAGMA optimize
  - Run after bulk insert/update operations
  - Schedule periodic optimization (daily)
- [ ] Schedule periodic VACUUM
  - Run weekly to reclaim space
  - Run during low-traffic hours

**Content Compression**:

**Tasks**:
- [ ] Implement zstd compression
  - Compress `chunk_content.content` on insert
  - Decompress on select
  - Make compression configurable
- [ ] Benchmark compression
  - Measure compression ratio (expect 60%)
  - Measure decompression overhead (expect 10-20ms)
  - Test on various content types
- [ ] Update search path
  - Decompress before returning results
  - Cache decompressed content if needed

**Deliverables**:
- LanceDB compaction scheduler
- SQLite optimizations applied
- Content compression system
- Storage monitoring dashboard
- Configuration options

**Estimated Time**: 2 days

---

#### Day 3-5: Runtime Optimization

**Lazy Initialization**:

**Tasks**:
- [ ] Refactor model loading
  - Move embedding model load to first use
  - Singleton pattern with lazy init
  - Measure activation time improvement
- [ ] Test lazy loading
  - Verify model loads on first search
  - Verify no impact on subsequent searches
  - Measure 80%+ activation time reduction

**Webview Optimization**:

**Tasks**:
- [ ] Implement code splitting
  - Dynamic imports for routes
  - Lazy load heavy components
  - Measure bundle size reduction
- [ ] Add virtual scrolling
  - Use `svelte-virtual-list`
  - Render only visible messages
  - Test with 1000+ message history
- [ ] Debounce search input
  - Wait 300ms before searching
  - Cancel previous search requests
  - Show loading indicator
- [ ] Memoize components
  - Use `$:` reactive statements
  - Memoize expensive computations
  - Profile rendering performance

**IPC Optimization**:

**Tasks**:
- [ ] Implement MessagePack serialization
  - Replace `JSON.stringify()` with `msgpack.encode()`
  - Replace `JSON.parse()` with `msgpack.decode()`
  - Update both extension and agent-core
- [ ] Benchmark serialization
  - Measure overhead for various message sizes
  - Verify 40%+ reduction in overhead
  - Test with real-world messages
- [ ] Test compatibility
  - Verify all message types work
  - Handle version mismatches
  - Backward compatibility with JSON

**Deliverables**:
- Lazy initialization implementation
- Optimized webview code
- MessagePack IPC
- Runtime performance report
- Configuration options

**Estimated Time**: 3 days

---

### Phase 5: Load Testing & Documentation (Week 7)

#### Day 1-2: Load Test Suite

**Tasks**:
- [ ] Build load test scenarios
  - **Concurrent search**: 10 simultaneous users
  - **Indexing during search**: Background indexing with queries
  - **Large result sets**: Queries returning 100+ results
  - **Stress test**: 100 QPS for 5 minutes
- [ ] Implement load test scripts
  - Use Locust for HTTP load testing
  - Custom Python scripts for CLI operations
  - Monitor latency, error rate, resource usage
- [ ] Set up monitoring
  - Prometheus metrics collection
  - Grafana dashboard for load tests
  - Resource monitoring (CPU, memory, disk I/O)
- [ ] Run comprehensive tests
  - Execute all scenarios
  - Collect detailed metrics
  - Identify bottlenecks under load
  - Generate flame graphs for analysis

**Deliverables**:
- Load test suite (`tests/load/`)
- Monitoring setup
- Load test execution scripts
- Initial results and analysis

**Estimated Time**: 2 days

---

#### Day 3-4: Performance Regression Tests & CI Integration

**Tasks**:
- [ ] Build regression test suite
  - Indexing throughput test
  - Search latency test
  - Extension activation test
  - Resource usage test
- [ ] Set up CI integration
  - GitHub Actions workflow
  - Run on every PR and main branch
  - Compare against baseline metrics
  - Fail build if regression >10%
- [ ] Implement performance budgets
  - Indexing: <10 min for 10K files
  - Search: <300ms p50, <1s p95
  - Extension activation: <2s
  - Webview load: <1s
- [ ] Test CI integration
  - Create sample PR with performance change
  - Verify tests detect regression
  - Verify alerts fire as expected

**Deliverables**:
- Regression test suite
- CI workflow configuration
- Performance budget enforcement
- CI integration documentation

**Estimated Time**: 2 days

---

#### Day 5: Final Report & Documentation

**Tasks**:
- [ ] Generate comprehensive performance report
  - Before/after comparison for all metrics
  - Flame graphs and profiling visualizations
  - Load test results and analysis
  - Recommendations for further optimization
- [ ] Update documentation
  - **Performance optimization guide** (`docs/performance-optimization.md`)
  - **Configuration tuning guide** (`docs/configuration-tuning.md`)
  - **Troubleshooting performance issues** (`docs/troubleshooting-performance.md`)
  - **Best practices for large repos** (`docs/large-repo-best-practices.md`)
- [ ] Create performance dashboard
  - Grafana dashboard for production monitoring
  - Export dashboard JSON
  - Document dashboard setup
- [ ] Team review and sign-off
  - Present results to team
  - Demo performance improvements
  - Gather feedback for future work

**Deliverables**:
- Final performance report
- Updated documentation
- Performance dashboard
- Team presentation and demo

**Estimated Time**: 1 day

---

## Timeline and Schedule

### Gantt Chart

```
Week 1: Phase 1 - Profiling & Baseline
├─ Mon-Tue:  Setup profiling infrastructure
├─ Wed-Thu:  Collect baseline metrics
└─ Fri:      Analyze and prioritize

Week 2: Phase 2 - Indexing Optimization (Part 1)
├─ Mon-Tue:  Parallel file scanning
├─ Wed-Thu:  Parallel tree-sitter parsing
└─ Fri:      Incremental embedding

Week 3: Phase 2 - Indexing Optimization (Part 2)
├─ Mon-Tue:  Adaptive batch sizing
├─ Wed-Thu:  Tree-sitter AST caching
└─ Fri:      Integration testing

Week 4: Phase 3 - Search Optimization (Part 1)
├─ Mon-Tue:  Query result caching
├─ Wed-Thu:  Vector search optimization
└─ Fri:      Query analytics dashboard

Week 5: Phase 3 - Search Optimization (Part 2)
├─ Mon-Tue:  SQLite connection pooling
├─ Wed-Thu:  Parallelize hybrid search
└─ Fri:      Load testing (concurrent users)

Week 6: Phase 4 - Storage & Runtime Optimization
├─ Mon-Tue:  Storage optimization (LanceDB, SQLite, compression)
└─ Wed-Fri:  Runtime optimization (lazy init, webview, IPC)

Week 7: Phase 5 - Load Testing & Documentation
├─ Mon-Tue:  Load test suite
├─ Wed-Thu:  Regression tests & CI integration
└─ Fri:      Final report & documentation
```

### Milestones

| Milestone | Date | Deliverables | Success Criteria |
|-----------|------|--------------|------------------|
| **M1: Baseline Established** | End of Week 1 | Profiling infrastructure, baseline report, bottleneck analysis | All baseline metrics collected, top 10 bottlenecks identified |
| **M2: Indexing Optimized** | End of Week 3 | Parallel processing, incremental embedding, adaptive batching, AST caching | 5x indexing throughput, 90% reindex time reduction |
| **M3: Search Optimized** | End of Week 5 | Query caching, vector search optimization, connection pooling, parallel hybrid search | 50% search latency reduction, 70% cache hit rate |
| **M4: Storage & Runtime Optimized** | End of Week 6 | LanceDB compaction, SQLite optimization, compression, lazy loading, webview optimization, MessagePack IPC | 50% storage reduction, <2s activation time |
| **M5: Project Complete** | End of Week 7 | Load test suite, CI integration, performance report, documentation | All success criteria met, load tests passing, documentation complete |

---

## Resource Requirements

### Team

**Primary**:
- **1x Full-Stack Engineer** (5-7 weeks, full-time)
  - Python expertise (KB optimization)
  - TypeScript expertise (extension/agent-core)
  - Performance engineering experience
  - Profiling and benchmarking skills

**Supporting**:
- **Tech Lead / Architect** (2-4 hours/week)
  - Code review
  - Architecture decisions
  - Bottleneck analysis
- **QA Engineer** (1 week, part-time in Phase 5)
  - Load testing support
  - Test strategy review

### Infrastructure

**Development**:
- Local development machine (MacBook Pro M4, 24GB RAM)
- Test repositories of various sizes:
  - Small: 1K files (~chromium single directory)
  - Medium: 10K files (~rails or django)
  - Large: 50K files (~linux kernel subsystem)
  - XL: 100K files (synthetic or large monorepo)

**Monitoring**:
- Prometheus server (Docker container)
- Grafana server (Docker container)
- Loki for log aggregation (optional)
- Jaeger for tracing (optional, Phase 6+)

**CI/CD**:
- GitHub Actions runners (existing)
- Performance test baseline storage
- Artifact storage for flame graphs

### Tools & Licenses

**Profiling**:
- py-spy (open source, MIT)
- clinic.js (open source, MIT)
- speedscope.app (web-based, free)

**Load Testing**:
- Locust (open source, MIT)
- k6 (open source, AGPL)

**Monitoring**:
- Prometheus (open source, Apache 2.0)
- Grafana (open source, AGPL)

**Development**:
- VSCode (free)
- Node.js / Bun (free)
- Python / uv (free)

**Total Cost**: $0 (all open source tools)

---

## Risk Management

### Technical Risks

#### High Priority Risks

**Risk 1: Parallel Processing Introduces Race Conditions**

- **Probability**: Medium (40%)
- **Impact**: High (data corruption, incorrect results)
- **Mitigation**:
  - Comprehensive testing with large repos
  - Use immutable data structures where possible
  - Implement file-level locking for critical sections
  - Code review focused on concurrency
- **Contingency**: Fall back to sequential processing with optional parallel mode

**Risk 2: LanceDB Performance Doesn't Scale as Expected**

- **Probability**: Low (20%)
- **Impact**: High (fails to meet latency targets)
- **Mitigation**:
  - Profile LanceDB queries early (Phase 1)
  - Test with 100K+ file repos
  - Engage with LanceDB community for optimization tips
  - Consider pre-filtering and index tuning
- **Contingency**: Evaluate alternative vector databases (Faiss, Annoy) in Phase 5

**Risk 3: Cache Invalidation Bugs Lead to Stale Results**

- **Probability**: Medium (30%)
- **Impact**: High (incorrect search results)
- **Mitigation**:
  - Conservative cache invalidation strategy
  - Comprehensive integration tests for cache behavior
  - Manual cache clear endpoint for troubleshooting
  - Cache versioning to detect stale entries
- **Contingency**: Disable caching by default, make opt-in

#### Medium Priority Risks

**Risk 4: Compression Overhead Negates Storage Savings**

- **Probability**: Low (20%)
- **Impact**: Medium (storage goals not met, latency increased)
- **Mitigation**:
  - Benchmark compression on representative data
  - Make compression configurable
  - Test decompression overhead on target hardware
- **Contingency**: Offer compression as optional feature

**Risk 5: MessagePack IPC Breaks Existing Functionality**

- **Probability**: Low (15%)
- **Impact**: Medium (rollback required)
- **Mitigation**:
  - Comprehensive testing of all message types
  - Backward compatibility with JSON fallback
  - Staged rollout (opt-in first)
- **Contingency**: Keep JSON serialization as fallback

**Risk 6: Performance Tests Are Flaky in CI**

- **Probability**: Medium (35%)
- **Impact**: Medium (slows down development)
- **Mitigation**:
  - Use consistent hardware for CI runners
  - Run tests multiple times and average
  - Set reasonable thresholds (10% regression)
  - Isolate performance tests from other CI jobs
- **Contingency**: Run performance tests nightly instead of per-PR

#### Low Priority Risks

**Risk 7: Optimization Breaks Backward Compatibility**

- **Probability**: Low (10%)
- **Impact**: Low (minor API changes)
- **Mitigation**:
  - Maintain backward compatibility as design goal
  - Version APIs if breaking changes needed
  - Comprehensive integration tests
- **Contingency**: Provide migration guide

**Risk 8: Team Member Unavailability**

- **Probability**: Low (15%)
- **Impact**: Medium (project delay)
- **Mitigation**:
  - Document all work thoroughly
  - Regular progress updates
  - Knowledge sharing sessions
- **Contingency**: Extend timeline by 1-2 weeks

### Risk Matrix

| Risk | Probability | Impact | Score | Priority |
|------|-------------|--------|-------|----------|
| Race conditions | 40% | High | 12 | High |
| LanceDB scaling | 20% | High | 6 | High |
| Cache invalidation | 30% | High | 9 | High |
| Compression overhead | 20% | Medium | 4 | Medium |
| MessagePack breaks | 15% | Medium | 3 | Medium |
| Flaky CI tests | 35% | Medium | 7 | Medium |
| Breaks compatibility | 10% | Low | 1 | Low |
| Team unavailability | 15% | Medium | 3 | Low |

---

## Testing Strategy

### Unit Testing

**Coverage Target**: 80%+ for new code

**Key Test Areas**:
- Parallel processing logic
  - Worker pool initialization
  - Work distribution
  - Error handling and retry
- Caching logic
  - Cache hit/miss behavior
  - Invalidation triggers
  - TTL expiration
- Compression/decompression
  - Correctness for various content types
  - Error handling for corrupt data
- Adaptive algorithms
  - Batch size adjustment
  - Nprobes tuning
  - Cache size management

**Tools**:
- Python: pytest, pytest-cov
- TypeScript: Jest, Vitest

---

### Integration Testing

**Key Test Scenarios**:
- End-to-end indexing with various repo sizes
- Search queries with caching (cold and warm)
- Concurrent operations (indexing + searching)
- Storage compaction and optimization
- Extension activation and IPC communication

**Test Repositories**:
- Small (1K files): Fast iteration
- Medium (10K files): Realistic use case
- Large (50K files): Stress test
- XL (100K files): Scale test

**Tools**:
- pytest for Python integration tests
- VSCode Extension Test Runner for extension tests

---

### Performance Testing

**Benchmarks**:
- Indexing throughput (files/min)
- Search latency (p50, p95, p99)
- Cache hit rate
- Resource usage (CPU, memory, disk I/O)
- Extension activation time

**Comparison**:
- Baseline (before optimization)
- After each phase
- Final (all optimizations)

**Tools**:
- Custom benchmarking scripts
- Prometheus metrics collection
- Grafana visualization

---

### Load Testing

**Scenarios**:
1. **Concurrent search**: 10 simultaneous users
   - Duration: 5 minutes
   - Expected: <1s p95 latency, <0.1% error rate
2. **Indexing during search**: Background indexing with queries
   - Scenario: Index 10K files while 5 users search
   - Expected: Search latency <300ms, indexing unaffected
3. **Large result sets**: Queries returning 100+ results
   - Scenario: 100 queries with 100-200 results each
   - Expected: <2s latency, no OOM errors
4. **Stress test**: 100 QPS for 5 minutes
   - Expected: Graceful degradation, <5% error rate

**Tools**:
- Locust (HTTP load testing)
- Custom Python scripts (CLI operations)
- Prometheus + Grafana (monitoring)

---

### Regression Testing

**Automated Tests in CI**:
- Indexing throughput test (10K files)
- Search latency test (100 queries)
- Extension activation test
- Resource usage test (memory <4GB)

**Fail Conditions**:
- >10% regression in any metric
- Test timeout (>30 minutes)
- Memory leak detected

**Tools**:
- GitHub Actions workflow
- Performance baseline storage
- Automated alerts on failure

---

## Deliverables

### Code Deliverables

1. **Parallel Processing Implementation**
   - `kb/ingest/parallel_scanner.py`
   - `kb/ingest/parallel_parser.py`
   - Unit and integration tests

2. **Incremental Embedding System**
   - SHA256 change detection
   - Incremental vector table updates
   - Telemetry and logging

3. **Adaptive Batching**
   - Dynamic batch size adjustment
   - Configuration options
   - Throughput monitoring

4. **AST Caching**
   - LRU cache implementation
   - Pickle serialization
   - Cache hit rate metrics

5. **Query Caching**
   - In-memory cache with TTL
   - Cache invalidation logic
   - Analytics and metrics

6. **Vector Search Optimization**
   - Pre-filtering by repository
   - Adaptive nprobes
   - Profiling and benchmarks

7. **Connection Pooling**
   - SQLite connection pool
   - Concurrency handling
   - Error recovery

8. **Parallel Hybrid Search**
   - Async vector and BM25 queries
   - Result fusion
   - Error handling

9. **Storage Optimization**
   - LanceDB compaction scheduler
   - SQLite WAL mode and indexing
   - Content compression (zstd)

10. **Runtime Optimization**
    - Lazy model initialization
    - Webview code splitting and virtual scrolling
    - MessagePack IPC serialization

### Documentation Deliverables

1. **Profiling Guide** (`docs/profiling-guide.md`)
   - How to profile indexing and search
   - Interpreting flame graphs
   - Common bottlenecks and fixes

2. **Performance Optimization Guide** (`docs/performance-optimization.md`)
   - Overview of all optimizations
   - Configuration options
   - Trade-offs and recommendations

3. **Configuration Tuning Guide** (`docs/configuration-tuning.md`)
   - Tuning for different repo sizes
   - Balancing latency vs throughput
   - Resource allocation guidelines

4. **Troubleshooting Performance** (`docs/troubleshooting-performance.md`)
   - Common performance issues
   - Diagnostic steps
   - Solutions and workarounds

5. **Large Repo Best Practices** (`docs/large-repo-best-practices.md`)
   - Strategies for 100K+ file repos
   - Incremental indexing workflows
   - Query optimization tips

6. **Load Testing Guide** (`docs/load-testing-guide.md`)
   - Running load tests locally
   - Interpreting results
   - CI integration

### Infrastructure Deliverables

1. **Profiling Scripts** (`scripts/profile_*.sh`)
   - `profile_indexing.sh`
   - `profile_search.sh`
   - `profile_extension.sh`

2. **Benchmarking Scripts** (`scripts/benchmark_*.py`)
   - `benchmark_indexing.py`
   - `benchmark_search.py`
   - `benchmark_storage.py`

3. **Load Test Suite** (`tests/load/`)
   - `concurrent_search.py`
   - `indexing_during_search.py`
   - `large_result_sets.py`
   - `stress_test.py`

4. **CI Workflows** (`.github/workflows/`)
   - `performance-tests.yml`
   - `regression-tests.yml`

5. **Monitoring Dashboards**
   - Grafana dashboard JSON export
   - Prometheus alerting rules
   - Dashboard setup documentation

### Reporting Deliverables

1. **Baseline Performance Report** (Week 1)
   - Current metrics for all areas
   - Flame graphs and profiling data
   - Bottleneck analysis

2. **Phase 2 Report** (Week 3)
   - Indexing optimization results
   - Before/after comparisons
   - Recommendations for Phase 3

3. **Phase 3 Report** (Week 5)
   - Search optimization results
   - Cache analytics
   - Load test results

4. **Phase 4 Report** (Week 6)
   - Storage and runtime optimization results
   - Resource usage analysis
   - Configuration recommendations

5. **Final Performance Report** (Week 7)
   - Comprehensive before/after comparison
   - All metrics and success criteria
   - Flame graphs and visualizations
   - Recommendations for future work

---

## Dependencies

### Internal Dependencies

1. **Existing Knowledge Bank Infrastructure**
   - Dependency: Current KB API must remain stable
   - Impact: Breaking changes would require extension updates
   - Mitigation: Maintain backward compatibility

2. **Agent Core Integration**
   - Dependency: JSON-RPC communication protocol
   - Impact: IPC optimization requires changes to both sides
   - Mitigation: Coordinate changes, maintain fallback

3. **VSCode Extension**
   - Dependency: Webview and extension host code
   - Impact: Runtime optimization requires extension changes
   - Mitigation: Staged rollout, feature flags

### External Dependencies

1. **LanceDB Library**
   - Dependency: LanceDB API and performance characteristics
   - Impact: Major version changes could affect optimization
   - Mitigation: Pin version, monitor release notes

2. **OpenAI Embedding API**
   - Dependency: API availability and rate limits
   - Impact: Downtime affects indexing
   - Mitigation: Adaptive batching respects rate limits, retry logic

3. **Tree-Sitter Parsers**
   - Dependency: Language parsers for chunking
   - Impact: Parser bugs could affect AST caching
   - Mitigation: Pin parser versions, comprehensive testing

4. **Python/Bun Runtime**
   - Dependency: Runtime performance and APIs
   - Impact: Runtime changes could affect benchmarks
   - Mitigation: Pin versions, test on multiple versions

### Cross-Phase Dependencies

1. **Phase 1 → Phase 2-5**
   - Profiling data informs optimization priorities
   - Baseline metrics required for comparison

2. **Phase 2 → Phase 3**
   - Faster indexing enables more load testing
   - Incremental embedding affects cache invalidation

3. **Phase 3 → Phase 5**
   - Cache implementation affects load test results
   - Connection pooling required for concurrent load tests

4. **Phase 4 → Phase 5**
   - Storage optimization affects load test disk I/O
   - Runtime optimization affects extension activation tests

---

## Post-Implementation

### Monitoring and Alerting

**Ongoing Monitoring**:
- Prometheus metrics collection (always-on)
- Grafana dashboards (production-ready)
- Log aggregation with Loki (optional)

**Key Alerts**:
- Search latency p95 >1s
- Cache hit rate <50%
- Indexing throughput <1,000 files/min
- Error rate >1%
- Disk usage >90%

**Alert Channels**:
- Slack integration
- Email notifications
- PagerDuty (for production)

---

### Maintenance Plan

**Weekly**:
- Review performance metrics
- Check for slow queries
- Monitor resource usage trends
- Review error logs

**Monthly**:
- Run full load test suite
- Review and update performance budgets
- Analyze user feedback on performance
- Plan next round of optimizations

**Quarterly**:
- Deep dive performance analysis
- Update profiling and benchmarks
- Review and tune configuration
- Training on performance tools

---

### Future Optimization Opportunities

**Beyond EP-6 Scope**:

1. **Distributed Architecture** (EP-7?)
   - Multi-node vector search
   - Distributed caching with Redis
   - Horizontal scaling for high QPS

2. **Advanced Caching Strategies**
   - Semantic cache (embedding similarity)
   - Predictive prefetching
   - Multi-tier cache (L1/L2)

3. **ML-Based Optimization**
   - Query result ranking with ML
   - Adaptive nprobes via reinforcement learning
   - Anomaly detection for performance issues

4. **Alternative Vector Databases**
   - Evaluate Faiss for ultra-low latency
   - Evaluate Milvus for distributed deployment
   - Benchmark Pinecone/Weaviate for managed options

5. **GPU Acceleration**
   - GPU-accelerated vector search
   - GPU-accelerated embedding
   - CUDA optimization for tree-sitter parsing

---

### Knowledge Transfer

**Documentation**:
- All optimization techniques documented
- Configuration options explained
- Troubleshooting guides created
- Best practices established

**Training**:
- Team walkthrough of optimizations
- Demo of profiling tools
- Load testing training
- Performance monitoring overview

**Artifacts**:
- Profiling scripts and benchmarks
- Load test suite
- CI integration
- Monitoring dashboards

---

### Success Review

**Week 8: Post-Implementation Review**

**Agenda**:
1. Review all success criteria
2. Compare against baseline metrics
3. Discuss challenges and lessons learned
4. Identify areas for further improvement
5. Plan EP-7 (if needed)

**Deliverables**:
- Success review document
- Lessons learned
- EP-7 proposal (optional)
- Team retrospective notes

---

## Appendix

### A. Technology Stack

**Profiling**:
- **py-spy**: Sampling profiler for Python (0.3.14)
- **clinic.js**: Profiler for Node.js/Bun (13.0.0)
- **speedscope.app**: Flame graph visualizer (web)

**Caching**:
- **functools.lru_cache**: Python built-in (Python 3.11)
- **Redis**: Optional distributed cache (7.0+)

**Async**:
- **asyncio**: Python built-in (Python 3.11)
- **aiosqlite**: Async SQLite driver (0.19.0)

**Compression**:
- **zstd**: Fast compression library (1.5.5)

**Load Testing**:
- **Locust**: Python load testing framework (2.16.1)
- **k6**: Go-based load testing (0.47.0)

**Monitoring**:
- **Prometheus**: Metrics collection (2.45.0)
- **Grafana**: Visualization (10.2.0)
- **Loki**: Log aggregation (2.9.0, optional)

---

### B. Configuration Options

**Indexing**:
```yaml
indexing:
  parallel_workers: 8-16  # Number of parallel processes
  batch_size: 100         # Initial batch size (adaptive)
  min_batch_size: 10      # Minimum batch size
  max_batch_size: 500     # Maximum batch size
  ast_cache_size: 1000    # Number of ASTs to cache
  incremental: true       # Enable incremental embedding
```

**Search**:
```yaml
search:
  cache_enabled: true     # Enable query caching
  cache_size: 1000        # Number of queries to cache
  cache_ttl: 300          # TTL in seconds (5 minutes)
  nprobes: 10             # Initial nprobes for LanceDB
  adaptive_nprobes: true  # Enable adaptive nprobes
  connection_pool_size: 10 # SQLite connection pool size
  parallel_hybrid: true   # Enable parallel hybrid search
```

**Storage**:
```yaml
storage:
  compaction_enabled: true        # Enable LanceDB compaction
  compaction_schedule: weekly     # Compaction schedule
  compaction_threshold: 0.2       # Compact after 20% new data
  wal_mode: true                  # Enable SQLite WAL mode
  compression_enabled: true       # Enable content compression
  compression_algorithm: zstd     # Compression algorithm
  vacuum_schedule: weekly         # SQLite VACUUM schedule
```

**Runtime**:
```yaml
runtime:
  lazy_loading: true              # Enable lazy model loading
  webview_code_splitting: true    # Enable code splitting
  webview_virtual_scrolling: true # Enable virtual scrolling
  ipc_serialization: messagepack  # IPC serialization format
```

**Performance Budgets**:
```yaml
performance_budgets:
  indexing_throughput_min: 2500   # files/min
  search_latency_p50_max: 150     # ms
  search_latency_p95_max: 1000    # ms
  extension_activation_max: 2000  # ms
  webview_load_max: 1000          # ms
```

---

### C. Flame Graph Interpretation Guide

**Key Patterns**:

**Wide Bars**: Functions that consume a lot of CPU time
- Look for wide bars high in the stack
- These are good optimization targets

**Tall Stacks**: Deep call chains
- May indicate recursive algorithms
- Consider iterative alternatives

**Repeated Patterns**: Same function called many times
- Good candidates for caching or memoization
- Consider batching if applicable

**Platform/Library Code**: Bottom of the stack
- Usually not worth optimizing
- Focus on your own code above it

**Hot Colors**: Functions with high self-time
- Functions that do work themselves (not just call others)
- Prime targets for optimization

---

### D. Glossary

**Terms**:

- **p50, p95, p99**: Percentile metrics (50th, 95th, 99th percentile)
- **QPS**: Queries per second
- **TTL**: Time to live (cache expiration time)
- **Nprobes**: Number of clusters to search in IVF index
- **IVF_PQ**: Inverted File with Product Quantization (vector index type)
- **WAL**: Write-Ahead Logging (SQLite journal mode)
- **LRU**: Least Recently Used (cache eviction policy)
- **KNN**: K-Nearest Neighbors (vector search algorithm)
- **BM25**: Best Matching 25 (text search algorithm)
- **AST**: Abstract Syntax Tree
- **IPC**: Inter-Process Communication

---

### E. References

**Profiling**:
- py-spy documentation: https://github.com/benfred/py-spy
- clinic.js documentation: https://clinicjs.org/
- speedscope.app: https://speedscope.app/

**Optimization**:
- LanceDB documentation: https://lancedb.github.io/lancedb/
- SQLite performance tuning: https://www.sqlite.org/optoverview.html
- Python multiprocessing: https://docs.python.org/3/library/multiprocessing.html

**Load Testing**:
- Locust documentation: https://docs.locust.io/
- k6 documentation: https://k6.io/docs/

**Monitoring**:
- Prometheus documentation: https://prometheus.io/docs/
- Grafana documentation: https://grafana.com/docs/

---

## Sign-Off

**Project Manager**: ___________________________ Date: ___________

**Tech Lead**: ___________________________ Date: ___________

**Engineer**: ___________________________ Date: ___________

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-11  
**Next Review**: After Phase 1 completion
