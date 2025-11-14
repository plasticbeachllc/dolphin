# Comprehensive Caching Functionality Testing Guide

## Overview

This guide provides a complete testing strategy for the multi-level query caching system in Dolphin. It covers unit tests, integration tests, performance tests, and real-world scenarios to ensure the caching implementation is robust, performant, and production-ready.

## Table of Contents

1. [Testing Strategy](#testing-strategy)
2. [Unit Tests](#unit-tests)
3. [Integration Tests](#integration-tests)
4. [Performance Tests](#performance-tests)
5. [Real-World Scenarios](#real-world-scenarios)
6. [Verification Methods](#verification-methods)
7. [Test Data & Fixtures](#test-data--fixtures)
8. [CI/CD Considerations](#cicd-considerations)

---

## Testing Strategy

### Test Pyramid

```
           ┌─────────────────┐
           │   E2E Tests     │  ← Real-world scenarios (5%)
           │  (Production)   │
           └─────────────────┘
         ┌───────────────────────┐
         │  Integration Tests    │  ← Cache + Backend (20%)
         │  (Redis + API)        │
         └───────────────────────┘
    ┌────────────────────────────────┐
    │      Unit Tests                │  ← Cache logic (75%)
    │  (In-memory, isolated)         │
    └────────────────────────────────┘
```

### Coverage Goals

- **Unit Tests**: 95%+ coverage of [`cache.py`](../kb/cache/cache.py)
- **Integration Tests**: All cache integration points (embedding provider, search backend)
- **Performance Tests**: Latency, throughput, hit rates
- **E2E Tests**: Complete workflows with real data

---

## Unit Tests

### 1. Basic Cache Operations

**Test File**: [`tests/unit/test_cache.py`](../tests/unit/test_cache.py)

#### Test Cases

```python
# L1: Embedding Cache
def test_embedding_cache_hit():
    """Verify cached embeddings are retrieved correctly."""

def test_embedding_cache_miss():
    """Verify cache returns None for non-existent embeddings."""

def test_embedding_model_isolation():
    """Verify different models use separate cache keys."""
    cache.set_embedding("query", "small", [0.1, 0.2])
    cache.set_embedding("query", "large", [0.5, 0.6])
    assert cache.get_embedding("query", "small") != cache.get_embedding("query", "large")

# L2: Result Cache
def test_result_cache_hit():
    """Verify cached results are retrieved correctly."""

def test_result_cache_miss():
    """Verify cache returns None for non-existent results."""

def test_result_cache_params_matter():
    """Verify different search params create different cache keys."""
```

#### Run Unit Tests

```bash
# All cache unit tests
pytest tests/unit/test_cache.py -v

# Specific test class
pytest tests/unit/test_cache.py::TestQueryCache -v

# With coverage
pytest tests/unit/test_cache.py --cov=kb.cache --cov-report=html
```

### 2. Cache Key Generation

```python
def test_hash_key_stability():
    """Verify hash keys are deterministic."""
    cache = QueryCache()
    key1 = cache._hash_key("query", "param1", "param2")
    key2 = cache._hash_key("query", "param1", "param2")
    assert key1 == key2

def test_hash_key_uniqueness():
    """Verify different inputs produce different keys."""
    cache = QueryCache()
    key1 = cache._hash_key("query1")
    key2 = cache._hash_key("query2")
    assert key1 != key2

def test_param_order_independence():
    """Verify params are sorted for cache key consistency."""
    cache = QueryCache()
    cache.set_results("q", [{"id": "1"}], a="1", b="2")
    cached = cache.get_results("q", b="2", a="1")  # Different order
    assert cached is not None
```

### 3. Cache Statistics

```python
def test_stats_tracking():
    """Verify stats are tracked accurately."""
    cache = QueryCache()

    # Generate hits and misses
    cache.set_embedding("q1", "small", [0.1])
    cache.get_embedding("q1", "small")  # hit
    cache.get_embedding("q2", "small")  # miss

    stats = cache.get_stats()
    assert stats["embedding_hits"] == 1
    assert stats["embedding_misses"] == 1
    assert stats["embedding_hit_rate"] == 0.5

def test_stats_reset():
    """Verify stats can be reset."""
    cache = QueryCache()
    cache.set_embedding("q", "small", [0.1])
    cache.get_embedding("q", "small")

    cache.stats = {"embedding_hits": 0, "embedding_misses": 0,
                   "result_hits": 0, "result_misses": 0}

    stats = cache.get_stats()
    assert stats["total_requests"] == 0
```

### 4. Cache Invalidation

```python
def test_invalidate_repo():
    """Verify repo-specific invalidation."""
    cache = QueryCache()
    cache.set_results("q1", [{"id": "1"}], repo="repo1")
    cache.set_results("q2", [{"id": "2"}], repo="repo2")

    cache.invalidate_repo("repo1")

    assert cache.get_results("q1", repo="repo1") is None
    # Note: In-memory cache invalidation is conservative

def test_clear_all():
    """Verify complete cache clear."""
    cache = QueryCache()
    cache.set_embedding("q", "small", [0.1])
    cache.set_results("q", [{"id": "1"}])

    cache.clear()

    assert cache.get_embedding("q", "small") is None
    assert cache.get_results("q") is None
```

### 5. Cache Enable/Disable

```python
def test_cache_disabled():
    """Verify caching can be disabled."""
    cache = QueryCache(enabled=False)

    cache.set_embedding("q", "small", [0.1])
    cached = cache.get_embedding("q", "small")

    assert cached is None

def test_toggle_enabled():
    """Verify cache can be toggled at runtime."""
    cache = QueryCache(enabled=True)
    cache.set_embedding("q", "small", [0.1])

    cache.enabled = False
    assert cache.get_embedding("q", "small") is None

    cache.enabled = True
    assert cache.get_embedding("q", "small") == [0.1]
```

### 6. Error Handling

```python
def test_cache_read_error_handling():
    """Verify cache gracefully handles read errors."""
    cache = QueryCache()

    # Simulate corrupted cache data
    cache._memory_cache["embed:small:abc"] = ("invalid", 0)

    # Should return None, not crash
    result = cache.get_embedding("query", "small")
    assert result is None

def test_cache_write_error_handling():
    """Verify cache gracefully handles write errors."""
    # With mock Redis that raises exceptions
    mock_redis = MagicMock()
    mock_redis.setex.side_effect = Exception("Redis unavailable")

    cache = QueryCache(redis_client=mock_redis)

    # Should not crash
    cache.set_embedding("q", "small", [0.1])
```

---

## Integration Tests

### 1. Cache with Embedding Provider

**Test File**: [`tests/integration/test_cache_embeddings.py`](../tests/integration/test_cache_embeddings.py) (create this)

```python
import pytest
from kb.embeddings.provider import OpenAIEmbeddingProvider
from kb.cache import create_cache

@pytest.mark.integration
def test_embedding_provider_uses_cache():
    """Verify embedding provider integrates with cache."""
    cache = create_cache(enabled=True)
    provider = OpenAIEmbeddingProvider(cache=cache)

    # First call - miss
    embeddings1 = provider.embed_texts("small", ["test query"])
    assert cache.stats["embedding_misses"] == 1

    # Second call - hit (with mock or stub)
    embeddings2 = provider.embed_texts("small", ["test query"])
    assert cache.stats["embedding_hits"] == 1
    assert embeddings1 == embeddings2

@pytest.mark.integration
def test_cache_reduces_api_calls():
    """Verify cache reduces embedding API calls."""
    cache = create_cache(enabled=True)
    provider = OpenAIEmbeddingProvider(cache=cache)

    with patch.object(provider.client.embeddings, 'create') as mock_create:
        mock_create.return_value = MagicMock(data=[MagicMock(embedding=[0.1, 0.2])])

        # First call
        provider.embed_texts("small", ["query"])
        assert mock_create.call_count == 1

        # Second call - should use cache
        provider.embed_texts("small", ["query"])
        assert mock_create.call_count == 1  # No additional call
```

### 2. Cache with Search Backend

**Test File**: [`tests/integration/test_cache_search.py`](../tests/integration/test_cache_search.py) (create this)

```python
import pytest
from kb.api.search_backend import create_search_backend
from pathlib import Path
import tempfile

@pytest.mark.integration
def test_search_backend_caches_results():
    """Verify search backend caches complete results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backend = create_search_backend(
            store_root=Path(tmpdir),
            embedding_provider_type="stub",
            cache_enabled=True,
        )

        # Populate test data
        # ... add test chunks ...

        # First search - miss
        request = SearchRequest(query="test", top_k=5)
        results1 = backend.search(request)
        assert backend.cache.stats["result_misses"] == 1

        # Second search - hit
        results2 = backend.search(request)
        assert backend.cache.stats["result_hits"] == 1
        assert results1 == results2

@pytest.mark.integration
def test_cache_invalidation_on_reindex():
    """Verify cache is invalidated when repo is reindexed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backend = create_search_backend(
            store_root=Path(tmpdir),
            cache_enabled=True,
        )

        # Search and cache results
        request = SearchRequest(query="test", repo="test-repo")
        backend.search(request)

        # Reindex repo
        backend.cache.invalidate_repo("test-repo")

        # Next search should miss cache
        backend.search(request)
        assert backend.cache.stats["result_misses"] == 2
```

### 3. Redis Integration

**Test File**: [`tests/integration/test_cache_redis.py`](../tests/integration/test_cache_redis.py) (create this)

```python
import pytest
from kb.cache import create_cache

@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("REDIS_URL"),
    reason="Requires Redis server"
)
def test_redis_cache_persistence():
    """Verify Redis cache persists across instances."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # First cache instance
    cache1 = create_cache(redis_url=redis_url)
    cache1.set_embedding("test", "small", [0.1, 0.2, 0.3])

    # Second cache instance (simulates restart)
    cache2 = create_cache(redis_url=redis_url)
    cached = cache2.get_embedding("test", "small")

    assert cached == [0.1, 0.2, 0.3]

    # Cleanup
    cache2.clear()

@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("REDIS_URL"),
    reason="Requires Redis server"
)
def test_redis_ttl_expiration():
    """Verify Redis TTL expires old cache entries."""
    redis_url = os.getenv("REDIS_URL")

    cache = create_cache(
        redis_url=redis_url,
        embedding_ttl=1,  # 1 second
    )

    cache.set_embedding("test", "small", [0.1])

    # Immediately available
    assert cache.get_embedding("test", "small") is not None

    # Wait for expiration
    time.sleep(2)

    # Should be expired
    assert cache.get_embedding("test", "small") is None

    cache.clear()
```

---

## Performance Tests

### 1. Latency Benchmarks

**Test File**: [`tests/performance/test_cache_latency.py`](../tests/performance/test_cache_latency.py) (create this)

```python
import pytest
import time
from kb.cache import create_cache

@pytest.mark.performance
def test_cache_read_latency():
    """Measure cache read performance."""
    cache = create_cache(enabled=True)
    cache.set_embedding("test", "small", [0.1] * 1536)

    iterations = 1000
    start = time.time()

    for _ in range(iterations):
        cache.get_embedding("test", "small")

    elapsed = time.time() - start
    avg_latency = (elapsed / iterations) * 1000  # ms

    print(f"Average read latency: {avg_latency:.3f}ms")
    assert avg_latency < 1.0  # Should be sub-millisecond

@pytest.mark.performance
def test_cache_write_latency():
    """Measure cache write performance."""
    cache = create_cache(enabled=True)
    embedding = [0.1] * 1536

    iterations = 1000
    start = time.time()

    for i in range(iterations):
        cache.set_embedding(f"test_{i}", "small", embedding)

    elapsed = time.time() - start
    avg_latency = (elapsed / iterations) * 1000  # ms

    print(f"Average write latency: {avg_latency:.3f}ms")
    assert avg_latency < 2.0  # Should be fast

@pytest.mark.performance
def test_end_to_end_query_speedup():
    """Measure speedup from caching on complete queries."""
    backend = create_search_backend(cache_enabled=True)
    request = SearchRequest(query="authentication", top_k=5)

    # First query (cache miss)
    start = time.time()
    results1 = backend.search(request)
    time_uncached = time.time() - start

    # Second query (cache hit)
    start = time.time()
    results2 = backend.search(request)
    time_cached = time.time() - start

    speedup = time_uncached / time_cached
    print(f"Speedup: {speedup:.1f}x ({time_uncached*1000:.0f}ms → {time_cached*1000:.0f}ms)")

    assert speedup > 2.0  # Should be at least 2x faster
    assert results1 == results2
```

### 2. Throughput Tests

```python
@pytest.mark.performance
def test_concurrent_cache_access():
    """Test cache performance under concurrent load."""
    import concurrent.futures

    cache = create_cache(enabled=True)

    def worker(worker_id):
        for i in range(100):
            query = f"query_{worker_id}_{i}"
            cache.set_embedding(query, "small", [0.1] * 100)
            cached = cache.get_embedding(query, "small")
            assert cached is not None

    num_workers = 10
    start = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker, i) for i in range(num_workers)]
        concurrent.futures.wait(futures)

    elapsed = time.time() - start
    total_ops = num_workers * 100 * 2  # set + get
    throughput = total_ops / elapsed

    print(f"Throughput: {throughput:.0f} ops/sec")
    assert throughput > 1000  # Should handle >1000 ops/sec
```

### 3. Memory Usage

```python
@pytest.mark.performance
def test_cache_memory_footprint():
    """Measure memory usage of in-memory cache."""
    import sys

    cache = create_cache(enabled=True)

    # Baseline
    baseline = sys.getsizeof(cache._memory_cache)

    # Add 1000 embeddings
    for i in range(1000):
        cache.set_embedding(f"query_{i}", "small", [0.1] * 1536)

    # Measure growth
    size = sys.getsizeof(cache._memory_cache)
    growth_mb = (size - baseline) / 1024 / 1024

    print(f"Memory growth: {growth_mb:.2f} MB for 1000 embeddings")

    # 1000 embeddings × 1536 dims × 8 bytes ≈ 12 MB
    assert growth_mb < 20  # Should be reasonable
```

---

## Real-World Scenarios

### 1. Development Workflow

```python
@pytest.mark.scenario
def test_development_workflow():
    """Simulate typical development usage pattern."""
    cache = create_cache(enabled=True)

    # Developer makes same queries repeatedly
    common_queries = [
        "how to authenticate",
        "database schema",
        "API endpoints",
    ]

    # Initial queries (all misses)
    for query in common_queries:
        cache.get_embedding(query, "small")

    assert cache.stats["embedding_misses"] == 3
    assert cache.stats["embedding_hit_rate"] == 0.0

    # Cache responses
    for i, query in enumerate(common_queries):
        cache.set_embedding(query, "small", [float(i)] * 1536)

    # Repeated queries (all hits)
    for _ in range(5):
        for query in common_queries:
            cache.get_embedding(query, "small")

    # Should have high hit rate
    stats = cache.get_stats()
    print(f"Hit rate: {stats['embedding_hit_rate']:.1%}")
    assert stats["embedding_hit_rate"] > 0.8  # >80% hits
```

### 2. Production API Load

```python
@pytest.mark.scenario
def test_production_api_pattern():
    """Simulate production API with mixed queries."""
    cache = create_cache(enabled=True)

    # Zipfian distribution: some queries very common, most rare
    query_distribution = {
        "login": 100,       # Very common
        "signup": 50,
        "dashboard": 30,
        "settings": 20,
        "profile": 10,
        # 45 more rare queries...
    }

    for query, count in query_distribution.items():
        # First request caches
        cache.set_embedding(query, "small", [0.1] * 1536)

        # Subsequent requests hit cache
        for _ in range(count - 1):
            cache.get_embedding(query, "small")

    stats = cache.get_stats()
    print(f"Production hit rate: {stats['embedding_hit_rate']:.1%}")

    # Should achieve reasonable hit rate
    assert stats["embedding_hit_rate"] > 0.5
```

### 3. Repository Reindex

```python
@pytest.mark.scenario
def test_reindex_invalidation_workflow():
    """Test cache behavior during repository reindexing."""
    backend = create_search_backend(cache_enabled=True)

    # Initial searches
    queries = ["auth", "database", "api"]
    for query in queries:
        request = SearchRequest(query=query, repo="my-repo")
        backend.search(request)

    # Verify caching
    for query in queries:
        request = SearchRequest(query=query, repo="my-repo")
        backend.search(request)

    initial_hits = backend.cache.stats["result_hits"]
    assert initial_hits == 3  # All cached

    # Simulate reindex
    backend.cache.invalidate_repo("my-repo")

    # Searches should miss cache
    for query in queries:
        request = SearchRequest(query=query, repo="my-repo")
        backend.search(request)

    final_misses = backend.cache.stats["result_misses"]
    assert final_misses == 6  # 3 initial + 3 after invalidation
```

### 4. Cold Start vs Warm Cache

```python
@pytest.mark.scenario
def test_cold_start_vs_warm_cache():
    """Compare performance between cold start and warm cache."""
    backend = create_search_backend(cache_enabled=True)
    test_queries = ["test query"] * 10

    # Cold start
    backend.cache.clear()
    cold_start = time.time()
    for query in test_queries:
        backend.search(SearchRequest(query=query))
    cold_time = time.time() - cold_start

    # Warm cache
    warm_start = time.time()
    for query in test_queries:
        backend.search(SearchRequest(query=query))
    warm_time = time.time() - warm_start

    improvement = (cold_time - warm_time) / cold_time * 100
    print(f"Warm cache improvement: {improvement:.1f}%")
    print(f"Cold: {cold_time:.3f}s, Warm: {warm_time:.3f}s")

    assert warm_time < cold_time * 0.5  # At least 50% faster
```

---

## Verification Methods

### 1. Visual Inspection

#### Cache Statistics Dashboard

```python
def print_cache_dashboard(cache):
    """Print formatted cache statistics."""
    stats = cache.get_stats()

    print("\n" + "="*60)
    print("CACHE STATISTICS DASHBOARD")
    print("="*60)
    print(f"\n📊 Embeddings:")
    print(f"   Hits:   {stats['embedding_hits']:,}")
    print(f"   Misses: {stats['embedding_misses']:,}")
    print(f"   Rate:   {stats['embedding_hit_rate']:.1%}")

    print(f"\n🔍 Results:")
    print(f"   Hits:   {stats['result_hits']:,}")
    print(f"   Misses: {stats['result_misses']:,}")
    print(f"   Rate:   {stats['result_hit_rate']:.1%}")

    print(f"\n💯 Overall:")
    print(f"   Total:  {stats['total_requests']:,} requests")
    print("="*60 + "\n")

# Usage in tests
def test_with_dashboard():
    cache = create_cache(enabled=True)
    # ... run test operations ...
    print_cache_dashboard(cache)
```

### 2. Logging Verification

```python
import logging

def test_cache_with_logging(caplog):
    """Verify cache operations through logs."""
    caplog.set_level(logging.INFO)

    cache = create_cache(redis_url="redis://localhost:6379/0")
    cache.clear()
    cache.invalidate_repo("test-repo")

    # Verify log messages
    assert "Cache cleared" in caplog.text
    assert "Invalidated cache for repo: test-repo" in caplog.text
```

### 3. Direct Redis Inspection

```bash
# Connect to Redis
redis-cli

# List all cache keys
KEYS embed:*
KEYS results:*

# Check TTL
TTL embed:small:abc123

# Get cached value
GET embed:small:abc123

# Count cache entries
DBSIZE

# Monitor cache activity in real-time
MONITOR
```

### 4. Programmatic Verification

```python
def verify_cache_behavior(cache, query, model="small"):
    """Comprehensive cache verification."""
    embedding = [0.1] * 1536

    # 1. Verify cache miss
    assert cache.get_embedding(query, model) is None
    print("✓ Cache miss verified")

    # 2. Set embedding
    cache.set_embedding(query, model, embedding)
    print("✓ Embedding cached")

    # 3. Verify cache hit
    cached = cache.get_embedding(query, model)
    assert cached == embedding
    print("✓ Cache hit verified")

    # 4. Verify stats updated
    stats = cache.get_stats()
    assert stats["embedding_hits"] > 0
    print("✓ Stats tracking verified")

    print("\n✅ All verifications passed!")

# Usage
cache = create_cache(enabled=True)
verify_cache_behavior(cache, "test query")
```

### 5. Performance Comparison

```python
def compare_with_without_cache(backend, queries):
    """Compare performance with and without cache."""
    results = {}

    # Without cache
    backend.cache.enabled = False
    start = time.time()
    for query in queries:
        backend.search(SearchRequest(query=query))
    results["without_cache"] = time.time() - start

    # With cache (warm)
    backend.cache.enabled = True
    backend.cache.clear()  # Start fresh

    # Prime cache
    for query in queries:
        backend.search(SearchRequest(query=query))

    # Measure warm cache
    start = time.time()
    for query in queries:
        backend.search(SearchRequest(query=query))
    results["with_cache"] = time.time() - start

    # Report
    speedup = results["without_cache"] / results["with_cache"]
    print(f"\n{'Scenario':<20} {'Time (ms)':<15} {'Speedup'}")
    print("-" * 50)
    print(f"{'Without cache':<20} {results['without_cache']*1000:>10.1f} ms {'1.0x':>10}")
    print(f"{'With cache (warm)':<20} {results['with_cache']*1000:>10.1f} ms {speedup:>9.1f}x")

    return results
```

---

## Test Data & Fixtures

### 1. Sample Embeddings

```python
@pytest.fixture
def sample_embeddings():
    """Generate realistic test embeddings."""
    return {
        "small": [[float(i) / 1536 for i in range(1536)] for _ in range(10)],
        "large": [[float(i) / 3072 for i in range(3072)] for _ in range(10)],
    }

@pytest.fixture
def sample_queries():
    """Common test queries."""
    return [
        "how to authenticate users",
        "database schema design",
        "API endpoint documentation",
        "error handling best practices",
        "deployment configuration",
    ]
```

### 2. Mock Redis

```python
@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    class MockRedis:
        def __init__(self):
            self.data = {}
            self.ttls = {}

        def get(self, key):
            if key in self.data:
                # Check TTL
                if key in self.ttls and time.time() > self.ttls[key]:
                    del self.data[key]
                    del self.ttls[key]
                    return None
                return self.data[key]
            return None

        def setex(self, key, ttl, value):
            self.data[key] = value
            self.ttls[key] = time.time() + ttl

        def delete(self, key):
            self.data.pop(key, None)
            self.ttls.pop(key, None)

        def scan_iter(self, match=None):
            if match:
                pattern = match.replace("*", "")
                return [k for k in self.data.keys() if pattern in k]
            return list(self.data.keys())

        def ping(self):
            return True

    return MockRedis()
```

### 3. Test Backends

```python
@pytest.fixture
def cache_enabled_backend(tmp_path):
    """Search backend with caching enabled."""
    return create_search_backend(
        store_root=tmp_path,
        embedding_provider_type="stub",
        cache_enabled=True,
    )

@pytest.fixture
def cache_disabled_backend(tmp_path):
    """Search backend with caching disabled."""
    return create_search_backend(
        store_root=tmp_path,
        embedding_provider_type="stub",
        cache_enabled=False,
    )
```

---

## CI/CD Considerations

### 1. Test Matrix

```yaml
# .github/workflows/test-cache.yml
name: Cache Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run unit tests
        run: pytest tests/unit/test_cache.py -v

  integration-tests-redis:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:7
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v3
      - name: Run Redis integration tests
        env:
          REDIS_URL: redis://localhost:6379/0
        run: pytest tests/integration/test_cache_redis.py -v

  performance-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run performance benchmarks
        run: pytest tests/performance/test_cache_latency.py -v --benchmark
```

### 2. Test Environments

```bash
# Local development (in-memory cache)
CACHE_ENABLED=true pytest tests/

# CI/CD (with Redis)
CACHE_ENABLED=true REDIS_URL=redis://localhost:6379/0 pytest tests/

# Performance testing
CACHE_ENABLED=true pytest tests/performance/ --benchmark-only

# Coverage reporting
pytest tests/ --cov=kb.cache --cov-report=html --cov-report=term
```

### 3. Test Data Cleanup

```python
@pytest.fixture(autouse=True)
def cleanup_cache():
    """Auto-cleanup cache after each test."""
    yield

    # Cleanup Redis if used
    if os.getenv("REDIS_URL"):
        import redis
        client = redis.from_url(os.getenv("REDIS_URL"))
        for key in client.scan_iter(match="embed:*"):
            client.delete(key)
        for key in client.scan_iter(match="results:*"):
            client.delete(key)
```

---

## Running the Full Test Suite

### Quick Start

```bash
# All cache tests
pytest tests/unit/test_cache.py -v

# With coverage
pytest tests/unit/test_cache.py --cov=kb.cache --cov-report=term-missing

# Integration tests (requires Redis)
REDIS_URL=redis://localhost:6379/0 pytest tests/integration/test_cache*.py -v

# Performance tests
pytest tests/performance/test_cache*.py -v --benchmark
```

### Comprehensive Testing

```bash
# 1. Unit tests
pytest tests/unit/test_cache.py -v

# 2. Integration tests
docker-compose up -d redis  # Start Redis
REDIS_URL=redis://localhost:6379/0 pytest tests/integration/test_cache*.py -v

# 3. Performance tests
pytest tests/performance/test_cache*.py -v

# 4. Real-world scenarios
pytest tests/ -m scenario -v

# 5. Generate coverage report
pytest tests/ --cov=kb.cache --cov-report=html
open htmlcov/index.html
```

### Test Markers

```python
# In test files
@pytest.mark.unit
def test_basic_cache():
    """Unit test - fast, isolated."""
    pass

@pytest.mark.integration
def test_with_redis():
    """Integration test - requires Redis."""
    pass

@pytest.mark.performance
def test_latency():
    """Performance test - benchmarking."""
    pass

@pytest.mark.scenario
def test_real_world():
    """Real-world scenario test."""
    pass
```

```bash
# Run specific test types
pytest -m unit
pytest -m integration
pytest -m performance
pytest -m scenario
```

---

## Summary Checklist

### ✅ Unit Tests

- [x] Basic cache operations (get/set)
- [x] Cache key generation and stability
- [x] Statistics tracking
- [x] Invalidation logic
- [x] Enable/disable functionality
- [x] Error handling
- [x] TTL behavior (in-memory)

### ✅ Integration Tests

- [ ] Cache + Embedding Provider
- [ ] Cache + Search Backend
- [ ] Redis persistence
- [ ] Redis TTL expiration
- [ ] Multi-process sharing (Redis)

### ✅ Performance Tests

- [ ] Read/write latency
- [ ] Throughput under load
- [ ] Memory footprint
- [ ] Concurrent access
- [ ] End-to-end speedup

### ✅ Real-World Scenarios

- [ ] Development workflow (high hit rate)
- [ ] Production API load (mixed queries)
- [ ] Repository reindex invalidation
- [ ] Cold start vs warm cache

### ✅ Verification

- [ ] Cache statistics monitoring
- [ ] Log message verification
- [ ] Direct Redis inspection
- [ ] Performance comparisons

---

## Next Steps

1. **Run existing tests**: `pytest tests/unit/test_cache.py -v`
2. **Add integration tests**: Create test files for Redis and backend integration
3. **Create performance benchmarks**: Measure latency and throughput
4. **Document results**: Update this guide with actual performance numbers
5. **Set up CI/CD**: Add cache tests to your continuous integration pipeline

## References

- [Cache Implementation](../kb/cache/cache.py)
- [Existing Unit Tests](../tests/unit/test_cache.py)
- [Caching Documentation](../docs/CACHING.md)
- [Testing Documentation](./TESTING.md)
