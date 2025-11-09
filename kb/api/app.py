from __future__ import annotations

from inspect import isawaitable
from pathlib import Path
from time import perf_counter
from typing import Awaitable, Iterable, Protocol, Sequence

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from pydantic import BaseModel

from .task_queue import TaskStatus, get_task_queue

app = FastAPI(title="Unified Knowledge Store", version="0.1.0")

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


def reset_stores():
    """Reset stores to None (for testing)."""
    global _sql_store, _lance_store, _pipeline
    _sql_store = None
    _lance_store = None
    _pipeline = None


class SearchRequest(BaseModel):
    query: str
    repos: list[str] | None = None
    path_prefix: list[str] | None = None
    exclude_paths: list[str] | None = None
    exclude_patterns: list[str] | None = None
    top_k: int = 8
    max_snippet_tokens: int = 240
    embed_model: str = "large"
    score_cutoff: float | None = 0.0
    # Defaults set to None so backend can fall back to global config when unspecified
    mmr_enabled: bool | None = None
    mmr_lambda: float | None = None
    ann_strategy: str | None = None
    ann_nprobes: int | None = None
    ann_refine_factor: int | None = None
    # Graph context enrichment (enabled by default for better context)
    include_graph_context: bool = True
    # Leading/trailing line context (disabled by default for backwards compatibility)
    context_lines_before: int = 0
    context_lines_after: int = 0


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
    error: str | None = None
    result: dict | None = None


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
            name=existing["name"],
            path=existing["root_path"],
            message=f"Repository '{request.name}' already registered"
        )

    # Validate path exists
    repo_path = Path(request.path)
    if not repo_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {request.path}")

    if not repo_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {request.path}")

    # Register the repository
    try:
        repo_id = _sql_store.upsert_repo(
            name=request.name,
            root_path=str(repo_path.resolve()),
            default_embed_model=request.default_embed_model
        )

        return RegisterRepoResponse(
            repo_id=repo_id,
            name=request.name,
            path=str(repo_path.resolve()),
            message=f"Repository '{request.name}' registered successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register repository: {str(e)}")


def _process_index_task(task_id: str, repo_name: str, files: list[str]):
    """Background task to process file indexing."""
    task_queue = get_task_queue()

    try:
        # Update task to processing
        import asyncio
        asyncio.run(task_queue.update_task(task_id, status=TaskStatus.PROCESSING))

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
                resolved = full_path.resolve()
                if not str(resolved).startswith(str(root.resolve())):
                    continue  # Skip files outside repo
            except Exception:
                continue

            if full_path.exists() and full_path.is_file():
                valid_files.append(filepath)

        if not valid_files:
            asyncio.run(task_queue.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                result={"indexed": 0, "skipped": len(files), "message": "No valid files to index"}
            ))
            return

        # Process files
        import subprocess
        from ..ingest.dedup import ChunkDeduplicator
        from ..chunkers.registry import detect_language_from_extension, chunk_file as chunk_file_with_config
        from ..chunkers.repo_config import load_repo_chunking_config
        from ..hashing import hash_text
        from ..embeddings.provider import embed_texts_with_retry
        from ..ingest._helpers import build_desired_map, representative_text_for_hash

        # Get commit info for provenance
        try:
            commit_sha = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                stderr=subprocess.STDOUT
            ).decode("utf-8").strip()
            branch = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.STDOUT
            ).decode("utf-8").strip()
        except Exception:
            # Non-git repo or git not available
            commit_sha = "unknown"
            branch = "unknown"

        # Start session
        session_id = _sql_store.begin_session(repo_id, commit_sha, branch, embed_model)

        chunks_indexed = chunks_skipped = 0
        repo_config = load_repo_chunking_config(root)

        for idx, filepath in enumerate(valid_files, 1):
            # Update progress
            asyncio.run(task_queue.update_task(task_id, progress=idx))

            file_path = root / filepath

            # Resolve or upsert file_id
            file_id = _sql_store.upsert_file(
                repo_id=repo_id,
                path=filepath,
                ext=file_path.suffix,
                language=None,  # Will be detected by chunker
                is_binary=False,
                size_bytes=file_path.stat().st_size
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

            # Compute text_hash for each chunk
            for chunk in chunks:
                chunk.text_hash = hash_text(chunk.text)

            # Build desired map
            desired = build_desired_map(chunks)
            desired_row_ids: set[str] = set()

            # Deduplicate by text_hash
            dedup = ChunkDeduplicator(_sql_store)
            changed_chunks, unchanged_chunks = dedup.filter_unchanged_chunks(
                chunks, repo_id, file_id, embed_model
            )
            new_hashes = {c.text_hash for c in changed_chunks}
            skipped_occurrences = len(unchanged_chunks)

            # Embed only new hashes (batched)
            hash_to_vec: dict = {}
            if new_hashes:
                hashes_list = sorted(new_hashes)
                batch_size = 128
                for i in range(0, len(hashes_list), batch_size):
                    batch_hashes = hashes_list[i:i+batch_size]
                    texts_to_embed = [
                        representative_text_for_hash(h, chunks) for h in batch_hashes
                    ]
                    if not texts_to_embed:
                        continue
                    vectors = embed_texts_with_retry(embed_model, texts_to_embed)
                    hash_to_vec.update(dict(zip(batch_hashes, vectors)))

            # Upsert metadata and locations
            mapping = _sql_store.ensure_content_rows_for_file(
                repo_id, file_id, embed_model, list(desired.keys())
            )

            for h, occs in desired.items():
                cid = mapping.get(h)
                if cid:
                    _sql_store.sync_locations_for_content_row(cid, occs)

            _sql_store.prune_invalidated_content_for_file(
                repo_id, file_id, embed_model, set(desired.keys())
            )

            # Build token count lookup
            occ_token_counts = {
                (ch.start_line, ch.end_line): getattr(ch, 'token_count', 0) for ch in chunks
            }

            # Persist vectors to LanceDB
            payload = []
            fts_chunks = []
            for h, occs in desired.items():
                content_id = mapping.get(h)
                vec = hash_to_vec.get(h)
                for idx_occ, occ in enumerate(occs):
                    row_id = f"{repo_id}:{file_id}:{embed_model}:{h}:{occ['start_line']}:{occ['end_line']}"
                    desired_row_ids.add(row_id)
                    if vec is None:
                        continue  # unchanged hash
                    payload.append({
                        'id': row_id,
                        'vector': vec,
                        'repo': repo_name,
                        'path': filepath,
                        'start_line': occ['start_line'],
                        'end_line': occ['end_line'],
                        'text_hash': h,
                        'commit': commit_sha,
                        'branch': branch,
                        'embed_model': embed_model,
                        'language': language,
                        'symbol_kind': occ.get('symbol_kind'),
                        'symbol_name': occ.get('symbol_name'),
                        'symbol_path': occ.get('symbol_path'),
                        'heading_h1': occ.get('heading_h1'),
                        'heading_h2': occ.get('heading_h2'),
                        'heading_h3': occ.get('heading_h3'),
                        'token_count': occ_token_counts.get((occ['start_line'], occ['end_line']), 0),
                        'created_at': None,
                    })

                    # Prepare chunk for FTS5 indexing (first occurrence only)
                    if content_id and idx_occ == 0:
                        chunk_text = None
                        for chunk in chunks:
                            if chunk.text_hash == h:
                                chunk_text = chunk.text
                                break

                        if chunk_text:
                            fts_chunks.append({
                                'content_id': content_id,
                                'repo': repo_name,
                                'path': filepath,
                                'content': chunk_text,
                                'symbol_name': occ.get('symbol_name'),
                                'symbol_path': occ.get('symbol_path'),
                            })

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

            # Update counters
            chunks_indexed += len(new_hashes)
            chunks_skipped += skipped_occurrences

        # Update session
        _sql_store.bump_session_counters(
            session_id,
            files_indexed=len(valid_files),
            chunks_indexed=chunks_indexed,
            chunks_skipped=chunks_skipped,
            vectors_written=chunks_indexed,
            chunks_pruned=0
        )
        _sql_store.set_session_status(session_id, "succeeded")

        # Mark task complete
        asyncio.run(task_queue.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            result={
                "indexed": chunks_indexed,
                "skipped": chunks_skipped,
                "files_processed": len(valid_files),
                "message": f"Indexed {len(valid_files)} files: {chunks_indexed} new chunks, {chunks_skipped} skipped"
            }
        ))

    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        asyncio.run(task_queue.update_task(
            task_id,
            status=TaskStatus.FAILED,
            error=error_msg
        ))


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
        message=f"Queued {len(request.files)} files for indexing"
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
        indexed=task.result.get("indexed", 0) if task.result else 0,
        skipped=task.result.get("skipped", 0) if task.result else 0,
        error=task.error,
        result=task.result
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


# Keep old synchronous endpoint for backwards compatibility (deprecated)
@app.post("/v1/index/sync")
async def index_files_sync(request: IndexRequest):
    """Synchronous indexing endpoint (deprecated - use /v1/index instead)."""
    if _sql_store is None or _lance_store is None:
        raise HTTPException(status_code=503, detail="Stores not initialized")

    # Create and process task synchronously
    task_queue = get_task_queue()
    task = task_queue.create_task(request.repo, request.files)

    _process_index_task(task.task_id, request.repo, request.files)

    # Get final result
    final_task = task_queue.get_task(task.task_id)
    if final_task and final_task.status == TaskStatus.COMPLETED:
        return final_task.result
    elif final_task and final_task.status == TaskStatus.FAILED:
        raise HTTPException(status_code=500, detail=final_task.error)
    else:
        raise HTTPException(status_code=500, detail="Unknown error occurred")


# Remove old implementation code below this point
@app.post("/v1/index_old")
async def index_files_old(request: IndexRequest):
    """Old implementation - kept for reference only."""
    if _sql_store is None or _lance_store is None:
        raise HTTPException(status_code=503, detail="Stores not initialized")

    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Ingestion pipeline not initialized")

    # Get repo
    repo = _sql_store.get_repo_by_name(request.repo)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{request.repo}' not found")

    repo_id = int(repo["id"])
    root = Path(repo["root_path"])
    embed_model = repo.get("default_embed_model", "large")

    # Filter files that actually exist
    valid_files = []
    for filepath in request.files:
        full_path = root / filepath

        # Security check: ensure path is within repo
        try:
            resolved = full_path.resolve()
            if not str(resolved).startswith(str(root.resolve())):
                continue  # Skip files outside repo
        except Exception:
            continue

        if full_path.exists() and full_path.is_file():
            valid_files.append(filepath)

    if not valid_files:
        raise HTTPException(status_code=400, detail="No valid files to index")

    # Old sync implementation follows...
        import subprocess
        from ..ingest.dedup import ChunkDeduplicator
        from ..chunkers.registry import detect_language_from_extension, chunk_file as chunk_file_with_config
        from ..chunkers.repo_config import load_repo_chunking_config
        from ..hashing import hash_text
        from ..embeddings.provider import embed_texts_with_retry
        from ..ingest._helpers import build_desired_map, representative_text_for_hash

        # Get commit info for provenance
        try:
            commit_sha = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                stderr=subprocess.STDOUT
            ).decode("utf-8").strip()
            branch = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.STDOUT
            ).decode("utf-8").strip()
        except Exception:
            # Non-git repo or git not available
            commit_sha = "unknown"
            branch = "unknown"

        # Start session
        session_id = _sql_store.begin_session(repo_id, commit_sha, branch, embed_model)

        chunks_indexed = chunks_skipped = 0
        repo_config = load_repo_chunking_config(root)

        for filepath in valid_files:
            file_path = root / filepath

            # Resolve or upsert file_id
            file_id = _sql_store.upsert_file(
                repo_id=repo_id,
                path=filepath,
                ext=file_path.suffix,
                language=None,  # Will be detected by chunker
                is_binary=False,
                size_bytes=file_path.stat().st_size
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

            # Compute text_hash for each chunk
            for chunk in chunks:
                chunk.text_hash = hash_text(chunk.text)

            # Build desired map
            desired = build_desired_map(chunks)
            desired_row_ids: set[str] = set()

            # Deduplicate by text_hash
            dedup = ChunkDeduplicator(_sql_store)
            changed_chunks, unchanged_chunks = dedup.filter_unchanged_chunks(
                chunks, repo_id, file_id, embed_model
            )
            new_hashes = {c.text_hash for c in changed_chunks}
            skipped_occurrences = len(unchanged_chunks)

            # Embed only new hashes (batched)
            hash_to_vec: dict = {}
            if new_hashes:
                hashes_list = sorted(new_hashes)
                batch_size = 128
                for i in range(0, len(hashes_list), batch_size):
                    batch_hashes = hashes_list[i:i+batch_size]
                    texts_to_embed = [
                        representative_text_for_hash(h, chunks) for h in batch_hashes
                    ]
                    if not texts_to_embed:
                        continue
                    vectors = embed_texts_with_retry(embed_model, texts_to_embed)
                    hash_to_vec.update(dict(zip(batch_hashes, vectors)))

            # Upsert metadata and locations
            mapping = _sql_store.ensure_content_rows_for_file(
                repo_id, file_id, embed_model, list(desired.keys())
            )

            for h, occs in desired.items():
                cid = mapping.get(h)
                if cid:
                    _sql_store.sync_locations_for_content_row(cid, occs)

            _sql_store.prune_invalidated_content_for_file(
                repo_id, file_id, embed_model, set(desired.keys())
            )

            # Build token count lookup
            occ_token_counts = {
                (ch.start_line, ch.end_line): getattr(ch, 'token_count', 0) for ch in chunks
            }

            # Persist vectors to LanceDB
            payload = []
            fts_chunks = []
            for h, occs in desired.items():
                content_id = mapping.get(h)
                vec = hash_to_vec.get(h)
                for idx, occ in enumerate(occs):
                    row_id = f"{repo_id}:{file_id}:{embed_model}:{h}:{occ['start_line']}:{occ['end_line']}"
                    desired_row_ids.add(row_id)
                    if vec is None:
                        continue  # unchanged hash
                    payload.append({
                        'id': row_id,
                        'vector': vec,
                        'repo': request.repo,
                        'path': filepath,
                        'start_line': occ['start_line'],
                        'end_line': occ['end_line'],
                        'text_hash': h,
                        'commit': commit_sha,
                        'branch': branch,
                        'embed_model': embed_model,
                        'language': language,
                        'symbol_kind': occ.get('symbol_kind'),
                        'symbol_name': occ.get('symbol_name'),
                        'symbol_path': occ.get('symbol_path'),
                        'heading_h1': occ.get('heading_h1'),
                        'heading_h2': occ.get('heading_h2'),
                        'heading_h3': occ.get('heading_h3'),
                        'token_count': occ_token_counts.get((occ['start_line'], occ['end_line']), 0),
                        'created_at': None,
                    })

                    # Prepare chunk for FTS5 indexing (first occurrence only)
                    if content_id and idx == 0:
                        chunk_text = None
                        for chunk in chunks:
                            if chunk.text_hash == h:
                                chunk_text = chunk.text
                                break

                        if chunk_text:
                            fts_chunks.append({
                                'content_id': content_id,
                                'repo': request.repo,
                                'path': filepath,
                                'content': chunk_text,
                                'symbol_name': occ.get('symbol_name'),
                                'symbol_path': occ.get('symbol_path'),
                            })

            if payload:
                _lance_store.upsert_chunks(request.repo, payload, model=embed_model)

            # Index chunks in FTS5 for BM25 search
            if fts_chunks:
                _sql_store.bulk_index_chunks_for_fts(fts_chunks)

            # Prune any stale vectors for this file/model
            if desired_row_ids:
                _lance_store.prune_file_rows(request.repo, filepath, model=embed_model, keep_ids=desired_row_ids)
            else:
                _lance_store.prune_file_rows(request.repo, filepath, model=embed_model)

            # Update counters
            chunks_indexed += len(new_hashes)
            chunks_skipped += skipped_occurrences

        # Update session
        _sql_store.bump_session_counters(
            session_id,
            files_indexed=len(valid_files),
            chunks_indexed=chunks_indexed,
            chunks_skipped=chunks_skipped,
            vectors_written=chunks_indexed,
            chunks_pruned=0
        )
        _sql_store.set_session_status(session_id, "succeeded")

        return IndexResponse(
            indexed=chunks_indexed,
            skipped=chunks_skipped,
            tokens_used=0,  # TODO: Track token usage
            cost_usd=0.0,   # TODO: Calculate cost
            message=f"Indexed {len(valid_files)} files: {chunks_indexed} new chunks, {chunks_skipped} skipped"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


def main() -> None:
    import uvicorn

    uvicorn.run("pb_kb.api.app:app", host="127.0.0.1", port=7777, reload=False)


if __name__ == "__main__":
    main()
