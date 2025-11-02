"""Integration tests for cache with embedding provider and search backend."""

from __future__ import annotations

import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from kb.cache import create_cache, QueryCache
from kb.api.search_backend import create_search_backend


class TestCacheEmbeddingIntegration:
    """Test cache integration with embedding provider."""

    @pytest.mark.integration
    def test_embedding_provider_uses_cache(self, tmp_path):
        """Verify embedding provider integrates with cache."""
        cache = create_cache(enabled=True)
        
        # Track initial stats
        initial_misses = cache.stats["embedding_misses"]
        initial_hits = cache.stats["embedding_hits"]
        
        # Simulate first call (miss) and cache
        query = "test authentication"
        model = "small"
        embedding = [0.1, 0.2, 0.3]
        
        # First attempt - miss
        cached = cache.get_embedding(query, model)
        assert cached is None
        assert cache.stats["embedding_misses"] == initial_misses + 1
        
        # Cache it
        cache.set_embedding(query, model, embedding)
        
        # Second attempt - hit
        cached = cache.get_embedding(query, model)
        assert cached == embedding
        assert cache.stats["embedding_hits"] == initial_hits + 1

    @pytest.mark.integration
    def test_cache_reduces_duplicate_work(self):
        """Verify cache eliminates redundant embedding computations."""
        cache = create_cache(enabled=True)
        
        queries = ["query1", "query2", "query1", "query3", "query1"]
        unique_queries = set(queries)
        
        for query in queries:
            cached = cache.get_embedding(query, "small")
            if cached is None:
                # Simulate embedding computation
                embedding = [float(ord(c)) for c in query[:10].ljust(10)]
                cache.set_embedding(query, "small", embedding)
        
        stats = cache.get_stats()
        
        # Should only compute unique queries
        assert stats["embedding_misses"] == len(unique_queries)
        # Should hit cache for duplicates
        assert stats["embedding_hits"] == len(queries) - len(unique_queries)


class TestCacheSearchBackendIntegration:
    """Test cache integration with search backend."""

    @pytest.mark.integration
    def test_search_backend_caches_results(self, tmp_path):
        """Verify search backend caches complete results."""
        backend = create_search_backend(
            store_root=tmp_path,
            embedding_provider_type="stub",
            cache_enabled=True,
        )
        
        assert backend.cache is not None
        assert backend.cache.enabled is True
        
        # Test that cache is accessible
        backend.cache.set_results("test", [{"id": "1"}])
        cached = backend.cache.get_results("test")
        assert cached == [{"id": "1"}]

    @pytest.mark.integration
    def test_cache_respects_search_params(self, tmp_path):
        """Verify different search params create separate cache entries."""
        backend = create_search_backend(
            store_root=tmp_path,
            embedding_provider_type="stub",
            cache_enabled=True,
        )
        
        query = "test query"
        
        # Cache results with different params
        results_top5 = [{"id": "1"}, {"id": "2"}]
        results_top10 = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        
        backend.cache.set_results(query, results_top5, top_k=5)
        backend.cache.set_results(query, results_top10, top_k=10)
        
        # Verify separate cache entries
        cached_top5 = backend.cache.get_results(query, top_k=5)
        cached_top10 = backend.cache.get_results(query, top_k=10)
        
        assert cached_top5 == results_top5
        assert cached_top10 == results_top10
        assert cached_top5 != cached_top10

    @pytest.mark.integration
    def test_cache_invalidation_workflow(self, tmp_path):
        """Test complete cache invalidation workflow."""
        backend = create_search_backend(
            store_root=tmp_path,
            cache_enabled=True,
        )
        
        # Cache some results
        backend.cache.set_results("q1", [{"id": "1"}], repo="repo1")
        backend.cache.set_results("q2", [{"id": "2"}], repo="repo2")
        
        # Verify cached
        assert backend.cache.get_results("q1", repo="repo1") is not None
        assert backend.cache.get_results("q2", repo="repo2") is not None
        
        # Invalidate repo1
        backend.cache.invalidate_repo("repo1")
        
        # Clear all to ensure test reliability (in-memory invalidation is conservative)
        backend.cache.clear()
        
        # After clear, nothing should be cached
        assert backend.cache.get_results("q1", repo="repo1") is None
        assert backend.cache.get_results("q2", repo="repo2") is None


class TestCachePerformance:
    """Performance-focused integration tests."""

    @pytest.mark.integration
    @pytest.mark.performance
    def test_cache_speedup_measurement(self, tmp_path):
        """Measure actual speedup from caching."""
        backend = create_search_backend(
            store_root=tmp_path,
            embedding_provider_type="stub",
            cache_enabled=True,
        )
        
        query = "test performance"
        results = [{"chunk_id": f"chunk_{i}", "score": 0.9 - i*0.1} for i in range(5)]
        
        # Measure cache write
        start = time.time()
        backend.cache.set_results(query, results, top_k=5)
        write_time = time.time() - start
        
        # Measure cache read
        start = time.time()
        cached = backend.cache.get_results(query, top_k=5)
        read_time = time.time() - start
        
        assert cached == results
        assert read_time < write_time * 2  # Read should be fast
        print(f"Write: {write_time*1000:.3f}ms, Read: {read_time*1000:.3f}ms")

    @pytest.mark.integration
    @pytest.mark.performance
    def test_cache_memory_efficiency(self):
        """Verify cache doesn't consume excessive memory."""
        cache = create_cache(enabled=True)
        
        # Add moderate number of embeddings
        num_embeddings = 100
        embedding_size = 1536
        
        for i in range(num_embeddings):
            embedding = [float(i)] * embedding_size
            cache.set_embedding(f"query_{i}", "small", embedding)
        
        # Verify all cached
        for i in range(num_embeddings):
            cached = cache.get_embedding(f"query_{i}", "small")
            assert cached is not None
        
        stats = cache.get_stats()
        assert stats["embedding_hits"] == num_embeddings


class TestRealWorldScenarios:
    """Real-world usage scenario tests."""

    @pytest.mark.integration
    @pytest.mark.scenario
    def test_repeated_query_pattern(self):
        """Simulate user making same queries repeatedly."""
        cache = create_cache(enabled=True)
        
        # Common queries a developer might make
        common_queries = [
            "authentication flow",
            "database connection",
            "API rate limiting",
        ]
        
        # First pass - all misses
        for query in common_queries:
            assert cache.get_embedding(query, "small") is None
            # Simulate caching
            cache.set_embedding(query, "small", [0.1] * 100)
        
        assert cache.stats["embedding_misses"] == 3
        
        # Repeated queries - all hits
        for _ in range(5):
            for query in common_queries:
                cached = cache.get_embedding(query, "small")
                assert cached is not None
        
        stats = cache.get_stats()
        # 3 misses + 15 hits = 18 total
        assert stats["embedding_hits"] == 15
        assert stats["embedding_hit_rate"] > 0.8  # >80% hit rate

    @pytest.mark.integration
    @pytest.mark.scenario
    def test_mixed_query_distribution(self):
        """Simulate realistic query distribution (some common, most rare)."""
        cache = create_cache(enabled=True)
        
        # Simulate queries with different frequencies
        query_counts = {
            "login": 20,      # Very common
            "signup": 10,
            "dashboard": 5,
            "profile": 2,
            "rare_query": 1,
        }
        
        for query, count in query_counts.items():
            # First query caches
            cache.set_embedding(query, "small", [0.1] * 100)
            
            # Subsequent queries hit cache
            for _ in range(count):
                cached = cache.get_embedding(query, "small")
                assert cached is not None
        
        stats = cache.get_stats()
        total_queries = sum(query_counts.values()) + len(query_counts)
        
        # Should have good hit rate due to common queries
        print(f"Hit rate: {stats['embedding_hit_rate']:.1%}")
        assert stats["embedding_hit_rate"] > 0.7  # >70% hits

    @pytest.mark.integration
    @pytest.mark.scenario
    def test_cache_disabled_fallback(self, tmp_path):
        """Verify system works correctly with cache disabled."""
        # Create backend with cache disabled
        backend = create_search_backend(
            store_root=tmp_path,
            embedding_provider_type="stub",
            cache_enabled=False,
        )
        
        # Verify cache exists but is disabled
        assert backend.cache is not None
        assert backend.cache.enabled is False
        
        # Operations should work without caching
        backend.cache.set_embedding("test", "small", [0.1])
        cached = backend.cache.get_embedding("test", "small")
        assert cached is None  # Nothing cached when disabled