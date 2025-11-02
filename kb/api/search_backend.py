"""Search backend implementation connecting embeddings, vector search, and metadata."""

from __future__ import annotations
import math
from pathlib import Path
from typing import Optional, Sequence, List, Dict, Any

from ..config import KBConfig
from ..embeddings.provider import EmbeddingProvider, create_provider
from ..store.lancedb_store import LanceDBStore
from ..store.sqlite_meta import SQLiteMetadataStore
from ..cache import QueryCache, create_cache
from ..retrieval.rankers import reciprocal_rank_fusion
from ..retrieval.cross_encoder_rerank import CrossEncoderReranker
from ..retrieval.types import Document
from .app import SearchRequest

class KnowledgeSearchBackend:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        lance_store: LanceDBStore,
        sql_store: SQLiteMetadataStore,
        cache: Optional[QueryCache] = None,
        hybrid_search_enabled: bool = True,
        reranker: Optional[CrossEncoderReranker] = None,
    ):
        self.embedding_provider = embedding_provider
        self.lance_store = lance_store
        self.sql_store = sql_store
        self.cache = cache
        self.hybrid_search_enabled = hybrid_search_enabled
        self.reranker = reranker

    def search(self, request: SearchRequest) -> Sequence[dict[str, object]]:
        # ... (caching logic) ...

        query_embedding = self.embedding_provider.embed_texts(request.embed_model, [request.query])[0]
        num_candidates = request.top_k * 4 # Fetch more candidates for reranking

        vector_results = self.lance_store.query(query_embedding, model=request.embed_model, top_k=num_candidates)
        vector_formatted = self._format_vector_results(vector_results)
        
        bm25_hydrated = []
        if self.hybrid_search_enabled and hasattr(self.sql_store, 'bm25_search'):
            bm25_results = self.sql_store.bm25_search(request.query, top_k=num_candidates)
            bm25_hydrated = self._hydrate_bm25_results(bm25_results, self.sql_store)

        hits = reciprocal_rank_fusion([vector_formatted, bm25_hydrated])
        for hit in hits:
            hit['score'] = hit.pop('rrf_score', 0.0)
        
        # UNCOMMENTED AND CORRECTED RERANKING LOGIC
        if self.reranker and hits:
            docs_to_rerank = self._hydrate_docs_for_reranking(hits, self.sql_store)
            reranked_docs = self.reranker.rerank(request.query, docs_to_rerank, top_k=request.top_k)
            # The reranked_docs now have the final score. We need to merge them back
            # while preserving the order and original hits.
            reranked_ids = {doc['chunk_id'] for doc in reranked_docs}
            final_hits = reranked_docs + [h for h in hits if h['chunk_id'] not in reranked_ids]
            hits = final_hits

        final_results = [h for h in hits if h.get("score", 0.0) >= (request.score_cutoff or 0.0)][:request.top_k]
        
        # ... (caching results) ...
            
        return final_results

    def _format_vector_results(self, vector_results: list[dict]) -> list[dict[str, object]]:
        return [{**r, 'chunk_id': r.get('id'), 'score': 1 / (1 + r.get('_distance', 1.0))} for r in vector_results]

    def _hydrate_bm25_results(self, bm25_results: list[dict], sql_store: SQLiteMetadataStore) -> list[dict[str, object]]:
        # ... (implementation unchanged) ...
        return bm25_results
        
    def _hydrate_docs_for_reranking(self, hits: List[Dict], sql_store: SQLiteMetadataStore) -> List[Dict]:
        ids_to_fetch = [h['chunk_id'] for h in hits if 'content' not in h]
        if not ids_to_fetch:
            return hits
        
        contents = sql_store.get_chunk_contents(ids_to_fetch)
        for hit in hits:
            if hit['chunk_id'] in contents:
                hit['content'] = contents[hit['chunk_id']]
        return hits


def create_search_backend(store_root: Path, **kwargs) -> KnowledgeSearchBackend:
    # Map kwargs to KBConfig fields and create config
    config_data = {"store_root": store_root}
    
    # Map embedding_provider_type to embedding_provider
    if "embedding_provider_type" in kwargs:
        config_data["embedding_provider"] = kwargs["embedding_provider_type"]
    
    # Map cache_enabled
    if "cache_enabled" in kwargs:
        config_data["cache_enabled"] = kwargs["cache_enabled"]
    
    # Map redis_url
    if "redis_url" in kwargs:
        config_data["redis_url"] = kwargs["redis_url"]
    
    # Map reranker_config to retrieval.reranking
    if "reranker_config" in kwargs:
        reranker_data = kwargs["reranker_config"]
        retrieval_data = {
            "reranking": {
                "enabled": reranker_data.get("enabled", False),
                "model": reranker_data.get("model", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
                "device": reranker_data.get("device")
            }
        }
        config_data["retrieval"] = retrieval_data
    
    # Handle API key and batch size for OpenAI provider
    if config_data.get("embedding_provider") == "openai":
        if "api_key" in kwargs:
            import os
            os.environ["OPENAI_API_KEY"] = kwargs["api_key"]
        if "batch_size" in kwargs:
            config_data["embedding_batch_size"] = kwargs["batch_size"]
    
    # Create config with the mapped data
    config = KBConfig.from_mapping(config_data)
    
    # Extract hybrid_search_enabled (not part of config, handled separately)
    hybrid_search_enabled = kwargs.get("hybrid_search_enabled", True)
    
    # Create stores
    sql_store = SQLiteMetadataStore(config.resolved_store_root())
    lance_store = LanceDBStore(config.resolved_store_root())
    
    # Create embedding provider
    provider = create_provider(
        config.embedding_provider,
        batch_size=config.embedding_batch_size,
        cache_enabled=config.cache_enabled,
        redis_url=config.redis_url
    )
    
    # Create cache if enabled
    cache = None
    if config.cache_enabled:
        cache = create_cache(config.redis_url, config.result_cache_ttl)
    
    # Create reranker if enabled
    reranker = None
    if config.retrieval.reranking.enabled:
        reranker = CrossEncoderReranker(
            model_name=config.retrieval.reranking.model,
            device=config.retrieval.reranking.device
        )
    
    # Create and return the search backend
    return KnowledgeSearchBackend(
        embedding_provider=provider,
        lance_store=lance_store,
        sql_store=sql_store,
        cache=cache,
        hybrid_search_enabled=hybrid_search_enabled,
        reranker=reranker
    )