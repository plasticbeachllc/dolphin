"""Query caching implementation with Redis backend.

This module provides multi-level caching for embeddings and search results
to improve performance and reduce API costs.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
from typing import Any

_log = logging.getLogger(__name__)

_REPO_INDEX_PREFIX = "repo_index"
_GLOBAL_RESULTS_SCOPE = "__global__"
_RESULTS_CACHE_VERSION = "v2"


class QueryCache:
    """Multi-level cache for query embeddings and search results.

    Cache Levels:
    - L1: Embedding cache (query text -> embedding vector)
    - L2: Result cache (query + params -> search results)

    TTL Settings:
    - Embeddings: 1 hour (3600s) - embeddings are stable
    - Results: 15 minutes (900s) - results may change as index updates
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        embedding_ttl: int = 3600,
        result_ttl: int = 900,
        enabled: bool = True,
    ):
        """Initialize query cache.

        Args:
            redis_client: Redis client instance. If None, uses in-memory dict (for testing)
            embedding_ttl: Time-to-live for embeddings in seconds (default: 1 hour)
            result_ttl: Time-to-live for results in seconds (default: 15 minutes)
            enabled: Whether caching is enabled (default: True)
        """
        self.redis = redis_client
        self.embedding_ttl = embedding_ttl
        self.result_ttl = result_ttl
        self.enabled = enabled

        # Fallback in-memory cache if Redis not available
        self._memory_cache: dict[str, tuple[Any, float]] = {}
        self._repo_index: dict[str, set[str]] = {}
        self._key_repos: dict[str, set[str]] = {}

        # Cache statistics
        self.stats = {
            "embedding_hits": 0,
            "embedding_misses": 0,
            "result_hits": 0,
            "result_misses": 0,
        }

    def _hash_key(self, *parts: str) -> str:
        """Create a stable hash key from multiple parts.

        Args:
            *parts: String parts to hash together

        Returns:
            SHA256 hex digest of the concatenated parts
        """
        combined = "|".join(parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _repo_index_key(self, repo: str) -> str:
        return f"{_REPO_INDEX_PREFIX}:{repo}"

    def _global_index_key(self) -> str:
        return self._repo_index_key(_GLOBAL_RESULTS_SCOPE)

    def _result_cache_key(self, query: str, params: dict[str, Any]) -> str:
        # Include a cache version marker so key-shape upgrades do not risk stale collisions.
        param_str = json.dumps(params, sort_keys=True, separators=(",", ":"))
        return f"results:{_RESULTS_CACHE_VERSION}:{self._hash_key(query, param_str)}"

    def _extract_repos(self, params: dict[str, Any]) -> list[str]:
        repos: list[str] = []
        raw_repos = params.get("repos")
        if isinstance(raw_repos, str):
            repos.append(raw_repos)
        elif isinstance(raw_repos, list):
            repos.extend([repo for repo in raw_repos if isinstance(repo, str)])
        repo = params.get("repo")
        if isinstance(repo, str):
            repos.append(repo)
        # Remove duplicates while preserving order
        seen: set[str] = set()
        ordered = []
        for repo_name in repos:
            if repo_name not in seen:
                seen.add(repo_name)
                ordered.append(repo_name)
        return ordered

    def _get_memory_value(self, cache_key: str) -> Any | None:
        cached = self._memory_cache.get(cache_key)
        if not cached:
            return None
        value, expires_at = cached
        if expires_at <= time.time():
            self._memory_cache.pop(cache_key, None)
            self._remove_key_from_repo_index(cache_key)
            return None
        return copy.deepcopy(value)

    def _remove_key_from_repo_index(self, cache_key: str) -> None:
        repos = self._key_repos.pop(cache_key, set())
        for repo in repos:
            repo_keys = self._repo_index.get(repo)
            if repo_keys:
                repo_keys.discard(cache_key)
                if not repo_keys:
                    self._repo_index.pop(repo, None)

    def _index_result_key(self, cache_key: str, params: dict[str, Any]) -> None:
        scopes = self._extract_repos(params)
        if not scopes:
            scopes = [_GLOBAL_RESULTS_SCOPE]
        if self.redis:
            for scope in scopes:
                index_key = self._repo_index_key(scope)
                self.redis.sadd(index_key, cache_key)
                self.redis.expire(index_key, self.result_ttl)
        else:
            for scope in scopes:
                self._repo_index.setdefault(scope, set()).add(cache_key)
            self._key_repos.setdefault(cache_key, set()).update(scopes)

    @staticmethod
    def _decode_redis_key(key: Any) -> str:
        if isinstance(key, (bytes, bytearray)):
            return key.decode()
        return str(key)

    def _get_cached_results_payload(self, query: str, params: dict[str, Any]) -> Any | None:
        if not self.enabled:
            return None

        cache_key = self._result_cache_key(query, params)

        try:
            if self.redis:
                cached = self.redis.get(cache_key)
                if cached:
                    self.stats["result_hits"] += 1
                    return json.loads(cached)
            else:
                value = self._get_memory_value(cache_key)
                if value is not None:
                    self.stats["result_hits"] += 1
                    return value

            self.stats["result_misses"] += 1
            return None

        except Exception as e:
            _log.warning("Cache read error for results: %s", e)
            return None

    def _set_cached_results_payload(self, query: str, payload: Any, params: dict[str, Any]) -> None:
        if not self.enabled:
            return

        cache_key = self._result_cache_key(query, params)

        try:
            if self.redis:
                self.redis.setex(cache_key, self.result_ttl, json.dumps(payload))
                self._index_result_key(cache_key, params)
            else:
                self._memory_cache[cache_key] = (copy.deepcopy(payload), time.time() + self.result_ttl)
                self._index_result_key(cache_key, params)

        except Exception as e:
            _log.warning("Cache write error for results: %s", e)

    def get_embedding(self, query: str, model: str) -> list[float] | None:
        """Get cached embedding for a query.

        Args:
            query: Query text
            model: Embedding model name ('small' or 'large')

        Returns:
            Cached embedding vector or None if not cached
        """
        if not self.enabled:
            return None

        cache_key = f"embed:{model}:{self._hash_key(query)}"

        try:
            if self.redis:
                cached = self.redis.get(cache_key)
                if cached:
                    self.stats["embedding_hits"] += 1
                    return json.loads(cached)
            else:
                # In-memory fallback
                value = self._get_memory_value(cache_key)
                if value is not None:
                    self.stats["embedding_hits"] += 1
                    return value

            self.stats["embedding_misses"] += 1
            return None

        except Exception as e:
            _log.warning("Cache read error for embedding: %s", e)
            return None

    def set_embedding(self, query: str, model: str, embedding: list[float]) -> None:
        """Cache an embedding for a query.

        Args:
            query: Query text
            model: Embedding model name
            embedding: Embedding vector to cache
        """
        if not self.enabled:
            return

        cache_key = f"embed:{model}:{self._hash_key(query)}"

        try:
            if self.redis:
                self.redis.setex(cache_key, self.embedding_ttl, json.dumps(embedding))
            else:
                # In-memory fallback
                self._memory_cache[cache_key] = (
                    copy.deepcopy(embedding),
                    time.time() + self.embedding_ttl,
                )

        except Exception as e:
            _log.warning("Cache write error for embedding: %s", e)

    def get_results(self, query: str, **params: Any) -> list[dict[str, Any]] | None:
        """Get cached search results.

        Args:
            query: Query text
            **params: Search parameters (repo, top_k, etc.)

        Returns:
            Cached search results or None if not cached
        """
        payload = self._get_cached_results_payload(query, params)
        if payload is None:
            return None
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            hits = payload.get("hits")
            if isinstance(hits, list):
                return hits
        return None

    def set_results(self, query: str, results: list[dict[str, Any]], **params: Any) -> None:
        """Cache search results.

        Args:
            query: Query text
            results: Search results to cache
            **params: Search parameters used
        """
        self._set_cached_results_payload(query, results, params)

    def get_search_results(self, query: str, **params: Any) -> tuple[list[dict[str, Any]], str | None] | None:
        """Get cached search response payload including pagination cursor."""
        payload = self._get_cached_results_payload(query, params)
        if payload is None:
            return None
        if isinstance(payload, list):
            # Backward compatibility for pre-v2 payload shape.
            return payload, None
        if isinstance(payload, dict):
            hits = payload.get("hits")
            if isinstance(hits, list):
                raw_cursor = payload.get("next_cursor")
                next_cursor = raw_cursor if isinstance(raw_cursor, str) else None
                return hits, next_cursor
        return None

    def set_search_results(
        self,
        query: str,
        results: list[dict[str, Any]],
        *,
        next_cursor: str | None,
        **params: Any,
    ) -> None:
        """Cache search results plus next-cursor metadata for pagination correctness."""
        payload: dict[str, Any] = {"hits": results, "next_cursor": next_cursor}
        self._set_cached_results_payload(query, payload, params)

    def invalidate_repo(self, repo: str) -> None:
        """Invalidate all cached results for a repository.

        This should be called when a repository is reindexed.

        Args:
            repo: Repository name to invalidate
        """
        if not self.enabled:
            return

        try:
            if self.redis:
                index_key = self._repo_index_key(repo)
                global_key = self._global_index_key()
                repo_keys = {self._decode_redis_key(key) for key in self.redis.smembers(index_key)}
                global_keys = {self._decode_redis_key(key) for key in self.redis.smembers(global_key)}
                cache_keys = sorted(repo_keys.union(global_keys))
                if cache_keys:
                    pipeline = self.redis.pipeline()
                    pipeline.delete(*cache_keys)
                    pipeline.delete(index_key)
                    pipeline.delete(global_key)
                    pipeline.execute()
                else:
                    self.redis.delete(index_key)
                    self.redis.delete(global_key)
                _log.info("Invalidated cache for repo: %s (removed_keys=%d)", repo, len(cache_keys))
            else:
                keys = set(self._repo_index.get(repo, set()))
                keys.update(self._repo_index.get(_GLOBAL_RESULTS_SCOPE, set()))
                for key in keys:
                    self._memory_cache.pop(key, None)
                    self._remove_key_from_repo_index(key)
                self._repo_index.pop(repo, None)
                self._repo_index.pop(_GLOBAL_RESULTS_SCOPE, None)
                _log.info("Invalidated cache for repo: %s (removed_keys=%d)", repo, len(keys))

        except Exception as e:
            _log.warning("Cache invalidation error for repo %s: %s", repo, e)

    def clear(self) -> None:
        """Clear all cached data."""
        if not self.enabled:
            return

        try:
            if self.redis:
                # Clear all dolphin cache keys
                for pattern in ["embed:*", "results:*", f"{_REPO_INDEX_PREFIX}:*"]:
                    for key in self.redis.scan_iter(match=pattern):
                        self.redis.delete(key)
                _log.info("Cache cleared")
            else:
                self._memory_cache.clear()
                self._repo_index.clear()
                self._key_repos.clear()

        except Exception as e:
            _log.warning("Cache clear error: %s", e)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache hit/miss statistics and rates
        """
        total_embedding_requests = self.stats["embedding_hits"] + self.stats["embedding_misses"]
        total_result_requests = self.stats["result_hits"] + self.stats["result_misses"]

        embedding_hit_rate = (
            self.stats["embedding_hits"] / total_embedding_requests if total_embedding_requests > 0 else 0.0
        )

        result_hit_rate = self.stats["result_hits"] / total_result_requests if total_result_requests > 0 else 0.0

        return {
            "embedding_hits": self.stats["embedding_hits"],
            "embedding_misses": self.stats["embedding_misses"],
            "embedding_hit_rate": embedding_hit_rate,
            "result_hits": self.stats["result_hits"],
            "result_misses": self.stats["result_misses"],
            "result_hit_rate": result_hit_rate,
            "total_requests": total_embedding_requests + total_result_requests,
        }


def create_cache(
    redis_url: str | None = None,
    embedding_ttl: int = 3600,
    result_ttl: int = 900,
    enabled: bool = True,
) -> QueryCache:
    """Factory function to create a query cache.

    Args:
        redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
                  If None, uses in-memory cache
        embedding_ttl: Time-to-live for embeddings in seconds
        result_ttl: Time-to-live for results in seconds
        enabled: Whether caching is enabled

    Returns:
        QueryCache instance
    """
    redis_client = None

    if redis_url and enabled:
        try:
            # Optional dependency: resolve at runtime so environments without
            # redis still type-check and gracefully fall back to memory cache.
            redis_module = __import__("redis")
            redis_client = redis_module.from_url(redis_url)
            # Test connection
            redis_client.ping()
            _log.info("Connected to Redis cache at %s", redis_url)
        except ImportError:
            _log.warning(
                "Redis package not available. Install with: pip install redis. Using in-memory cache as fallback."
            )
        except Exception as e:
            redis_client = None
            _log.warning(
                "Failed to connect to Redis at %s: %s. Using in-memory cache as fallback.",
                redis_url,
                e,
            )

    return QueryCache(
        redis_client=redis_client,
        embedding_ttl=embedding_ttl,
        result_ttl=result_ttl,
        enabled=enabled,
    )
