from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence


class LanceDBStore:
    """LanceDB integration for vector storage and retrieval (Sprint 1).

    For initialization, we eagerly create global collections for the supported
    embedding dimensions and ensure the root directory exists.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def connect(self) -> None:
        """Ensure the LanceDB root directory exists."""
        self.root.mkdir(parents=True, exist_ok=True)

    def initialize_collections(self) -> None:
        """Create (or open) the global collections per the authoritative schema.

        Collections:
        - chunks_small: 1536-dim embeddings
        - chunks_large: 3072-dim embeddings
        """
        self.connect()
        # Import locally to avoid import cost when unused.
        import pyarrow as pa  # type: ignore
        import lancedb  # type: ignore

        db = lancedb.connect(self.root.as_posix())

        def _vector_field(dim: int) -> pa.Field:
            # Arrow has no fixed-size list for variable enforcement in LanceDB;
            # use a list<float32>, LanceDB will validate vector length at write.
            return pa.field("vector", pa.list_(pa.float32()))

        def _schema_for(dim: int) -> pa.Schema:
            fields = [
                pa.field("id", pa.string()),
                _vector_field(dim),
                pa.field("repo", pa.string()),
                pa.field("path", pa.string()),
                pa.field("start_line", pa.int32()),
                pa.field("end_line", pa.int32()),
                pa.field("text_hash", pa.string()),
                pa.field("commit", pa.string()),
                pa.field("branch", pa.string()),
                pa.field("embed_model", pa.string()),
                pa.field("language", pa.string()),
                pa.field("symbol_kind", pa.string()),
                pa.field("symbol_name", pa.string()),
                pa.field("symbol_path", pa.string()),
                pa.field("heading_h1", pa.string()),
                pa.field("heading_h2", pa.string()),
                pa.field("heading_h3", pa.string()),
                pa.field("token_count", pa.int32()),
                pa.field("created_at", pa.timestamp("us", tz="UTC")),
            ]
            return pa.schema(fields)

        collections = [("chunks_small", 1536), ("chunks_large", 3072)]
        existing = set(getattr(db, "table_names", lambda: [])())
        for name, dim in collections:
            schema = _schema_for(dim)
            if name in existing:
                # Table already exists; nothing to do.
                continue
            # Create an empty table with the target schema.
            db.create_table(name, data=[], schema=schema)

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
