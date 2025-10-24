from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence


class LanceDBStore:
    """Placeholder LanceDB integration used during the bootstrap phase."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def connect(self) -> None:
        """Establish a connection to LanceDB (stub)."""
        self.root.mkdir(parents=True, exist_ok=True)

    def upsert_chunks(self, repo: str, chunks: Iterable[Any], *, model: str) -> None:
        """Persist chunk data (stub)."""
        _ = (repo, chunks, model)  # suppress unused-variable warnings

    def query(
        self,
        query_vector: Sequence[float],
        *,
        repo: str | None = None,
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        """Return an empty result set until retrieval is implemented."""
        _ = (query_vector, repo, top_k)
        return []
