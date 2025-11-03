from __future__ import annotations

from inspect import isawaitable
from pathlib import Path
from time import perf_counter
from typing import Awaitable, Iterable, Protocol, Sequence

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(title="Unified Knowledge Store", version="0.1.0")

# Will be set by server startup
_sql_store = None
_lance_store = None

def set_stores(sql_store, lance_store):
    """Set the SQL and Lance stores for API endpoints."""
    global _sql_store, _lance_store
    _sql_store = sql_store
    _lance_store = lance_store


def reset_stores():
    """Reset stores to None (for testing)."""
    global _sql_store, _lance_store
    _sql_store = None
    _lance_store = None


class SearchRequest(BaseModel):
    query: str
    repos: list[str] | None = None
    path_prefix: list[str] | None = None
    top_k: int = 8
    max_snippet_tokens: int = 240
    embed_model: str = "large"
    score_cutoff: float | None = 0.0
    mmr_enabled: bool | None = False
    mmr_lambda: float | None = 0.7
    ann_strategy: str | None = None
    ann_nprobes: int | None = None
    ann_refine_factor: int | None = None


class SearchBackend(Protocol):
    """Protocol describing the dependency used to execute searches."""

    def search(
        self, request: SearchRequest
    ) -> Sequence[dict[str, object]] | Awaitable[Sequence[dict[str, object]]]:
        ...


class _EmptySearchBackend:
    """Default backend that returns zero hits until retrieval is implemented."""

    def search(
        self, request: SearchRequest
    ) -> Sequence[dict[str, object]] | Awaitable[Sequence[dict[str, object]]]:
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


@app.get("/health")
async def health(check: str = Query(default="shallow")) -> dict[str, object]:
    """Health check endpoint with optional deep checks."""
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

    return {"status": "ok", "checks": checks}


@app.post("/search")
async def search(request: SearchRequest) -> dict[str, object]:
    """Dispatch the search request to the configured backend."""
    backend = get_search_backend()
    
    # Extract ANN configuration from request if provided
    if hasattr(request, 'ann_strategy') and request.ann_strategy:
        # Create temporary config for this request
        temp_config_data = {}
        if request.ann_strategy:
            temp_config_data['ann_strategy'] = request.ann_strategy
        if request.ann_nprobes:
            temp_config_data['ann_nprobes'] = request.ann_nprobes
        if request.ann_refine_factor:
            temp_config_data['ann_refine_factor'] = request.ann_refine_factor
        
        # Set on backend temporarily if it supports per-request config
        if hasattr(backend, 'set_request_ann_config'):
            backend.set_request_ann_config(temp_config_data)
    
    started = perf_counter()
    raw_hits = backend.search(request)
    hits: Iterable[dict[str, object]]
    if isawaitable(raw_hits):
        hits = await raw_hits  # type: ignore[assignment]
    else:
        hits = raw_hits
    hits_list = list(hits)
    latency_ms = int((perf_counter() - started) * 1000)
    
    # Include ANN config in response meta if it was used
    meta = {
        "top_k": request.top_k,
        "model": request.embed_model,
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


@app.get("/repos")
async def list_repos() -> dict[str, list[dict[str, object]]]:
    """List all registered repositories with metadata."""
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Query all repos from SQL store
    try:
        import sqlite3
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

                repos.append({
                    "name": name,
                    "path": root_path,
                    "default_embed_model": default_model,
                    "files": file_count,
                    "chunks": chunk_count
                })

        return {"repos": repos}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/chunks/{chunk_id}")
async def fetch_chunk(chunk_id: str) -> dict[str, object]:
    """Fetch a specific chunk by ID."""
    if _sql_store is None or _lance_store is None:
        raise HTTPException(status_code=503, detail="Stores not initialized")

    try:
        import lancedb

        # Connect to LanceDB and search for the chunk by ID
        db = lancedb.connect(_lance_store.root.as_posix())

        # Try both small and large tables
        metadata = None
        for table_name in ["chunks_small", "chunks_large"]:
            try:
                table = db.open_table(table_name)
                # Query by ID
                results = table.search().where(f"id = '{chunk_id}'").limit(1).to_list()

                if results:
                    metadata = results[0]
                    break
            except Exception:
                continue

        if not metadata:
            raise HTTPException(status_code=404, detail=f"Chunk not found: {chunk_id}")

        # Fetch content from FTS table via SQL store
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
            "resource_link": f"kb://{metadata.get('repo')}/{metadata.get('path')}#L{metadata.get('start_line')}-L{metadata.get('end_line')}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching chunk: {str(e)}")


@app.get("/file")
async def fetch_file_slice(
    repo: str = Query(..., description="Repository name"),
    path: str = Query(..., description="File path relative to repo root"),
    start: int = Query(1, description="Start line (1-indexed, inclusive)"),
    end: int = Query(..., description="End line (1-indexed, inclusive)")
) -> dict[str, object]:
    """Fetch a slice of a file by line range."""
    if _sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    try:
        # Get repo info
        repo_info = _sql_store.get_repo_by_name(repo)
        if not repo_info:
            raise HTTPException(status_code=404, detail=f"Repository not found: {repo}")

        # Build full file path
        repo_root = Path(repo_info["root_path"])
        full_path = repo_root / path

        # Security check: ensure path is within repo
        try:
            full_path = full_path.resolve()
            if not str(full_path).startswith(str(repo_root.resolve())):
                raise HTTPException(status_code=403, detail="Path outside repository")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid file path")

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
            with open(full_path, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()

            # Convert to 0-indexed
            start_idx = max(0, start - 1)
            end_idx = min(len(all_lines), end)

            if start_idx >= len(all_lines):
                selected_lines = []
            else:
                selected_lines = all_lines[start_idx:end_idx]

            # Join lines
            content = ''.join(selected_lines)

            return {
                "repo": repo,
                "path": path,
                "start_line": start,
                "end_line": end,
                "content": content,
                "lang": lang,
                "source": "disk",
                "total_lines": len(all_lines)
            }

        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="File is not valid UTF-8")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


def main() -> None:
    import uvicorn

    uvicorn.run("pb_kb.api.app:app", host="127.0.0.1", port=7777, reload=False)


if __name__ == "__main__":
    main()
