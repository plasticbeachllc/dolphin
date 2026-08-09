"""Parallel file scanner using multiprocessing for improved performance.

This module provides a parallel implementation of the file scanner that uses
multiprocessing to scan files concurrently, achieving 5-10x speedup over
sequential scanning.
"""

from __future__ import annotations

import multiprocessing as mp
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

from pathspec import PathSpec

from kb.services.repository_boundaries import path_is_within_boundary

from ._helpers import worker_ignore_sigint
from .lang import classify_language
from .scanner import FileCandidate, ScannerError, _inspect_candidate_file


def _process_file_batch(
    file_paths: list[str],
    root: Path,
    excluded_subtrees: list[str],
    ignore_patterns: list[str],
) -> list[FileCandidate]:
    """Process a batch of files in a worker process.

    Args:
        file_paths: List of relative file paths to process
        root: Repository root path
        excluded_subtrees: Repository-relative subtree roots to skip
        ignore_patterns: List of ignore patterns

    Returns:
        List of FileCandidate objects for valid files
    """
    spec = PathSpec.from_lines("gitignore", ignore_patterns)
    boundary_roots = set(excluded_subtrees)
    candidates: list[FileCandidate] = []

    for rel in file_paths:
        if path_is_within_boundary(rel, boundary_roots):
            continue
        # Skip by pathspec
        if spec.match_file(rel):
            continue

        inspection = _inspect_candidate_file(root, rel)
        if inspection is None:
            continue
        size, is_bin = inspection
        if is_bin:
            continue

        # Language
        _, language = classify_language(Path(rel))
        ext = Path(rel).suffix.lower() or None

        candidates.append(
            FileCandidate(
                repo_root=root,
                rel_path=rel,
                ext=ext,
                language=language,
                size_bytes=size,
                is_binary=is_bin,
            )
        )

    return candidates


def scan_repo_parallel(
    root: Path,
    ignores: Iterable[str],
    num_workers: int | None = None,
    batch_size: int = 100,
    pool: ProcessPoolExecutor | None = None,
) -> list[FileCandidate]:
    """Scan a git repo for candidate files using parallel processing.

    This is a drop-in replacement for scan_repo() that uses multiprocessing
    to achieve 5-10x speedup on repositories with many files.

    Args:
        root: Repository root path
        ignores: Iterable of ignore patterns
        num_workers: Number of worker processes (default: CPU count)
        batch_size: Number of files per batch (default: 100)
        pool: Optional shared executor to use

    Returns:
        List of FileCandidate objects

    Raises:
        ScannerError: If not a git repository or git command fails
    """
    # Import here to avoid issues on module load
    from .scanner import _list_tracked, _repository_boundary_plan, _validate_repository_boundary_plan

    root = root.expanduser().resolve()
    if not (root / ".git").exists():
        raise ScannerError(f"Not a git repository: {root}")

    # Get list of tracked files (this is fast, no need to parallelize)
    boundary_plan = _repository_boundary_plan(root)
    rel_paths = _list_tracked(root)
    excluded_subtrees = boundary_plan.excluded_subtrees
    ignore_patterns = list(ignores or [])

    if not rel_paths:
        _validate_repository_boundary_plan(boundary_plan)
        return []

    # Determine number of workers
    if pool is None and num_workers is None:
        num_workers = min(mp.cpu_count(), 8)  # Cap at 8 to avoid overhead

    # For small repos, use sequential processing if no pool provided
    if pool is None and len(rel_paths) < batch_size * 2:
        from .scanner import scan_repo

        return scan_repo(root, ignores)

    # Split files into batches
    batches = []
    for i in range(0, len(rel_paths), batch_size):
        batch = rel_paths[i : i + batch_size]
        batches.append(batch)

    # Process batches in parallel
    process_batch = partial(
        _process_file_batch,
        root=root,
        excluded_subtrees=list(excluded_subtrees),
        ignore_patterns=ignore_patterns,
    )

    all_candidates: list[FileCandidate] = []

    try:
        if pool:
            # Use shared executor
            # Note: ProcessPoolExecutor map returns iterator, but order is preserved
            for batch_candidates in pool.map(process_batch, batches):
                all_candidates.extend(batch_candidates)
        else:
            with mp.Pool(processes=num_workers, initializer=worker_ignore_sigint) as mp_pool:
                # Process batches and collect results
                for batch_candidates in mp_pool.imap_unordered(process_batch, batches):
                    all_candidates.extend(batch_candidates)
    except Exception as e:
        # Fall back to sequential processing on error
        import logging

        logging.warning(f"Parallel scanning failed: {e}. Falling back to sequential.")
        from .scanner import scan_repo

        return scan_repo(root, ignores)

    _validate_repository_boundary_plan(boundary_plan)
    return all_candidates
