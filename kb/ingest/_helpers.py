"""Helper functions for the ingestion pipeline."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Sequence

from ..chunkers.types import Chunk


def build_desired_map(chunks: Sequence[Chunk]) -> Dict[str, List[Dict]]:
    """Build a mapping from text_hash to list of occurrence dictionaries.
    
    Args:
        chunks: Sequence of Chunk objects
        
    Returns:
        Dictionary mapping text_hash -> list of occurrence dicts
        Each occurrence dict contains:
          - start_line
          - end_line  
          - symbol_kind
          - symbol_name
          - symbol_path
          - heading_h1, heading_h2, heading_h3 (if present)
    """
    desired_map: Dict[str, List[Dict]] = {}
    
    for chunk in chunks:
        # Ensure chunk has a text_hash
        if not hasattr(chunk, 'text_hash') or chunk.text_hash is None:
            continue
            
        # Build occurrence dict
        occurrence = {
            'start_line': chunk.start_line,
            'end_line': chunk.end_line,
            'symbol_kind': getattr(chunk, 'symbol_kind', None),
            'symbol_name': getattr(chunk, 'symbol_name', None),
            'symbol_path': getattr(chunk, 'symbol_path', None),
        }
        
        # Add heading information if present
        for heading_level in ['h1', 'h2', 'h3']:
            heading_attr = f'heading_{heading_level}'
            if hasattr(chunk, heading_attr):
                occurrence[heading_attr] = getattr(chunk, heading_attr)
        
        # Group by text_hash
        if chunk.text_hash not in desired_map:
            desired_map[chunk.text_hash] = []
        desired_map[chunk.text_hash].append(occurrence)
    
    return desired_map


def git_changed_files_modified_added(repo_root: Path, from_commit: str, to_commit: str = 'HEAD') -> List[str]:
    """Get list of modified and added files between two commits.
    
    This uses three-way comparison via merge-base to correctly handle pulls and merges:
    1. Finds the merge base between from_commit and to_commit
    2. Compares merge base to to_commit to get all changes (local + remote)
    3. Returns union of changes, ensuring files changed on either branch are re-indexed
    
    This fixes the bug where pulling remote changes wouldn't re-index locally-modified files.
    
    Args:
        repo_root: Root path of the git repository
        from_commit: Starting commit (exclusive)
        to_commit: Ending commit (inclusive, defaults to HEAD)
        
    Returns:
        List of file paths relative to repo root
    """
    try:
        # Get merge base between from_commit and to_commit
        # This handles both linear history and merge scenarios correctly
        merge_base_result = subprocess.run(
            ['git', '-C', str(repo_root), 'merge-base', from_commit, to_commit],
            capture_output=True, text=True, check=True
        )
        merge_base = merge_base_result.stdout.strip()
        
        # Get all files changed from merge base to HEAD
        # This includes both local changes and remote changes after a pull
        result = subprocess.run(
            ['git', '-C', str(repo_root), 'diff', '--name-only', f'{merge_base}..{to_commit}'],
            capture_output=True, text=True, check=True
        )
        files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return files
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get git diff: {e.stderr}")


def git_changed_files_deleted(repo_root: Path, from_commit: str, to_commit: str = 'HEAD') -> List[str]:
    """Get list of deleted files between two commits.
    
    Uses merge-base comparison to correctly detect deletions after pulls/merges.
    
    Args:
        repo_root: Root path of the git repository
        from_commit: Starting commit (exclusive)
        to_commit: Ending commit (inclusive, defaults to HEAD)
        
    Returns:
        List of file paths relative to repo root
    """
    try:
        # Get merge base for consistent comparison
        merge_base_result = subprocess.run(
            ['git', '-C', str(repo_root), 'merge-base', from_commit, to_commit],
            capture_output=True, text=True, check=True
        )
        merge_base = merge_base_result.stdout.strip()
        
        # Get deleted files from merge base to HEAD
        result = subprocess.run(
            ['git', '-C', str(repo_root), 'diff', '--name-only', '--diff-filter=D', f'{merge_base}..{to_commit}'],
            capture_output=True, text=True, check=True
        )
        files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return files
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get git diff for deleted files: {e.stderr}")


def get_all_tracked_files(repo_root: Path) -> List[str]:
    """Get all tracked files in the repository.
    
    Args:
        repo_root: Root path of the git repository
        
    Returns:
        List of file paths relative to repo root
    """
    try:
        result = subprocess.run(
            ['git', '-C', str(repo_root), 'ls-files'],
            capture_output=True, text=True, check=True
        )
        files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return files
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get tracked files: {e.stderr}")


def representative_text_for_hash(text_hash: str, chunks: Sequence[Chunk]) -> str:
    """Get representative text for a given text_hash from chunks.
    
    Args:
        text_hash: The text hash to find
        chunks: Sequence of chunks to search
        
    Returns:
        The text content of the first chunk with matching hash
        
    Raises:
        ValueError: If no chunk with the given hash is found
    """
    for chunk in chunks:
        if hasattr(chunk, 'text_hash') and chunk.text_hash == text_hash:
            return chunk.text
    raise ValueError(f"No chunk found with text_hash: {text_hash}")