"""Search backend implementation connecting embeddings, vector search, and metadata."""

from __future__ import annotations
import math
from pathlib import Path
from typing import Optional, Sequence, List, Dict, Any

from ..config import KBConfig
from ..embeddings.provider import EmbeddingProvider, create_provider, set_default_provider
from ..store.lancedb_store import LanceDBStore
from ..store.sqlite_meta import SQLiteMetadataStore
from ..store.graph_store import GraphStore
from ..cache import QueryCache, create_cache
from ..retrieval.rankers import reciprocal_rank_fusion, maximal_marginal_relevance
from ..retrieval.cross_encoder_rerank import CrossEncoderReranker
from ..retrieval.types import Document
from ..retrieval.ann_tuning import ANNParams
from ..retrieval.graph_context import GraphContextEnricher
from .app import SearchRequest

# Constants
CANDIDATE_MULTIPLIER = 4
CONFIG_FILE_SCORE_PENALTY = 0.5
BM25_SCORE_NORMALIZATION_FACTOR = 10

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
        graph_store: Optional[GraphStore] = None,
    ):
        self.embedding_provider = embedding_provider
        self.lance_store = lance_store
        self.sql_store = sql_store
        self.cache = cache
        self.hybrid_search_enabled = hybrid_search_enabled
        self.reranker = reranker
        self.config = config
        self.graph_store = graph_store
        self._request_ann_config = None  # Per-request ANN configuration overrides
        
        # Initialize graph enricher if graph store is available
        self.graph_enricher = None
        if self.graph_store:
            self.graph_enricher = GraphContextEnricher(
                graph_store=self.graph_store,
                sql_store=self.sql_store,
                max_related_nodes=10,
                max_edges_per_node=5
            )

    def search(self, request: SearchRequest) -> Sequence[dict[str, object]]:
        import logging
        logger = logging.getLogger(__name__)

        # Log incoming search request
        logger.info(f"[SEARCH] Query: {request.query[:100]}")
        logger.info(f"[SEARCH] Repos filter: {request.repos}")
        logger.info(f"[SEARCH] Path prefix: {request.path_prefix}")
        logger.info(f"[SEARCH] Top-K: {request.top_k}, Score cutoff: {request.score_cutoff}")
        logger.info(f"[SEARCH] Embed model: {request.embed_model}")

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
                logger.info(f"[SEARCH] Returning {len(cached_results)} results from cache")
                return cached_results

        query_embedding = self.embedding_provider.embed_texts(request.embed_model, [request.query])[0]
        num_candidates = request.top_k * CANDIDATE_MULTIPLIER  # Fetch more candidates for reranking

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
            logger.info(f"[SEARCH] Vector search returned {len(vector_formatted)} results")
        except Exception as e:
            # Log error but continue with empty vector results
            logger.warning(f"[SEARCH] Vector search failed: {e}", exc_info=True)

        # BM25 search with error handling
        bm25_hydrated = []
        if self.hybrid_search_enabled and hasattr(self.sql_store, 'bm25_search'):
            try:
                repo_filter = request.repos[0] if request.repos else None
                logger.info(f"[SEARCH] BM25 search with repo={repo_filter}, path_prefix={request.path_prefix}")
                bm25_results = self.sql_store.bm25_search(
                    request.query,
                    repo=repo_filter,
                    path_prefix=request.path_prefix,
                    top_k=num_candidates
                )
                logger.info(f"[SEARCH] BM25 raw results: {len(bm25_results)}")
                if bm25_results:
                    logger.info(f"[SEARCH] BM25 sample result: chunk_id={bm25_results[0].get('chunk_id')}, repo={bm25_results[0].get('repo')}, score={bm25_results[0].get('score')}")
                bm25_hydrated = self._hydrate_bm25_results(bm25_results, self.sql_store)
                logger.info(f"[SEARCH] BM25 after hydration: {len(bm25_hydrated)} results")
            except Exception as e:
                # Log error but continue with empty BM25 results
                logger.warning(f"[SEARCH] BM25 search failed: {e}", exc_info=True)

        # Apply request filters to both vector and BM25 results
        vector_filtered = self._apply_request_filters(vector_formatted, request)
        bm25_filtered = self._apply_request_filters(bm25_hydrated, request)

        logger.info(f"[SEARCH] After filtering - Vector: {len(vector_filtered)}, BM25: {len(bm25_filtered)}")

        # Apply file type scoring adjustments to deprioritize config files
        vector_filtered = self._apply_file_type_scoring(vector_filtered)
        bm25_filtered = self._apply_file_type_scoring(bm25_filtered)

        logger.info(f"[SEARCH] After file type scoring - Vector: {len(vector_filtered)}, BM25: {len(bm25_filtered)}")

        hits = reciprocal_rank_fusion([vector_filtered, bm25_filtered])

        logger.info(f"[SEARCH] After RRF: {len(hits)} results")
        for i, hit in enumerate(hits[:3]):  # Log first 3 hits
            rrf_score = hit.get('rrf_score', 0.0)
            logger.info(f"[SEARCH] Hit {i+1}: chunk_id={hit.get('chunk_id')}, rrf_score={rrf_score}")
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

        # Optional MMR diversification (applied after fusion/reranking, before cutoff/limit)
        # Use request overrides when provided, otherwise fall back to global config.
        try:
            cfg_mmr_enabled = bool(self.config and getattr(self.config.retrieval, "mmr_enabled", False))
            cfg_mmr_lambda = (self.config.retrieval.mmr_lambda if self.config else 0.7)
        except Exception:
            cfg_mmr_enabled = False
            cfg_mmr_lambda = 0.7

        mmr_enabled = request.mmr_enabled if request.mmr_enabled is not None else cfg_mmr_enabled
        mmr_lambda = request.mmr_lambda if request.mmr_lambda is not None else cfg_mmr_lambda

        if mmr_enabled and hits:
            try:
                # Provide per-candidate vectors for diversity if available (fallback handled in ranker)
                for h in hits:
                    if "query_vector" not in h:
                        vec = h.get("vector")
                        if isinstance(vec, list) and vec:
                            h["query_vector"] = vec

                hits = maximal_marginal_relevance(
                    query_vector=query_embedding,  # computed earlier
                    candidates=hits,
                    top_k=request.top_k,
                    lambda_param=mmr_lambda,
                    id_field='chunk_id',
                )

                # Remove temporary fields to avoid inflating payload
                for h in hits:
                    if "query_vector" in h:
                        try:
                            del h["query_vector"]
                        except Exception:
                            pass
            except Exception as e:
                # Fall back gracefully if MMR fails for any reason
                import logging
                logging.warning(f"MMR diversification failed: {e}", exc_info=True)

        logger.info(f"[SEARCH] Before score cutoff: {len(hits)} hits")
        logger.info(f"[SEARCH] Score cutoff threshold: {request.score_cutoff}")

        final_results = [h for h in hits if h.get("score", 0.0) >= (request.score_cutoff or 0.0)][:request.top_k]

        logger.info(f"[SEARCH] After score cutoff and top-k limit: {len(final_results)} results")
        if not final_results:
            logger.warning(f"[SEARCH] ❌ NO RESULTS after score cutoff! Check if cutoff {request.score_cutoff} is too high")
        else:
            logger.info(f"[SEARCH] First result score: {final_results[0].get('score')}")

        # Hydrate content for all final results
        if final_results:
            chunk_ids_needing_content = [r['chunk_id'] for r in final_results if 'content' not in r]
            if chunk_ids_needing_content:
                try:
                    # Use helper to hydrate content
                    hydrated_content = self._hydrate_chunk_content(chunk_ids_needing_content, self.sql_store)

                    # Apply hydrated content to results
                    for result in final_results:
                        chunk_id = result['chunk_id']
                        if chunk_id in hydrated_content:
                            result['content'] = hydrated_content[chunk_id]
                            # Also add file_path for compatibility
                            if 'path' in result and 'file_path' not in result:
                                result['file_path'] = result['path']
                except Exception as e:
                    # Log error but don't fail the search
                    import logging
                    logging.warning(f"Failed to hydrate content for results: {e}", exc_info=True)
        
        # Enrich with graph context if requested and available
        include_graph = getattr(request, 'include_graph_context', False)
        if include_graph and self.graph_enricher:
            try:
                final_results = self.graph_enricher.enrich_search_results(
                    final_results,
                    include_callsites=True,
                    include_implementations=True,
                    include_dependencies=True
                )
            except Exception as e:
                # Log error but don't fail the search
                import logging
                logging.warning(f"Graph enrichment failed: {e}")
        
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
        """Apply repo, path_prefix, and negative filters to results."""
        from pathlib import PurePosixPath
        
        def normalize_path(path_str: str) -> PurePosixPath:
            """Normalize a path by removing leading ./ and / characters."""
            path_str = path_str.lstrip('./')
            path_str = path_str.lstrip('/')
            return PurePosixPath(path_str)
        
        filtered = results
        
        # Filter by repos if specified
        if request.repos:
            repo_set = set(request.repos)
            filtered = [r for r in filtered if r.get('repo') in repo_set]
        
        # Filter by path_prefix if specified (positive filtering)
        if request.path_prefix:
            def matches_prefix(path_str: str) -> bool:
                path = normalize_path(path_str)
                for prefix_str in request.path_prefix:
                    prefix = normalize_path(prefix_str)
                    try:
                        # Check if path is relative to prefix
                        path.relative_to(prefix)
                        return True
                    except ValueError:
                        # Not relative to this prefix
                        continue
                return False
            
            filtered = [r for r in filtered if matches_prefix(r.get('path', ''))]
        
        # Negative filtering: exclude_paths (exact path prefix exclusions)
        if request.exclude_paths:
            def matches_excluded_path(path_str: str) -> bool:
                path = normalize_path(path_str)
                for excl_str in request.exclude_paths:
                    excl = normalize_path(excl_str)
                    try:
                        # Check if path is relative to excluded prefix
                        path.relative_to(excl)
                        return True
                    except ValueError:
                        # Not relative to this exclusion
                        continue
                return False
            
            filtered = [r for r in filtered if not matches_excluded_path(r.get('path', ''))]
        
        # Negative filtering: exclude_patterns (glob/fnmatch pattern exclusions)
        if request.exclude_patterns:
            import fnmatch
            
            def matches_excluded_pattern(path_str: str) -> bool:
                path = normalize_path(path_str)
                
                for pattern in request.exclude_patterns:
                    # Match against both full path and basename
                    if fnmatch.fnmatch(str(path), pattern) or fnmatch.fnmatch(path.name, pattern):
                        return True
                return False
            
            filtered = [r for r in filtered if not matches_excluded_pattern(r.get('path', ''))]
        
        return filtered
    
    def _apply_file_type_scoring(self, results: list[dict[str, object]]) -> list[dict[str, object]]:
        """Apply scoring adjustments based on file type to deprioritize config files.

        Config files (TOML, JSON, YAML) are penalized to prevent them from
        dominating search results, especially when they contain many chunks.
        """
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
                result = {**result, 'score': score * CONFIG_FILE_SCORE_PENALTY}
            
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
            normalized_score = 1 / (1 + math.exp(-bm25_score / BM25_SCORE_NORMALIZATION_FACTOR))
            
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
        
    def _resolve_content_ids(self, row_ids: list[str]) -> dict[str, str]:
        """Convert LanceDB row IDs to metadata content_ids.
        
        LanceDB row IDs have format: {repo_id}:{file_id}:{embed_model}:{text_hash}:{start_line}:{end_line}
        We need to query the metadata store to get the corresponding content_id.
        
        Args:
            row_ids: List of LanceDB row IDs
            
        Returns:
            Dictionary mapping row_id -> content_id
        """
        row_id_to_content_id = {}
        
        for row_id in row_ids:
            try:
                # Parse the row_id format: repo_id:file_id:embed_model:text_hash:start_line:end_line
                parts = row_id.split(':')
                if len(parts) < 4:
                    continue
                    
                repo_id = int(parts[0])
                file_id = int(parts[1])
                embed_model = parts[2]
                text_hash = parts[3]
                
                # Query metadata store for the content_id
                with self.sql_store._connect() as conn:
                    from contextlib import closing
                    cur = conn.cursor()
                    cur.execute(
                        """
                        SELECT id FROM chunk_content
                        WHERE repo_id = ? AND file_id = ? AND embed_model = ? AND text_hash = ?
                        LIMIT 1
                        """,
                        (repo_id, file_id, embed_model, text_hash)
                    )
                    row = cur.fetchone()
                    if row:
                        content_id = str(row[0])
                        row_id_to_content_id[row_id] = content_id
                        
            except (ValueError, IndexError) as e:
                # Skip malformed row IDs
                import logging
                logging.warning(f"Failed to parse row_id {row_id}: {e}")
                continue
                
        return row_id_to_content_id

    def _hydrate_chunk_content(
        self,
        chunk_ids: list[str],
        sql_store: SQLiteMetadataStore
    ) -> dict[str, str]:
        """Hydrate content for chunk IDs.

        Args:
            chunk_ids: List of chunk row IDs from LanceDB
            sql_store: Metadata store for content lookup

        Returns:
            Dictionary mapping chunk_id -> content
        """
        if not chunk_ids:
            return {}

        # Convert LanceDB row IDs to content_ids
        content_id_map = self._resolve_content_ids(chunk_ids)
        content_ids = list(content_id_map.values())

        if not content_ids:
            return {}

        # Fetch content from metadata store
        contents = sql_store.get_chunk_contents(content_ids)

        # Map content back to original chunk_ids
        result = {}
        for chunk_id in chunk_ids:
            content_id = content_id_map.get(chunk_id)
            if content_id and content_id in contents:
                result[chunk_id] = contents[content_id]

        return result

    def _hydrate_docs_for_reranking(self, hits: List[Dict], sql_store: SQLiteMetadataStore) -> List[Dict]:
        ids_to_fetch = [h['chunk_id'] for h in hits if 'content' not in h]
        if not ids_to_fetch:
            return hits

        # Use helper to hydrate content
        hydrated_content = self._hydrate_chunk_content(ids_to_fetch, sql_store)

        # Apply hydrated content to hits
        for hit in hits:
            chunk_id = hit['chunk_id']
            if chunk_id in hydrated_content:
                hit['content'] = hydrated_content[chunk_id]

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
        cache_instance = create_cache(
            redis_url=config.redis_url,
            result_ttl=config.result_cache_ttl,
            enabled=config.cache_enabled
        )
        provider_kwargs['cache'] = cache_instance
    
    provider = create_provider(
        config.embedding_provider,
        **provider_kwargs
    )

    # Set as global default provider for async convenience functions
    set_default_provider(provider)

    # Create cache (always create but may be disabled)
    cache = create_cache(
        redis_url=config.redis_url if config.cache_enabled else None,
        result_ttl=config.result_cache_ttl,
        enabled=config.cache_enabled
    )
    
    # Create reranker if enabled
    reranker = None
    if config.retrieval.reranking.enabled:
        reranker = CrossEncoderReranker(
            model_name=config.retrieval.reranking.model,
            device=config.retrieval.reranking.device
        )
    
    # Create graph store
    graph_store = None
    try:
        graph_store = GraphStore(config.resolved_store_root() / "metadata.db")
    except Exception:
        # Graph store is optional
        import logging
        logging.debug("Graph store not available")
    
    # Create and return the search backend
    return KnowledgeSearchBackend(
        embedding_provider=provider,
        lance_store=lance_store,
        sql_store=sql_store,
        cache=cache,
        hybrid_search_enabled=hybrid_search_enabled,
        reranker=reranker,
        config=config,
        graph_store=graph_store
    )