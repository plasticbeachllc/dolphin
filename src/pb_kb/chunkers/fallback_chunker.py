from __future__ import annotations

from . import Chunk


def chunk_text(text: str) -> list[Chunk]:
    """Fallback chunker for non-TS/Python content; returns a single chunk stub."""
    line_count = len(text.splitlines() or [""])
    return [
        Chunk(
            text=text,
            start_line=1,
            end_line=line_count,
            symbol_kind=None,
            symbol_name=None,
            symbol_path=None,
        )
    ]
