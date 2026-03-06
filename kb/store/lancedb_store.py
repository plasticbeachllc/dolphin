from __future__ import annotations

import logging
import threading
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

logger = logging.getLogger(__name__)

# LanceDB uses Product Quantization (PQ) for IVF_PQ indices.  PQ training
# requires at least this many rows (the default ``num_sub_vectors``).
# See https://lancedb.github.io/lancedb/ann_indexes/ and the upstream
# Lance error "Not enough rows to train PQ. Requires 256 rows".
_MIN_ROWS_FOR_PQ_INDEX = 256


class LanceDBStore:
    """LanceDB integration for vector storage and retrieval (Sprint 1).

    For initialization, we eagerly create global collections for the supported
    embedding dimensions and ensure the root directory exists.
    """

    MODEL_TO_TABLE = MappingProxyType({"small": "chunks_small", "large": "chunks_large"})
    MODEL_TO_DIM = MappingProxyType({"small": 1536, "large": 3072})

    def _resolve_model(self, model: str) -> tuple[str, int]:
        """Validate model and return (table_name, dimension)."""
        if model not in self.MODEL_TO_TABLE:
            raise ValueError(f"Unknown model: {model!r}. Must be one of: {sorted(self.MODEL_TO_TABLE)}")
        return self.MODEL_TO_TABLE[model], self.MODEL_TO_DIM[model]

    def __init__(self, root: str | Path) -> None:
        # Handle both file paths and in-memory URIs
        # In-memory URIs like "memory://name" should remain as strings
        if isinstance(root, str) and root.startswith("memory://"):
            # Keep memory:// URIs as strings for LanceDB
            self.root: str | Path = root
        else:
            # Convert file paths to Path objects
            self.root = Path(root) if isinstance(root, str) else root

        # Cache for database connection to avoid connection isolation issues.
        # Lance format supports concurrent readers on a single connection, so
        # a single cached db object is safe for read-heavy workloads.  The
        # _connect_lock only guards the one-time lazy-initialisation of _db.
        self._db = None
        self._indexed_tables: set[str] = set()
        self._index_failures: set[str] = set()
        self._index_lock = threading.Lock()
        self._connect_lock = threading.Lock()

    def connect(self) -> Any:
        """Get or create a cached LanceDB connection (thread-safe initialisation)."""
        if self._db is not None:
            return self._db

        with self._connect_lock:
            # Re-check after acquiring the lock (double-checked locking).
            if self._db is not None:
                return self._db

            # Only create directory for file-based storage, not memory://
            if isinstance(self.root, Path):
                self.root.mkdir(parents=True, exist_ok=True)

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

        _, dim = self._resolve_model(model)

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

    def _collect_table_names(self, db: Any) -> set[str]:
        try:
            table_list = db.list_tables()
        except Exception:
            logger.debug("list_tables() unavailable, falling back to table_names()", exc_info=True)
            table_list = getattr(db, "table_names", lambda: [])()
        names: set[str] = set()
        for entry in table_list or []:
            if isinstance(entry, str):
                names.add(entry)
            elif isinstance(entry, dict):
                name = entry.get("name")
                if isinstance(name, str):
                    names.add(name)
            elif isinstance(entry, (list, tuple)) and entry:
                name = entry[0]
                if isinstance(name, str):
                    names.add(name)
        return names

    def _mark_index_stale(self, table_name: str) -> None:
        with self._index_lock:
            self._indexed_tables.discard(table_name)
            self._index_failures.discard(table_name)

    def _ensure_vector_index(self, table_name: str, metric: str = "cosine") -> None:
        """Create a vector index lazily and exactly once per table."""
        with self._index_lock:
            if table_name in self._indexed_tables or table_name in self._index_failures:
                return

        db = self.connect()
        try:
            table = db.open_table(table_name)
        except Exception:
            logger.debug("Table '%s' not yet created; skipping index build.", table_name, exc_info=True)
            return

        try:
            row_count = table.count_rows()
            # Brute-force KNN is fast enough below the PQ training
            # threshold, and attempting index creation would fail.
            if row_count < _MIN_ROWS_FOR_PQ_INDEX:
                if row_count > 0:
                    logger.debug(
                        "Table '%s' has only %d rows (< %d); skipping vector index (brute-force is sufficient).",
                        table_name,
                        row_count,
                        _MIN_ROWS_FOR_PQ_INDEX,
                    )
                return
        except Exception:
            # If row count is unavailable, continue best-effort.
            logger.debug("count_rows() unavailable for '%s'; proceeding.", table_name, exc_info=True)

        # If index metadata exists, skip create call.
        try:
            if hasattr(table, "list_indices"):
                existing = table.list_indices()
                if existing:
                    with self._index_lock:
                        self._indexed_tables.add(table_name)
                    return
        except Exception:
            logger.debug("list_indices() failed for '%s'; will attempt creation.", table_name, exc_info=True)

        create_attempts = (
            lambda: table.create_index(vector_column_name="vector", metric=metric, replace=False),
            lambda: table.create_index(vector_column_name="vector", metric=metric),
            lambda: table.create_index("vector", metric=metric),
            lambda: table.create_index("vector"),
        )

        last_error: Exception | None = None
        for attempt in create_attempts:
            try:
                attempt()
                with self._index_lock:
                    self._indexed_tables.add(table_name)
                return
            except TypeError as exc:
                last_error = exc
                continue
            except Exception as exc:
                message = str(exc).lower()
                if "already exists" in message and "index" in message:
                    with self._index_lock:
                        self._indexed_tables.add(table_name)
                    return
                last_error = exc
                break

        with self._index_lock:
            self._index_failures.add(table_name)
        if last_error is not None:
            logger.warning("Failed to create LanceDB vector index for table '%s': %s", table_name, last_error)

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
        existing = self._collect_table_names(db)
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
                self._mark_index_stale(name)
            except Exception as e:
                # If table creation fails, check if it now exists (race condition)
                try:
                    db.open_table(name)
                    continue
                except Exception:
                    existing_after = self._collect_table_names(db)
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
        table_name, expected_dim = self._resolve_model(model)

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
            except Exception:
                # If table doesn't exist or delete fails, we'll append anyway
                logger.warning("Failed to delete existing rows before upsert; will append anyway.", exc_info=True)

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
                    self._mark_index_stale(table_name)
                else:
                    # Has data - try to append
                    table.add(pa_table, mode="append")
            except Exception as append_error:
                # If append fails, try to drop and recreate
                try:
                    db.drop_table(table_name)
                    db.create_table(table_name, data=pa_table, mode="create")
                    self._mark_index_stale(table_name)
                except Exception:
                    raise append_error
        except Exception as e:
            # If table doesn't exist, create it with the data directly
            logger.debug("Table '%s' not found; creating from data.", table_name)
            try:
                # Create table directly from data instead of using initialize_collections
                # This ensures schema matches exactly
                db.create_table(table_name, data=pa_table, mode="create")
                self._mark_index_stale(table_name)
            except Exception as retry_error:
                # If still failing, raise a more descriptive error
                raise RuntimeError(f"Failed to create table {table_name}: {retry_error}") from e

        # Keep index lifecycle explicit: create lazily after data write, then reuse.
        self._ensure_vector_index(table_name)

    def prune_file_rows(
        self,
        repo: str,
        path: str,
        *,
        model: str,
        keep_ids: set[str] | None = None,
    ) -> None:
        """Remove vectors for a given repo/path, optionally preserving specific row IDs."""
        table_name, _ = self._resolve_model(model)

        # Use cached connection
        db = self.connect()
        try:
            table = db.open_table(table_name)
        except Exception:
            # Nothing to prune if the table does not exist yet
            logger.debug("Table '%s' not yet created; nothing to prune.", table_name, exc_info=True)
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
            logger.debug("prune_file_rows delete failed for repo=%s path=%s; skipping.", repo, path, exc_info=True)
            return

    def delete_repo(self, repo: str, *, model: str) -> None:
        """Delete all vectors for a given repository.

        Args:
            repo: Repository name
            model: Embedding model ('small' or 'large')
        """
        table_name, _ = self._resolve_model(model)

        # Use cached connection
        db = self.connect()
        try:
            table = db.open_table(table_name)
        except Exception:
            # Nothing to delete if the table does not exist yet
            logger.debug("Table '%s' not yet created; nothing to delete for repo=%s.", table_name, repo, exc_info=True)
            return

        repo_expr = repr(repo)
        filter_expr = f"repo = {repo_expr}"

        try:
            table.delete(filter_expr)
        except Exception:
            # If deletion fails (e.g., because no matching rows), ignore silently.
            logger.debug("delete_repo delete failed for repo=%s; skipping.", repo, exc_info=True)
            return

    def count_repo_vectors(self, repo: str, *, model: str) -> int:
        """Count the number of vectors for a repository.

        Args:
            repo: Repository name
            model: Embedding model ('small' or 'large')

        Returns:
            Number of vectors found for the repository
        """
        table_name, _ = self._resolve_model(model)

        # Use cached connection
        db = self.connect()
        try:
            table = db.open_table(table_name)
        except Exception:
            # Table doesn't exist yet
            logger.debug("Table '%s' not yet created; vector count=0 for repo=%s.", table_name, repo, exc_info=True)
            return 0

        repo_expr = repr(repo)
        filter_expr = f"repo = {repo_expr}"

        try:
            return table.count_rows(filter=filter_expr)
        except Exception:
            # If query fails, assume 0
            logger.warning("count_repo_vectors query failed for repo=%s.", repo, exc_info=True)
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

        table_name, expected_dim = self._resolve_model(model)

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
            logger.debug("Table '%s' not yet created; returning empty results.", table_name, exc_info=True)
            return []

        # Avoid triggering ANN index build paths when the table has no vectors.
        try:
            if table.count_rows() == 0:
                return []
        except Exception:
            # If row counting fails, continue with normal query flow.
            logger.debug("count_rows() unavailable for '%s'; proceeding with query.", table_name, exc_info=True)

        self._ensure_vector_index(table_name, metric=ann_params.metric)

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
            logger.warning("Vector search failed on table '%s'.", table_name, exc_info=True)
            return []

    def get_chunk_by_id(self, chunk_id: str, model: str = "small") -> dict[str, Any] | None:
        """Retrieve a chunk by its ID from the vector store.

        Args:
            chunk_id: The chunk ID to retrieve
            model: Model type ('small' or 'large') determines which table to search

        Returns:
            Chunk dictionary if found, None otherwise
        """
        table_name, _ = self._resolve_model(model)

        # Connect to database and open table using cached connection logic
        db = self.connect()

        try:
            table = db.open_table(table_name)
        except Exception:
            # Table doesn't exist yet
            logger.debug("Table '%s' not yet created; chunk_id=%s not found.", table_name, chunk_id, exc_info=True)
            return None

        # Query for the specific ID
        try:
            results = table.search().where(f"id = '{chunk_id}'").limit(1).to_list()
            return results[0] if results else None
        except Exception:
            logger.warning("get_chunk_by_id query failed for chunk_id=%s.", chunk_id, exc_info=True)
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
        table_name, _ = self._resolve_model(model)

        hash_list = list(hashes)
        if not hash_list:
            return {}

        # Use cached connection
        db = self.connect()
        try:
            table = db.open_table(table_name)
        except Exception:
            logger.warning("Failed to open table '%s'.", table_name, exc_info=True)
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
            results = table.search().where(filter_expr).select(["text_hash", "vector"]).to_list()

            return {r["text_hash"]: r["vector"] for r in results}
        except Exception:
            logger.warning("Failed to get vectors by hashes for repo=%s.", repo, exc_info=True)
            return {}
