"""Search backend implementation connecting embeddings, vector search, and metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..embeddings.provider import EmbeddingProvider, create_provider
from ..store.lancedb_store import LanceDBStore
from ..store.sqlite_meta import SQLiteMetadataStore
from .app import SearchRequest


class KnowledgeSearchBackend:
    """Production search backend using OpenAI embeddings and LanceDB vector search."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        lance_store: LanceDBStore,
        sql_store: SQLiteMetadataStore,
    ):
        """Initialize search backend with required stores.

        Args:
            embedding_provider: Provider for generating query embeddings
            lance_store: LanceDB vector store for KNN search
            sql_store: SQLite store for metadata hydration
        """
        self.embedding_provider = embedding_provider
        self.lance_store = lance_store
        self.sql_store = sql_store

    def search(self, request: SearchRequest) -> Sequence[dict[str, object]]:
        """Execute search request and return results.

        Args:
            request: Search request with query text and parameters

        Returns:
            List of search results with content and metadata
        """
        # Step 1: Embed the query
        query_embedding = self.embedding_provider.embed_texts(
            request.embed_model, [request.query]
        )[0]

        # Step 2: Search vector store for similar chunks
        # Handle repo filtering - LanceDB expects a single repo string
        repo_filter = request.repos[0] if request.repos and len(request.repos) == 1 else None

        vector_results = self.lance_store.query(
            query_embedding,
            model=request.embed_model,
            repo=repo_filter,
            top_k=request.top_k,
        )

        # Step 3: Format results for API response and apply score cutoff
        hits = []
        for result in vector_results:
            # Extract metadata from LanceDB result
            distance = float(result.get("_distance", 1.0))
            score = self._distance_to_similarity(distance)
            if request.score_cutoff is not None and score < request.score_cutoff:
                continue

            hit = {
                "chunk_id": result.get("id"),
                "repo": result.get("repo"),
                "path": result.get("path"),
                "start_line": result.get("start_line"),
                "end_line": result.get("end_line"),
                "language": result.get("language"),
                "symbol_kind": result.get("symbol_kind"),
                "symbol_name": result.get("symbol_name"),
                "symbol_path": result.get("symbol_path"),
                "score": score,
                "commit": result.get("commit"),
                "branch": result.get("branch"),
            }

            # Apply path prefix filter if specified
            if request.path_prefix:
                path = hit.get("path", "")
                if not any(path.startswith(prefix) for prefix in request.path_prefix):
                    continue

            # Filter by repo list if multiple repos specified
            if request.repos and len(request.repos) > 1:
                if hit.get("repo") not in request.repos:
                    continue

            hits.append(hit)

        return hits

    @staticmethod
    def _distance_to_similarity(distance: float) -> float:
        """Convert L2 distance to similarity score (0-1, higher is better).

        Args:
            distance: L2 distance from LanceDB

        Returns:
            Similarity score between 0 and 1
        """
        # Simple conversion: similarity = 1 / (1 + distance)
        # This maps distance=0 -> similarity=1.0, distance=inf -> similarity=0
        return 1.0 / (1.0 + distance)


def create_search_backend(
    store_root: Path,
    embedding_provider_type: str = "stub",
    **embedding_kwargs
) -> KnowledgeSearchBackend:
    """Factory function to create a search backend.

    Args:
        store_root: Root directory for knowledge store
        embedding_provider_type: Type of embedding provider ('stub' or 'openai')
        **embedding_kwargs: Additional kwargs for embedding provider (e.g., api_key)

    Returns:
        Configured KnowledgeSearchBackend instance
    """
    # Create embedding provider
    embedding_provider = create_provider(embedding_provider_type, **embedding_kwargs)

    # Create LanceDB store
    lance_root = store_root / "lancedb"
    lance_store = LanceDBStore(lance_root)

    # Create SQL metadata store
    sql_path = store_root / "knowledge.db"
    sql_store = SQLiteMetadataStore(sql_path)

    # Ensure stores are initialized (match ingestion pipeline expectations)
    sql_store.initialize()
    lance_store.initialize_collections()

    return KnowledgeSearchBackend(embedding_provider, lance_store, sql_store)
