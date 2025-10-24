from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

__all__ = ["Chunk", "ChunkList"]


@dataclass(slots=True)
class Chunk:
    text: str
    start_line: int
    end_line: int
    symbol_kind: str | None = None
    symbol_name: str | None = None
    symbol_path: str | None = None


ChunkList = Sequence[Chunk]
