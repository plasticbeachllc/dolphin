from __future__ import annotations

from . import Chunk


def chunk_source(source: str) -> list[Chunk]:
    """Temporary stub that returns the entire source as a single chunk."""
    line_count = len(source.splitlines() or [""])
    return [
        Chunk(
            text=source,
            start_line=1,
            end_line=line_count,
            symbol_kind=None,
            symbol_name=None,
            symbol_path=None,
        )
    ]
