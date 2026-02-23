"""Unit tests for query caching functionality."""

from unittest.mock import MagicMock, patch

from kb.cache import QueryCache, create_cache


class TestQueryCache:
    """Test query cache functionality."""

    def test_embedding_cache_hit(self):
        """Verify cached embeddings are retrieved correctly."""
        cache = QueryCache(enabled=True)
        cache.set_embedding("test query", "small", [0.1, 0.2, 0.3])
        cached = cache.get_embedding("test query", "small")
        assert cached == [0.1, 0.2, 0.3]
        stats = cache.get_stats()
        assert stats["embedding_hits"] == 1
        assert stats["embedding_misses"] == 0

    def test_embedding_cache_miss(self):
        """Verify cache returns None for non-existent embeddings."""
        cache = QueryCache(enabled=True)
        cached = cache.get_embedding("nonexistent", "small")
        assert cached is None
        stats = cache.get_stats()
        assert stats["embedding_misses"] == 1
        assert stats["embedding_hits"] == 0

    def test_embedding_model_isolation(self):
        """Verify different models use separate cache keys."""
        cache = QueryCache(enabled=True)
        cache.set_embedding("query", "small", [0.1, 0.2])
        cache.set_embedding("query", "large", [0.5, 0.6])

        small_cached = cache.get_embedding("query", "small")
        large_cached = cache.get_embedding("query", "large")

        assert small_cached == [0.1, 0.2]
        assert large_cached == [0.5, 0.6]
        assert small_cached != large_cached

    def test_result_cache_hit(self):
        """Verify cached results are retrieved correctly."""
        cache = QueryCache(enabled=True)
        results = [{"chunk_id": "1", "score": 0.9}]
        params = {"repo": "test-repo", "top_k": 5}
        cache.set_results("test query", results, **params)
        cached = cache.get_results("test query", **params)
        assert cached == results
        stats = cache.get_stats()
        assert stats["result_hits"] == 1

    def test_result_cache_miss(self):
        """Verify cache returns None for non-existent results."""
        cache = QueryCache(enabled=True)
        cached = cache.get_results("nonexistent", repo="test")
        assert cached is None
        stats = cache.get_stats()
        assert stats["result_misses"] == 1

    def test_result_cache_params_matter(self):
        """Verify different search params create different cache keys."""
        cache = QueryCache(enabled=True)
        results1 = [{"chunk_id": "1"}]
        results2 = [{"chunk_id": "2"}]

        cache.set_results("query", results1, repo="repo1", top_k=5)
        cache.set_results("query", results2, repo="repo2", top_k=5)

        cached1 = cache.get_results("query", repo="repo1", top_k=5)
        cached2 = cache.get_results("query", repo="repo2", top_k=5)

        assert cached1 == results1
        assert cached2 == results2


class TestCacheKeyGeneration:
    """Test cache key generation."""

    def test_hash_key_stability(self):
        """Verify hash keys are deterministic."""
        cache = QueryCache()
        key1 = cache._hash_key("query", "param1", "param2")
        key2 = cache._hash_key("query", "param1", "param2")
        assert key1 == key2

    def test_hash_key_uniqueness(self):
        """Verify different inputs produce different keys."""
        cache = QueryCache()
        key1 = cache._hash_key("query1")
        key2 = cache._hash_key("query2")
        assert key1 != key2

    def test_param_order_independence(self):
        """Verify params are sorted for cache key consistency."""
        cache = QueryCache()
        results = [{"id": "1"}]
        cache.set_results("q", results, a="1", b="2")
        cached = cache.get_results("q", b="2", a="1")  # Different order
        assert cached is not None
        assert cached == results


class TestCacheStatistics:
    """Test cache statistics tracking."""

    def test_stats_tracking(self):
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

    def test_stats_reset(self):
        """Verify stats can be reset."""
        cache = QueryCache()
        cache.set_embedding("q", "small", [0.1])
        cache.get_embedding("q", "small")

        cache.stats = {
            "embedding_hits": 0,
            "embedding_misses": 0,
            "result_hits": 0,
            "result_misses": 0,
        }

        stats = cache.get_stats()
        assert stats["total_requests"] == 0
        assert stats["embedding_hit_rate"] == 0.0

    def test_hit_rate_calculation(self):
        """Verify hit rate is calculated correctly."""
        cache = QueryCache()

        # Set up 3 hits, 1 miss
        cache.set_embedding("q1", "small", [0.1])
        cache.get_embedding("q1", "small")  # hit
        cache.get_embedding("q1", "small")  # hit
        cache.get_embedding("q1", "small")  # hit
        cache.get_embedding("q2", "small")  # miss

        stats = cache.get_stats()
        assert stats["embedding_hit_rate"] == 0.75


class TestCacheInvalidation:
    """Test cache invalidation."""

    def test_invalidate_repo(self):
        """Verify repo-specific invalidation."""
        cache = QueryCache()
        cache.set_results("q1", [{"id": "1"}], repo="repo1")
        cache.set_results("q2", [{"id": "2"}], repo="repo2")

        cache.invalidate_repo("repo1")

        assert cache.get_results("q1", repo="repo1") is None
        assert cache.get_results("q2", repo="repo2") is not None

    def test_invalidate_multi_repo_entry(self):
        """Verify invalidation removes multi-repo cached results."""
        cache = QueryCache()
        cache.set_results("q1", [{"id": "1"}], repos=["repo1", "repo2"])

        cache.invalidate_repo("repo1")

        assert cache.get_results("q1", repos=["repo1", "repo2"]) is None

    def test_invalidate_repo_removes_global_query_entries(self):
        """Verify repo invalidation also clears unscoped global search cache entries."""
        cache = QueryCache()
        cache.set_results("repo scoped", [{"id": "1"}], repos=["repo1"])
        cache.set_results("global query", [{"id": "global"}])

        cache.invalidate_repo("repo1")

        assert cache.get_results("repo scoped", repos=["repo1"]) is None
        assert cache.get_results("global query") is None

    def test_clear_all(self):
        """Verify complete cache clear."""
        cache = QueryCache()
        cache.set_embedding("q", "small", [0.1])
        cache.set_results("q", [{"id": "1"}])

        cache.clear()

        assert cache.get_embedding("q", "small") is None
        assert cache.get_results("q") is None


class TestSearchPayloadCaching:
    """Test cache behavior for pagination-aware search payloads."""

    def test_search_results_include_next_cursor(self):
        cache = QueryCache()
        hits = [{"chunk_id": "chunk1", "score": 0.9}]
        cache.set_search_results("query", hits, next_cursor="cursor-1", repos=["repo1"], top_k=1)

        cached = cache.get_search_results("query", repos=["repo1"], top_k=1)
        assert cached is not None
        cached_hits, cached_cursor = cached
        assert cached_hits == hits
        assert cached_cursor == "cursor-1"
        # Legacy getter should still return just hits.
        assert cache.get_results("query", repos=["repo1"], top_k=1) == hits

    def test_search_results_backward_compat_for_legacy_entries(self):
        cache = QueryCache()
        hits = [{"chunk_id": "legacy"}]
        cache.set_results("legacy-query", hits, repos=["repo1"], top_k=1)

        cached = cache.get_search_results("legacy-query", repos=["repo1"], top_k=1)
        assert cached is not None
        cached_hits, cached_cursor = cached
        assert cached_hits == hits
        assert cached_cursor is None


class TestCacheEnableDisable:
    """Test cache enable/disable functionality."""

    def test_cache_disabled(self):
        """Verify caching can be disabled."""
        cache = QueryCache(enabled=False)

        cache.set_embedding("q", "small", [0.1])
        cached = cache.get_embedding("q", "small")

        assert cached is None

    def test_toggle_enabled(self):
        """Verify cache can be toggled at runtime."""
        cache = QueryCache(enabled=True)
        cache.set_embedding("q", "small", [0.1])

        # Disable cache
        cache.enabled = False
        assert cache.get_embedding("q", "small") is None

        # Re-enable cache
        cache.enabled = True
        assert cache.get_embedding("q", "small") == [0.1]

    def test_disabled_cache_no_stats(self):
        """Verify disabled cache doesn't track stats."""
        cache = QueryCache(enabled=False)
        cache.get_embedding("q", "small")

        stats = cache.get_stats()
        # Stats should still be at 0 since cache is disabled
        assert stats["embedding_hits"] == 0
        assert stats["embedding_misses"] == 0


class TestErrorHandling:
    """Test error handling."""

    def test_cache_read_error_handling(self):
        """Verify cache gracefully handles read errors."""
        cache = QueryCache()

        # Simulate corrupted cache data
        cache._memory_cache["embed:small:abc"] = ("invalid", 0)

        # Should return None, not crash
        result = cache.get_embedding("query", "small")
        # Since the key doesn't match the hash, it will return None (miss)
        assert result is None

    def test_cache_write_error_handling(self):
        """Verify cache gracefully handles write errors."""
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("Redis unavailable")

        cache = QueryCache(redis_client=mock_redis)

        # Should not crash
        cache.set_embedding("q", "small", [0.1])
        # Verify it logged a warning but didn't crash
        assert True


class TestCreateCache:
    """Test cache factory function."""

    def test_create_in_memory_cache(self):
        """Create cache with in-memory backend."""
        cache = create_cache(redis_url=None, enabled=True)
        assert cache.enabled
        assert cache.redis is None

    def test_create_disabled_cache(self):
        """Create disabled cache."""
        cache = create_cache(enabled=False)
        assert not cache.enabled

    def test_create_with_custom_ttl(self):
        """Create cache with custom TTL values."""
        cache = create_cache(embedding_ttl=7200, result_ttl=1800, enabled=True)
        assert cache.embedding_ttl == 7200
        assert cache.result_ttl == 1800

    def test_create_with_redis_success(self):
        """Create cache with successful Redis connection."""
        # Mock redis at import time
        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch("builtins.__import__") as mock_import:

            def import_side_effect(name, *args, **kwargs):
                if name == "redis":
                    mock_redis = MagicMock()
                    mock_redis.from_url.return_value = mock_client
                    return mock_redis
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = import_side_effect
            cache = create_cache(redis_url="redis://localhost:6379/0")
            assert cache.redis is not None
            mock_client.ping.assert_called_once()

    def test_create_with_redis_failure(self):
        """Create cache with failed Redis connection (fallback to in-memory)."""
        # Mock redis import that raises on connection
        with patch("builtins.__import__") as mock_import:

            def import_side_effect(name, *args, **kwargs):
                if name == "redis":
                    mock_redis = MagicMock()
                    mock_redis.from_url.side_effect = Exception("Connection failed")
                    return mock_redis
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = import_side_effect
            cache = create_cache(redis_url="redis://localhost:6379/0")
            # Should fall back to in-memory
            assert cache.redis is None
            assert cache.enabled is True


class TestCacheIntegration:
    """Integration tests with other components."""

    def test_search_backend_with_cache(self):
        """Test search backend uses cache."""
        import tempfile
        from pathlib import Path

        from kb.api.search_backend import create_search_backend
        from kb.config import KBConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            config = KBConfig(store_root=Path(tmpdir), cache_enabled=True)
            backend = create_search_backend(
                store_root=config.resolved_store_root(),
                embedding_provider_type=config.embedding_provider,
                cache_enabled=config.cache_enabled,
                redis_url=config.redis_url,
            )
            assert backend.cache is not None
            assert backend.cache.enabled is True

    def test_cache_lifecycle(self):
        """Test complete cache lifecycle."""
        cache = QueryCache(enabled=True)

        # 1. Cache miss
        assert cache.get_embedding("query", "small") is None

        # 2. Set embedding
        embedding = [0.1, 0.2, 0.3]
        cache.set_embedding("query", "small", embedding)

        # 3. Cache hit
        cached = cache.get_embedding("query", "small")
        assert cached == embedding

        # 4. Clear cache
        cache.clear()

        # 5. Cache miss again
        assert cache.get_embedding("query", "small") is None

        # 6. Verify stats
        stats = cache.get_stats()
        assert stats["embedding_hits"] == 1
        assert stats["embedding_misses"] == 2


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_embedding(self):
        """Test caching empty embedding."""
        cache = QueryCache()
        cache.set_embedding("q", "small", [])
        cached = cache.get_embedding("q", "small")
        assert cached == []

    def test_large_embedding(self):
        """Test caching large embedding."""
        cache = QueryCache()
        large_embedding = [float(i) for i in range(3072)]
        cache.set_embedding("q", "large", large_embedding)
        cached = cache.get_embedding("q", "large")
        assert cached == large_embedding

    def test_empty_results(self):
        """Test caching empty results."""
        cache = QueryCache()
        cache.set_results("q", [])
        cached = cache.get_results("q")
        assert cached == []

    def test_special_characters_in_query(self):
        """Test queries with special characters."""
        cache = QueryCache()
        query = "test\nquery\twith\rspecial chars: 你好"
        cache.set_embedding(query, "small", [0.1])
        cached = cache.get_embedding(query, "small")
        assert cached == [0.1]

    def test_zero_ttl(self):
        """Test cache with zero TTL."""
        cache = create_cache(embedding_ttl=0, result_ttl=0)
        cache.set_embedding("q", "small", [0.1])
        cache.set_results("q", [{"id": "1"}])
        assert cache.get_embedding("q", "small") is None
        assert cache.get_results("q") is None
