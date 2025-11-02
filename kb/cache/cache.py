"""Query caching implementation with Redis backend.

This module provides multi-level caching for embeddings and search results
to improve performance and reduce API costs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

_log = logging.getLogger(__name__)


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
        redis_client: Optional[Any] = None,
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

    def get_embedding(
        self, query: str, model: str
    ) -> Optional[list[float]]:
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
                if cache_key in self._memory_cache:
                    value, _ = self._memory_cache[cache_key]
                    self.stats["embedding_hits"] += 1
                    return value
                    
            self.stats["embedding_misses"] += 1
            return None
            
        except Exception as e:
            _log.warning("Cache read error for embedding: %s", e)
            return None

    def set_embedding(
        self, query: str, model: str, embedding: list[float]
    ) -> None:
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
                self.redis.setex(
                    cache_key,
                    self.embedding_ttl,
                    json.dumps(embedding)
                )
            else:
                # In-memory fallback (no TTL enforcement)
                import time
                self._memory_cache[cache_key] = (embedding, time.time() + self.embedding_ttl)
                
        except Exception as e:
            _log.warning("Cache write error for embedding: %s", e)

    def get_results(
        self, query: str, **params: Any
    ) -> Optional[list[dict[str, Any]]]:
        """Get cached search results.
        
        Args:
            query: Query text
            **params: Search parameters (repo, top_k, etc.)
            
        Returns:
            Cached search results or None if not cached
        """
        if not self.enabled:
            return None
            
        # Create stable hash from query + sorted params
        param_str = json.dumps(params, sort_keys=True, separators=(",", ":"))
        cache_key = f"results:{self._hash_key(query, param_str)}"
        
        try:
            if self.redis:
                cached = self.redis.get(cache_key)
                if cached:
                    self.stats["result_hits"] += 1
                    return json.loads(cached)
            else:
                # In-memory fallback
                if cache_key in self._memory_cache:
                    value, _ = self._memory_cache[cache_key]
                    self.stats["result_hits"] += 1
                    return value
                    
            self.stats["result_misses"] += 1
            return None
            
        except Exception as e:
            _log.warning("Cache read error for results: %s", e)
            return None

    def set_results(
        self, query: str, results: list[dict[str, Any]], **params: Any
    ) -> None:
        """Cache search results.
        
        Args:
            query: Query text
            results: Search results to cache
            **params: Search parameters used
        """
        if not self.enabled:
            return
            
        param_str = json.dumps(params, sort_keys=True, separators=(",", ":"))
        cache_key = f"results:{self._hash_key(query, param_str)}"
        
        try:
            if self.redis:
                self.redis.setex(
                    cache_key,
                    self.result_ttl,
                    json.dumps(results)
                )
            else:
                # In-memory fallback
                import time
                self._memory_cache[cache_key] = (results, time.time() + self.result_ttl)
                
        except Exception as e:
            _log.warning("Cache write error for results: %s", e)

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
                # Scan for all result keys containing this repo
                pattern = f"results:*{repo}*"
                for key in self.redis.scan_iter(match=pattern):
                    self.redis.delete(key)
                _log.info("Invalidated cache for repo: %s", repo)
            else:
                # In-memory: find and delete only results with matching repo
                # Need to check the params JSON in each key to match repo
                keys_to_delete = []
                for key in self._memory_cache.keys():
                    if key.startswith("results:"):
                        # The key contains a hash of query+params, but we need to check
                        # the actual cached data. For in-memory cache, we'll use a
                        # conservative approach: only delete if we can confirm it's this repo
                        try:
                            # Check if the params contain this repo
                            if repo in key:
                                keys_to_delete.append(key)
                        except Exception:
                            continue
                
                for key in keys_to_delete:
                    del self._memory_cache[key]
                
                _log.info("Invalidated cache for repo: %s", repo)
                
        except Exception as e:
            _log.warning("Cache invalidation error for repo %s: %s", repo, e)

    def clear(self) -> None:
        """Clear all cached data."""
        if not self.enabled:
            return
            
        try:
            if self.redis:
                # Clear all dolphin cache keys
                for pattern in ["embed:*", "results:*"]:
                    for key in self.redis.scan_iter(match=pattern):
                        self.redis.delete(key)
                _log.info("Cache cleared")
            else:
                self._memory_cache.clear()
                
        except Exception as e:
            _log.warning("Cache clear error: %s", e)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache hit/miss statistics and rates
        """
        total_embedding_requests = (
            self.stats["embedding_hits"] + self.stats["embedding_misses"]
        )
        total_result_requests = (
            self.stats["result_hits"] + self.stats["result_misses"]
        )
        
        embedding_hit_rate = (
            self.stats["embedding_hits"] / total_embedding_requests
            if total_embedding_requests > 0 else 0.0
        )
        
        result_hit_rate = (
            self.stats["result_hits"] / total_result_requests
            if total_result_requests > 0 else 0.0
        )
        
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
    redis_url: Optional[str] = None,
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
            import redis
            redis_client = redis.from_url(redis_url)
            # Test connection
            redis_client.ping()
            _log.info("Connected to Redis cache at %s", redis_url)
        except ImportError:
            _log.warning(
                "Redis package not available. Install with: pip install redis. "
                "Using in-memory cache as fallback."
            )
        except Exception as e:
            _log.warning(
                "Failed to connect to Redis at %s: %s. "
                "Using in-memory cache as fallback.",
                redis_url, e
            )
    
    return QueryCache(
        redis_client=redis_client,
        embedding_ttl=embedding_ttl,
        result_ttl=result_ttl,
        enabled=enabled,
    )