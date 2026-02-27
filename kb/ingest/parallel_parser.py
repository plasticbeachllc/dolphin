"""Parallel tree-sitter parsing using multiprocessing.

This module provides parallel parsing of source files using tree-sitter,
achieving significant speedup on multi-core systems.
"""

from __future__ import annotations

import multiprocessing as mp
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..chunkers.registry import get_chunker_for_file
from ..chunkers.types import Chunk


@dataclass
class ParseJob:
    """A parsing job for a single file."""

    file_path: Path
    content: str
    language: str
    model: str
    token_target: int
    overlap_pct: float


@dataclass
class ParseResult:
    """Result of parsing a file."""

    file_path: Path
    chunks: list[Chunk]
    success: bool
    error: str | None = None


def _parse_file_worker(job: ParseJob) -> ParseResult:
    """Worker function to parse a single file.

    Args:
        job: ParseJob containing file info and parsing parameters

    Returns:
        ParseResult with chunks or error information
    """
    try:
        chunker = get_chunker_for_file(job.file_path)

        # Type narrowing: chunker is callable if get_chunker_for_file returned successfully
        if chunker is None:
            raise ValueError(f"No chunker available for {job.file_path}")

        chunks = chunker(
            job.content,
            model=job.model,
            token_target=job.token_target,
            overlap_pct=job.overlap_pct,
        )

        return ParseResult(
            file_path=job.file_path,
            chunks=chunks,
            success=True,
        )
    except Exception as e:
        return ParseResult(
            file_path=job.file_path,
            chunks=[],
            success=False,
            error=str(e),
        )


def parse_files_parallel(
    jobs: list[ParseJob],
    num_workers: int | None = None,
    pool: Any = None,  # Can be ProcessPoolExecutor or DynamicWorkerPool
) -> list[ParseResult]:
    """Parse multiple files in parallel using multiprocessing.

    Args:
        jobs: List of ParseJob objects
        num_workers: Number of worker processes (default: CPU count)
        pool: Optional shared executor to use (overrides num_workers)

    Returns:
        List of ParseResult objects in the same order as jobs
    """
    if not jobs:
        return []

    # Determine number of workers logic
    if pool is None and num_workers is None:
        num_workers = min(mp.cpu_count(), 8)  # Cap at 8 to avoid overhead

    # For small batches, use sequential processing unless pool is provided
    # (If pool is provided, we assume caller wants parallel regardless)
    if pool is None and len(jobs) < 4:
        return [_parse_file_worker(job) for job in jobs]

    # Process in parallel
    try:
        if pool:
            # Use shared executor
            results = list(pool.map(_parse_file_worker, jobs))
            return results
        else:
            # Create new pool
            with mp.Pool(processes=num_workers) as mp_pool:
                results = mp_pool.map(_parse_file_worker, jobs)
            return results
    except Exception as e:
        # Fall back to sequential processing on error
        import logging

        logging.warning(f"Parallel parsing failed: {e}. Falling back to sequential.")
        return [_parse_file_worker(job) for job in jobs]


class ParallelChunkCache:
    """Thread-safe LRU cache for parsed chunks to avoid re-parsing unchanged files.

    Uses OrderedDict for O(1) LRU operations and a lock for thread safety.
    """

    def __init__(self, max_size: int = 1000):
        """Initialize cache with maximum size.

        Args:
            max_size: Maximum number of files to cache (default: 1000)
        """
        self.max_size = max_size
        self._cache: OrderedDict[tuple[str, str], list[Chunk]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, file_path: str, content_hash: str) -> list[Chunk] | None:
        """Get cached chunks for a file.

        Args:
            file_path: Path to the file
            content_hash: SHA256 hash of file content

        Returns:
            List of cached chunks or None if not found
        """
        key = (file_path, content_hash)
        with self._lock:
            if key in self._cache:
                self._hits += 1
                self._cache.move_to_end(key)
                return self._cache[key]
            self._misses += 1
            return None

    def put(self, file_path: str, content_hash: str, chunks: list[Chunk]) -> None:
        """Store chunks in cache.

        Args:
            file_path: Path to the file
            content_hash: SHA256 hash of file content
            chunks: List of chunks to cache
        """
        key = (file_path, content_hash)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = chunks
            else:
                if len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)  # Evict oldest
                self._cache[key] = chunks

    def clear(self) -> None:
        """Clear all cached chunks."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)

    def hit_rate(self) -> float:
        """Get cache hit rate."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return (self._hits / total) * 100


# Global cache instance
_chunk_cache = ParallelChunkCache(max_size=1000)


def get_chunk_cache() -> ParallelChunkCache:
    """Get the global chunk cache instance."""
    return _chunk_cache
