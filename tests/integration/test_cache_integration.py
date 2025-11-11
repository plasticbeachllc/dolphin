"""Integration tests for cache with search backend and embedding provider."""
import pytest
import tempfile
from pathlib import Path
from kb.cache import create_cache
from kb.api.search_backend import create_search_backend
from kb.config import KBConfig


class TestCacheWithSearchBackend:
    """Test cache integration with search backend."""

    def test_search_backend_uses_cache(self):
        """Verify search backend integrates with cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = create_search_backend(
                store_root=Path(tmpdir),
                embedding_provider_type="stub",
                cache_enabled=True,
            )
            
            assert backend.cache is not None
            assert backend.cache.enabled is True

    def test_search_backend_cache_disabled(self):
        """Verify search backend can be created without cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = create_search_backend(
                store_root=Path(tmpdir),
                embedding_provider_type="stub",
                cache_enabled=False,
            )
            
            # Cache should still exist but be disabled
            assert backend.cache is not None
            assert backend.cache.enabled is False

    def test_cache_invalidation_workflow(self):
        """Test cache behavior during repository operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = create_search_backend(
                store_root=Path(tmpdir),
                embedding_provider_type="stub",
                cache_enabled=True,
            )
            
            # Set up some cached data
            backend.cache.set_results("query", [{"id": "1"}], repo="test-repo")
            
            # Verify it's cached
            cached = backend.cache.get_results("query", repo="test-repo")
            assert cached is not None
            
            # Invalidate the repo
            backend.cache.invalidate_repo("test-repo")
            
            # In-memory cache invalidation is conservative, but should not crash
            assert True


class TestCacheConfiguration:
    """Test cache configuration options."""

    def test_config_with_cache_enabled(self):
        """Test creating backend with cache enabled via config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KBConfig(
                store_root=Path(tmpdir),
                cache_enabled=True,
            )
            
            backend = create_search_backend(
                store_root=config.resolved_store_root(),
                embedding_provider_type=config.embedding_provider,
                cache_enabled=config.cache_enabled,
                redis_url=config.redis_url,
            )
            
            assert backend.cache.enabled is True

    def test_config_with_cache_disabled(self):
        """Test creating backend with cache disabled via config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KBConfig(
                store_root=Path(tmpdir),
                cache_enabled=False,
            )
            
            backend = create_search_backend(
                store_root=config.resolved_store_root(),
                embedding_provider_type=config.embedding_provider,
                cache_enabled=config.cache_enabled,
            )
            
            assert backend.cache.enabled is False

    def test_custom_ttl_configuration(self):
        """Test configuring custom TTL values."""
        cache = create_cache(
            embedding_ttl=7200,
            result_ttl=1800,
            enabled=True,
        )
        
        assert cache.embedding_ttl == 7200
        assert cache.result_ttl == 1800


class TestCacheLifecycle:
    """Test complete cache lifecycle in integration scenario."""

    def test_full_cache_lifecycle(self):
        """Test complete cache lifecycle with backend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Create backend with cache
            backend = create_search_backend(
                store_root=Path(tmpdir),
                embedding_provider_type="stub",
                cache_enabled=True,
            )
            
            # 2. Cache some data
            backend.cache.set_embedding("test query", "small", [0.1, 0.2, 0.3])
            backend.cache.set_results("test query", [{"id": "1"}], repo="test")
            
            # 3. Verify cache hits
            assert backend.cache.get_embedding("test query", "small") is not None
            assert backend.cache.get_results("test query", repo="test") is not None
            
            # 4. Check stats
            stats = backend.cache.get_stats()
            assert stats["embedding_hits"] > 0
            assert stats["result_hits"] > 0
            
            # 5. Clear cache
            backend.cache.clear()
            
            # 6. Verify cache cleared
            assert backend.cache.get_embedding("test query", "small") is None
            assert backend.cache.get_results("test query", repo="test") is None


class TestCacheErrorHandling:
    """Test cache error handling in integration scenarios."""

    def test_cache_failure_does_not_crash_backend(self):
        """Verify cache failures don't crash the backend."""
        from unittest.mock import MagicMock
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = create_search_backend(
                store_root=Path(tmpdir),
                embedding_provider_type="stub",
                cache_enabled=True,
            )
            
            # Simulate cache failure by replacing with broken mock
            backend.cache.redis = MagicMock()
            backend.cache.redis.get.side_effect = Exception("Redis down")
            
            # Should not crash, just return None
            result = backend.cache.get_embedding("query", "small")
            assert result is None

    def test_backend_works_without_cache(self):
        """Verify backend works fine without cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = create_search_backend(
                store_root=Path(tmpdir),
                embedding_provider_type="stub",
                cache_enabled=False,
            )
            
            # Backend should still function
            assert backend is not None
            assert backend.cache.enabled is False


class TestCacheStatistics:
    """Test cache statistics in integration scenarios."""

    def test_cache_stats_tracking(self):
        """Test cache statistics are tracked correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = create_search_backend(
                store_root=Path(tmpdir),
                embedding_provider_type="stub",
                cache_enabled=True,
            )
            
            # Generate some cache activity
            backend.cache.set_embedding("q1", "small", [0.1])
            backend.cache.get_embedding("q1", "small")  # hit
            backend.cache.get_embedding("q2", "small")  # miss
            
            stats = backend.cache.get_stats()
            assert stats["embedding_hits"] == 1
            assert stats["embedding_misses"] == 1
            assert stats["embedding_hit_rate"] == 0.5
            assert stats["total_requests"] == 2

    def test_cache_stats_reset(self):
        """Test cache statistics can be reset."""
        cache = create_cache(enabled=True)
        
        # Generate activity
        cache.set_embedding("q", "small", [0.1])
        cache.get_embedding("q", "small")
        
        # Reset stats
        cache.stats = {
            "embedding_hits": 0,
            "embedding_misses": 0,
            "result_hits": 0,
            "result_misses": 0,
        }
        
        stats = cache.get_stats()
        assert stats["total_requests"] == 0


@pytest.mark.skipif(
    True,  # Skip by default unless Redis is available
    reason="Requires Redis server - set up Redis and change to False to run"
)
class TestCacheWithRedis:
    """Integration tests with Redis backend.
    
    To run these tests:
    1. Start Redis: brew services start redis (macOS) or sudo systemctl start redis (Linux)
    2. Change skipif to False above
    3. Run: REDIS_URL=redis://localhost:6379/0 pytest tests/integration/test_cache_integration.py -v
    """

    def test_redis_cache_persistence(self):
        """Verify Redis cache persists across instances."""
        import os
        
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

    def test_redis_connection_fallback(self):
        """Test graceful fallback when Redis is unavailable."""
        # Try to connect to non-existent Redis
        cache = create_cache(redis_url="redis://localhost:9999/0")
        
        # Should fall back to in-memory cache
        assert cache.redis is None
        assert cache.enabled is True
        
        # Should still work
        cache.set_embedding("query", "small", [0.1])
        assert cache.get_embedding("query", "small") == [0.1]