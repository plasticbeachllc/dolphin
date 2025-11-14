"""Unit tests for query result caching."""

import time

import pytest

from kb.cache.query_cache import (
    QueryResultCache,
    clear_query_cache,
    get_query_cache,
)


class TestQueryResultCache:
    """Unit tests for QueryResultCache class."""

    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = QueryResultCache(max_size=100, ttl_seconds=300.0)

        assert cache.max_size == 100
        assert cache.ttl_seconds == 300.0
        assert cache.size() == 0
        assert cache.hit_rate() == 0.0

    def test_put_and_get(self):
        """Test basic put and get operations."""
        cache = QueryResultCache(max_size=10)
        results = [{"id": "1", "text": "test"}]

        cache.put("test query", {}, results)
        cached = cache.get("test query", {})

        assert cached == results

    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = QueryResultCache(max_size=10)

        result = cache.get("nonexistent query", {})
        assert result is None

    def test_cache_with_different_params(self):
        """Test that different params create different cache entries."""
        cache = QueryResultCache(max_size=10)

        results1 = [{"id": "1"}]
        results2 = [{"id": "2"}]

        cache.put("query", {"repo": "repo1"}, results1)
        cache.put("query", {"repo": "repo2"}, results2)

        assert cache.get("query", {"repo": "repo1"}) == results1
        assert cache.get("query", {"repo": "repo2"}) == results2

    def test_ttl_expiration(self):
        """Test TTL-based cache expiration."""
        cache = QueryResultCache(max_size=10, ttl_seconds=0.1)
        results = [{"id": "1"}]

        cache.put("test query", {}, results)
        assert cache.get("test query", {}) == results

        # Wait for TTL to expire
        time.sleep(0.15)

        # Should be expired
        assert cache.get("test query", {}) is None

    def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = QueryResultCache(max_size=3)

        cache.put("query1", {}, [{"id": "1"}])
        cache.put("query2", {}, [{"id": "2"}])
        cache.put("query3", {}, [{"id": "3"}])

        # Cache is now full
        assert cache.size() == 3

        # Add a 4th item, should evict query1
        cache.put("query4", {}, [{"id": "4"}])

        assert cache.size() == 3
        assert cache.get("query1", {}) is None  # Evicted
        assert cache.get("query2", {}) is not None
        assert cache.get("query3", {}) is not None
        assert cache.get("query4", {}) is not None

    def test_lru_ordering_on_access(self):
        """Test that accessing an item moves it to the end."""
        cache = QueryResultCache(max_size=3)

        cache.put("query1", {}, [{"id": "1"}])
        cache.put("query2", {}, [{"id": "2"}])
        cache.put("query3", {}, [{"id": "3"}])

        # Access query1, making it most recent
        cache.get("query1", {})

        # Add query4, should evict query2 (oldest)
        cache.put("query4", {}, [{"id": "4"}])

        assert cache.get("query1", {}) is not None  # Still present
        assert cache.get("query2", {}) is None  # Evicted
        assert cache.get("query3", {}) is not None
        assert cache.get("query4", {}) is not None

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        cache = QueryResultCache(max_size=10)
        results = [{"id": "1"}]

        cache.put("test query", {}, results)

        # 2 hits
        cache.get("test query", {})
        cache.get("test query", {})

        # 2 misses
        cache.get("other1", {})
        cache.get("other2", {})

        # Hit rate should be 50%
        assert cache.hit_rate() == 50.0

    def test_invalidate_repo(self):
        """Test repository-based cache invalidation."""
        cache = QueryResultCache(max_size=10)

        cache.put("query1", {"repo": "repo1"}, [{"id": "1"}])
        cache.put("query2", {"repo": "repo1"}, [{"id": "2"}])
        cache.put("query3", {"repo": "repo2"}, [{"id": "3"}])

        # Update repo1 timestamp
        cache.invalidate_repo("repo1")

        # Queries for repo1 should be invalid
        assert cache.get("query1", {"repo": "repo1"}) is None
        assert cache.get("query2", {"repo": "repo1"}) is None

        # Query for repo2 should still be valid
        assert cache.get("query3", {"repo": "repo2"}) is not None

    def test_clear(self):
        """Test cache clear."""
        cache = QueryResultCache(max_size=10)

        cache.put("query1", {}, [{"id": "1"}])
        cache.put("query2", {}, [{"id": "2"}])

        assert cache.size() == 2

        cache.clear()

        assert cache.size() == 0
        assert cache.hit_rate() == 0.0

    def test_stats(self):
        """Test stats method."""
        cache = QueryResultCache(max_size=10)

        cache.put("query", {}, [{"id": "1"}])
        cache.get("query", {})  # Hit
        cache.get("other", {})  # Miss

        stats = cache.stats()

        assert stats["size"] == 1
        assert stats["max_size"] == 10
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 50.0
        assert stats["total_requests"] == 2

    def test_param_normalization(self):
        """Test that parameter order doesn't affect caching."""
        cache = QueryResultCache(max_size=10)
        results = [{"id": "1"}]

        # Put with params in one order
        cache.put("query", {"b": 2, "a": 1}, results)

        # Get with params in different order
        cached = cache.get("query", {"a": 1, "b": 2})

        # Should still hit cache
        assert cached == results
        assert cache.hit_rate() == 100.0

    def test_similarity_search_disabled(self):
        """Test that similarity search is disabled by default."""
        cache = QueryResultCache(max_size=10)

        cache.put("hello world", {}, [{"id": "1"}])

        # Similar but not exact query should miss
        result = cache.get("hello there", {})
        assert result is None

    def test_cache_key_generation(self):
        """Test cache key generation."""
        cache = QueryResultCache(max_size=10)

        # Different queries should generate different keys
        key1 = cache._make_cache_key("query1", {})
        key2 = cache._make_cache_key("query2", {})
        key3 = cache._make_cache_key("query1", {"repo": "test"})

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3


class TestGlobalCacheHelpers:
    """Unit tests for global cache helper functions."""

    def test_get_query_cache(self):
        """Test getting global cache instance."""
        # Clear first
        clear_query_cache()

        cache1 = get_query_cache()
        cache2 = get_query_cache()

        # Should return same instance
        assert cache1 is cache2

    def test_clear_query_cache(self):
        """Test clearing global cache."""
        cache = get_query_cache()

        cache.put("query", {}, [{"id": "1"}])
        assert cache.size() == 1

        clear_query_cache()

        # Cache should be cleared
        assert cache.size() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
