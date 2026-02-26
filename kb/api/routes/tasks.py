"""Background task management and admin endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

import kb.api.app as _app_mod

from ..app import IndexRequest, IndexResponse, IndexStatusResponse, _process_index_task
from ..task_queue import get_task_queue

router = APIRouter()

_log = logging.getLogger(__name__)


@router.post("/v1/index")
async def index_files(request: IndexRequest, background_tasks: BackgroundTasks) -> IndexResponse:
    """Queue files for indexing and return immediately with task ID.

    This endpoint creates an indexing task and processes it in the background.
    Use GET /v1/index/status/{task_id} to check progress.
    """
    sql_store = _app_mod._sql_store
    lance_store = _app_mod._lance_store

    if sql_store is None or lance_store is None:
        raise HTTPException(status_code=503, detail="Stores not initialized")

    # Validate repo exists
    repo = sql_store.get_repo_by_name(request.repo)
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


@router.get("/v1/index/status/{task_id}")
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


@router.get("/v1/index/tasks")
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


@router.post("/v1/admin/reload")
async def admin_reload_backend() -> dict[str, str]:
    """Reload the search backend and store connections.

    This is used by the indexing CLI to notify the server that the index has changed.
    """
    # Import here to avoid circular dependency with server.py
    # server.py imports app.py, so app.py cannot import server.py at top level
    try:
        from ..server import reload_search_backend

        reload_search_backend()
        return {"status": "ok", "message": "Search backend reloaded"}
    except Exception as e:
        logging.error("Failed to reload backend", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Reload failed: {str(e)}")


@router.post("/v1/admin/rebuild-fts5")
async def rebuild_fts5() -> dict[str, str]:
    """Rebuild the FTS5 table with updated schema.

    This drops and recreates the FTS5 table. After calling this endpoint,
    you should trigger a full re-index to populate the FTS5 table with
    the new deterministic content_ids.
    """
    sql_store = _app_mod._sql_store
    if sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    try:
        sql_store.rebuild_fts5_table()
        return {
            "status": "success",
            "message": "FTS5 table rebuilt successfully. Please trigger a re-index to populate it.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild FTS5 table: {str(e)}")
