"""Backward compatible alias for the LanceDB vector store implementation."""
from __future__ import annotations

from pathlib import Path

from .lancedb_store import LanceDBStore

PathLike = Path | str


class LanceDBVectorStore(LanceDBStore):
    """Compatibility wrapper exposing the historical LanceDBVectorStore name.

    Some legacy integrations and tests still import :class:`LanceDBVectorStore`
    from ``kb.store.lancedb_vector``. The modern implementation lives in
    :class:`~kb.store.lancedb_store.LanceDBStore`, so this subclass simply
    forwards initialisation to the updated class while accepting either
    ``Path`` or string inputs for convenience.
    """

    def __init__(self, root: PathLike) -> None:
        path = Path(root) if not isinstance(root, Path) else root
        super().__init__(path)


__all__ = ["LanceDBVectorStore"]
