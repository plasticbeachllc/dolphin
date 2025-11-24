# Query Caching System

**Version:** 1.0  
**Last Updated:** 2025-11-11

---

## Overview

The Dolphin knowledge base implements a **multi-level query caching system** to improve search performance and reduce API costs. The cache stores both embedding vectors and search results with configurable time-to-live (TTL) settings.

### Benefits

- **🚀 Performance**: 2-10x faster query response times for cached queries
- **💰 Cost Reduction**: Eliminates redundant embedding API calls
- **📊 Scalability**: Supports both in-memory and Redis backends for different deployment scenarios
- **🔧 Flexibility**: Can be enabled/disabled at runtime without code changes

---

## Architecture

### Cache Levels

The caching system operates at two levels:

```
┌─────────────────────────────────────────┐
│          User Query                     │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  L1: Embedding Cache                    │
│  Query Text → Embedding Vector          │
│  TTL: 1 hour (3600s)                    │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  L2: Result Cache                       │
│  (Query + Params) → Search Results      │
│  TTL: 15 minutes (900s)                 │
└─────────────────────────────────────────┘
```

**L1: Embedding Cache**

- **Purpose**: Cache embedding vectors to avoid redundant API calls
- **Key**: `embed:{model}:{hash(query)}`
- **Value**: JSON-encoded embedding vector
- **TTL**: 1 hour (embeddings are stable)

**L2: Result Cache**

- **Purpose**: Cache complete search results
- **Key**: `results:{hash(query + params)}`
- **Value**: JSON-encoded search results
- **TTL**: 15 minutes (results may change as index updates)

### Storage Backends

The cache supports two storage backends:

| Backend       | Use Case                  | Persistence | Shared | Performance |
| ------------- | ------------------------- | ----------- | ------ | ----------- |
| **In-Memory** | Development, testing      | No          | No     | Fastest     |
| **Redis**     | Production, multi-process | Yes         | Yes    | Fast        |

---

## Usage

### Basic Setup

#### In-Memory Cache (Development)

```python
from kb.cache import create_cache

# Create in-memory cache
cache = create_cache(enabled=True)

# Cache an embedding
cache.set_embedding("authentication query", "small", [0.1, 0.2, 0.3])

# Retrieve cached embedding
embedding = cache.get_embedding("authentication query", "small")
```

#### Redis Cache (Production)

```python
from kb.cache import create_cache

# Create Redis-backed cache
cache = create_cache(
    redis_url="redis://localhost:6379/0",
    embedding_ttl=3600,  # 1 hour
    result_ttl=900,      # 15 minutes
    enabled=True
)
```

### Integration with Search Backend

The search backend automatically uses caching when enabled:

```python
from kb.api.search_backend import create_search_backend
from pathlib import Path

backend = create_search_backend(
    store_root=Path("/path/to/store"),
    cache_enabled=True,
    redis_url="redis://localhost:6379/0"  # Optional
)

# First search - cache miss, slow
results = backend.search(SearchRequest(query="authentication", top_k=5))

# Second search - cache hit, fast (2-10x faster)
results = backend.search(SearchRequest(query="authentication", top_k=5))
```

### Cache Management

#### Get Statistics

```python
stats = cache.get_stats()
print(f"Embedding hit rate: {stats['embedding_hit_rate']:.1%}")
print(f"Result hit rate: {stats['result_hit_rate']:.1%}")
print(f"Total requests: {stats['total_requests']}")
```

#### Invalidate Cache

```python
# Invalidate all cached results for a repository
# (Call this after reindexing)
cache.invalidate_repo("my-repo")

# Clear all cache data
cache.clear()
```

#### Enable/Disable at Runtime

```python
# Disable caching
cache.enabled = False

# Re-enable caching
cache.enabled = True
```

---

## Configuration

### Environment Variables

```bash
# Redis connection URL
export REDIS_URL="redis://localhost:6379/0"

# Enable/disable caching
export CACHE_ENABLED="true"
```

### Configuration File

```python
# kb/config.py
from kb.config import KBConfig

config = KBConfig(
    cache_enabled=True,
    redis_url="redis://localhost:6379/0"
)
```

### Custom TTL Settings

```python
cache = create_cache(
    redis_url="redis://localhost:6379/0",
    embedding_ttl=7200,   # 2 hours
    result_ttl=1800,      # 30 minutes
    enabled=True
)
```

---

## Cache Key Design

### Embedding Keys

Format: `embed:{model}:{hash}`

```python
# Example
query = "how to authenticate users"
model = "small"
key = f"embed:{model}:{hash(query)}"
# → "embed:small:a1b2c3d4e5f6g7h8"
```

### Result Keys

Format: `results:{hash}`

```python
# Example
query = "authentication"
params = {"repo": "my-app", "top_k": 5}
key = f"results:{hash(query + json.dumps(params, sort_keys=True))}"
# → "results:x9y8z7w6v5u4t3s2"
```

**Important**: Parameters are sorted alphabetically before hashing to ensure cache consistency regardless of parameter order.

---

## Performance Characteristics

### Latency

| Operation        | In-Memory | Redis | No Cache  |
| ---------------- | --------- | ----- | --------- |
| Embedding lookup | <1ms      | 1-3ms | 50-200ms  |
| Result lookup    | <1ms      | 2-5ms | 100-500ms |

### Hit Rates

Expected hit rates vary by usage pattern:

| Scenario                       | Expected Hit Rate |
| ------------------------------ | ----------------- |
| Development (repeated queries) | 80-95%            |
| Production API (mixed queries) | 50-70%            |
| First-time queries             | 0%                |

### Memory Usage

In-memory cache footprint:

- **Embeddings**: ~12 KB per embedding (1536 dims × 8 bytes)
- **Results**: Varies by result size (typically 1-5 KB per query)
- **1000 cached queries**: ~15-20 MB

---

## Best Practices

### 1. Use Redis in Production

```python
# ✅ Good - Shared cache across processes
cache = create_cache(redis_url="redis://localhost:6379/0")

# ❌ Avoid - Separate cache per process
cache = create_cache(redis_url=None)
```

### 2. Invalidate on Reindex

```python
# After reindexing a repository
backend.index_repository(repo_name="my-app")
backend.cache.invalidate_repo("my-app")
```

### 3. Monitor Hit Rates

```python
import logging

stats = cache.get_stats()
logging.info(f"Cache performance: {stats['embedding_hit_rate']:.1%} hit rate")

# Alert if hit rate is unexpectedly low
if stats['total_requests'] > 100 and stats['embedding_hit_rate'] < 0.3:
    logging.warning("Low cache hit rate detected")
```

### 4. Set Appropriate TTLs

```python
# Embeddings: Long TTL (stable)
embedding_ttl = 3600  # 1 hour

# Results: Short TTL (may change)
result_ttl = 900  # 15 minutes

cache = create_cache(
    embedding_ttl=embedding_ttl,
    result_ttl=result_ttl
)
```

### 5. Graceful Degradation

The cache is designed to fail gracefully:

```python
# Cache failures don't crash the application
cache.set_embedding("query", "small", [0.1])  # If Redis is down, logs warning
embedding = cache.get_embedding("query", "small")  # Returns None, continues
```

---

## Troubleshooting

### Cache Not Working

**Symptom**: No performance improvement from caching

**Solutions**:

1. Verify cache is enabled:

   ```python
   assert cache.enabled is True
   ```

2. Check Redis connection:

   ```python
   if cache.redis:
       cache.redis.ping()  # Should not raise exception
   ```

3. Monitor hit rates:
   ```python
   stats = cache.get_stats()
   print(f"Hit rate: {stats['embedding_hit_rate']:.1%}")
   ```

### Redis Connection Errors

**Symptom**: `ConnectionError: Error connecting to Redis`

**Solutions**:

1. Verify Redis is running:

   ```bash
   redis-cli ping
   # Should return: PONG
   ```

2. Check connection URL:

   ```python
   cache = create_cache(redis_url="redis://localhost:6379/0")
   ```

3. Fallback to in-memory:
   ```python
   # Cache automatically falls back if Redis unavailable
   cache = create_cache(redis_url="redis://localhost:6379/0")
   # Logs warning and uses in-memory cache
   ```

### Low Hit Rates

**Symptom**: Hit rate <30% in production

**Possible Causes**:

1. Queries are too diverse (expected for new systems)
2. TTL is too short
3. Cache is being cleared too frequently

**Solutions**:

1. Increase TTL for stable data:

   ```python
   cache = create_cache(embedding_ttl=7200)  # 2 hours
   ```

2. Review invalidation frequency:
   ```python
   # Only invalidate on actual reindex, not on every change
   if reindex_completed:
       cache.invalidate_repo(repo_name)
   ```

---

## API Reference

### `QueryCache`

Main cache class.

#### Constructor

```python
QueryCache(
    redis_client: Optional[Any] = None,
    embedding_ttl: int = 3600,
    result_ttl: int = 900,
    enabled: bool = True
)
```

#### Methods

##### `get_embedding(query: str, model: str) -> Optional[list[float]]`

Retrieve cached embedding.

**Parameters:**

- `query`: Query text
- `model`: Model name (`"small"` or `"large"`)

**Returns:** Embedding vector or `None` if not cached

##### `set_embedding(query: str, model: str, embedding: list[float]) -> None`

Cache an embedding.

##### `get_results(query: str, **params) -> Optional[list[dict]]`

Retrieve cached search results.

**Parameters:**

- `query`: Query text
- `**params`: Search parameters (repo, top_k, etc.)

##### `set_results(query: str, results: list[dict], **params) -> None`

Cache search results.

##### `invalidate_repo(repo: str) -> None`

Invalidate all cached results for a repository.

##### `clear() -> None`

Clear all cached data.

##### `get_stats() -> dict`

Get cache statistics.

**Returns:**

```python
{
    "embedding_hits": int,
    "embedding_misses": int,
    "embedding_hit_rate": float,
    "result_hits": int,
    "result_misses": int,
    "result_hit_rate": float,
    "total_requests": int
}
```

### `create_cache()`

Factory function to create a cache instance.

```python
create_cache(
    redis_url: Optional[str] = None,
    embedding_ttl: int = 3600,
    result_ttl: int = 900,
    enabled: bool = True
) -> QueryCache
```

**Parameters:**

- `redis_url`: Redis connection URL (e.g., `"redis://localhost:6379/0"`)
- `embedding_ttl`: TTL for embeddings in seconds
- `result_ttl`: TTL for results in seconds
- `enabled`: Whether caching is enabled

---

## Testing

### Running Cache Tests

```bash
# Unit tests
pytest tests/unit/test_cache.py -v

# With coverage
pytest tests/unit/test_cache.py --cov=kb.cache --cov-report=term-missing

# Integration tests (requires Redis)
REDIS_URL=redis://localhost:6379/0 pytest tests/integration/test_cache*.py -v
```

### Test Coverage

Current test coverage: **95%+**

See [`tests/CACHE_TESTING_GUIDE.md`](../tests/CACHE_TESTING_GUIDE.md) for comprehensive testing documentation.

---

## Migration Guide

### Upgrading from No Cache

1. Install Redis (optional but recommended):

   ```bash
   # macOS
   brew install redis
   brew services start redis

   # Ubuntu/Debian
   sudo apt-get install redis-server
   sudo systemctl start redis
   ```

2. Update configuration:

   ```python
   # Before
   backend = create_search_backend(store_root=path)

   # After
   backend = create_search_backend(
       store_root=path,
       cache_enabled=True,
       redis_url="redis://localhost:6379/0"
   )
   ```

3. Monitor performance:
   ```python
   stats = backend.cache.get_stats()
   print(f"Hit rate: {stats['embedding_hit_rate']:.1%}")
   ```

---

## Related Documentation

- [Architecture Guide](./ARCHITECTURE.md)
- [Testing Guide](../tests/CACHE_TESTING_GUIDE.md)
- [Main Guide](./GUIDE.md)

---

## Support

For issues or questions:

- Documentation: [docs/](./README.md)
