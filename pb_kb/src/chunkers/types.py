"""Core data types for the chunking system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

__all__ = ["Chunk", "ChunkList"]


@dataclass(slots=True)
class Chunk:
    """A chunk of text with provenance and metadata.
    
    Attributes:
        text: The chunk text (canonicalized for embedding)
        start_line: 1-based inclusive starting line number
        end_line: 1-based inclusive ending line number
        token_count: Number of tokens in the chunk (computed by tiktoken)
        text_hash: SHA256 hash of canonicalized text for deduplication
        symbol_kind: Optional symbol kind (function|class|method|module)
        symbol_name: Optional symbol name
        symbol_path: Optional symbol path (e.g., "path/to/file.py:Class.method")
        h1: Optional H1 heading (Markdown only)
        h2: Optional H2 heading (Markdown only)
        h3: Optional H3 heading (Markdown only)
    """
    
    text: str
    start_line: int
    end_line: int
    token_count: int
    text_hash: str | None = None
    symbol_kind: str | None = None
    symbol_name: str | None = None
    symbol_path: str | None = None
    h1: str | None = None
    h2: str | None = None
    h3: str | None = None


ChunkList = Sequence[Chunk]
