from __future__ import annotations

import asyncio
import datetime
import hmac
import logging
import re
import threading
from collections import OrderedDict
from collections.abc import Awaitable, Iterable, Sequence
from inspect import isawaitable, iscoroutinefunction
from pathlib import Path
from time import perf_counter
from typing import Any, NamedTuple, Protocol, cast

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..api_key import load_kb_api_key
from ..config import KBConfig, load_config
from ..constants.retrieval_config import RETRIEVAL_PARAMS
from ..store.sqlite_meta import SQLiteMetadataStore, generate_fts_content_id
from ..utils.tokens import estimate_tokens
from ..version import get_version as _get_pkg_version
from .task_queue import TaskStatus, get_task_queue
from .utils import GitRepository, validate_path_within_repo

_log = logging.getLogger(__name__)

# Constants
# Batch size for metadata hash lookups (distinct from config.embedding_batch_size for the embedding API).
EMBEDDING_BATCH_SIZE = 128
ESTIMATED_TOKENS_PER_CHUNK = RETRIEVAL_PARAMS.ESTIMATED_TOKENS_PER_CHUNK
CHUNK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_:-]+$")

_APP_VERSION = _get_pkg_version(fallback="0.0.0-dev")

app = FastAPI(title="Unified Knowledge Store", version=_APP_VERSION)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()

    unknown_fields: list[str] = []
    for err in errors:
        err_type = str(err.get("type", ""))
        if err_type in {"value_error.extra", "extra_forbidden"}:
            loc = err.get("loc") or ()
            if isinstance(loc, (list, tuple)) and loc:
                field = loc[-1]
                if isinstance(field, str):
                    unknown_fields.append(field)

    remediation = "Fix the request body and try again."
    if unknown_fields:
        uniq = sorted(set(unknown_fields))
        remediation = f"Remove unsupported field(s): {', '.join(uniq)}."

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "invalid_request",
                "message": "Request validation failed.",
                "remediation": remediation,
                "details": errors,
            },
            # Backwards-compatible FastAPI-style detail.
            "detail": errors,
        },
    )


def _load_default_config() -> KBConfig:
    try:
        return load_config()
    except FileNotFoundError:
        _log.info("No config file found; using defaults.")
        return KBConfig()
    except Exception:
        _log.error("Failed to load config; using defaults. Fix config to avoid unexpected behavior.", exc_info=True)
        return KBConfig()


_DEFAULT_CONFIG = _load_default_config()
_API_LIMITS = _DEFAULT_CONFIG.api


# Add CORS middleware for local development clients.
# Note: CORSMiddleware is a class, not a factory function, but FastAPI's add_middleware
# accepts both. We need to help the type checker by explicitly typing this.
app.add_middleware(
    cast(type, CORSMiddleware),
    allow_origins=_API_LIMITS.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Accept"],
)


# API Key Authentication Middleware
@app.middleware("http")
async def validate_api_key(request: Request, call_next):
    """Validate API key for protected endpoints.

    All /v1/ endpoints (except /v1/health) require authentication via X-API-Key header.
    The API key must match the configured KB key, which may come from:
    - DOLPHIN_API_KEY environment variable (primary)
    - DOLPHIN_KB_API_KEY environment variable (legacy / override)
    - Managed key file (~/.dolphin/kb_api_key)
    Health check endpoint (/v1/health) remains public for monitoring.
    """
    # Protect all /v1/ endpoints with API key authentication
    if request.url.path.startswith("/v1/") and request.url.path != "/v1/health":
        api_key = request.headers.get("X-API-Key")
        expected_key = load_kb_api_key()

        if not api_key or not hmac.compare_digest(api_key, expected_key or ""):
            return JSONResponse({"error": "Unauthorized", "detail": "Valid API key required"}, status_code=401)

    return await call_next(request)


# Will be set by server startup.
# Lock guards all writes; reads are unlocked because they only occur on the
# async event loop after startup has completed and stores are stable.
_sql_store = None
_lance_store = None
_pipeline = None
_store_lock = threading.Lock()

# Flips to False on the first cache-invalidation failure so the deep health
# check can surface it without re-running a live invalidation.
_cache_invalidation_healthy: bool = True

# Module-level bounded LRU file-lines cache shared across search requests.
# Keyed by (absolute_path_str, mtime) so file edits produce automatic misses.
# CPython dict ops are GIL-protected so no additional lock is needed here.
_FILE_LINES_CACHE: OrderedDict[tuple[str, float], list[str] | None] = OrderedDict()
_FILE_LINES_CACHE_MAX = 256
_FILE_LINES_CACHE_MISS = object()  # Sentinel to distinguish cached None from cache miss
# Don't cache files larger than this to prevent memory bloat.
_FILE_LINES_MAX_LINES = 50_000


def get_sql_store():
    """Return the current SQL metadata store (or None if not yet initialised)."""
    return _sql_store


def get_lance_store():
    """Return the current LanceDB vector store (or None if not yet initialised)."""
    return _lance_store


def set_stores(sql_store, lance_store):
    """Set the SQL and Lance stores for API endpoints."""
    global _sql_store, _lance_store
    with _store_lock:
        _sql_store = sql_store
        _lance_store = lance_store


def set_pipeline(pipeline):
    """Set the ingestion pipeline for API endpoints."""
    global _pipeline
    with _store_lock:
        _pipeline = pipeline


def get_pipeline():
    """Get the current ingestion pipeline."""
    return _pipeline


def reset_pipeline():
    """Reset the ingestion pipeline to None (for testing)."""
    global _pipeline
    with _store_lock:
        _pipeline = None


def reset_stores():
    """Reset stores to None (for testing)."""
    global _sql_store, _lance_store, _pipeline
    with _store_lock:
        _sql_store = None
        _lance_store = None
        _pipeline = None


def _read_file_lines(full_path: Path) -> list[str] | None:
    """Read file lines using the module-level bounded LRU cache keyed on (path, mtime).

    Returns None on any read error.  The least-recently-used entry is evicted
    when the cache exceeds ``_FILE_LINES_CACHE_MAX`` entries.
    """
    try:
        mtime = full_path.stat().st_mtime
    except OSError:
        return None
    key = (str(full_path), mtime)
    cached = _FILE_LINES_CACHE.get(key, _FILE_LINES_CACHE_MISS)
    if cached is not _FILE_LINES_CACHE_MISS:
        _FILE_LINES_CACHE.move_to_end(key)
        return cached  # type: ignore[return-value]
    # Read line-by-line so we can bail early for huge files without
    # buffering the entire contents into memory via readlines().
    try:
        lines: list[str] = []
        with open(full_path, encoding="utf-8") as fh:
            for line in fh:
                lines.append(line)
                if len(lines) >= _FILE_LINES_MAX_LINES:
                    # Cache None so repeated requests for the same oversized
                    # file are short-circuited without re-reading.
                    _log.debug("File too large to serve: %s (>%d lines)", full_path, _FILE_LINES_MAX_LINES)
                    if len(_FILE_LINES_CACHE) >= _FILE_LINES_CACHE_MAX:
                        _FILE_LINES_CACHE.popitem(last=False)
                    _FILE_LINES_CACHE[key] = None
                    return None
    except (OSError, UnicodeDecodeError):
        return None
    # Cache files within the size limit.
    if len(_FILE_LINES_CACHE) >= _FILE_LINES_CACHE_MAX:
        _FILE_LINES_CACHE.popitem(last=False)
    _FILE_LINES_CACHE[key] = lines
    return lines


def _enrich_hits_with_snippets(
    hits: list[dict[str, object]],
    request: SearchRequest,
    sql_store: SQLiteMetadataStore,
) -> list[dict[str, object]]:
    repo_root_cache: dict[str, Path] = {}

    for hit in hits:
        existing_snippet = hit.get("snippet")
        if isinstance(existing_snippet, dict):
            continue

        repo = hit.get("repo")
        path = hit.get("path")
        start_line = hit.get("start_line")
        end_line = hit.get("end_line")

        if not repo or not path:
            continue
        if not isinstance(start_line, (int, float, str, bytes, bytearray)) or not isinstance(
            end_line, (int, float, str, bytes, bytearray)
        ):
            continue

        repo_name = str(repo)
        path_str = str(path)

        if repo_name not in repo_root_cache:
            repo_info = sql_store.get_repo_by_name(repo_name)
            if not repo_info:
                continue
            repo_root_cache[repo_name] = Path(repo_info["root_path"])

        repo_root = repo_root_cache[repo_name]
        full_path = validate_path_within_repo(repo_root / path_str, repo_root)

        if not full_path.exists() or not full_path.is_file():
            continue

        lines = _read_file_lines(full_path)
        if lines is None:
            continue
        if not lines:
            continue

        total_lines = len(lines)
        try:
            start_int = int(start_line)
            end_int = int(end_line)
        except (TypeError, ValueError):
            continue

        context_before = request.context_lines_before
        context_after = request.context_lines_after

        # Calculate ranges (1-indexed input, converted to 0-indexed slice)
        # Match range
        match_start_idx = max(0, start_int - 1)
        match_end_idx = min(total_lines, end_int)

        # Context ranges
        before_start_idx = max(0, match_start_idx - context_before)
        before_end_idx = match_start_idx

        after_start_idx = match_end_idx
        after_end_idx = min(total_lines, match_end_idx + context_after)

        # Extract content
        text_content = "".join(lines[match_start_idx:match_end_idx])
        before_content = "".join(lines[before_start_idx:before_end_idx])
        after_content = "".join(lines[after_start_idx:after_end_idx])

        # Token estimation via tiktoken (falls back to chars/4 if unavailable).
        combined_text = text_content + before_content + after_content
        max_tokens = request.max_snippet_tokens
        estimated_tokens = estimate_tokens(combined_text)

        truncated = False
        if estimated_tokens > max_tokens:
            truncated = True
            max_chars = int(max_tokens * 4)
            match_chars = len(text_content)

            if match_chars >= max_chars:
                # Match alone exceeds budget: truncate match, drop all context.
                text_content = text_content[:max_chars]
                before_content = ""
                after_content = ""
            else:
                # Match fits; distribute remaining budget to context (context_before
                # gets half, context_after gets the other half, then swap leftover).
                remaining = max_chars - match_chars
                before_budget = remaining // 2
                after_budget = remaining - before_budget

                # context_after: keep lines closest to the match (trim from the end).
                if len(after_content) > after_budget:
                    after_content = after_content[:after_budget]

                # context_before: keep lines closest to the match (trim from the start).
                if len(before_content) > before_budget:
                    before_content = before_content[len(before_content) - before_budget :]

        snippet_obj = {
            "start_line": before_start_idx + 1 if before_content else start_int,
            "end_line": after_end_idx if after_content else end_int,
            "text": text_content,
            "context_before": before_content,
            "context_after": after_content,
            "truncated": truncated,
        }

        hit["snippet"] = snippet_obj
        # Remove flat fields (breaking change as per plan)
        hit.pop("snippet_start_line", None)
        hit.pop("snippet_end_line", None)

    return hits


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    repos: list[str] | None = None
    path_prefix: list[str] | None = None
    exclude_paths: list[str] | None = None
    exclude_patterns: list[str] | None = None
    top_k: int = Field(default=_DEFAULT_CONFIG.retrieval.top_k, ge=1, le=_API_LIMITS.max_top_k)
    max_snippet_tokens: int = Field(
        default=_DEFAULT_CONFIG.retrieval.max_snippet_tokens,
        ge=1,
        le=_API_LIMITS.max_snippet_tokens,
    )
    # embed_model removed: always use global default
    score_cutoff: float | None = _DEFAULT_CONFIG.retrieval.score_cutoff
    mmr_enabled: bool | None = _DEFAULT_CONFIG.retrieval.mmr_enabled
    mmr_lambda: float | None = _DEFAULT_CONFIG.retrieval.mmr_lambda
    ann_strategy: str | None = None
    ann_nprobes: int | None = None
    ann_refine_factor: int | None = None
    # top_k controls total results; max_snippets controls how many hits return a snippet payload.
    max_snippets: int = Field(default=0, ge=0, le=_API_LIMITS.max_top_k)
    # Graph context enrichment (enabled by default for better context)
    include_graph_context: bool = _DEFAULT_CONFIG.api.include_graph_context
    # Leading/trailing line context (disabled by default for backwards compatibility)
    context_lines_before: int = Field(
        default=_DEFAULT_CONFIG.api.context_lines_before,
        ge=0,
        le=_API_LIMITS.max_context_lines,
    )
    context_lines_after: int = Field(
        default=_DEFAULT_CONFIG.api.context_lines_after,
        ge=0,
        le=_API_LIMITS.max_context_lines,
    )
    cursor: str | None = None


class SearchResultSet(NamedTuple):
    """Canonical return type for all search backend calls.

    Using NamedTuple preserves tuple unpacking (``hits, cursor = result``)
    while adding named-field access and eliminating the previous
    tuple/dict/list polymorphism at call sites.
    """

    hits: Sequence[dict[str, object]]
    next_cursor: str | None


class SearchBackend(Protocol):
    """Protocol describing the dependency used to execute searches."""

    def search(self, request: SearchRequest) -> SearchResultSet | Awaitable[SearchResultSet]: ...

    def close(self) -> None: ...


class _EmptySearchBackend:
    """Default backend that returns zero hits until retrieval is implemented."""

    def search(self, request: SearchRequest) -> SearchResultSet:
        _ = request
        return SearchResultSet([], None)

    def close(self) -> None:
        pass


_DEFAULT_BACKEND = _EmptySearchBackend()
_search_backend: SearchBackend = _DEFAULT_BACKEND
# Cache of (backend_instance, search_fn) resolved by set_search_backend().
# The instance check in search() ensures a runtime-replaced backend (e.g. in tests)
# always gets a freshly-resolved callable.
_resolved_search_cache: tuple[SearchBackend, Any] | None = None


def _make_search_fn(backend: SearchBackend):
    """Return an async callable that dispatches a SearchRequest to *backend*.

    The dispatch strategy is resolved once here rather than being re-evaluated on
    every request.
    """
    search_async = getattr(backend, "search_async", None)
    if callable(search_async) and iscoroutinefunction(search_async):
        return search_async

    search_method = backend.search
    if iscoroutinefunction(search_method):
        return search_method

    # Synchronous backend: wrap in asyncio.to_thread and handle the edge case
    # where the sync method itself returns an awaitable.
    async def _sync_wrapper(request):
        result = await asyncio.to_thread(search_method, request)
        if isawaitable(result):
            result = await result
        return result

    return _sync_wrapper


def set_search_backend(backend: SearchBackend | None) -> None:
    """Override the search backend used by the API."""
    global _search_backend, _resolved_search_cache
    _search_backend = backend or _DEFAULT_BACKEND
    _resolved_search_cache = (_search_backend, _make_search_fn(_search_backend))


def get_search_backend() -> SearchBackend:
    """Return the currently configured search backend."""
    return _search_backend


def reset_search_backend() -> None:
    """Restore the default empty backend, closing the previous one if applicable.

    Note: ``close()`` delegates to ``shutdown(wait=True)``, which **blocks**
    until all in-flight search tasks finish.  This is acceptable because
    reset is only called during config reload or test teardown — both
    low-concurrency paths where waiting for completion is preferable to
    leaving orphaned futures.  A concurrent ``search()`` call that captured
    the old backend reference but hasn't yet called ``executor.submit()``
    may raise ``RuntimeError`` after shutdown completes.

    ``_EmptySearchBackend.close()`` is a no-op, so the ``except Exception``
    guard only fires for real backends whose executor shutdown fails.
    """
    old = _search_backend
    set_search_backend(None)
    try:
        old.close()
    except Exception:
        _log.warning("Error closing previous search backend", exc_info=True)


def _invalidate_search_cache(repo_name: str) -> None:
    global _cache_invalidation_healthy
    backend = get_search_backend()
    cache = getattr(backend, "cache", None)
    if not cache:
        return
    try:
        cache.invalidate_repo(repo_name)
    except Exception:  # pragma: no cover - defensive
        _cache_invalidation_healthy = False
        _log.error(
            "Failed to invalidate cache for repo %s — stale results may be served until the next restart",
            repo_name,
            exc_info=True,
        )


def _get_system_stats() -> dict[str, Any]:
    """Gather system resource statistics."""
    stats = {}
    try:
        import resource
        import shutil

        # Disk usage
        config = _load_default_config()
        total, used, free = shutil.disk_usage(config.store_root)
        stats["disk"] = {
            "total_gb": round(total / (2**30), 2),
            "free_gb": round(free / (2**30), 2),
            "percent_free": round((free / total) * 100, 1),
        }

        # Memory usage (RSS)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is in bytes on macOS/BSD and kilobytes on Linux
        import sys

        divisor = (1024 * 1024) if sys.platform == "darwin" else 1024
        stats["memory"] = {"rss_mb": round(usage.ru_maxrss / divisor, 2)}
    except Exception as e:
        import logging

        logging.warning("Failed to collect system stats", exc_info=e)
        stats["error"] = "failed_to_collect"

    return stats


async def health(check: str = Query(default="shallow")) -> dict[str, object]:
    """Health check logic with optional deep checks."""
    if check == "shallow":
        return {"status": "ok"}

    # Deep health check
    checks = {}

    # Check LanceDB
    if _lance_store is not None:
        try:
            # Try to connect
            _lance_store.connect()
            checks["lancedb"] = "ok"
        except Exception:
            _log.warning("LanceDB health check failed.", exc_info=True)
            checks["lancedb"] = "error"
    else:
        checks["lancedb"] = "not_configured"

    # Check embeddings (just verify backend exists)
    backend = get_search_backend()
    if backend and not isinstance(backend, _EmptySearchBackend):
        checks["embeddings"] = "ok"
    else:
        checks["embeddings"] = "not_configured"

    # Cache invalidation health
    checks["cache_invalidation"] = "ok" if _cache_invalidation_healthy else "degraded"

    # System stats
    checks["system"] = _get_system_stats()

    overall = "ok" if _cache_invalidation_healthy else "degraded"
    return {"status": overall, "checks": checks}


async def search(request: SearchRequest) -> dict[str, Any]:
    """Search implementation used by the versioned API."""
    backend = get_search_backend()

    if request.repos and _sql_store is not None:
        found = _sql_store.get_repos_by_names(list(request.repos))
        missing = [r for r in request.repos if r not in found]
        if missing:
            raise HTTPException(status_code=404, detail=f"Repository not found: {', '.join(missing)}")

    # Extract ANN configuration from request if provided
    if hasattr(request, "ann_strategy") and request.ann_strategy:
        # Create temporary config for this request
        temp_config_data = {}
        if request.ann_strategy:
            temp_config_data["ann_strategy"] = request.ann_strategy
        if request.ann_nprobes:
            temp_config_data["ann_nprobes"] = request.ann_nprobes
        if request.ann_refine_factor:
            temp_config_data["ann_refine_factor"] = request.ann_refine_factor

        # Set on backend temporarily if it supports per-request config
        set_config_method = getattr(backend, "set_request_ann_config", None)
        if callable(set_config_method):
            set_config_method(temp_config_data)

    started = perf_counter()
    hits: Iterable[dict[str, object]]
    next_cursor: str | None = None

    cache = _resolved_search_cache
    search_fn = cache[1] if cache is not None and cache[0] is backend else _make_search_fn(backend)
    result = await search_fn(request)

    # Result is always (hits, next_cursor) per Protocol
    hits, next_cursor = result

    hits_list = list(hits)
    latency_ms = int((perf_counter() - started) * 1000)

    snippet_limit = request.max_snippets
    snippet_limit = max(0, min(int(snippet_limit), len(hits_list)))

    if snippet_limit > 0 and _sql_store is not None:
        hits_list[:snippet_limit] = _enrich_hits_with_snippets(hits_list[:snippet_limit], request, _sql_store)

    if snippet_limit < len(hits_list):
        for hit in hits_list[snippet_limit:]:
            hit.pop("snippet", None)
            hit.pop("snippet_start_line", None)
            hit.pop("snippet_end_line", None)
            hit.pop("snippet_tokens", None)
            hit.pop("total_tokens", None)
            hit.pop("truncated", None)

    # Include ANN config in response meta if it was used
    meta = {
        "top_k": request.top_k,
        "model": _DEFAULT_CONFIG.default_embed_model,
        "latency_ms": latency_ms,
        "max_snippet_tokens": request.max_snippet_tokens,
        "max_snippets": snippet_limit,
        "mmr_enabled": request.mmr_enabled,
        "mmr_lambda": request.mmr_lambda,
        "next_cursor": next_cursor,
    }

    if request.ann_strategy:
        meta["ann_strategy"] = request.ann_strategy
        if request.ann_nprobes:
            meta["ann_nprobes"] = request.ann_nprobes
        if request.ann_refine_factor:
            meta["ann_refine_factor"] = request.ann_refine_factor

    if next_cursor:
        meta["next_cursor"] = next_cursor

    # Collect warnings for conditions the caller should know about.
    warnings: list[str] = []
    _backend = get_search_backend()
    _reranker = getattr(_backend, "reranker", None)
    if _reranker is not None and not _reranker.enabled:
        _config = getattr(_backend, "config", None)
        _rerank_cfg = getattr(_config, "reranking", None)
        if _rerank_cfg and getattr(_rerank_cfg, "enabled", False):
            reason = getattr(_reranker, "load_error", None) or "unknown reason"
            warnings.append(f"Reranking is configured but unavailable: {reason}")

    response: dict[str, Any] = {"hits": hits_list, "meta": meta}
    if warnings:
        response["warnings"] = warnings
    return response


async def list_repos() -> dict[str, list[dict[str, object]]]:
    """List all registered repositories with metadata."""
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    try:
        all_repos = _sql_store.list_all_repos()
        all_counts = _sql_store.get_all_repo_counts()
        repos = []
        for repo in all_repos:
            counts = all_counts.get(repo["id"], {"files": 0, "chunks": 0})
            repos.append(
                {
                    "name": repo["name"],
                    "path": repo["root_path"],
                    "default_embed_model": repo["default_embed_model"],
                    "files": counts["files"],
                    "chunks": counts["chunks"],
                }
            )

        return {"repos": repos}

    except Exception as e:
        import logging

        logging.error("Failed to list repositories", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


async def fetch_chunk(chunk_id: str) -> dict[str, object]:
    """Fetch a specific chunk by ID."""
    if _sql_store is None or _lance_store is None:
        raise HTTPException(status_code=503, detail="Stores not initialized")

    # Validate chunk_id to prevent injection and traversal attacks
    if not CHUNK_ID_PATTERN.match(chunk_id):
        raise HTTPException(status_code=400, detail="Invalid chunk_id format")

    try:
        metadata = None
        # Try finding the chunk in either model (small/large) using the store helper
        for model_name in ["small", "large"]:
            found = _lance_store.get_chunk_by_id(chunk_id, model=model_name)
            if found:
                metadata = found
                break

        if not metadata:
            raise HTTPException(status_code=404, detail=f"Chunk not found: {chunk_id}")

        # Fetch content.
        # If we have metadata, we have text_hash, repo, path.
        # We can construct the deterministic FTS content ID.
        content = ""
        text_hash = metadata.get("text_hash")
        repo_name = metadata.get("repo")
        path = metadata.get("path")

        if text_hash and repo_name and path:
            # Get repo_id and file_id
            repo_info = _sql_store.get_repo_by_name(repo_name)
            if repo_info:
                repo_id = repo_info["id"]
                file_id = _sql_store.get_file_id(repo_id, path)
                if file_id:
                    fts_content_id = generate_fts_content_id(repo_id, file_id, text_hash)
                    content_map = _sql_store.get_chunk_contents([fts_content_id])
                    content = content_map.get(fts_content_id, "")

        # Fallback: if content logic above failed (e.g. repo not found), try using chunk_id directly
        if not content:
            content_map = _sql_store.get_chunk_contents([chunk_id])
            content = content_map.get(chunk_id, "")

        return {
            "chunk_id": metadata.get("id"),
            "repo": metadata.get("repo"),
            "path": metadata.get("path"),
            "start_line": metadata.get("start_line"),
            "end_line": metadata.get("end_line"),
            "content": content,
            "lang": metadata.get("language"),
            "text_hash": metadata.get("text_hash"),
            "commit": metadata.get("commit"),
            "branch": metadata.get("branch"),
            "symbol_kind": metadata.get("symbol_kind"),
            "symbol_name": metadata.get("symbol_name"),
            "symbol_path": metadata.get("symbol_path"),
            "token_count": metadata.get("token_count"),
            "resource_link": f"kb://{metadata.get('repo')}/{metadata.get('path')}#L{metadata.get('start_line')}-L{metadata.get('end_line')}",
        }

    except HTTPException:
        raise
    except Exception as e:
        import logging

        logging.error(f"Error fetching chunk {chunk_id}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching chunk: {str(e)}")


async def fetch_file_slice(
    repo: str = Query(..., description="Repository name"),
    path: str = Query(..., description="File path relative to repo root"),
    start: int = Query(1, description="Start line (1-indexed, inclusive)"),
    end: int = Query(..., description="End line (1-indexed, inclusive)"),
) -> dict[str, object]:
    """Fetch a slice of a file by line range."""
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    if start > end:
        raise HTTPException(status_code=400, detail=f"Invalid range: start ({start}) > end ({end})")

    try:
        # Get repo info
        repo_info = _sql_store.get_repo_by_name(repo)
        if not repo_info:
            raise HTTPException(status_code=404, detail=f"Repository not found: {repo}")

        # Build full file path
        repo_root = Path(repo_info["root_path"])
        full_path = repo_root / path

        # Security check: ensure path is within repo
        full_path = validate_path_within_repo(full_path, repo_root)

        # Check file exists
        if not full_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {path}")

        if not full_path.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {path}")

        # Detect language from file extension
        from ..chunkers.registry import detect_language_from_extension

        lang = detect_language_from_extension(Path(path)) or "text"

        # Read file and extract lines
        try:
            with open(full_path, encoding="utf-8") as f:
                all_lines = f.readlines()

            # Convert to 0-indexed
            start_idx = max(0, start - 1)
            end_idx = min(len(all_lines), end)

            if start_idx >= len(all_lines):
                selected_lines = []
            else:
                selected_lines = all_lines[start_idx:end_idx]

            # Join lines
            content = "".join(selected_lines)

            return {
                "repo": repo,
                "path": path,
                "start_line": start,
                "end_line": end,
                "content": content,
                "lang": lang,
                "source": "disk",
                "total_lines": len(all_lines),
            }

        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="File is not valid UTF-8")

    except HTTPException:
        raise
    except Exception as e:
        import logging

        logging.error(f"Error reading file: {full_path}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


class RegisterRepoRequest(BaseModel):
    name: str
    path: str
    default_embed_model: str = "large"


class RegisterRepoResponse(BaseModel):
    repo_id: int
    name: str
    path: str
    message: str = ""


class IndexRequest(BaseModel):
    repo: str
    files: list[str]
    incremental: bool = True


class IndexResponse(BaseModel):
    task_id: str
    status: str
    message: str = ""


class IndexStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    total: int
    indexed: int = 0
    skipped: int = 0
    current_file: str | None = None  # Currently processing file path
    error: str | None = None
    result: dict | None = None


class RepoStatsResponse(BaseModel):
    """Repository statistics for cost estimation and UI display."""

    name: str
    path: str
    files_count: int
    chunks_count: int
    total_tokens: int
    embed_model: str
    last_indexed: str | None = None
    needs_reindex: bool = False


class ReindexRequest(BaseModel):
    """Request to trigger a full or incremental reindex."""

    mode: str = "incremental"  # "full" or "incremental"
    confirmed: bool = False
    clear_existing: bool = False


class ReindexResponse(BaseModel):
    """Response from reindex trigger."""

    task_id: str
    mode: str
    message: str


# =====================
# File Sync Models
# =====================


class FileChange(BaseModel):
    """Individual file change."""

    file_path: str
    change_type: str
    old_path: str | None = None


class PendingChangeRequest(BaseModel):
    """Request to record pending file changes."""

    changes: list[FileChange]


class PendingChangeResponse(BaseModel):
    """Response from recording pending changes."""

    recorded: int
    message: str


class PendingChangesListResponse(BaseModel):
    """Response with list of pending changes."""

    changes: list[dict[str, object]]
    total: int


class MarkProcessedRequest(BaseModel):
    """Request to mark changes as processed."""

    change_ids: list[int]


class MarkProcessedResponse(BaseModel):
    """Response from marking changes as processed."""

    processed: int
    message: str


class DriftDetectionResponse(BaseModel):
    """Response from drift detection."""

    drift_events: list[dict[str, object]]
    total: int


async def process_index_task(task_id: str, repo_name: str, files: list[str]) -> None:
    """Background task to process file indexing."""
    import asyncio

    task_queue = get_task_queue()
    session_id: int | None = None

    try:
        # Update task to processing
        await task_queue.update_task(task_id, status=TaskStatus.PROCESSING)

        if _sql_store is None or _lance_store is None:
            raise RuntimeError("Stores not initialized")

        # Get repo
        repo = _sql_store.get_repo_by_name(repo_name)
        if not repo:
            raise ValueError(f"Repository '{repo_name}' not found")

        repo_id = int(repo["id"])
        root = Path(repo["root_path"])
        embed_model = repo.get("default_embed_model", "large")

        _invalidate_search_cache(repo_name)

        # Filter files that actually exist
        valid_files = []
        for filepath in files:
            full_path = root / filepath

            # Security check: ensure path is within repo
            try:
                validate_path_within_repo(full_path, root)
            except HTTPException:
                continue  # Skip files outside repo

            if full_path.exists() and full_path.is_file():
                valid_files.append(filepath)

        if not valid_files:
            await task_queue.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                result={
                    "indexed": 0,
                    "skipped": len(files),
                    "message": "No valid files to index",
                },
            )
            return

        # Process files
        from ..chunkers.registry import chunk_file as chunk_file_with_config, detect_language_from_extension
        from ..chunkers.repo_config import load_repo_chunking_config
        from ..embeddings.provider import embed_texts_with_retry
        from ..hashing import hash_text
        from ..ingest._helpers import build_desired_map, representative_text_for_hash
        from ..ingest.dedup import ChunkDeduplicator

        # Get commit info for provenance
        git_repo = GitRepository(root)
        commit_sha, branch = git_repo.get_commit_and_branch()

        # Start session
        from ..store.sqlite_meta import ActiveSessionError

        try:
            session_id = _sql_store.begin_session(repo_id, commit_sha, branch, embed_model)
        except ActiveSessionError as exc:
            await task_queue.update_task(
                task_id,
                status=TaskStatus.FAILED,
                error=str(exc),
            )
            return

        chunks_indexed = chunks_skipped = 0
        repo_config = load_repo_chunking_config(root)

        # Track initial snapshots for post-index validation (Phase 3)
        import hashlib

        initial_snapshots = {}

        for idx, filepath in enumerate(valid_files, 1):
            # Update progress with current file and yield to event loop
            await task_queue.update_task(task_id, progress=idx, current_file=filepath)
            await asyncio.sleep(0)  # Yield to event loop to handle status requests

            file_path = root / filepath

            # Capture initial snapshot before processing (Phase 3)
            try:
                stat = file_path.stat()
                file_bytes = file_path.read_bytes()
                initial_snapshots[filepath] = {
                    "mtime_ns": stat.st_mtime_ns,
                    "size_bytes": stat.st_size,
                    "content_hash": hashlib.sha256(file_bytes).hexdigest(),
                }
            except Exception:
                continue  # Skip file if we can't read it

            # Resolve or upsert file_id
            file_id = _sql_store.upsert_file(
                repo_id=repo_id,
                path=filepath,
                ext=file_path.suffix,
                language=None,  # Will be detected by chunker
                is_binary=False,
                size_bytes=file_path.stat().st_size,
            )

            # Determine language and chunk the file
            language = detect_language_from_extension(file_path) or "text"
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            chunks = chunk_file_with_config(
                abs_path=file_path,
                rel_path=filepath,
                language=language,
                text=text,
                repo_config=repo_config,
                model=embed_model,
            )

            import logging

            logger = logging.getLogger(__name__)

            # Compute text_hash for each chunk
            for chunk in chunks:
                chunk.text_hash = hash_text(chunk.text)

            # Build desired map
            desired = build_desired_map(chunks)
            desired_row_ids: set[str] = set()

            # Deduplicate by text_hash
            chunk_deduplicator = ChunkDeduplicator(_sql_store)
            changed_chunks, unchanged_chunks = chunk_deduplicator.filter_unchanged_chunks(
                chunks, repo_id, file_id, embed_model
            )
            new_hashes = {c.text_hash for c in changed_chunks}
            skipped_occurrences = len(unchanged_chunks)
            logger.debug(
                f"File {filepath}: {len(changed_chunks)} changed, "
                f"{len(unchanged_chunks)} unchanged, {len(new_hashes)} new hashes"
            )

            # Embed only new hashes (batched to avoid redundant requests)
            text_hash_to_embedding: dict = {}

            # For unchanged chunks, we need to recover their vectors from LanceDB
            # to prevent them from being lost when row IDs change (due to location changes)
            if unchanged_chunks:
                unchanged_hashes = {c.text_hash for c in unchanged_chunks}
                try:
                    existing_vectors = _lance_store.get_vectors_by_hashes(
                        repo_name, unchanged_hashes, model=embed_model
                    )
                    text_hash_to_embedding.update(existing_vectors)
                except Exception as e:
                    logger.warning(f"Failed to recover vectors for unchanged chunks: {e}")

            if new_hashes:
                hashes_list = sorted(new_hashes)
                for i in range(0, len(hashes_list), EMBEDDING_BATCH_SIZE):
                    batch_hashes = hashes_list[i : i + EMBEDDING_BATCH_SIZE]
                    texts_to_embed = [representative_text_for_hash(h, chunks) for h in batch_hashes]
                    if not texts_to_embed:
                        continue
                    vectors = embed_texts_with_retry(embed_model, texts_to_embed)
                    text_hash_to_embedding.update(dict(zip(batch_hashes, vectors)))
                    # Yield to event loop after each batch to handle status requests
                    await asyncio.sleep(0)

            # Upsert metadata and locations
            mapping = _sql_store.ensure_content_rows_for_file(repo_id, file_id, embed_model, list(desired.keys()))
            for h, occs in desired.items():
                cid = mapping.get(h)
                if cid:
                    _sql_store.sync_locations_for_content_row(cid, occs)

            _sql_store.prune_invalidated_content_for_file(repo_id, file_id, embed_model, set(desired.keys()))

            # Build quick lookups for token_count and chunk text by hash
            occ_token_counts = {(ch.start_line, ch.end_line): getattr(ch, "token_count", 0) for ch in chunks}
            hash_to_text: dict[str, str] = {ch.text_hash: ch.text for ch in chunks}

            # Persist vectors to LanceDB and prepare FTS5 chunks
            payload = []
            fts_chunks = []
            for h, occs in desired.items():
                content_id = mapping.get(h)
                vec = text_hash_to_embedding.get(h)

                # Prepare chunk for FTS5 indexing (once per hash, independent of vector status)
                # FTS5 is for BM25 text search and should work even without embeddings
                if content_id:
                    chunk_text = hash_to_text.get(h)

                    if chunk_text:
                        # Generate deterministic FTS5 content_id (independent of embed_model)
                        fts_content_id = generate_fts_content_id(repo_id, file_id, h)

                        fts_chunks.append(
                            {
                                "content_id": fts_content_id,
                                "repo": repo_name,
                                "path": filepath,
                                "text_hash": h,
                                "content": chunk_text,
                                "symbol_name": (occs[0].get("symbol_name") if occs else None),
                                "symbol_path": (occs[0].get("symbol_path") if occs else None),
                            }
                        )

                # Build LanceDB payload for chunks with vectors
                for idx_occ, occ in enumerate(occs):
                    row_id = f"{repo_id}:{file_id}:{embed_model}:{h}:{occ['start_line']}:{occ['end_line']}"
                    desired_row_ids.add(row_id)
                    if vec is None:
                        continue  # unchanged hash, skip vector storage
                    payload.append(
                        {
                            "id": row_id,
                            "vector": vec,
                            "repo": repo_name,
                            "path": filepath,
                            "start_line": occ["start_line"],
                            "end_line": occ["end_line"],
                            "text_hash": h,
                            "commit": commit_sha,
                            "branch": branch,
                            "embed_model": embed_model,
                            "language": language,
                            "symbol_kind": occ.get("symbol_kind"),
                            "symbol_name": occ.get("symbol_name"),
                            "symbol_path": occ.get("symbol_path"),
                            "heading_h1": occ.get("heading_h1"),
                            "heading_h2": occ.get("heading_h2"),
                            "heading_h3": occ.get("heading_h3"),
                            "token_count": occ_token_counts.get((occ["start_line"], occ["end_line"]), 0),
                            "created_at": datetime.datetime.now(datetime.UTC),
                        }
                    )

            if payload:
                _lance_store.upsert_chunks(repo_name, payload, model=embed_model)

            # Index chunks in FTS5 for BM25 search
            if fts_chunks:
                _sql_store.bulk_index_chunks_for_fts(fts_chunks)

            # Prune any stale vectors for this file/model
            if desired_row_ids:
                _lance_store.prune_file_rows(repo_name, filepath, model=embed_model, keep_ids=desired_row_ids)
            else:
                _lance_store.prune_file_rows(repo_name, filepath, model=embed_model)

            # Update counters and task progress
            chunks_indexed += len(new_hashes)
            chunks_skipped += skipped_occurrences

            # Save file snapshot after successful indexing (Phase 3)
            snapshot = initial_snapshots.get(filepath)
            if snapshot:
                _sql_store.upsert_file_snapshot(
                    file_id=file_id,
                    repo_id=repo_id,
                    path=filepath,
                    mtime_ns=snapshot["mtime_ns"],
                    size_bytes=snapshot["size_bytes"],
                    content_hash=snapshot["content_hash"],
                )

            # Automatically mark pending changes for this file as processed
            # This file has been successfully indexed, so any pending changes
            # that triggered the indexing are now resolved
            _sql_store.mark_changes_for_file_processed(repo_id=repo_id, file_path=filepath)

            # Update task with current indexed/skipped counts
            await task_queue.update_task(task_id, indexed=chunks_indexed, skipped=chunks_skipped)

        # Update session
        _sql_store.bump_session_counters(
            session_id,
            files_indexed=len(valid_files),
            chunks_indexed=chunks_indexed,
            chunks_skipped=chunks_skipped,
            vectors_written=chunks_indexed,
            chunks_pruned=0,
        )
        _sql_store.set_session_status(session_id, "succeeded")

        # Post-index validation: detect mid-index changes (Phase 3)
        changed_files = []
        for filepath, initial_snapshot in initial_snapshots.items():
            file_path = root / filepath
            try:
                if not file_path.exists():
                    # File was deleted during indexing
                    changed_files.append((filepath, "deleted"))
                    continue

                # Check if file changed during indexing
                stat = file_path.stat()
                current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

                if (
                    stat.st_mtime_ns != initial_snapshot["mtime_ns"]
                    or stat.st_size != initial_snapshot["size_bytes"]
                    or current_hash != initial_snapshot["content_hash"]
                ):
                    changed_files.append((filepath, "modified"))
            except Exception:
                # Error reading file, skip validation
                pass

        # Queue changed files as pending changes
        if changed_files:
            for filepath, change_type in changed_files:
                try:
                    _sql_store.record_pending_change(repo_id=repo_id, file_path=filepath, change_type=change_type)
                except Exception:
                    pass  # Continue even if recording fails

        # Mark task complete
        result_message = f"Indexed {len(valid_files)} files: {chunks_indexed} new chunks, {chunks_skipped} skipped"
        if changed_files:
            result_message += f" (Warning: {len(changed_files)} files changed during indexing and were re-queued)"

        await task_queue.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            current_file=None,  # Clear current file on completion
            result={
                "indexed": chunks_indexed,
                "skipped": chunks_skipped,
                "files_processed": len(valid_files),
                "mid_index_changes": len(changed_files),
                "message": result_message,
            },
        )

    except Exception as e:
        import traceback

        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        if session_id is not None:
            _sql_store.set_session_status(session_id, "failed", notes=str(e))
        await task_queue.update_task(task_id, status=TaskStatus.FAILED, error=error_msg)


async def _process_full_reindex_task(
    task_id: str, repo_name: str, files: list[str], clear_existing: bool = False
) -> None:
    """Background task for full reindex with optional index clearing."""
    import logging

    logger = logging.getLogger(__name__)
    task_queue = get_task_queue()

    try:
        # Update task to processing
        await task_queue.update_task(task_id, status=TaskStatus.PROCESSING)

        logger.info(
            f"[Full Reindex Task] Starting for {repo_name} with {len(files)} files (clear_existing={clear_existing})"
        )

        # Stores are validated in the endpoint handler before queuing the task
        # If clear_existing is True, we need pipeline (also validated in handler)
        if clear_existing:
            if _sql_store is None or _pipeline is None:
                raise RuntimeError("Stores not initialized for index clearing")

            # Get repo
            repo = _sql_store.get_repo_by_name(repo_name)
            if not repo:
                raise ValueError(f"Repository '{repo_name}' not found")

            repo_id = int(repo["id"])

            logger.info(f"[Full Reindex Task] Clearing existing index for {repo_name} (repo_id={repo_id})")
            # Clear existing index
            _pipeline._drop_repo_index(repo_id, repo_name)
            logger.info("[Full Reindex Task] Index cleared successfully")

        logger.info(f"[Full Reindex Task] About to process {len(files)} files for {repo_name}")
        # Now process all files using standard indexing
        await process_index_task(task_id, repo_name, files)
        logger.info("[Full Reindex Task] Completed processing")

    except Exception as e:
        import traceback

        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        await task_queue.update_task(task_id, status=TaskStatus.FAILED, error=error_msg)


# ---------------------------------------------------------------------------
# Register route modules
# ---------------------------------------------------------------------------
from .routes import files_router, health_router, repos_router, search_router, tasks_router  # noqa: E402

app.include_router(health_router)
app.include_router(search_router)
app.include_router(repos_router)
app.include_router(files_router)
app.include_router(tasks_router)


def main() -> None:
    import uvicorn

    uvicorn.run("kb.api.app:app", host="127.0.0.1", port=7777, reload=False)


if __name__ == "__main__":
    main()
