"""Search backend implementation connecting embeddings, vector search, and metadata."""

from __future__ import annotations

import os
import random
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..cache import QueryCache, create_cache
from ..config import GraphConfig, KBConfig
from ..constants.retrieval_config import RETRIEVAL_PARAMS
from ..embeddings.provider import EmbeddingProvider, create_provider, set_default_provider
from ..observability.structured_logger import StructuredLogger
from ..retrieval.ann_tuning import ANNParams
from ..retrieval.bm25_normalizer import MinMaxNormalizer, QuantileNormalizer, ScoreNormalizer, SigmoidNormalizer
from ..retrieval.bm25_stats import BM25Statistics
from ..retrieval.cross_encoder_rerank import CrossEncoderReranker
from ..retrieval.graph_context import GraphContextEnricher
from ..retrieval.rankers import maximal_marginal_relevance, reciprocal_rank_fusion
from ..store.graph_store import GraphStore
from ..store.lancedb_store import LanceDBStore
from ..store.sqlite_meta import SQLiteMetadataStore
from .app import SearchRequest


class KnowledgeSearchBackend:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        lance_store: LanceDBStore,
        sql_store: SQLiteMetadataStore,
        cache: QueryCache | None = None,
        hybrid_search_enabled: bool = True,
        reranker: CrossEncoderReranker | None = None,
        config: KBConfig | None = None,
        graph_store: GraphStore | None = None,
    ):
        self.embedding_provider = embedding_provider
        self.lance_store = lance_store
        self.sql_store = sql_store
        self.cache = cache
        self.hybrid_search_enabled = hybrid_search_enabled
        self.reranker = reranker

        if config is None:
            # Fallback to default config if not provided
            # This ensures self.config is never None (for type checkers)
            from ..config import KBConfig

            config = KBConfig()

        self.config: KBConfig = config
        self.graph_store = graph_store
        self._request_ann_config = None  # Per-request ANN configuration overrides

        # Initialize structured logger
        self.logger = StructuredLogger("kb.api.search_backend", {"component": "KnowledgeSearchBackend"})

        # Initialize graph enricher if graph store is available
        self.graph_enricher = None
        if self.graph_store:
            graph_config = self.config.graph if self.config else GraphConfig()
            self.graph_enricher = GraphContextEnricher(
                graph_store=self.graph_store,
                sql_store=self.sql_store,
                max_related_nodes=graph_config.max_related_nodes,
                max_edges_per_node=graph_config.max_edges_per_node,
            )
        self._bm25_stats_path = self._resolve_bm25_stats_path()
        self._bm25_normalizer: ScoreNormalizer | None = None
        self._bm25_normalizer_metadata: dict[str, Any] = {}
        self._configure_bm25_statistics_collection()

    def _resolve_bm25_stats_path(self) -> Path:
        env_override = os.environ.get("DOLPHIN_BM25_STATS_PATH")
        if env_override:
            return Path(env_override).expanduser()
        if self.config and self.config.retrieval.bm25_normalization.stats_path:
            return Path(self.config.retrieval.bm25_normalization.stats_path).expanduser()
        if self.config:
            return self.config.resolved_store_root() / RETRIEVAL_PARAMS.BM25_NORMALIZATION.stats_filename
        return Path.home() / ".dolphin" / "knowledge_store" / RETRIEVAL_PARAMS.BM25_NORMALIZATION.stats_filename

    def _configure_bm25_statistics_collection(self) -> None:
        if not hasattr(self.sql_store, "configure_bm25_statistics"):
            return
        try:
            self.sql_store.configure_bm25_statistics(self._bm25_stats_path)
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.warning("Failed to enable BM25 statistics collection", error=exc)

    def _load_bm25_stats(self) -> BM25Statistics | None:
        if not self._bm25_stats_path or not self._bm25_stats_path.exists():
            return None
        try:
            stats = BM25Statistics.load(self._bm25_stats_path)
        except Exception as exc:
            self.logger.warning("Unable to load BM25 stats", {"path": str(self._bm25_stats_path)}, error=exc)
            return None
        min_sample = RETRIEVAL_PARAMS.BM25_NORMALIZATION.min_sample_size
        if stats.sample_size < min_sample:
            self.logger.debug(
                "BM25 stats present but below minimum sample size",
                {"sample_size": stats.sample_size, "required": min_sample},
            )
            return None
        return stats

    def _build_bm25_normalizer(self) -> ScoreNormalizer:
        defaults = RETRIEVAL_PARAMS.BM25_NORMALIZATION
        config = self.config.retrieval.bm25_normalization if self.config else None
        forced_strategy = os.environ.get("DOLPHIN_FORCE_BM25_NORMALIZER")
        requested = (forced_strategy or (config.strategy if config else defaults.default_strategy)).lower()
        fallback = (config.fallback_strategy if config else defaults.fallback_strategy).lower()
        probability = config.ab_variant_probability if config else defaults.ab_variant_probability
        stats: BM25Statistics | None = None
        selected = requested
        variant_applied = True
        if not forced_strategy and selected != fallback and 0.0 < probability < 1.0:
            roll = random.random()
            if roll > probability:
                selected = fallback
                variant_applied = False
        if selected in {"min_max", "quantile"}:
            stats = self._load_bm25_stats()
            if not stats:
                self.logger.warning(
                    "BM25 stats unavailable, reverting to fallback",
                    {"requested": selected, "fallback": fallback},
                )
                selected = fallback
        if selected == "min_max" and stats:
            normalizer: ScoreNormalizer = MinMaxNormalizer(stats)
        elif selected == "quantile" and stats:
            normalizer = QuantileNormalizer(stats)
        else:
            normalizer = SigmoidNormalizer(RETRIEVAL_PARAMS.BM25_SCORE_NORMALIZATION_FACTOR)
            selected = "sigmoid"
        self._bm25_normalizer_metadata = {
            "strategy": selected,
            "requested": requested,
            "fallback": fallback,
            "forced": bool(forced_strategy),
            "ab_probability": probability,
            "ab_variant_enabled": variant_applied,
            "stats_path": str(self._bm25_stats_path),
            "stats_sample_size": (stats.sample_size if stats else 0),
        }
        self.logger.debug("BM25 normalizer initialized", self._bm25_normalizer_metadata)
        return normalizer

    def _normalize_bm25_score(self, score: float) -> float:
        if self._bm25_normalizer is None:
            self._bm25_normalizer = self._build_bm25_normalizer()
        try:
            return float(self._bm25_normalizer.normalize(score))
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.warning("BM25 normalization failed, reverting to sigmoid", error=exc)
            self._bm25_normalizer = SigmoidNormalizer(RETRIEVAL_PARAMS.BM25_SCORE_NORMALIZATION_FACTOR)
            return float(self._bm25_normalizer.normalize(score))

    def search(self, request: SearchRequest) -> Sequence[dict[str, object]]:
        # Generate correlation ID for this search request
        correlation_id = f"search_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        # Create child logger with request-specific context
        request_logger = self.logger.create_child({"correlation_id": correlation_id, "method": "search"})

        # Log incoming search request at INFO level for production observability
        request_logger.info(
            "Search request received",
            {
                "query_length": len(request.query),
                "query_preview": request.query[:100],
                "repos": request.repos,
                "path_prefix": request.path_prefix,
                "top_k": request.top_k,
                "score_cutoff": request.score_cutoff,
                "embed_model": self.config.default_embed_model,
            },
        )

        # Check cache first if available
        if self.cache:
            # Create cache key from request parameters
            cache_params = {
                "top_k": request.top_k,
                "score_cutoff": request.score_cutoff,
                "embed_model": self.config.default_embed_model,
                "repos": request.repos,
                "path_prefix": request.path_prefix,
            }
            cached_results = self.cache.get_results(request.query, **cache_params)
            if cached_results is not None:
                request_logger.info(
                    "Search completed (cache hit)",
                    {
                        "results_count": len(cached_results),
                        "cache_hit": True,
                    },
                )
                return cached_results

        query_embedding = self.embedding_provider.embed_texts(self.config.default_embed_model, [request.query])[0]
        num_candidates = request.top_k * RETRIEVAL_PARAMS.CANDIDATE_MULTIPLIER  # Fetch more candidates for reranking

        # Get ANN parameters from config or use defaults
        ann_params = self._get_ann_params(request)

        # Vector search with error handling
        vector_formatted = []
        try:
            vector_results = self.lance_store.query(
                query_embedding,
                model=self.config.default_embed_model,
                top_k=num_candidates,
                ann_params=ann_params,
            )
            vector_formatted = self._format_vector_results(vector_results)
            request_logger.debug("Vector search completed", {"results_count": len(vector_formatted)})
        except Exception as e:
            # Log error but continue with empty vector results
            request_logger.warning("Vector search failed", error=e)

        # BM25 search with error handling
        bm25_hydrated = []
        if self.hybrid_search_enabled and hasattr(self.sql_store, "bm25_search"):
            try:
                repo_filter = request.repos[0] if request.repos else None
                request_logger.debug(
                    "BM25 search started",
                    {
                        "repo": repo_filter,
                        "path_prefix": request.path_prefix,
                    },
                )
                bm25_results = self.sql_store.bm25_search(
                    request.query,
                    repo=repo_filter,
                    path_prefix=request.path_prefix,
                    top_k=num_candidates,
                )
                request_logger.debug(
                    "BM25 search completed",
                    {
                        "raw_results_count": len(bm25_results),
                        "sample_chunk_id": (bm25_results[0].get("chunk_id") if bm25_results else None),
                        "sample_score": (bm25_results[0].get("score") if bm25_results else None),
                    },
                )
                bm25_hydrated = self._hydrate_bm25_results(
                    bm25_results, self.sql_store, self.config.default_embed_model
                )
                request_logger.debug("BM25 results hydrated", {"hydrated_count": len(bm25_hydrated)})
            except Exception as e:
                # Log error but continue with empty BM25 results
                request_logger.warning("BM25 search failed", error=e)

        # Apply request filters and file-type scoring in a single pass for better perf
        vector_filtered = self._filter_and_score_results(vector_formatted, request)
        bm25_filtered = self._filter_and_score_results(bm25_hydrated, request)

        request_logger.debug(
            "Applied request filtering and scoring adjustments",
            {
                "vector_filtered_count": len(vector_filtered),
                "bm25_filtered_count": len(bm25_filtered),
            },
        )

        hits = reciprocal_rank_fusion([vector_filtered, bm25_filtered])

        request_logger.debug("Reciprocal rank fusion completed", {"hits_count": len(hits)})

        # Convert rrf_score to score for all hits
        for hit in hits:
            hit["score"] = hit.pop("rrf_score", 0.0)

        # Log top 3 hits at DEBUG level
        if hits:
            request_logger.debug(
                "Top hits",
                {
                    "top_hits": [
                        {
                            "chunk_id": hit.get("chunk_id"),
                            "score": hit.get("score", 0.0),
                        }
                        for hit in hits[:3]
                    ]
                },
            )

        # UNCOMMENTED AND CORRECTED RERANKING LOGIC
        if self.reranker and hits:
            docs_to_rerank = self._hydrate_docs_for_reranking(hits, self.sql_store)
            reranked_docs = self.reranker.rerank(request.query, docs_to_rerank, top_k=request.top_k)
            # The reranked_docs now have the final score. We need to merge them back
            # while preserving the order and original hits.
            reranked_ids = {doc["chunk_id"] for doc in reranked_docs}
            final_hits = reranked_docs + [h for h in hits if h["chunk_id"] not in reranked_ids]
            hits = final_hits

        # Optional MMR diversification (applied after fusion/reranking, before cutoff/limit)
        # Use request overrides when provided, otherwise fall back to global config.
        try:
            cfg_mmr_enabled = bool(self.config and getattr(self.config.retrieval, "mmr_enabled", False))
            cfg_mmr_lambda = self.config.retrieval.mmr_lambda if self.config else RETRIEVAL_PARAMS.MMR_LAMBDA_DEFAULT
        except Exception:
            cfg_mmr_enabled = False
            cfg_mmr_lambda = RETRIEVAL_PARAMS.MMR_LAMBDA_DEFAULT

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
                    id_field="chunk_id",
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
                request_logger.warning("MMR diversification failed", error=e)

        if hits:
            for h in hits:
                if "vector" in h:
                    h.pop("vector", None)

        request_logger.debug(
            "Applying score cutoff",
            {
                "before_cutoff_count": len(hits),
                "score_cutoff": request.score_cutoff,
            },
        )

        final_results = [h for h in hits if h.get("score", 0.0) >= (request.score_cutoff or 0.0)][: request.top_k]

        if not final_results:
            request_logger.warning(
                "No results after score cutoff",
                {
                    "cutoff_threshold": request.score_cutoff,
                    "hits_before_cutoff": len(hits),
                },
            )
        else:
            request_logger.debug(
                "Results after score cutoff",
                {
                    "results_count": len(final_results),
                    "first_result_score": final_results[0].get("score"),
                },
            )

        # Hydrate content for all final results
        if final_results:
            chunk_ids_needing_content = [
                r["chunk_id"] for r in final_results if "content" not in r or not r.get("content")
            ]
            if chunk_ids_needing_content:
                try:
                    # Use helper to hydrate content
                    hydrated_content = self._hydrate_chunk_content(chunk_ids_needing_content, self.sql_store)

                    # Apply hydrated content to results
                    for result in final_results:
                        chunk_id = result["chunk_id"]
                        if chunk_id in hydrated_content:
                            result["content"] = hydrated_content[chunk_id]
                        elif "content" not in result:
                            # Initialize empty content if not present
                            result["content"] = ""
                        # Also add file_path for compatibility
                        if "path" in result and "file_path" not in result:
                            result["file_path"] = result["path"]
                except Exception as e:
                    # Log error but don't fail the search
                    request_logger.warning("Failed to hydrate content for results", error=e)
            else:
                # Ensure all results have file_path even if no hydration needed
                for result in final_results:
                    if "path" in result and "file_path" not in result:
                        result["file_path"] = result["path"]

        # Enrich with graph context if requested and available
        include_graph = getattr(request, "include_graph_context", False)
        if include_graph and self.graph_enricher:
            try:
                final_results = self.graph_enricher.enrich_search_results(
                    final_results,
                    include_callsites=True,
                    include_implementations=True,
                    include_dependencies=True,
                )
            except Exception as e:
                # Log error but don't fail the search
                request_logger.warning("Graph enrichment failed", error=e)

        # Cache results if cache is available
        if self.cache:
            self.cache.set_results(request.query, list(final_results), **cache_params)

        # Log search completion with summary at INFO level
        duration_ms = (time.time() - start_time) * 1000
        request_logger.info(
            "Search completed",
            {
                "results_count": len(final_results),
                "cache_hit": False,
                "duration_ms": round(duration_ms, 2),
            },
        )

        return final_results

    def _format_vector_results(self, vector_results: list[dict]) -> list[dict[str, object]]:
        formatted = []
        for r in vector_results:
            distance = r.get("_distance", 1.0)
            score = 1 / (1 + distance)
            self.logger.debug(
                "Formatted vector result",
                {
                    "id": r.get("id"),
                    "distance": distance,
                    "score": score,
                },
            )
            result = {**r, "chunk_id": r.get("id"), "score": score}
            formatted.append(result)
        return formatted

    def _filter_and_score_results(
        self, results: list[dict[str, object]], request: SearchRequest
    ) -> list[dict[str, object]]:
        """Apply repo filters, path rules, and file-type scoring in one pass."""

        import fnmatch

        def normalize_path(path_str: str) -> str:
            normalized = (path_str or "").lstrip("./")
            normalized = normalized.lstrip("/")
            normalized = normalized.rstrip("/")
            return normalized

        def matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
            for prefix in prefixes:
                if not prefix:
                    return True
                try:
                    if path == prefix or path.startswith(f"{prefix}/"):
                        return True
                except Exception:
                    # Pure string operations shouldn't raise but keep defensive handling
                    continue
            return False

        def matches_pattern(path: str, basename: str, patterns: tuple[str, ...]) -> bool:
            for pattern in patterns:
                if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(basename, pattern):
                    return True
            return False

        def is_config_file(path: str) -> bool:
            lowered = path.lower()
            return (
                lowered.endswith(".toml")
                or lowered.endswith(".json")
                or lowered.endswith(".yaml")
                or lowered.endswith(".yml")
                or "config.toml" in lowered
                or "package.json" in lowered
                or "tsconfig.json" in lowered
            )

        def apply_penalty(result: dict[str, object]) -> dict[str, object]:
            score_obj = result.get("score", 0.0)
            score = float(score_obj) if isinstance(score_obj, (int, float)) else 0.0
            return {
                **result,
                "score": score * RETRIEVAL_PARAMS.CONFIG_FILE_SCORE_PENALTY,
            }

        repo_filter = set(request.repos) if request.repos else None
        include_prefixes: tuple[str, ...] = (
            tuple(normalize_path(prefix) for prefix in request.path_prefix) if request.path_prefix else tuple()
        )
        exclude_prefixes: tuple[str, ...] = (
            tuple(normalize_path(prefix) for prefix in request.exclude_paths) if request.exclude_paths else tuple()
        )
        exclude_patterns: tuple[str, ...] = tuple(request.exclude_patterns or tuple())

        filtered: list[dict[str, object]] = []

        for result in results:
            repo_name = result.get("repo")
            if repo_filter and repo_name not in repo_filter:
                continue

            raw_path = str(result.get("path", "") or "")
            normalized_path = normalize_path(raw_path)
            basename = normalized_path.rsplit("/", 1)[-1] if normalized_path else ""

            if include_prefixes and not matches_prefix(normalized_path, include_prefixes):
                continue

            if exclude_prefixes and matches_prefix(normalized_path, exclude_prefixes):
                continue

            if exclude_patterns and matches_pattern(normalized_path, basename, exclude_patterns):
                continue

            if is_config_file(raw_path):
                filtered.append(apply_penalty(result))
            else:
                filtered.append(result)

        return filtered

    def _hydrate_bm25_results(
        self, bm25_results: list[dict], sql_store: SQLiteMetadataStore, embed_model: str
    ) -> list[dict[str, object]]:
        """Hydrate BM25 results with full chunk metadata.

        BM25 search returns minimal metadata (content_id, repo, path, score, text_hash).
        We need to fetch full chunk data including line numbers, symbol info, etc.
        from the metadata store for proper result formatting.

        We expand single BM25 hits into multiple results (one per location) with
        LanceDB-compatible row IDs to ensure proper deduplication during fusion.
        """
        if not bm25_results:
            return []

        hydrated = []
        for result in bm25_results:
            chunk_id = result["chunk_id"]
            text_hash = result.get("text_hash")
            repo_name = result["repo"]
            path = result["path"]

            # Normalize BM25 score to [0, 1] range for fusion
            normalized_score = self._normalize_bm25_score(result["score"])

            locations = []
            file_id = None
            repo_id = None

            # Look up locations using text_hash and repo/path
            if text_hash:
                repo_info = sql_store.get_repo_by_name(repo_name)
                if repo_info:
                    repo_id = repo_info["id"]
                    file_id = sql_store.get_file_id(repo_id, path)
                    if file_id:
                        locations = sql_store.get_chunk_locations_by_identity(
                            repo_id, file_id, text_hash, embed_model
                        )

            # If we found locations, create a result for each one
            if locations and repo_id is not None and file_id is not None:
                for loc in locations:
                    start_line = loc.get("start_line")
                    end_line = loc.get("end_line")
                    # Use the actual model from the location, or fallback to requested if missing (should be there now)
                    actual_model = loc.get("embed_model", embed_model)

                    # Generate LanceDB-compatible row ID
                    # Format: {repo_id}:{file_id}:{embed_model}:{text_hash}:{start_line}:{end_line}
                    if start_line is not None and end_line is not None:
                        row_id = f"{repo_id}:{file_id}:{actual_model}:{text_hash}:{start_line}:{end_line}"
                    else:
                        row_id = chunk_id  # Fallback

                    hydrated_result = {
                        "chunk_id": row_id,  # Use row_id for fusion key
                        "repo": repo_name,
                        "path": path,
                        "score": normalized_score,
                        "id": row_id,
                        "text_hash": text_hash,
                        "embed_model": actual_model,
                        # We don't have language here easily without extra query,
                        # but hydration later might fill it if needed.
                        "start_line": start_line,
                        "end_line": end_line,
                        "symbol_kind": loc.get("symbol_kind"),
                        "symbol_name": loc.get("symbol_name"),
                        "symbol_path": loc.get("symbol_path"),
                    }
                    hydrated.append(hydrated_result)
            else:
                # Fallback: try direct lookup by chunk_id (legacy) or just return what we have
                chunk_data = sql_store.get_chunk_by_id(chunk_id)

                hydrated_result = {
                    "chunk_id": chunk_id,
                    "repo": repo_name,
                    "path": path,
                    "score": normalized_score,
                    "id": chunk_id,
                }

                if chunk_data:
                    hydrated_result.update(
                        {
                            "text_hash": chunk_data.get("text_hash"),
                            "embed_model": chunk_data.get("embed_model"),
                            "language": chunk_data.get("language"),
                            "start_line": chunk_data.get("start_line"),
                            "end_line": chunk_data.get("end_line"),
                            "symbol_kind": chunk_data.get("symbol_kind"),
                            "symbol_name": chunk_data.get("symbol_name"),
                            "symbol_path": chunk_data.get("symbol_path"),
                        }
                    )
                else:
                    self.logger.warning(
                        "Failed to hydrate BM25 result in fallback",
                        {
                            "chunk_id": chunk_id,
                            "repo": repo_name,
                            "path": path,
                            "text_hash": text_hash,
                        },
                    )

                hydrated.append(hydrated_result)

        return hydrated

    @staticmethod
    def _parse_fts_content_id(content_id: str) -> tuple[int, int, str] | None:
        """Parse deterministic FTS content IDs (repo_id:file_id:text_hash)."""

        if content_id.count(":") < 2:
            return None

        try:
            repo_id_str, file_id_str, text_hash = content_id.split(":", 2)
            return int(repo_id_str), int(file_id_str), text_hash
        except (ValueError, TypeError):
            return None

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
                parts = row_id.split(":")
                if len(parts) < 4:
                    continue

                repo_id = int(parts[0])
                file_id = int(parts[1])
                embed_model = parts[2]
                text_hash = parts[3]

                # Query metadata store for the content_id
                with self.sql_store._connect() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        SELECT id FROM chunk_content
                        WHERE repo_id = ? AND file_id = ? AND embed_model = ? AND text_hash = ?
                        LIMIT 1
                        """,
                        (repo_id, file_id, embed_model, text_hash),
                    )
                    row = cur.fetchone()
                    if row:
                        content_id = str(row[0])
                        row_id_to_content_id[row_id] = content_id

            except (ValueError, IndexError) as e:
                # Skip malformed row IDs
                self.logger.warning("Failed to parse row_id", {"row_id": row_id, "error": str(e)})
                continue

        return row_id_to_content_id

    def _hydrate_chunk_content(self, chunk_ids: list[str], sql_store: SQLiteMetadataStore) -> dict[str, str]:
        """Hydrate content for chunk IDs.

        Args:
            chunk_ids: List of chunk IDs (can be LanceDB row IDs or FTS content IDs)
            sql_store: Metadata store for content lookup

        Returns:
            Dictionary mapping chunk_id -> content
        """
        from kb.store.sqlite_meta import generate_fts_content_id

        if not chunk_ids:
            return {}

        # Separate LanceDB row IDs from FTS content IDs
        # LanceDB row IDs have format: repo_id:file_id:embed_model:text_hash:start_line:end_line
        # FTS content IDs are 32-character hex strings
        lancedb_row_ids = []
        fts_content_ids = []

        for chunk_id in chunk_ids:
            # Check if this looks like a LanceDB row ID (has multiple colons)
            if chunk_id.count(":") >= 5:
                lancedb_row_ids.append(chunk_id)
            else:
                # Treat as FTS content ID
                fts_content_ids.append(chunk_id)

        result = {}

        # Handle LanceDB row IDs - convert to FTS content_ids for lookup
        if lancedb_row_ids:
            # Parse LanceDB row IDs and generate corresponding FTS content_ids
            lancedb_to_fts = {}
            for row_id in lancedb_row_ids:
                try:
                    parts = row_id.split(":")
                    if len(parts) >= 4:
                        repo_id = int(parts[0])
                        file_id = int(parts[1])
                        # embed_model = parts[2]  # Not needed for FTS lookup
                        text_hash = parts[3]
                        # Generate deterministic FTS content_id
                        fts_content_id = generate_fts_content_id(repo_id, file_id, text_hash)
                        lancedb_to_fts[row_id] = fts_content_id
                except (ValueError, IndexError):
                    # Skip malformed row IDs
                    continue

            if lancedb_to_fts:
                # Fetch content using FTS content_ids
                fts_ids = list(lancedb_to_fts.values())
                contents = sql_store.get_chunk_contents(fts_ids)

                # Map content back to original LanceDB row IDs
                for row_id, fts_id in lancedb_to_fts.items():
                    if fts_id in contents:
                        result[row_id] = contents[fts_id]

        # Handle FTS content IDs (can be used directly)
        if fts_content_ids:
            # These can be used directly with get_chunk_contents
            fts_contents = sql_store.get_chunk_contents(fts_content_ids)
            result.update(fts_contents)

        return result

    def _hydrate_docs_for_reranking(self, hits: list[dict], sql_store: SQLiteMetadataStore) -> list[dict]:
        ids_to_fetch = [h["chunk_id"] for h in hits if "content" not in h]
        if not ids_to_fetch:
            return hits

        # Use helper to hydrate content
        hydrated_content = self._hydrate_chunk_content(ids_to_fetch, sql_store)

        # Apply hydrated content to hits
        for hit in hits:
            chunk_id = hit["chunk_id"]
            if chunk_id in hydrated_content:
                hit["content"] = hydrated_content[chunk_id]

        return hits

    def set_request_ann_config(self, config: dict[str, Any]) -> None:
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
            strategy = self._request_ann_config.get("ann_strategy")
            nprobes = self._request_ann_config.get("ann_nprobes")
            refine_factor = self._request_ann_config.get("ann_refine_factor")

            if strategy == "speed":
                params = ANNParams.for_speed()
            elif strategy == "accuracy":
                params = ANNParams.for_accuracy()
            elif strategy == "development":
                params = ANNParams.for_development()
            elif strategy == "custom" and nprobes and refine_factor:
                params = ANNParams(
                    metric="cosine",
                    nprobes=nprobes,
                    refine_factor=refine_factor,
                    use_index=True,
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
        if hasattr(self.config.retrieval.ann, "strategy") and self.config.retrieval.ann.strategy == "adaptive":
            # Determine query type based on query characteristics
            query_type = self._classify_query_type(request.query)

            # Estimate dataset size for adaptive tuning
            estimated_size = 100000  # Default, could be made configurable
            if hasattr(self.config.retrieval.ann, "adaptive"):
                adaptive_config = self.config.retrieval.ann.adaptive
                if hasattr(adaptive_config, "estimated_dataset_size"):
                    estimated_size = adaptive_config.estimated_dataset_size

            # Cast estimated_size to int with fallback
            dataset_size = int(estimated_size) if isinstance(estimated_size, (int, float)) else 100000
            return ANNParams.adaptive(query_type=query_type, top_k=request.top_k, dataset_size=dataset_size)

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
            "class ",
            "def ",
            "function ",
            "variable ",
            "const ",
            "let ",
            "import ",
            "from ",
            "module ",
            "package ",
            "usercontroller",
            "authenticationflow",
            "main.py",
        ]

        # Example patterns (how-to questions)
        example_patterns = [
            "how to",
            "example",
            "tutorial",
            "how do i",
            "show me",
            "demo",
            "sample code",
            "walkthrough",
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
    config_data = {"storage": {"store_root": store_root}}

    # Initialize embedding section for nested config
    embedding_data = {}

    # Map grouping of provider settings
    # Map embedding_provider_type to embedding_provider (nested under "embedding")
    if "embedding_provider_type" in kwargs:
        embedding_data["provider"] = kwargs["embedding_provider_type"]
    
    # Map default_embed_model if provided (CRITICAL FIX FOR OPTIONS B)
    if "default_embed_model" in kwargs:
         embedding_data["default_embed_model"] = kwargs["default_embed_model"]

    # Map default_embed_model if provided (CRITICAL FIX FOR OPTIONS B)
    if "default_embed_model" in kwargs:
        embedding_data["default_embed_model"] = kwargs["default_embed_model"]

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
            "score_threshold": reranker_data.get("score_threshold", 0.3),
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
        "default_query_type": ann_config.get("default_query_type", "concept"),
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
    sql_store.initialize()  # Ensure DB is initialized with proper schema
    lance_store = LanceDBStore(config.resolved_store_root() / "lancedb")

    # Create embedding provider
    # Note: Only pass cache and redis_url if cache is enabled
    provider_kwargs = {
        "batch_size": config.embedding_batch_size,
    }

    if config.cache_enabled:
        cache_instance = create_cache(
            redis_url=config.redis_url,
            result_ttl=config.result_cache_ttl,
            enabled=config.cache_enabled,
        )
        provider_kwargs["cache"] = cache_instance

    provider = create_provider(config.embedding_provider, **provider_kwargs)

    # Set as global default provider for async convenience functions
    set_default_provider(provider)

    # Create cache (always create but may be disabled)
    cache = create_cache(
        redis_url=config.redis_url if config.cache_enabled else None,
        result_ttl=config.result_cache_ttl,
        enabled=config.cache_enabled,
    )

    # Create reranker if enabled
    reranker = None
    if config.retrieval.reranking.enabled:
        reranker = CrossEncoderReranker(
            model_name=config.retrieval.reranking.model,
            device=config.retrieval.reranking.device,
        )

    # Create graph store
    graph_store = None
    try:
        graph_store = GraphStore(config.resolved_store_root() / "metadata.db")
    except Exception as e:
        # Graph store is optional - no logging needed for expected absence
        print(f"ERROR: GraphStore init failed: {e}", flush=True)
        pass

    # Create and return the search backend
    return KnowledgeSearchBackend(
        embedding_provider=provider,
        lance_store=lance_store,
        sql_store=sql_store,
        cache=cache,
        hybrid_search_enabled=hybrid_search_enabled,
        reranker=reranker,
        config=config,
        graph_store=graph_store,
    )
