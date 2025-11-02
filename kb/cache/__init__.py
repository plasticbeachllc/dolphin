"""Query caching module for Dolphin knowledge base.

This module provides multi-level caching for query embeddings and search results
to improve performance and reduce embedding API costs.
"""

from .cache import QueryCache, create_cache

__all__ = ["QueryCache", "create_cache"]