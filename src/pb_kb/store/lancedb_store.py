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
                # Optional/nullable metadata fields
                pa.field("language", pa.string(), nullable=True),
                pa.field("symbol_kind", pa.string(), nullable=True),
                pa.field("symbol_name", pa.string(), nullable=True),
                pa.field("symbol_path", pa.string(), nullable=True),
                pa.field("heading_h1", pa.string(), nullable=True),
                pa.field("heading_h2", pa.string(), nullable=True),
                pa.field("heading_h3", pa.string(), nullable=True),
                pa.field("token_count", pa.int32()),
                pa.field("created_at", pa.timestamp("us", tz="UTC"), nullable=True),
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
        """Persist chunk data using delete-then-append strategy.
        
        Args:
            repo: Repository name
            chunks: Iterable of chunk dictionaries with LanceDB schema
            model: Embedding model name ('small' or 'large')
        """
        import lancedb
        import pyarrow as pa
        
        # Map model to table name and expected dimension
        model_to_table = {
            'small': 'chunks_small',
            'large': 'chunks_large'
        }
        model_to_dim = {
            'small': 1536,
            'large': 3072
        }
        
        if model not in model_to_table:
            raise ValueError(f"Unknown model: {model}. Must be 'small' or 'large'")
        
        table_name = model_to_table[model]
        expected_dim = model_to_dim[model]
        
        # Connect to database
        db = lancedb.connect(self.root.as_posix())
        
        # Convert chunks to list for processing
        chunks_list = list(chunks)
        if not chunks_list:
            return  # Nothing to do
        
        # Validate vector dimensions
        for chunk in chunks_list:
            vector = chunk.get('vector', [])
            if len(vector) != expected_dim:
                raise ValueError(
                    f"Vector dimension mismatch for model '{model}': "
                    f"expected {expected_dim}, got {len(vector)}"
                )
        
        # Extract IDs for deletion
        ids_to_delete = [chunk['id'] for chunk in chunks_list if 'id' in chunk]
        
        # Delete existing rows with these IDs
        if ids_to_delete:
            try:
                table = db.open_table(table_name)
                # Build safe filter expression for IDs using IN clause
                id_list = ", ".join([repr(x) for x in ids_to_delete])
                filter_expr = f"id in ({id_list})"
                table.delete(filter_expr)
            except Exception as e:
                # If table doesn't exist or delete fails, we'll append anyway
                print(f"Warning: Failed to delete existing rows: {e}")
        
        # Append new rows
        try:
            table = db.open_table(table_name)
            table.add(chunks_list)
        except Exception as e:
            # If table doesn't exist, create it and try again
            print(f"Table {table_name} not found, creating it: {e}")
            self.initialize_collections()
            table = db.open_table(table_name)
            table.add(chunks_list)

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
