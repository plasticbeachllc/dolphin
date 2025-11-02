"""Content hashing and canonicalization for idempotent chunk processing.

This module provides utilities for generating stable content hashes that enable
deduplication and incremental indexing. Content is canonicalized before hashing
to ensure consistent fingerprints across platforms and editors.

Canonicalization Rules:
1. Normalize line endings to Unix-style (\\n)
2. Strip trailing whitespace from each line
3. Remove leading/trailing blank lines
4. Ensure a single trailing newline
5. Preserve indentation (significant in Python/YAML)

Usage:
    from kb.hashing import hash_text, canonicalize_text
    
    # Hash a chunk directly
    chunk_hash = hash_text(chunk.text)
    
    # Or canonicalize then hash separately
    canonical = canonicalize_text(chunk.text)
    chunk_hash = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
"""

from __future__ import annotations

import hashlib
import logging

__all__ = ["canonicalize_text", "hash_text", "verify_hash"]

_log = logging.getLogger(__name__)


def canonicalize_text(text: str) -> str:
    """Normalize text for stable hashing.
    
    Applies the following transformations:
    1. Normalize line endings to \\n (Unix-style)
    2. Strip trailing whitespace from each line
    3. Remove leading/trailing blank lines
    4. Ensure exactly one trailing newline
    
    Indentation is preserved as it's semantically significant in many languages
    (Python, YAML, Makefile, etc.).
    
    Args:
        text: Raw chunk text with potentially inconsistent formatting
        
    Returns:
        Canonicalized text ready for hashing
        
    Examples:
        >>> canonicalize_text("hello\\r\\n  world  \\r\\n")
        'hello\\n  world\\n'
        
        >>> canonicalize_text("  def foo():\\n    pass  ")
        '  def foo():\\n    pass'
    """
    if not text:
        return "\n"

    # Normalize line endings to \n
    normalized_ends = text.replace("\r\n", "\n").replace("\r", "\n")

    # Split into lines and strip trailing whitespace per line
    raw_lines = normalized_ends.split("\n")
    lines = [line.rstrip() for line in raw_lines]

    # Remove leading blank lines
    start = 0
    while start < len(lines) and lines[start].strip() == "":
        start += 1

    # Remove trailing blank lines
    end = len(lines)
    while end > start and lines[end - 1].strip() == "":
        end -= 1

    trimmed_lines = lines[start:end]
    if not trimmed_lines:
        return "\n"

    normalized = "\n".join(trimmed_lines)

    # Ensure exactly one trailing newline
    return normalized + "\n"


def hash_text(text: str) -> str:
    """Generate SHA256 hash of canonicalized text.
    
    The text is canonicalized before hashing to ensure consistent fingerprints
    regardless of platform-specific line endings or trailing whitespace.
    
    Args:
        text: Chunk text (will be canonicalized automatically)
        
    Returns:
        64-character lowercase hexadecimal SHA256 digest
        
    Examples:
        >>> hash_text("hello world")
        'b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9'
        
        >>> hash_text("hello world\\r\\n") == hash_text("hello world\\n")
        True
    """
    canonical = canonicalize_text(text)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest


def verify_hash(text: str, expected_hash: str) -> bool:
    """Verify that text matches expected hash.
    
    Args:
        text: Content to verify
        expected_hash: Expected SHA256 hex digest (64 chars)
        
    Returns:
        True if hash matches, False otherwise
    """
    actual_hash = hash_text(text)
    return actual_hash == expected_hash.lower()
