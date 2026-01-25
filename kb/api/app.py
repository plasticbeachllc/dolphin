from __future__ import annotations

import datetime
import re
from collections.abc import Awaitable, Iterable, Sequence
from inspect import isawaitable
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol, cast

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..api_key import load_kb_api_key
from ..config import KBConfig, load_config
from ..store.sqlite_meta import SQLiteMetadataStore, generate_fts_content_id
from .task_queue import TaskStatus, get_task_queue
from .utils import GitRepository, validate_path_within_repo

# Constants
EMBEDDING_BATCH_SIZE = 128
ESTIMATED_TOKENS_PER_CHUNK = 200
CHUNK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_:-]+$")

app = FastAPI(title="Unified Knowledge Store", version="0.2.0")


def _load_default_config() -> KBConfig:
    try:
        return load_config()
    except Exception:
        return KBConfig()


_DEFAULT_CONFIG = _load_default_config()
_API_LIMITS = _DEFAULT_CONFIG.api

# Add CORS middleware to allow requests from VSCode webviews
# Note: CORSMiddleware is a class, not a factory function, but FastAPI's add_middleware
# accepts both. We need to help the type checker by explicitly typing this.
app.add_middleware(
    cast(type, CORSMiddleware),
    allow_origins=[
        "vscode-webview://*",
        "http://localhost:3000",  # Development only
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

        if not api_key or api_key != expected_key:
            return JSONResponse({"error": "Unauthorized", "detail": "Valid API key required"}, status_code=401)

    return await call_next(request)


# Will be set by server startup
_sql_store = None
_lance_store = None
_pipeline = None


def set_stores(sql_store, lance_store):
    """Set the SQL and Lance stores for API endpoints."""
    global _sql_store, _lance_store
    _sql_store = sql_store
    _lance_store = lance_store


def set_pipeline(pipeline):
    """Set the ingestion pipeline for API endpoints."""
    global _pipeline
    _pipeline = pipeline


def get_pipeline():
    """Get the current ingestion pipeline."""
    return _pipeline


def reset_pipeline():
    """Reset the ingestion pipeline to None (for testing)."""
    global _pipeline
    _pipeline = None


def reset_stores():
    """Reset stores to None (for testing)."""
    global _sql_store, _lance_store, _pipeline
    _sql_store = None
    _lance_store = None
    _pipeline = None


def _enrich_hits_with_snippets(
    hits: list[dict[str, object]],
    request: SearchRequest,
    sql_store: SQLiteMetadataStore,
) -> list[dict[str, object]]:
    repo_root_cache: dict[str, Path] = {}
    file_lines_cache: dict[tuple[str, str], list[str]] = {}

    for hit in hits:
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

        cache_key = (repo_name, path_str)
        if cache_key not in file_lines_cache:
            try:
                with open(full_path, encoding="utf-8") as fh:
                    file_lines_cache[cache_key] = fh.readlines()
            except UnicodeDecodeError:
                continue

        lines = file_lines_cache.get(cache_key, [])
        if not lines:
            continue

        total_lines = len(lines)
        try:
            start_int = int(start_line)
            end_int = int(end_line)
        except (TypeError, ValueError):
            continue
        context_before = request.context_lines_before or 0
        context_after = request.context_lines_after or 0

        snippet_start = max(1, start_int - context_before)
        snippet_end = min(total_lines, end_int + context_after)

        snippet = "".join(lines[snippet_start - 1 : snippet_end])
        hit["snippet"] = snippet
        hit["snippet_start_line"] = snippet_start
        hit["snippet_end_line"] = snippet_end

    return hits


class SearchRequest(BaseModel):
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
    include_snippets: bool = False
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


class SearchBackend(Protocol):
    """Protocol describing the dependency used to execute searches."""

    def search(
        self, request: SearchRequest
    ) -> Sequence[dict[str, object]] | Awaitable[Sequence[dict[str, object]]]: ...


class _EmptySearchBackend:
    """Default backend that returns zero hits until retrieval is implemented."""

    def search(self, request: SearchRequest) -> Sequence[dict[str, object]] | Awaitable[Sequence[dict[str, object]]]:
        _ = request
        return ()


_DEFAULT_BACKEND = _EmptySearchBackend()
_search_backend: SearchBackend = _DEFAULT_BACKEND


def set_search_backend(backend: SearchBackend | None) -> None:
    """Override the search backend used by the API."""
    global _search_backend
    _search_backend = backend or _DEFAULT_BACKEND


def get_search_backend() -> SearchBackend:
    """Return the currently configured search backend."""
    return _search_backend


def reset_search_backend() -> None:
    """Restore the default empty backend."""
    set_search_backend(None)


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
            "percent_free": round((free / total) * 100, 1)
        }

        # Memory usage (RSS)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        stats["memory"] = {
            "rss_mb": round(usage.ru_maxrss / 1024 / 1024, 2)  # Mac returns bytes, Linux returns kb.
            # Actually on Mac ru_maxrss is in bytes, on Linux it is in kilobytes.
            # Wait, python docs say: "ru_maxrss is in kilobytes on Linux... and bytes on OS X"
            # We are on Mac. So div by 1024*1024 for MB.
        }
    except Exception:
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
            checks["lancedb"] = "error"
    else:
        checks["lancedb"] = "not_configured"

    # Check embeddings (just verify backend exists)
    backend = get_search_backend()
    if backend and not isinstance(backend, _EmptySearchBackend):
        checks["embeddings"] = "ok"
    else:
        checks["embeddings"] = "not_configured"

        checks["embeddings"] = "not_configured"

    # System stats
    checks["system"] = _get_system_stats()

    return {"status": "ok", "checks": checks}


@app.get("/v1/health")
async def health_v1(check: str = Query(default="shallow")) -> dict[str, object]:
    """Health check endpoint (v1)."""
    return await health(check)


async def search(request: SearchRequest) -> dict[str, Any]:
    """Search implementation used by the versioned API."""
    backend = get_search_backend()

    if request.repos and _sql_store is not None:
        missing = [repo for repo in request.repos if not _sql_store.get_repo_by_name(repo)]
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
    raw_hits = backend.search(request)
    hits: Iterable[dict[str, object]]
    if isawaitable(raw_hits):
        hits = await raw_hits
    else:
        hits = raw_hits
    hits_list = list(hits)
    latency_ms = int((perf_counter() - started) * 1000)

    if request.include_snippets and _sql_store is not None:
        hits_list = _enrich_hits_with_snippets(hits_list, request, _sql_store)

    # Include ANN config in response meta if it was used
    meta = {
        "top_k": request.top_k,
        "model": _DEFAULT_CONFIG.default_embed_model,
        "latency_ms": latency_ms,
        "max_snippet_tokens": request.max_snippet_tokens,
        "mmr_enabled": request.mmr_enabled,
        "mmr_lambda": request.mmr_lambda,
    }

    if request.ann_strategy:
        meta["ann_strategy"] = request.ann_strategy
        if request.ann_nprobes:
            meta["ann_nprobes"] = request.ann_nprobes
        if request.ann_refine_factor:
            meta["ann_refine_factor"] = request.ann_refine_factor

    return {
        "hits": hits_list,
        "meta": meta,
    }


@app.post("/v1/search")
async def search_v1(request: SearchRequest) -> dict[str, object]:
    """Dispatch the search request to the configured backend (v1)."""
    return await search(request)


async def list_repos() -> dict[str, list[dict[str, object]]]:
    """List all registered repositories with metadata."""
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Query all repos from SQL store
    try:
        from contextlib import closing

        repos = []
        with _sql_store._connect() as conn, closing(conn.cursor()) as cur:
            # Get all repos
            cur.execute("SELECT id, name, root_path, default_embed_model FROM repos")
            repo_rows = cur.fetchall()

            for repo_row in repo_rows:
                repo_id, name, root_path, default_model = repo_row

                # Count files for this repo
                cur.execute("SELECT COUNT(*) FROM files WHERE repo_id = ?", (repo_id,))
                file_count = cur.fetchone()[0]

                # Count chunks for this repo
                cur.execute("SELECT COUNT(*) FROM chunk_content WHERE repo_id = ?", (repo_id,))
                chunk_count = cur.fetchone()[0]

                repos.append(
                    {
                        "name": name,
                        "path": root_path,
                        "default_embed_model": default_model,
                        "files": file_count,
                        "chunks": chunk_count,
                    }
                )

        return {"repos": repos}

    except Exception as e:
        import logging

        logging.error("Failed to list repositories", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/v1/repos")
async def list_repos_v1() -> dict[str, list[dict[str, object]]]:
    """List all registered repositories with metadata (v1)."""
    return await list_repos()


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


@app.get("/v1/chunks/{chunk_id}")
async def fetch_chunk_v1(chunk_id: str) -> dict[str, object]:
    """Fetch a specific chunk by ID (v1)."""
    return await fetch_chunk(chunk_id)


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


@app.get("/v1/file")
async def fetch_file_slice_v1(
    repo: str = Query(..., description="Repository name"),
    path: str = Query(..., description="File path relative to repo root"),
    start: int = Query(1, description="Start line (1-indexed, inclusive)"),
    end: int = Query(..., description="End line (1-indexed, inclusive)"),
) -> dict[str, object]:
    """Fetch a slice of a file by line range (v1)."""
    return await fetch_file_slice(repo=repo, path=path, start=start, end=end)


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


@app.post("/v1/repos")
async def register_repo(request: RegisterRepoRequest) -> RegisterRepoResponse:
    """Register a new repository for indexing.

    This creates a repository entry in the metadata store, allowing it to be indexed.
    """
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Check if repo already exists
    existing = _sql_store.get_repo_by_name(request.name)
    if existing:
        return RegisterRepoResponse(
            repo_id=existing["id"],
            name=request.name,
            path=existing["root_path"],
            message=f"Repository '{request.name}' already registered",
        )

    # Validate path exists
    repo_path = Path(request.path)
    if not repo_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {request.path}")

    if not repo_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {request.path}")

    # Register the repository
    try:
        # Resolve and normalize path (macOS /var -> /private/var handling)
        resolved_path = repo_path.resolve()

        _sql_store.record_repo(
            name=request.name,
            path=resolved_path,
            default_embed_model=request.default_embed_model,
        )

        # Get the registered repo to retrieve its ID
        repo = _sql_store.get_repo_by_name(request.name)
        if not repo:
            raise HTTPException(status_code=500, detail="Failed to retrieve registered repository")

        # Return normalized path from database to ensure consistency
        return RegisterRepoResponse(
            repo_id=repo["id"],
            name=request.name,
            path=repo["root_path"],
            message=f"Repository '{request.name}' registered successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register repository: {str(e)}")


@app.post("/v1/admin/reload")
async def admin_reload_backend() -> dict[str, str]:
    """Reload the search backend and store connections.

    This is used by the indexing CLI to notify the server that the index has changed.
    """
    # Import here to avoid circular dependency with server.py
    # server.py imports app.py, so app.py cannot import server.py at top level
    try:
        from .server import reload_search_backend

        reload_search_backend()
        return {"status": "ok", "message": "Search backend reloaded"}
    except Exception as e:
        import logging

        logging.error("Failed to reload backend", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Reload failed: {str(e)}")


@app.post("/v1/admin/rebuild-fts5")
async def rebuild_fts5() -> dict[str, str]:
    """Rebuild the FTS5 table with updated schema.

    This drops and recreates the FTS5 table. After calling this endpoint,
    you should trigger a full re-index to populate the FTS5 table with
    the new deterministic content_ids.
    """
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    try:
        _sql_store.rebuild_fts5_table()
        return {
            "status": "success",
            "message": "FTS5 table rebuilt successfully. Please trigger a re-index to populate it.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild FTS5 table: {str(e)}")


async def _process_index_task(task_id: str, repo_name: str, files: list[str]) -> None:
    """Background task to process file indexing."""
    import asyncio

    task_queue = get_task_queue()

    try:
        # Update task to processing
        await task_queue.update_task(task_id, status=TaskStatus.PROCESSING)

        if _sql_store is None or _lance_store is None:
            raise Exception("Stores not initialized")

        # Get repo
        repo = _sql_store.get_repo_by_name(repo_name)
        if not repo:
            raise Exception(f"Repository '{repo_name}' not found")

        repo_id = int(repo["id"])
        root = Path(repo["root_path"])
        embed_model = repo.get("default_embed_model", "large")

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
        session_id = _sql_store.begin_session(repo_id, commit_sha, branch, embed_model)

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

            # Build token count lookup
            occ_token_counts = {(ch.start_line, ch.end_line): getattr(ch, "token_count", 0) for ch in chunks}

            # Persist vectors to LanceDB and prepare FTS5 chunks
            payload = []
            fts_chunks = []
            for h, occs in desired.items():
                content_id = mapping.get(h)
                vec = text_hash_to_embedding.get(h)

                # Prepare chunk for FTS5 indexing (once per hash, independent of vector status)
                # FTS5 is for BM25 text search and should work even without embeddings
                if content_id:
                    chunk_text = None
                    for chunk in chunks:
                        if chunk.text_hash == h:
                            chunk_text = chunk.text
                            break

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
        await task_queue.update_task(task_id, status=TaskStatus.FAILED, error=error_msg)


@app.post("/v1/index")
async def index_files(request: IndexRequest, background_tasks: BackgroundTasks) -> IndexResponse:
    """Queue files for indexing and return immediately with task ID.

    This endpoint creates an indexing task and processes it in the background.
    Use GET /v1/index/status/{task_id} to check progress.
    """
    if _sql_store is None or _lance_store is None:
        raise HTTPException(status_code=503, detail="Stores not initialized")

    # Validate repo exists
    repo = _sql_store.get_repo_by_name(request.repo)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{request.repo}' not found")

    # Create task
    task_queue = get_task_queue()
    task = task_queue.create_task(request.repo, request.files)

    # Queue background processing
    background_tasks.add_task(_process_index_task, task.task_id, request.repo, request.files)

    return IndexResponse(
        task_id=task.task_id,
        status="queued",
        message=f"Queued {len(request.files)} files for indexing",
    )


@app.get("/v1/index/status/{task_id}")
async def get_index_status(task_id: str) -> IndexStatusResponse:
    """Get the status of an indexing task."""
    task_queue = get_task_queue()
    task = task_queue.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    return IndexStatusResponse(
        task_id=task.task_id,
        status=task.status.value,
        progress=task.progress,
        total=task.total,
        indexed=task.indexed,  # Use real-time task field instead of result
        skipped=task.skipped,  # Use real-time task field instead of result
        current_file=task.current_file,  # Current file being processed
        error=task.error,
        result=task.result,
    )


@app.get("/v1/index/tasks")
async def list_index_tasks(repo: str | None = None) -> dict:
    """List all indexing tasks, optionally filtered by repository."""
    task_queue = get_task_queue()
    tasks = task_queue.get_all_tasks(repo)

    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "repo": t.repo,
                "status": t.status.value,
                "progress": t.progress,
                "total": t.total,
                "created_at": t.created_at.isoformat(),
                "error": t.error,
            }
            for t in tasks
        ]
    }


@app.get("/v1/repos/{repo_name}/stats")
async def get_repo_stats(repo_name: str) -> RepoStatsResponse:
    """Get repository statistics for cost estimation and UI display.

    Returns file count, chunk count, token count, and last index timestamp.
    Used by the frontend to calculate reindex costs and show current status.
    """
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Get repo
    repo = _sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    repo_id = int(repo["id"])
    repo_path = repo["root_path"]
    embed_model = repo.get("default_embed_model", "large")

    try:
        from contextlib import closing

        with _sql_store._connect() as conn, closing(conn.cursor()) as cur:
            # Count files
            cur.execute("SELECT COUNT(*) FROM files WHERE repo_id = ?", (repo_id,))
            files_count = cur.fetchone()[0]

            # Count chunks
            cur.execute("SELECT COUNT(*) FROM chunk_content WHERE repo_id = ?", (repo_id,))
            chunks_count = cur.fetchone()[0]

            # Sum token counts (from LanceDB metadata or estimate)
            total_tokens = chunks_count * ESTIMATED_TOKENS_PER_CHUNK

            # Get last successful session timestamp
            cur.execute(
                """
                SELECT MAX(created_at)
                FROM sessions
                WHERE repo_id = ? AND status = 'succeeded'
            """,
                (repo_id,),
            )
            last_indexed_row = cur.fetchone()
            last_indexed = last_indexed_row[0] if last_indexed_row[0] else None

            # Check if reindex is needed (simple heuristic: no successful sessions)
            cur.execute(
                """
                SELECT COUNT(*)
                FROM sessions
                WHERE repo_id = ? AND status = 'succeeded'
            """,
                (repo_id,),
            )
            successful_sessions = cur.fetchone()[0]
            needs_reindex = successful_sessions == 0

        return RepoStatsResponse(
            name=repo_name,
            path=repo_path,
            files_count=files_count,
            chunks_count=chunks_count,
            total_tokens=total_tokens,
            embed_model=embed_model,
            last_indexed=last_indexed,
            needs_reindex=needs_reindex,
        )

    except Exception as e:
        import logging

        logging.error(f"Failed to get stats for repo {repo_name}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get repo stats: {str(e)}")


@app.post("/v1/repos/{repo_name}/reindex")
async def reindex_repo(repo_name: str, request: ReindexRequest, background_tasks: BackgroundTasks) -> IndexResponse:
    """Trigger a full or incremental reindex of the repository.

    Full reindex clears existing index and reprocesses all files.
    Incremental reindex only processes changed files.

    Requires confirmation for full reindex due to cost implications.
    """
    if _sql_store is None or _lance_store is None:
        raise HTTPException(status_code=503, detail="Stores not initialized")

    # Pipeline is only required for full reindex with clear_existing
    if request.mode == "full" and request.clear_existing and _pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="Pipeline not initialized (required for index clearing)",
        )

    # Get repo
    repo = _sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    # Validate mode
    if request.mode not in ["full", "incremental"]:
        raise HTTPException(status_code=400, detail="Mode must be 'full' or 'incremental'")

    # Require confirmation for full reindex
    if request.mode == "full" and not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Full reindex requires confirmation due to cost implications",
        )

    try:
        # For full reindex, use pipeline's full_reindex flag
        if request.mode == "full":
            # Queue full reindex task
            import logging
            from pathlib import Path

            logger = logging.getLogger(__name__)
            repo_id = int(repo["id"])
            root = Path(repo["root_path"])

            # Get all tracked files
            from ..ingest._helpers import get_all_tracked_files

            all_files = get_all_tracked_files(root)

            logger.info(f"[Full Reindex] Found {len(all_files)} tracked files for {repo_name}")
            logger.info(f"[Full Reindex] Root path: {root}")
            if all_files:
                logger.info(f"[Full Reindex] First 5 files: {all_files[:5]}")
            else:
                logger.warning(f"[Full Reindex] NO TRACKED FILES FOUND for {repo_name} at {root}")

            # Create task
            task_queue = get_task_queue()
            task = task_queue.create_task(repo_name, all_files)
            logger.info(f"[Full Reindex] Created task {task.task_id} with {len(all_files)} files")

            # If clear_existing is requested, trigger index drop
            if request.clear_existing:
                # This will be handled by the background task
                pass

            # Queue background processing with full_reindex flag
            background_tasks.add_task(
                _process_full_reindex_task,
                task.task_id,
                repo_name,
                all_files,
                clear_existing=request.clear_existing,
            )

            return IndexResponse(
                task_id=task.task_id,
                status="queued",
                message=f"Full reindex queued: {len(all_files)} files to process",
            )
        else:
            # Incremental mode: use existing git-diff-based indexing
            # Get changed files since last commit
            from pathlib import Path

            from ..ingest._helpers import git_changed_files_modified_added

            repo_id = int(repo["id"])
            root = Path(repo["root_path"])

            # Get last successful commit
            last_success = _sql_store.get_last_successful_commit(repo_id)

            if last_success:
                # Get current commit
                try:
                    git_repo = GitRepository(root)
                    commit_sha = git_repo.get_current_commit()

                    # Get changed files
                    changed_files = git_changed_files_modified_added(root, last_success, commit_sha)
                except Exception:
                    # Fallback: queue all tracked files
                    from ..ingest._helpers import get_all_tracked_files

                    changed_files = get_all_tracked_files(root)
            else:
                # No previous index: process all files
                from ..ingest._helpers import get_all_tracked_files

                changed_files = get_all_tracked_files(root)

            if not changed_files:
                raise HTTPException(status_code=400, detail="No files to index (all files up to date)")

            # Create task
            task_queue = get_task_queue()
            task = task_queue.create_task(repo_name, changed_files)

            # Queue background processing
            background_tasks.add_task(_process_index_task, task.task_id, repo_name, changed_files)

            return IndexResponse(
                task_id=task.task_id,
                status="queued",
                message=f"Incremental index queued: {len(changed_files)} files to process",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger reindex: {str(e)}")


@app.delete("/v1/repos/{repo_name}/index")
async def clear_repo_index(repo_name: str, confirmed: bool = False) -> dict:
    """Clear all indexed data for a repository.

    This removes all chunks, vectors, and metadata for the repository.
    Requires confirmation due to destructive nature.
    """
    if not confirmed:
        raise HTTPException(status_code=400, detail="Index clearing requires confirmation parameter")

    if _sql_store is None or _lance_store is None or _pipeline is None:
        raise HTTPException(status_code=503, detail="Stores not initialized")

    # Get repo
    repo = _sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    repo_id = int(repo["id"])

    try:
        # Use pipeline's _drop_repo_index method
        _pipeline._drop_repo_index(repo_id, repo_name)

        return {
            "success": True,
            "message": f"Index cleared for repository '{repo_name}'",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear index: {str(e)}")


# =====================
# File Sync Endpoints (Phase 2)
# =====================


@app.post("/v1/repos/{repo_name}/changes")
async def record_pending_changes(repo_name: str, request: PendingChangeRequest) -> dict:
    """Record pending file changes detected by file watcher.

    This endpoint is called by the VSCode extension when files are created, modified, or deleted.
    Changes are persisted to survive crashes and restarts.
    """
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Get repo
    repo = _sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    repo_id = int(repo["id"])

    try:
        change_ids = []
        for change in request.changes:
            change_id = _sql_store.record_pending_change(
                repo_id=repo_id,
                file_path=change.file_path,
                change_type=change.change_type,
                old_path=change.old_path,
            )
            change_ids.append(change_id)

        return {
            "change_ids": change_ids,
            "message": f"Recorded {len(change_ids)} pending changes for '{repo_name}'",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record changes: {str(e)}")


@app.get("/v1/repos/{repo_name}/pending-changes")
async def get_pending_changes(repo_name: str, limit: int = 1000) -> dict:
    """Get unprocessed pending changes for a repository.

    This endpoint returns all file changes that have been detected but not yet indexed.
    Used by the auto-sync manager to process pending changes.
    """
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Get repo
    repo = _sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    repo_id = int(repo["id"])

    try:
        changes = _sql_store.get_pending_changes(repo_id=repo_id, limit=limit)

        # Add processed field to each change for compatibility
        for change in changes:
            change["processed"] = False

        return {"changes": changes, "total": len(changes)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pending changes: {str(e)}")


@app.post("/v1/repos/{repo_name}/changes/mark-processed")
async def mark_changes_processed(repo_name: str, request: MarkProcessedRequest) -> dict:
    """Mark pending changes as processed after indexing.

    This endpoint is called after the auto-sync manager successfully indexes pending changes.
    """
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Get repo
    repo = _sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    try:
        processed = _sql_store.mark_changes_processed(request.change_ids)

        return {
            "processed_count": processed,
            "message": f"Marked {processed} changes as processed",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark changes as processed: {str(e)}")


@app.get("/v1/repos/{repo_name}/drift")
async def detect_drift(repo_name: str) -> DriftDetectionResponse:
    """Detect files that have changed since last indexing (drift detection).

    This endpoint compares current file state with snapshots taken during indexing
    to identify files that were modified while VSCode was closed or during crashes.
    """
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Get repo
    repo = _sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    repo_id = int(repo["id"])

    try:
        drift_events = _sql_store.detect_drift(repo_id)

        return DriftDetectionResponse(drift_events=drift_events, total=len(drift_events))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to detect drift: {str(e)}")


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
                raise Exception("Stores not initialized for index clearing")

            # Get repo
            repo = _sql_store.get_repo_by_name(repo_name)
            if not repo:
                raise Exception(f"Repository '{repo_name}' not found")

            repo_id = int(repo["id"])

            logger.info(f"[Full Reindex Task] Clearing existing index for {repo_name} (repo_id={repo_id})")
            # Clear existing index
            _pipeline._drop_repo_index(repo_id, repo_name)
            logger.info("[Full Reindex Task] Index cleared successfully")

        logger.info(f"[Full Reindex Task] About to process {len(files)} files for {repo_name}")
        # Now process all files using standard indexing
        await _process_index_task(task_id, repo_name, files)
        logger.info("[Full Reindex Task] Completed processing")

    except Exception as e:
        import traceback

        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        await task_queue.update_task(task_id, status=TaskStatus.FAILED, error=error_msg)


def main() -> None:
    import uvicorn

    uvicorn.run("pb_kb.api.app:app", host="127.0.0.1", port=7777, reload=False)


if __name__ == "__main__":
    main()
