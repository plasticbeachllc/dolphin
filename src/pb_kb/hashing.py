"""Content hashing and canonicalization for idempotent chunk processing.

This module provides utilities for generating stable content hashes that enable
deduplication and incremental indexing. Content is canonicalized before hashing
to ensure consistent fingerprints across platforms and editors.

Canonicalization Rules:
1. Normalize line endings to Unix-style (\\n)
2. Strip trailing whitespace from each line
3. Preserve leading/trailing newlines if present in original
4. Preserve indentation (significant in Python/YAML)

Usage:
    from pb_kb.hashing import hash_text, canonicalize_text
    
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
    3. Preserve original trailing newline if present
    
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
        return ""
    
    # Normalize line endings and strip trailing whitespace per line
    lines = [line.rstrip() for line in text.splitlines()]
    normalized = "\n".join(lines)
    
    # Preserve trailing newline if present in original
    if text.endswith(("\n", "\r\n", "\r")):
        return normalized + "\n"
    return normalized


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
