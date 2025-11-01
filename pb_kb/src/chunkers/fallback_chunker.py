from __future__ import annotations

import bisect
from typing import List, Tuple

from .token_utils import get_tokenizer, window_text_by_tokens, count_tokens
from .types import Chunk


def chunk_text(
    text: str,
    *,
    model: str = "small",
    token_target: int = 400,
    overlap_pct: float = 0.10,
) -> list[Chunk]:
    """Fallback chunker for generic content using token windowing.
    
    Uses tiktoken to create overlapping windows of approximately `token_target` tokens.
    Maps each window to 1-based line ranges in the original file.
    
    Args:
        text: The file content to chunk
        model: Tokenizer model ("small" or "large")
        token_target: Target tokens per chunk (default 400)
        overlap_pct: Overlap percentage between chunks (default 0.10 = 10%)
    
    Returns:
        List of Chunk objects with accurate line numbers and token counts
    """
    if not text:
        return []
    
    tok = get_tokenizer(model)
    overlap = max(0, int(token_target * overlap_pct))
    windows = window_text_by_tokens(text, model=model, target=token_target, overlap=overlap)
    
    # Build line-start offsets for entire file
    line_offsets = _build_line_offsets(text)
    
    chunks: List[Chunk] = []
    for raw_text, start_char, end_char in windows:
        if not raw_text:
            continue
        
        # Map character offsets to line numbers
        abs_start_line = _offset_to_line(line_offsets, start_char)
        abs_end_line = abs_start_line + raw_text.count("\n")
        
        # Trim leading/trailing newlines and recompute token count
        trimmed_text, token_count, lead_trim, trail_trim = _trim_and_tokenize(raw_text, tok)
        if not trimmed_text:
            continue
        
        # Adjust line numbers for trimmed newlines
        adj_start = abs_start_line + lead_trim
        adj_end = max(adj_start, abs_end_line - trail_trim)
        
        chunks.append(
            Chunk(
                text=trimmed_text,
                start_line=adj_start,
                end_line=adj_end,
                token_count=token_count,
                symbol_kind=None,
                symbol_name=None,
                symbol_path=None,
            )
        )
    
    return chunks


def _build_line_offsets(text: str) -> List[int]:
    """Return character offsets where each line starts: offsets[i] = char index of line (i+1)."""
    offsets: List[int] = [0]
    for idx, ch in enumerate(text):
        if ch == "\n":
            offsets.append(idx + 1)
    return offsets


def _offset_to_line(line_offsets: List[int], offset: int) -> int:
    """Convert a character offset to a 1-based line number using binary search."""
    line_idx = bisect.bisect_right(line_offsets, offset) - 1
    return line_idx + 1


def _trim_and_tokenize(raw_text: str, tokenizer) -> Tuple[str, int, int, int]:
    """Trim leading/trailing newlines and compute token_count.
    
    Returns: (trimmed_text, token_count, lead_trim, trail_trim)
    where lead_trim and trail_trim are the number of newlines removed.
    """
    lead_trim = len(raw_text) - len(raw_text.lstrip("\n"))
    trail_trim = len(raw_text) - len(raw_text.rstrip("\n"))
    trimmed = raw_text.strip("\n")
    if not trimmed:
        return "", 0, lead_trim, trail_trim
    token_count = count_tokens(trimmed, tokenizer)
    return trimmed, token_count, lead_trim, trail_trim
