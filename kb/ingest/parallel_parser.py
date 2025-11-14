"""Parallel tree-sitter parsing using multiprocessing.

This module provides parallel parsing of source files using tree-sitter,
achieving significant speedup on multi-core systems.
"""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

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
    chunks: List[Chunk]
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
    jobs: List[ParseJob],
    num_workers: int | None = None,
) -> List[ParseResult]:
    """Parse multiple files in parallel using multiprocessing.

    Args:
        jobs: List of ParseJob objects
        num_workers: Number of worker processes (default: CPU count)

    Returns:
        List of ParseResult objects in the same order as jobs
    """
    if not jobs:
        return []

    # Determine number of workers
    if num_workers is None:
        num_workers = min(mp.cpu_count(), 8)  # Cap at 8 to avoid overhead

    # For small batches, use sequential processing
    if len(jobs) < 4:
        return [_parse_file_worker(job) for job in jobs]

    # Process in parallel
    try:
        with mp.Pool(processes=num_workers) as pool:
            results = pool.map(_parse_file_worker, jobs)
        return results
    except Exception as e:
        # Fall back to sequential processing on error
        import logging

        logging.warning(f"Parallel parsing failed: {e}. Falling back to sequential.")
        return [_parse_file_worker(job) for job in jobs]


class ParallelChunkCache:
    """LRU cache for parsed chunks to avoid re-parsing unchanged files.

    This cache stores parsed chunks indexed by (file_path, content_hash) to
    enable fast incremental re-indexing.
    """

    def __init__(self, max_size: int = 1000):
        """Initialize cache with maximum size.

        Args:
            max_size: Maximum number of files to cache (default: 1000)
        """

        self.max_size = max_size
        self._cache: Dict[tuple[str, str], List[Chunk]] = {}
        self._access_order: List[tuple[str, str]] = []

    def get(self, file_path: str, content_hash: str) -> List[Chunk] | None:
        """Get cached chunks for a file.

        Args:
            file_path: Path to the file
            content_hash: SHA256 hash of file content

        Returns:
            List of cached chunks or None if not found
        """
        key = (file_path, content_hash)
        if key in self._cache:
            # Move to end (most recently used)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            return self._cache[key]
        return None

    def put(self, file_path: str, content_hash: str, chunks: List[Chunk]) -> None:
        """Store chunks in cache.

        Args:
            file_path: Path to the file
            content_hash: SHA256 hash of file content
            chunks: List of chunks to cache
        """
        key = (file_path, content_hash)

        # Remove oldest if at capacity
        if len(self._cache) >= self.max_size and key not in self._cache:
            if self._access_order:
                oldest_key = self._access_order.pop(0)
                self._cache.pop(oldest_key, None)

        self._cache[key] = chunks
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    def clear(self) -> None:
        """Clear all cached chunks."""
        self._cache.clear()
        self._access_order.clear()

    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)

    def hit_rate(self) -> float:
        """Get cache hit rate (requires tracking hits/misses)."""
        # Simple implementation - could be enhanced with hit/miss counters
        return 0.0


# Global cache instance
_chunk_cache = ParallelChunkCache(max_size=1000)


def get_chunk_cache() -> ParallelChunkCache:
    """Get the global chunk cache instance."""
    return _chunk_cache
