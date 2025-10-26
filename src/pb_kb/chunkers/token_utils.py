from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

import tiktoken

# Mapping from our logical model buckets to tiktoken encodings.
# OpenAI text-embedding-3-small and -large both use cl100k_base.
_MODEL_TO_ENCODING = {
    "small": "cl100k_base",
    "large": "cl100k_base",
    "text-embedding-3-small": "cl100k_base",
    "text-embedding-3-large": "cl100k_base",
}


def get_tokenizer(model: str = "small") -> tiktoken.Encoding:
    """Return a tiktoken tokenizer appropriate for the given model bucket.

    Defaults to the 'small' embedding model bucket.
    """
    enc_name = _MODEL_TO_ENCODING.get(model, "cl100k_base")
    return tiktoken.get_encoding(enc_name)


def encode_tokens(text: str, tokenizer: tiktoken.Encoding | None = None) -> List[int]:
    """Encode text into token IDs using the provided tokenizer (or default)."""
    tok = tokenizer or get_tokenizer()
    return tok.encode(text)


def count_tokens(text: str, tokenizer: tiktoken.Encoding | None = None) -> int:
    """Return token count for the given text using tiktoken."""
    return len(encode_tokens(text, tokenizer))


def _normalize_overlap(target: int, overlap: int) -> int:
    if target <= 0:
        raise ValueError("target must be > 0")
    if overlap < 0:
        return 0
    if overlap >= target:
        return max(0, target - 1)
    return overlap


def window_token_ranges(
    num_tokens: int,
    *,
    target: int = 400,
    overlap: int = 40,
) -> List[Tuple[int, int]]:
    """Return a list of [start, end) token index ranges covering num_tokens with overlap.

    - Ensures the entire sequence [0, num_tokens) is covered.
    - For short sequences (<= target), returns a single window [0, num_tokens).
    - overlap is clamped to [0, target-1].
    """
    if num_tokens <= 0:
        return []
    overlap = _normalize_overlap(target, overlap)
    if num_tokens <= target:
        return [(0, num_tokens)]

    ranges: List[Tuple[int, int]] = []
    step = target - overlap
    start = 0
    while start < num_tokens:
        end = min(num_tokens, start + target)
        ranges.append((start, end))
        if end >= num_tokens:
            break
        start = start + step
    return ranges


def slice_text_by_token_ranges(
    text: str,
    ranges: Sequence[Tuple[int, int]],
    tokenizer: tiktoken.Encoding | None = None,
) -> List[str]:
    """Decode text slices from token index ranges.

    This reconstructs slice text from the encoded tokens; tiktoken decoding is
    reversible for these embed-model tokenizers, so slices should match original substrings.
    """
    tok = tokenizer or get_tokenizer()
    tokens = tok.encode(text)
    slices: List[str] = []
    n = len(tokens)
    for start, end in ranges:
        s = max(0, min(n, start))
        e = max(s, min(n, end))
        if s >= e:
            continue
        slices.append(tok.decode(tokens[s:e]))
    return slices


def window_text_by_tokens(
    text: str,
    *,
    model: str = "small",
    target: int = 400,
    overlap: int = 40,
) -> List[Tuple[str, int, int]]:
    """Return a list of (chunk_text, start_char_index, end_char_index) windows.

    - Uses tiktoken to create windows of approximately `target` tokens with `overlap`.
    - Computes character offsets by decoding each token once and building a cumulative
      character index, so we can slice the original text without an O(n^2) search.
    """
    tok = get_tokenizer(model)
    tokens = tok.encode(text)
    ranges = window_token_ranges(len(tokens), target=target, overlap=overlap)

    # Build cumulative character offsets per token index: char_offsets[i] = char index after i tokens
    char_offsets: List[int] = [0]
    append = char_offsets.append
    cur = 0
    for tid in tokens:
        piece = tok.decode([tid])
        cur += len(piece)
        append(cur)

    chunks: List[Tuple[str, int, int]] = []
    for s, e in ranges:
        s_char = char_offsets[s]
        e_char = char_offsets[e]
        sub = text[s_char:e_char]
        chunks.append((sub, s_char, e_char))
    return chunks
