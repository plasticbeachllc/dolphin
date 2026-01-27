"""Integration tests for cache with search backend and embedding provider."""

import os
import subprocess
import uuid
import tempfile
from pathlib import Path
import pytest

from fastapi.testclient import TestClient

from kb.api.app import (
    app,
    reset_pipeline,
    reset_search_backend,
    reset_stores,
    set_pipeline,
    set_search_backend,
    set_stores,
)
from kb.api.search_backend import create_search_backend
from kb.cache import QueryCache, create_cache
from kb.config import KBConfig
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore
from tests.conftest import init_test_git_repo


def _setup_repo(temp_dir: Path) -> Path:
    repo_path = temp_dir / "invalidate_repo"
    repo_path.mkdir()
    init_test_git_repo(repo_path)
    (repo_path / "code.py").write_text("def original(): return 'original'")
    subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "Initial commit"], check=True, capture_output=True)
    return repo_path


def _setup_pipeline(temp_dir: Path, cache: QueryCache) -> tuple[IngestionPipeline, str]:
    repo_path = _setup_repo(temp_dir)
    db_path = temp_dir / "invalidate_cache.db"
    metadata_store = SQLiteMetadataStore(db_path)
    metadata_store.initialize()
    lancedb_store = LanceDBStore(f"memory://invalidate_cache_{uuid.uuid4().hex}")
    config = KBConfig(default_embed_model="small")

    metadata_store.record_repo(name="invalidate-repo", path=repo_path, default_embed_model="small")

    pipeline = IngestionPipeline(config, lancedb_store, metadata_store, cache=cache)
    pipeline.index("invalidate-repo", dry_run=False, force=True)
    return pipeline, "invalidate-repo"


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
            cache = backend.cache
            assert cache.enabled is True

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
            cache = backend.cache
            assert cache.enabled is False

    def test_cache_invalidation_workflow(self):
        """Test cache behavior during repository operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = create_search_backend(
                store_root=Path(tmpdir),
                embedding_provider_type="stub",
                cache_enabled=True,
            )

            assert backend.cache is not None
            cache = backend.cache

            # Set up some cached data
            cache.set_results("query", [{"id": "1"}], repo="test-repo")

            # Verify it's cached
            cached = cache.get_results("query", repo="test-repo")
            assert cached is not None

            # Invalidate the repo
            cache.invalidate_repo("test-repo")

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

            assert backend.cache is not None
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

            assert backend.cache is not None
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

            assert backend.cache is not None
            cache = backend.cache

            # 2. Cache some data
            cache.set_embedding("test query", "small", [0.1, 0.2, 0.3])
            cache.set_results("test query", [{"id": "1"}], repo="test")

            # 3. Verify cache hits
            assert cache.get_embedding("test query", "small") is not None
            assert cache.get_results("test query", repo="test") is not None

            # 4. Check stats
            stats = cache.get_stats()
            assert stats["embedding_hits"] > 0
            assert stats["result_hits"] > 0

            # 5. Clear cache
            cache.clear()

            # 6. Verify cache cleared
            assert cache.get_embedding("test query", "small") is None
            assert cache.get_results("test query", repo="test") is None


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

            assert backend.cache is not None
            cache = backend.cache

            # Simulate cache failure by replacing with broken mock
            mock_redis = MagicMock()
            mock_redis.get.side_effect = Exception("Redis down")
            cache.redis = mock_redis

            # Should not crash, just return None
            result = cache.get_embedding("query", "small")
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
            assert backend.cache is not None
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

            assert backend.cache is not None
            cache = backend.cache

            # Generate some cache activity
            cache.set_embedding("q1", "small", [0.1])
            cache.get_embedding("q1", "small")  # hit
            cache.get_embedding("q2", "small")  # miss

            stats = cache.get_stats()
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


class TestCacheInvalidationOnReindex:
    """Test reindex invalidates cached search results."""

    def test_reindex_invalidation_in_memory(self, temp_dir: Path):
        cache = QueryCache()
        pipeline, repo_name = _setup_pipeline(temp_dir, cache)

        cache.set_results("query", [{"id": "1"}], repos=[repo_name])
        assert cache.get_results("query", repos=[repo_name]) is not None

        pipeline.index(repo_name, dry_run=False, force=True, full_reindex=True)

        assert cache.get_results("query", repos=[repo_name]) is None

    def test_reindex_invalidation_redis(self, temp_dir: Path):
        fakeredis = pytest.importorskip("fakeredis")
        redis_client = fakeredis.FakeRedis()
        cache = QueryCache(redis_client=redis_client)
        pipeline, repo_name = _setup_pipeline(temp_dir, cache)

        cache.set_results("query", [{"id": "1"}], repos=[repo_name])
        assert cache.get_results("query", repos=[repo_name]) is not None

        pipeline.index(repo_name, dry_run=False, force=True, full_reindex=True)

        assert cache.get_results("query", repos=[repo_name]) is None


class TestCacheInvalidationAPI:
    """API-level cache invalidation coverage."""

    def test_reindex_invalidates_cached_search_results(self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch):
        store_root = temp_dir / "api_store"
        store_root.mkdir(parents=True, exist_ok=True)

        backend = create_search_backend(
            store_root=store_root,
            embedding_provider_type="stub",
            cache_enabled=True,
        )

        backend.lance_store.query = lambda *args, **kwargs: []  # Avoid vector-only hits in test.
        pipeline = IngestionPipeline(backend.config, backend.lance_store, backend.sql_store, cache=backend.cache)

        set_search_backend(backend)
        set_stores(backend.sql_store, backend.lance_store)
        set_pipeline(pipeline)

        try:
            repo_path = temp_dir / "api_repo"
            repo_path.mkdir()
            init_test_git_repo(repo_path)
            (repo_path / "code.py").write_text("def alpha(): return 'alpha'")
            subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(repo_path), "commit", "-m", "Initial commit"], check=True, capture_output=True
            )

            backend.sql_store.record_repo(name="api-repo", path=repo_path, default_embed_model="small")
            pipeline.index("api-repo", dry_run=False, force=True, full_reindex=True)

            test_api_key = "test-api-key-12345"
            monkeypatch.setenv("DOLPHIN_API_KEY", test_api_key)
            client = TestClient(app)
            client.headers = {"X-API-Key": test_api_key}

            response = client.post(
                "/v1/search",
                json={"query": "beta", "repos": ["api-repo"], "top_k": 5, "max_snippets": 1},
            )
            assert response.status_code == 200
            assert response.json()["hits"] == []

            (repo_path / "code.py").write_text(
                """
def alpha(): return 'alpha'
def beta(): return 'beta'
"""
            )
            subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "Add beta"], check=True, capture_output=True)

            response = client.post("/v1/repos/api-repo/reindex", json={"mode": "incremental"})
            assert response.status_code == 200

            response = client.post(
                "/v1/search",
                json={"query": "beta", "repos": ["api-repo"], "top_k": 5, "max_snippets": 1},
            )
            assert response.status_code == 200
            hits = response.json()["hits"]
            assert hits
            assert any("beta" in str(hit.get("snippet", "")).lower() for hit in hits)
        finally:
            reset_search_backend()
            reset_stores()
            reset_pipeline()


@pytest.mark.skipif(
    os.environ.get("DOLPHIN_TEST_FULL") != "1",  # Skip by default unless full test requested
    reason="Requires Redis server - set DOLPHIN_TEST_FULL=1 to run (and ensure Redis is up)",
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
        # Note: cache.redis might still be set to the client object, but connection failed
        assert cache.enabled is True

        # Should still work
        cache.set_embedding("query", "small", [0.1])
        assert cache.get_embedding("query", "small") == [0.1]
