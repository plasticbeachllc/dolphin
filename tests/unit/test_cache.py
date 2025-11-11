"""Unit tests for query caching functionality."""
import pytest
from kb.cache import QueryCache, create_cache


class TestQueryCache:
    """Test query cache functionality."""

    def test_embedding_cache_hit(self):
        cache = QueryCache(enabled=True)
        cache.set_embedding("test query", "small", [0.1, 0.2, 0.3])
        cached = cache.get_embedding("test query", "small")
        assert cached == [0.1, 0.2, 0.3]
        stats = cache.get_stats()
        assert stats["embedding_hits"] == 1

    def test_result_cache_hit(self):
        cache = QueryCache(enabled=True)
        results = [{"chunk_id": "1", "score": 0.9}]
        params = {"repo": "test-repo", "top_k": 5}
        cache.set_results("test query", results, **params)
        cached = cache.get_results("test query", **params)
        assert cached == results
        stats = cache.get_stats()
        assert stats["result_hits"] == 1


class TestCreateCache:
    """Test cache factory function."""

    def test_create_in_memory_cache(self):
        cache = create_cache(redis_url=None, enabled=True)
        assert cache.enabled
        assert cache.redis is None

    def test_create_disabled_cache(self):
        cache = create_cache(enabled=False)
        assert not cache.enabled


class TestCacheIntegration:
    """Integration tests with other components."""

    def test_search_backend_with_cache(self):
        from kb.api.search_backend import create_search_backend
        from kb.config import KBConfig
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config = KBConfig(store_root=Path(tmpdir), cache_enabled=True)
            # The factory now takes a config object.
            # We need to ensure the test passes the config correctly.
            # Let's adjust the call if necessary, based on the stable signature.
            # The stable signature is create_search_backend(store_root, ...kwargs)
            # So the call in the test should be:
            backend = create_search_backend(
                store_root=config.resolved_store_root(),
                embedding_provider_type=config.embedding_provider,
                cache_enabled=config.cache_enabled,
                redis_url=config.redis_url
            )
            assert backend.cache is not None
            assert backend.cache.enabled is True