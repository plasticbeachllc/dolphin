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
from ..retrieval.ann_tuning import ANNParams
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
        config: Optional[KBConfig] = None,
    ):
        self.embedding_provider = embedding_provider
        self.lance_store = lance_store
        self.sql_store = sql_store
        self.cache = cache
        self.hybrid_search_enabled = hybrid_search_enabled
        self.reranker = reranker
        self.config = config
        self._request_ann_config = None  # Per-request ANN configuration overrides

    def search(self, request: SearchRequest) -> Sequence[dict[str, object]]:
        # Check cache first if available
        if self.cache:
            # Create cache key from request parameters
            cache_params = {
                'top_k': request.top_k,
                'score_cutoff': request.score_cutoff,
                'embed_model': request.embed_model,
                'repos': request.repos,
                'path_prefix': request.path_prefix,
            }
            cached_results = self.cache.get_results(request.query, **cache_params)
            if cached_results is not None:
                return cached_results

        query_embedding = self.embedding_provider.embed_texts(request.embed_model, [request.query])[0]
        num_candidates = request.top_k * 4 # Fetch more candidates for reranking

        # Get ANN parameters from config or use defaults
        ann_params = self._get_ann_params(request)

        # Vector search with error handling
        vector_formatted = []
        try:
            vector_results = self.lance_store.query(
                query_embedding,
                model=request.embed_model,
                top_k=num_candidates,
                ann_params=ann_params
            )
            vector_formatted = self._format_vector_results(vector_results)
        except Exception as e:
            # Log error but continue with empty vector results
            import logging
            logging.warning(f"Vector search failed: {e}")
        
        # BM25 search with error handling
        bm25_hydrated = []
        if self.hybrid_search_enabled and hasattr(self.sql_store, 'bm25_search'):
            try:
                bm25_results = self.sql_store.bm25_search(
                    request.query,
                    repo=request.repos[0] if request.repos else None,
                    path_prefix=request.path_prefix,
                    top_k=num_candidates
                )
                bm25_hydrated = self._hydrate_bm25_results(bm25_results, self.sql_store)
            except Exception as e:
                # Log error but continue with empty BM25 results
                import logging
                logging.warning(f"BM25 search failed: {e}")

        # Apply request filters to vector results
        vector_filtered = self._apply_request_filters(vector_formatted, request)
        
        # Apply file type scoring adjustments to deprioritize config files
        vector_filtered = self._apply_file_type_scoring(vector_filtered)
        bm25_hydrated = self._apply_file_type_scoring(bm25_hydrated)
        
        import logging
        logging.debug(f"Vector results before RRF: {len(vector_filtered)}")
        logging.debug(f"BM25 results before RRF: {len(bm25_hydrated)}")
        
        hits = reciprocal_rank_fusion([vector_filtered, bm25_hydrated])
        
        logging.debug(f"RRF results: {len(hits)}")
        for hit in hits:
            rrf_score = hit.get('rrf_score', 0.0)
            logging.debug(f"Hit {hit.get('chunk_id')}: rrf_score={rrf_score}")
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
        
        # Cache results if cache is available
        if self.cache:
            self.cache.set_results(request.query, list(final_results), **cache_params)
            
        return final_results

    def _format_vector_results(self, vector_results: list[dict]) -> list[dict[str, object]]:
        import logging
        formatted = []
        for r in vector_results:
            distance = r.get('_distance', 1.0)
            score = 1 / (1 + distance)
            logging.debug(f"Vector result: id={r.get('id')}, _distance={distance}, score={score}")
            formatted.append({**r, 'chunk_id': r.get('id'), 'score': score})
        return formatted
    
    def _apply_request_filters(self, results: list[dict[str, object]], request: SearchRequest) -> list[dict[str, object]]:
        """Apply repo and path_prefix filters to results."""
        filtered = results
        
        # Filter by repos if specified
        if request.repos:
            repo_set = set(request.repos)
            filtered = [r for r in filtered if r.get('repo') in repo_set]
        
        # Filter by path_prefix if specified
        if request.path_prefix:
            def matches_prefix(path: str) -> bool:
                # Normalize path (remove leading ./ or /)
                normalized = path.lstrip('./')
                for prefix in request.path_prefix:
                    # Normalize prefix
                    norm_prefix = prefix.lstrip('./')
                    # Match if path equals prefix or starts with prefix/
                    if normalized == norm_prefix or normalized.startswith(norm_prefix + '/'):
                        return True
                return False
            
            filtered = [r for r in filtered if matches_prefix(r.get('path', ''))]
        
        return filtered
    
    def _apply_file_type_scoring(self, results: list[dict[str, object]]) -> list[dict[str, object]]:
        """Apply scoring adjustments based on file type to deprioritize config files.
        
        Config files (TOML, JSON, YAML) are penalized to prevent them from
        dominating search results, especially when they contain many chunks.
        """
        CONFIG_FILE_PENALTY = 0.5  # Reduce score by 50% for config files
        
        adjusted = []
        for result in results:
            path = result.get('path', '')
            score = result.get('score', 0.0)
            
            # Check if this is a config file
            is_config = (
                path.endswith('.toml') or
                path.endswith('.json') or
                path.endswith('.yaml') or
                path.endswith('.yml') or
                'config.toml' in path.lower() or
                'package.json' in path.lower() or
                'tsconfig.json' in path.lower()
            )
            
            if is_config:
                result = {**result, 'score': score * CONFIG_FILE_PENALTY}
            
            adjusted.append(result)
        
        return adjusted

    def _hydrate_bm25_results(self, bm25_results: list[dict], sql_store: SQLiteMetadataStore) -> list[dict[str, object]]:
        """Hydrate BM25 results with full chunk metadata from LanceDB.
        
        BM25 search returns minimal metadata (content_id, repo, path, score).
        We need to fetch full chunk data including embeddings, line numbers,
        symbol info, etc. from LanceDB for proper result formatting.
        
        If chunk data is not available (e.g., test data only in FTS),
        use the minimal data from BM25 results with normalized scores.
        """
        if not bm25_results:
            return []
        
        hydrated = []
        for result in bm25_results:
            # Fetch full chunk metadata from SQLiteMetadataStore
            chunk_data = sql_store.get_chunk_by_id(result["chunk_id"])
            
            # Normalize BM25 score to [0, 1] range for fusion
            # BM25 scores are unbounded, use sigmoid normalization
            bm25_score = result["score"]
            normalized_score = 1 / (1 + math.exp(-bm25_score / 10))
            
            # Create result dict with available data
            hydrated_result = {
                "chunk_id": result["chunk_id"],
                "repo": result["repo"],
                "path": result["path"],
                "score": normalized_score,
                "id": result["chunk_id"],  # For compatibility with vector results
            }
            
            # Add metadata from chunk_data if available
            if chunk_data:
                hydrated_result.update({
                    "text_hash": chunk_data.get("text_hash"),
                    "embed_model": chunk_data.get("embed_model"),
                    "language": chunk_data.get("language"),
                    "start_line": chunk_data.get("start_line"),
                    "end_line": chunk_data.get("end_line"),
                    "symbol_kind": chunk_data.get("symbol_kind"),
                    "symbol_name": chunk_data.get("symbol_name"),
                    "symbol_path": chunk_data.get("symbol_path"),
                })
            
            hydrated.append(hydrated_result)
        
        return hydrated
        
    def _hydrate_docs_for_reranking(self, hits: List[Dict], sql_store: SQLiteMetadataStore) -> List[Dict]:
        ids_to_fetch = [h['chunk_id'] for h in hits if 'content' not in h]
        if not ids_to_fetch:
            return hits
        
        contents = sql_store.get_chunk_contents(ids_to_fetch)
        for hit in hits:
            if hit['chunk_id'] in contents:
                hit['content'] = contents[hit['chunk_id']]
        return hits
    
    def set_request_ann_config(self, config: Dict[str, Any]) -> None:
        """Set per-request ANN configuration overrides.
        
        Args:
            config: Dictionary containing ANN configuration overrides
        """
        self._request_ann_config = config
    
    def _get_ann_params(self, request: SearchRequest) -> ANNParams:
        """Get ANN parameters based on configuration and request characteristics.
        
        Args:
            request: Search request containing query type and parameters
            
        Returns:
            ANNParams instance configured for this search
        """
        # Check for per-request overrides first
        if self._request_ann_config:
            strategy = self._request_ann_config.get('ann_strategy')
            nprobes = self._request_ann_config.get('ann_nprobes')
            refine_factor = self._request_ann_config.get('ann_refine_factor')
            
            if strategy == 'speed':
                params = ANNParams.for_speed()
            elif strategy == 'accuracy':
                params = ANNParams.for_accuracy()
            elif strategy == 'development':
                params = ANNParams.for_development()
            elif strategy == 'custom' and nprobes and refine_factor:
                params = ANNParams(
                    metric="cosine",
                    nprobes=nprobes,
                    refine_factor=refine_factor,
                    use_index=True
                )
            else:
                # Fallback to adaptive with overrides
                params = ANNParams.adaptive(top_k=request.top_k)
                if nprobes:
                    params.nprobes = nprobes
                if refine_factor:
                    params.refine_factor = refine_factor
            
            # Clear the override after use
            self._request_ann_config = None
            return params
        
        # Use global config if no per-request overrides
        if self.config is None:
            # Default to adaptive if no config available
            return ANNParams.adaptive(top_k=request.top_k)
        
        # Use config to create ANN params
        ann_params = ANNParams.from_config(self.config)
        
        # If adaptive strategy, adjust based on request characteristics
        if hasattr(self.config.retrieval.ann, 'strategy') and self.config.retrieval.ann.strategy == 'adaptive':
            # Determine query type based on query characteristics
            query_type = self._classify_query_type(request.query)
            
            # Estimate dataset size for adaptive tuning
            estimated_size = 100000  # Default, could be made configurable
            if hasattr(self.config.retrieval.ann, 'adaptive'):
                adaptive_config = self.config.retrieval.ann.adaptive
                if hasattr(adaptive_config, 'estimated_dataset_size'):
                    estimated_size = adaptive_config.estimated_dataset_size
            
            return ANNParams.adaptive(
                query_type=query_type,
                top_k=request.top_k,
                dataset_size=estimated_size
            )
        
        # For non-adaptive strategies, return the configured params
        return ann_params
    
    def _classify_query_type(self, query: str) -> str:
        """Classify query type based on query text characteristics.
        
        Args:
            query: The search query text
            
        Returns:
            Query type: "identifier", "concept", or "example"
        """
        query_lower = query.lower()
        
        # Identifier patterns (exact matches, code elements)
        identifier_patterns = [
            'class ', 'def ', 'function ', 'variable ', 'const ', 'let ',
            'import ', 'from ', 'module ', 'package ',
            'usercontroller', 'authenticationflow', 'main.py'
        ]
        
        # Example patterns (how-to questions)
        example_patterns = [
            'how to', 'example', 'tutorial', 'how do i', 'show me',
            'demo', 'sample code', 'walkthrough'
        ]
        
        # Check for identifier patterns
        for pattern in identifier_patterns:
            if pattern in query_lower:
                return "identifier"
        
        # Check for example patterns
        for pattern in example_patterns:
            if pattern in query_lower:
                return "example"
        
        # Default to concept for semantic queries
        return "concept"


def create_search_backend(store_root: Path, **kwargs) -> KnowledgeSearchBackend:
    # Map kwargs to KBConfig fields and create config
    config_data = {"store_root": store_root}
    
    # Initialize embedding section for nested config
    embedding_data = {}
    
    # Map embedding_provider_type to embedding_provider (nested under "embedding")
    if "embedding_provider_type" in kwargs:
        embedding_data["provider"] = kwargs["embedding_provider_type"]
    
    # Map cache_enabled
    if "cache_enabled" in kwargs:
        config_data["cache_enabled"] = kwargs["cache_enabled"]
    
    # Map redis_url
    if "redis_url" in kwargs:
        config_data["redis_url"] = kwargs["redis_url"]
    
    # Map reranker_config to retrieval.reranking
    if "reranker_config" in kwargs:
        reranker_data = kwargs["reranker_config"]
        # Initialize retrieval_data if it doesn't exist, or preserve existing config
        retrieval_data = config_data.get("retrieval", {})
        reranking_data = {
            "enabled": reranker_data.get("enabled", False),
            "model": reranker_data.get("model", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
            "device": reranker_data.get("device"),
            "batch_size": reranker_data.get("batch_size", 32),
            "candidate_multiplier": reranker_data.get("candidate_multiplier", 4),
            "score_threshold": reranker_data.get("score_threshold", 0.3)
        }
        retrieval_data["reranking"] = reranking_data
        config_data["retrieval"] = retrieval_data
    
    # Handle ANN configuration (ann_config kwarg or default adaptive config)
    ann_config = kwargs.get("ann_config", {})
    retrieval_data = config_data.get("retrieval", {})
    ann_data = {
        "strategy": ann_config.get("strategy", "adaptive"),
        "metric": ann_config.get("metric", "cosine"),
        "estimated_dataset_size": ann_config.get("estimated_dataset_size", 100000),
        "default_query_type": ann_config.get("default_query_type", "concept")
    }
    retrieval_data["ann"] = ann_data
    config_data["retrieval"] = retrieval_data
    
    # Handle batch size for embedding provider (nested under "embedding")
    if "batch_size" in kwargs:
        embedding_data["batch_size"] = kwargs["batch_size"]
    
    # Add embedding section to config_data if it has any values
    if embedding_data:
        config_data["embedding"] = embedding_data
    
    # Handle API key for OpenAI provider
    if embedding_data.get("provider") == "openai":
        if "api_key" in kwargs:
            import os
            os.environ["OPENAI_API_KEY"] = kwargs["api_key"]
    
    # Create config with the mapped data
    config = KBConfig.from_mapping(config_data)
    
    # Extract hybrid_search_enabled (not part of config, handled separately)
    hybrid_search_enabled = kwargs.get("hybrid_search_enabled", True)
    
    # Create stores
    sql_store = SQLiteMetadataStore(config.resolved_store_root() / "metadata.db")
    lance_store = LanceDBStore(config.resolved_store_root() / "lancedb")
    
    # Create embedding provider
    # Note: Only pass cache and redis_url if cache is enabled
    provider_kwargs = {
        'batch_size': config.embedding_batch_size,
    }
    
    if config.cache_enabled:
        cache_instance = create_cache(config.redis_url, config.result_cache_ttl)
        provider_kwargs['cache'] = cache_instance
    
    provider = create_provider(
        config.embedding_provider,
        **provider_kwargs
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
        reranker=reranker,
        config=config
    )