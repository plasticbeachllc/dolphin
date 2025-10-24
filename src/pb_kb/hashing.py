from __future__ import annotations

import hashlib

__all__ = ["canonicalize_text", "hash_text"]


def canonicalize_text(text: str) -> str:
    """Normalize text prior to hashing to enforce idempotency across platforms."""
    lines = [line.rstrip() for line in text.splitlines()]
    normalized = "\n".join(lines)
    if text.endswith("\n"):
        return normalized + "\n"
    return normalized


def hash_text(text: str) -> str:
    """Compute the SHA256 hash of canonicalized text."""
    canonical = canonicalize_text(text)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
