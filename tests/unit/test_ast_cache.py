"""Unit tests for AST cache."""

import tempfile
from pathlib import Path

import pytest

from kb.cache.ast_cache import ASTCache, clear_ast_cache, get_ast_cache
from kb.chunkers.types import Chunk


class TestASTCache:
    """Unit tests for ASTCache class."""

    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = ASTCache(max_size=100)

        assert cache.max_size == 100
        assert cache.size() == 0
        assert cache.hit_rate() == 0.0

    def test_put_and_get(self):
        """Test basic put and get operations."""
        cache = ASTCache(max_size=10)
        chunks = [Chunk(text="test", start_line=1, end_line=1, token_count=10)]

        cache.put("file.py", "hash123", chunks, "python")
        result = cache.get("file.py", "hash123")

        assert result == chunks

    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = ASTCache(max_size=10)

        result = cache.get("nonexistent.py", "hash456")
        assert result is None

    def test_different_hashes_different_cache_entries(self):
        """Test that different hashes create different entries."""
        cache = ASTCache(max_size=10)

        chunks1 = [Chunk(text="test1", start_line=1, end_line=1, token_count=10)]
        chunks2 = [Chunk(text="test2", start_line=1, end_line=1, token_count=10)]

        cache.put("file.py", "hash1", chunks1, "python")
        cache.put("file.py", "hash2", chunks2, "python")

        assert cache.get("file.py", "hash1") == chunks1
        assert cache.get("file.py", "hash2") == chunks2
        assert cache.size() == 2

    def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = ASTCache(max_size=3)

        chunks1 = [Chunk(text="1", start_line=1, end_line=1, token_count=10)]
        chunks2 = [Chunk(text="2", start_line=1, end_line=1, token_count=10)]
        chunks3 = [Chunk(text="3", start_line=1, end_line=1, token_count=10)]
        chunks4 = [Chunk(text="4", start_line=1, end_line=1, token_count=10)]

        cache.put("file1.py", "hash1", chunks1, "python")
        cache.put("file2.py", "hash2", chunks2, "python")
        cache.put("file3.py", "hash3", chunks3, "python")

        # Cache is now full
        assert cache.size() == 3

        # Add a 4th item, should evict file1
        cache.put("file4.py", "hash4", chunks4, "python")

        assert cache.size() == 3
        assert cache.get("file1.py", "hash1") is None  # Evicted
        assert cache.get("file2.py", "hash2") == chunks2
        assert cache.get("file3.py", "hash3") == chunks3
        assert cache.get("file4.py", "hash4") == chunks4

    def test_lru_ordering_on_access(self):
        """Test that accessing an item moves it to the end (most recent)."""
        cache = ASTCache(max_size=3)

        chunks1 = [Chunk(text="1", start_line=1, end_line=1, token_count=10)]
        chunks2 = [Chunk(text="2", start_line=1, end_line=1, token_count=10)]
        chunks3 = [Chunk(text="3", start_line=1, end_line=1, token_count=10)]
        chunks4 = [Chunk(text="4", start_line=1, end_line=1, token_count=10)]

        cache.put("file1.py", "hash1", chunks1, "python")
        cache.put("file2.py", "hash2", chunks2, "python")
        cache.put("file3.py", "hash3", chunks3, "python")

        # Access file1, making it most recent
        cache.get("file1.py", "hash1")

        # Add file4, should evict file2 (oldest)
        cache.put("file4.py", "hash4", chunks4, "python")

        assert cache.get("file1.py", "hash1") == chunks1  # Still present
        assert cache.get("file2.py", "hash2") is None  # Evicted
        assert cache.get("file3.py", "hash3") == chunks3
        assert cache.get("file4.py", "hash4") == chunks4

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        cache = ASTCache(max_size=10)
        chunks = [Chunk(text="test", start_line=1, end_line=1, token_count=10)]

        cache.put("file.py", "hash", chunks, "python")

        # 2 hits
        cache.get("file.py", "hash")
        cache.get("file.py", "hash")

        # 2 misses
        cache.get("other1.py", "hash1")
        cache.get("other2.py", "hash2")

        # Hit rate should be 50%
        assert cache.hit_rate() == 50.0

    def test_stats(self):
        """Test stats method."""
        cache = ASTCache(max_size=10)
        chunks = [Chunk(text="test", start_line=1, end_line=1, token_count=10)]

        cache.put("file.py", "hash", chunks, "python")
        cache.get("file.py", "hash")  # Hit
        cache.get("other.py", "hash2")  # Miss

        stats = cache.stats()

        assert stats["size"] == 1
        assert stats["max_size"] == 10
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 50.0
        assert stats["total_requests"] == 2

    def test_clear(self):
        """Test cache clear."""
        cache = ASTCache(max_size=10)
        chunks = [Chunk(text="test", start_line=1, end_line=1, token_count=10)]

        cache.put("file1.py", "hash1", chunks, "python")
        cache.put("file2.py", "hash2", chunks, "python")

        assert cache.size() == 2

        cache.clear()

        assert cache.size() == 0
        assert cache.hit_rate() == 0.0

    def test_invalidate_file(self):
        """Test invalidating all cache entries for a file."""
        cache = ASTCache(max_size=10)

        chunks1 = [Chunk(text="test1", start_line=1, end_line=1, token_count=10)]
        chunks2 = [Chunk(text="test2", start_line=1, end_line=1, token_count=10)]

        cache.put("file.py", "hash1", chunks1, "python")
        cache.put("file.py", "hash2", chunks2, "python")
        cache.put("other.py", "hash3", chunks1, "python")

        cache.invalidate("file.py")

        # All versions of file.py should be removed
        assert cache.get("file.py", "hash1") is None
        assert cache.get("file.py", "hash2") is None

        # Other files should remain
        assert cache.get("other.py", "hash3") == chunks1

    def test_persistence(self):
        """Test cache persistence to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = Path(tmpdir) / "cache.pkl"

            # Create cache and add data
            cache1 = ASTCache(max_size=10, persist_path=persist_path)
            chunks = [Chunk(text="test", start_line=1, end_line=1, token_count=10)]
            cache1.put("file.py", "hash", chunks, "python")

            # Manually save
            cache1._save_to_disk()

            # Create new cache instance from same path
            cache2 = ASTCache(max_size=10, persist_path=persist_path)

            # Should load from disk
            result = cache2.get("file.py", "hash")
            assert result == chunks


class TestGlobalCacheHelpers:
    """Unit tests for global cache helper functions."""

    def test_get_ast_cache(self):
        """Test getting global cache instance."""
        # Clear first
        clear_ast_cache()

        cache1 = get_ast_cache()
        cache2 = get_ast_cache()

        # Should return same instance
        assert cache1 is cache2

    def test_clear_ast_cache(self):
        """Test clearing global cache."""
        cache = get_ast_cache()
        chunks = [Chunk(text="test", start_line=1, end_line=1, token_count=10)]

        cache.put("file.py", "hash", chunks, "python")
        assert cache.size() == 1

        clear_ast_cache()

        # Cache should be cleared
        assert cache.size() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
