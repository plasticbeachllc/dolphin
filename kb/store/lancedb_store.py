from __future__ import annotations

from collections.abc import Iterable, Sequence
import logging
from pathlib import Path
from typing import Any


class LanceDBStore:
    """LanceDB integration for vector storage and retrieval (Sprint 1).

    For initialization, we eagerly create global collections for the supported
    embedding dimensions and ensure the root directory exists.
    """

    def __init__(self, root: str | Path) -> None:
        # Handle both file paths and in-memory URIs
        # In-memory URIs like "memory://name" should remain as strings
        if isinstance(root, str) and root.startswith("memory://"):
            # Keep memory:// URIs as strings for LanceDB
            self.root: str | Path = root
        else:
            # Convert file paths to Path objects
            self.root = Path(root) if isinstance(root, str) else root

        # Cache for database connection to avoid connection isolation issues
        self._db = None

    def connect(self) -> Any:
        """Get or create a cached LanceDB connection."""
        # Only create directory for file-based storage, not memory://
        if isinstance(self.root, Path):
            self.root.mkdir(parents=True, exist_ok=True)

        # Return cached connection if available
        if self._db is not None:
            return self._db

        # Create new connection and cache it
        import lancedb

        db_uri = self.root if isinstance(self.root, str) else self.root.as_posix()
        self._db = lancedb.connect(db_uri)
        return self._db

    def _get_schema_for_model(self, model: str) -> Any:
        """Get PyArrow schema for the given model.

        Args:
            model: Embedding model ('small' or 'large')

        Returns:
            PyArrow schema for the model's table
        """
        import pyarrow as pa

        model_to_dim = {"small": 1536, "large": 3072}

        if model not in model_to_dim:
            raise ValueError(f"Unknown model: {model}. Must be 'small' or 'large'")

        dim = model_to_dim[model]

        # Use fixed-size list for LanceDB vector search to work properly
        vector_field = pa.field("vector", pa.list_(pa.float32(), dim))

        fields = [
            pa.field("id", pa.string()),
            vector_field,
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

    def initialize_collections(self) -> None:
        """Create (or open) the global collections per the authoritative schema.

        Collections:
        - chunks_small: 1536-dim embeddings
        - chunks_large: 3072-dim embeddings
        """
        # Import locally to avoid import cost when unused.

        # Use cached connection
        db = self.connect()

        collections = [("chunks_small", "small"), ("chunks_large", "large")]
        existing: set[str] = set()
        try:
            table_list = db.list_tables()
        except Exception:
            table_list = getattr(db, "table_names", lambda: [])()
        for entry in table_list or []:
            if isinstance(entry, str):
                existing.add(entry)
            elif isinstance(entry, dict):
                name = entry.get("name")
                if isinstance(name, str):
                    existing.add(name)
            elif isinstance(entry, (list, tuple)) and entry:
                name = entry[0]
                if isinstance(name, str):
                    existing.add(name)
        for name, model in collections:
            self._get_schema_for_model(model)
            dim = 1536 if model == "small" else 3072
            if name in existing:
                # Table already exists; nothing to do.
                continue
            # Create table with schema
            # LanceDB requires at least one row of data to properly create a table
            # Create a dummy row with null/zero values that we'll delete immediately
            try:
                import datetime

                # Create a single dummy row with the schema
                dummy_row = {
                    "id": "__init_placeholder__",
                    "vector": [0.0] * dim,
                    "repo": "",
                    "path": "",
                    "start_line": 0,
                    "end_line": 0,
                    "text_hash": "",
                    "commit": "",
                    "branch": "",
                    "embed_model": "",
                    "language": None,
                    "symbol_kind": None,
                    "symbol_name": None,
                    "symbol_path": None,
                    "heading_h1": None,
                    "heading_h2": None,
                    "heading_h3": None,
                    "token_count": 0,
                    "created_at": datetime.datetime.now(datetime.UTC),
                }
                # Create table with the dummy row
                table = db.create_table(name, data=[dummy_row])
                # Immediately delete the placeholder row
                table.delete("id = '__init_placeholder__'")
            except Exception as e:
                # If table creation fails, check if it now exists (race condition)
                existing_after = set(db.list_tables())
                if name not in existing_after:
                    # Table truly doesn't exist and creation failed
                    raise RuntimeError(f"Failed to create table {name}: {e}") from e
                # Otherwise table exists now (likely race condition), continue

    def upsert_chunks(self, repo: str, chunks: Iterable[Any], *, model: str) -> None:
        """Persist chunk data using delete-then-append strategy.

        Args:
            repo: Repository name
            chunks: Iterable of chunk dictionaries with LanceDB schema
            model: Embedding model name ('small' or 'large')
        """
        # Map model to table name and expected dimension
        model_to_table = {"small": "chunks_small", "large": "chunks_large"}
        model_to_dim = {"small": 1536, "large": 3072}

        if model not in model_to_table:
            raise ValueError(f"Unknown model: {model}. Must be 'small' or 'large'")

        table_name = model_to_table[model]
        expected_dim = model_to_dim[model]

        # Use cached connection
        db = self.connect()

        # Convert chunks to list for processing
        chunks_list = list(chunks)
        if not chunks_list:
            return  # Nothing to do

        # Validate vector dimensions
        for chunk in chunks_list:
            vector = chunk.get("vector", [])
            if len(vector) != expected_dim:
                raise ValueError(
                    f"Vector dimension mismatch for model '{model}': expected {expected_dim}, got {len(vector)}"
                )

        # Extract IDs for deletion
        ids_to_delete = [chunk["id"] for chunk in chunks_list if "id" in chunk]

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
        # Convert data to PyArrow table with explicit schema to avoid casting issues
        import pyarrow as pa

        # Get the schema for the target table
        schema = self._get_schema_for_model(model)

        # Convert chunks to PyArrow table with explicit schema
        try:
            # Normalize None values and create PyArrow table
            normalized_chunks = []
            for chunk in chunks_list:
                normalized = {}
                for key, value in chunk.items():
                    # Handle None values properly - PyArrow needs them as None, not as missing keys
                    normalized[key] = value
                normalized_chunks.append(normalized)

            pa_table = pa.Table.from_pylist(normalized_chunks, schema=schema)
        except Exception as schema_error:
            raise RuntimeError(
                f"Failed to convert chunks to PyArrow table with schema: {schema_error}"
            ) from schema_error

        try:
            table = db.open_table(table_name)
            # Table exists - check if it has the problematic schema from initialize_collections
            try:
                count = table.count_rows()
                if count == 0:
                    # Empty table from initialization - drop and recreate with real data
                    db.drop_table(table_name)
                    db.create_table(table_name, data=pa_table, mode="create")
                else:
                    # Has data - try to append
                    table.add(pa_table, mode="append")
            except Exception as append_error:
                # If append fails, try to drop and recreate
                try:
                    db.drop_table(table_name)
                    db.create_table(table_name, data=pa_table, mode="create")
                except Exception:
                    raise append_error
        except Exception as e:
            # If table doesn't exist, create it with the data directly
            print(f"Table {table_name} not found, creating it from data")
            try:
                # Create table directly from data instead of using initialize_collections
                # This ensures schema matches exactly
                db.create_table(table_name, data=pa_table, mode="create")
            except Exception as retry_error:
                # If still failing, raise a more descriptive error
                raise RuntimeError(f"Failed to create table {table_name}: {retry_error}") from e

    def prune_file_rows(
        self,
        repo: str,
        path: str,
        *,
        model: str,
        keep_ids: set[str] | None = None,
    ) -> None:
        """Remove vectors for a given repo/path, optionally preserving specific row IDs."""
        model_to_table = {"small": "chunks_small", "large": "chunks_large"}

        if model not in model_to_table:
            raise ValueError(f"Unknown model: {model}. Must be 'small' or 'large'")

        # Use cached connection
        db = self.connect()
        try:
            table = db.open_table(model_to_table[model])
        except Exception:
            # Nothing to prune if the table does not exist yet
            return

        repo_expr = repr(repo)
        path_expr = repr(path)
        if keep_ids:
            id_list = ", ".join(repr(_id) for _id in sorted(keep_ids))
            filter_expr = f"repo = {repo_expr} AND path = {path_expr} AND id NOT IN ({id_list})"
        else:
            filter_expr = f"repo = {repo_expr} AND path = {path_expr}"

        try:
            table.delete(filter_expr)
        except Exception:
            # If deletion fails (e.g., because no matching rows), ignore silently.
            return

    def delete_repo(self, repo: str, *, model: str) -> None:
        """Delete all vectors for a given repository.

        Args:
            repo: Repository name
            model: Embedding model ('small' or 'large')
        """
        model_to_table = {"small": "chunks_small", "large": "chunks_large"}

        if model not in model_to_table:
            raise ValueError(f"Unknown model: {model}. Must be 'small' or 'large'")

        # Use cached connection
        db = self.connect()
        try:
            table = db.open_table(model_to_table[model])
        except Exception:
            # Nothing to delete if the table does not exist yet
            return

        repo_expr = repr(repo)
        filter_expr = f"repo = {repo_expr}"

        try:
            table.delete(filter_expr)
        except Exception:
            # If deletion fails (e.g., because no matching rows), ignore silently.
            return

    def count_repo_vectors(self, repo: str, *, model: str) -> int:
        """Count the number of vectors for a repository.

        Args:
            repo: Repository name
            model: Embedding model ('small' or 'large')

        Returns:
            Number of vectors found for the repository
        """
        model_to_table = {"small": "chunks_small", "large": "chunks_large"}

        if model not in model_to_table:
            raise ValueError(f"Unknown model: {model}. Must be 'small' or 'large'")

        # Use cached connection
        db = self.connect()
        try:
            table = db.open_table(model_to_table[model])
        except Exception:
            # Table doesn't exist yet
            return 0

        repo_expr = repr(repo)
        filter_expr = f"repo = {repo_expr}"

        try:
            # Query matching rows and count them
            result = table.search().where(filter_expr).limit(1000000).to_list()
            return len(result)
        except Exception:
            # If query fails, assume 0
            return 0

    def query(
        self,
        query_vector: Sequence[float],
        *,
        model: str = "small",
        repo: str | None = None,
        top_k: int = 8,
        ann_params: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Execute KNN search against the vector store with configurable ANN parameters.

        Args:
            query_vector: The query embedding vector
            model: Model type ('small' or 'large') determines which table to search
            repo: Optional repository filter (exact match on 'repo' field)
            top_k: Number of nearest neighbors to return
            ann_params: ANN configuration (uses defaults if None)

        Returns:
            List of matching chunks with metadata, sorted by similarity (closest first)
        """
        from kb.retrieval.ann_tuning import ANNParams

        # Use default params if not provided
        if ann_params is None:
            ann_params = ANNParams()  # Default configuration

        # Map model to table name and expected dimension
        model_to_table = {"small": "chunks_small", "large": "chunks_large"}
        model_to_dim = {"small": 1536, "large": 3072}

        if model not in model_to_table:
            raise ValueError(f"Unknown model: {model}. Must be 'small' or 'large'")

        table_name = model_to_table[model]
        expected_dim = model_to_dim[model]

        # Validate query vector dimension
        if len(query_vector) != expected_dim:
            raise ValueError(
                f"Query vector dimension mismatch for model '{model}': expected {expected_dim}, got {len(query_vector)}"
            )

        # Use cached connection
        db = self.connect()

        try:
            table = db.open_table(table_name)
        except Exception:
            # Table doesn't exist yet
            return []

        # Build search query with ANN parameters - explicitly specify vector column name
        search_query = table.search(list(query_vector), vector_column_name="vector").limit(top_k)

        # Apply ANN parameters to LanceDB query
        # LanceDB API: https://lancedb.github.io/lancedb/search/
        lance_params = ann_params.to_lancedb_params()

        # Apply metric if supported
        if hasattr(search_query, "metric"):
            search_query = search_query.metric(lance_params["metric"])

        # Apply nprobes if using index
        if lance_params["use_index"] and hasattr(search_query, "nprobes"):
            search_query = search_query.nprobes(lance_params["nprobes"])

        # Apply refine_factor if using index
        if lance_params["use_index"] and hasattr(search_query, "refine_factor"):
            search_query = search_query.refine_factor(lance_params["refine_factor"])

        # Add repository filter if specified
        if repo is not None:
            search_query = search_query.where(f"repo = '{repo}'")

        # Execute search and convert to list of dicts
        try:
            results = search_query.to_list()
            return results
        except Exception:
            # Handle empty table or other search errors
            return []

    def get_chunk_by_id(self, chunk_id: str, model: str = "small") -> dict[str, Any] | None:
        """Retrieve a chunk by its ID from the vector store.

        Args:
            chunk_id: The chunk ID to retrieve
            model: Model type ('small' or 'large') determines which table to search

        Returns:
            Chunk dictionary if found, None otherwise
        """
        # Map model to table name
        model_to_table = {"small": "chunks_small", "large": "chunks_large"}

        if model not in model_to_table:
            raise ValueError(f"Unknown model: {model}. Must be 'small' or 'large'")

        table_name = model_to_table[model]

        # Connect to database and open table using cached connection logic
        db = self.connect()

        try:
            table = db.open_table(table_name)
        except Exception:
            # Table doesn't exist yet
            return None

        # Query for the specific ID
        try:
            results = table.search().where(f"id = '{chunk_id}'").limit(1).to_list()
            return results[0] if results else None
        except Exception:
            return None

    def get_vectors_by_hashes(self, repo: str, hashes: Iterable[str], *, model: str) -> dict[str, list[float]]:
        """Retrieve vectors for specific text hashes in a repository.

        Args:
            repo: Repository name
            hashes: List/Set of text hashes to look up
            model: Embedding model ('small' or 'large')

        Returns:
            Dictionary mapping text_hash -> vector
        """
        model_to_table = {"small": "chunks_small", "large": "chunks_large"}

        if model not in model_to_table:
            raise ValueError(f"Unknown model: {model}. Must be 'small' or 'large'")

        hash_list = list(hashes)
        if not hash_list:
            return {}

        # Use cached connection
        db = self.connect()
        try:
            table = db.open_table(model_to_table[model])
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(
                "Failed to open table '%s'",
                model_to_table[model],
                exc_info=e,
            )
            return {}

        repo_expr = repr(repo)

        # Build filter expression
        # Note: If hash_list is very large, this might hit SQL parser limits.
        # But for incremental updates, it's typically manageable.
        quoted_hashes = [repr(h) for h in hash_list]
        hash_expr = ", ".join(quoted_hashes)
        filter_expr = f"repo = {repo_expr} AND text_hash IN ({hash_expr})"

        try:
            # Select only text_hash and vector
            results = (
                table.search()
                .where(filter_expr)
                .select(["text_hash", "vector"])
                .to_list()
            )

            return {r["text_hash"]: r["vector"] for r in results}
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning("Failed to get vectors by hashes", exc_info=e)
            return {}
