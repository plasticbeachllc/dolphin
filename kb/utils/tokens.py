"""Shared token estimation using tiktoken.

Both snippet truncation (app.py) and rate-limit accounting (async_embedder.py)
previously used different, inaccurate heuristics.  This module provides a
single implementation backed by tiktoken's ``cl100k_base`` tokenizer (the
encoding used by ``text-embedding-3-small/large``).

If tiktoken is unavailable at runtime the functions fall back to a fast
character-based approximation and log a one-time debug message.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

# Module-level cached encoder to avoid the per-call load cost.
_encoder = None
_tiktoken_available: bool | None = None  # None = not yet attempted


def _get_encoder():
    global _encoder, _tiktoken_available
    if _tiktoken_available is False:
        return None
    if _encoder is not None:
        return _encoder
    try:
        import tiktoken

        _encoder = tiktoken.get_encoding("cl100k_base")
        _tiktoken_available = True
        return _encoder
    except Exception:
        _tiktoken_available = False
        _log.debug(
            "tiktoken unavailable; falling back to character-based token estimation. "
            "Install tiktoken for accurate counts: pip install tiktoken",
            exc_info=True,
        )
        return None


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in *text*.

    Uses tiktoken's ``cl100k_base`` encoder when available; falls back to
    ``ceil(len(text) / 4)`` otherwise (characters-per-token approximation).
    """
    enc = _get_encoder()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(text) // 4)


def estimate_tokens_batch(texts: list[str]) -> int:
    """Estimate the total number of tokens across all strings in *texts*."""
    enc = _get_encoder()
    if enc is not None:
        return sum(len(enc.encode(t)) for t in texts)
    return max(1, sum(len(t) for t in texts) // 4)
