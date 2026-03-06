"""Repository CRUD, reindex, and file-sync endpoints."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

import kb.api.app as _app_mod

from ...constants.retrieval_config import RETRIEVAL_PARAMS
from ..app import (
    DriftDetectionResponse,
    IndexResponse,
    MarkProcessedRequest,
    PendingChangeRequest,
    RegisterRepoRequest,
    RegisterRepoResponse,
    ReindexRequest,
    RepoStatsResponse,
    _invalidate_search_cache,
    _process_full_reindex_task,
    list_repos,
    process_index_task,
)
from ..task_queue import get_task_queue
from ..utils import normalize_repo_registration_path

_log = logging.getLogger(__name__)

router = APIRouter()

# ---- Constants re-used for token estimation ----
ESTIMATED_TOKENS_PER_CHUNK = RETRIEVAL_PARAMS.ESTIMATED_TOKENS_PER_CHUNK


@router.get("/v1/repos")
async def list_repos_v1() -> dict[str, list[dict[str, object]]]:
    """List all registered repositories with metadata (v1)."""
    return await list_repos()


@router.post("/v1/repos")
async def register_repo(request: RegisterRepoRequest) -> RegisterRepoResponse:
    """Register a new repository for indexing.

    This creates a repository entry in the metadata store, allowing it to be indexed.
    """
    sql_store = _app_mod._sql_store
    if sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Check if repo already exists
    existing = sql_store.get_repo_by_name(request.name)
    if existing:
        return RegisterRepoResponse(
            repo_id=existing["id"],
            name=request.name,
            path=existing["root_path"],
            message=f"Repository '{request.name}' already registered",
        )

    # Normalize and sanitize request path. Existence/type checks occur at actual use sites.
    normalized_repo_path = normalize_repo_registration_path(request.path)

    # Register the repository
    try:
        sql_store.record_repo(
            name=request.name,
            path=normalized_repo_path,
            default_embed_model=request.default_embed_model,
        )

        # Get the registered repo to retrieve its ID
        repo = sql_store.get_repo_by_name(request.name)
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


@router.get("/v1/repos/{repo_name}/stats")
async def get_repo_stats(repo_name: str) -> RepoStatsResponse:
    """Get repository statistics for cost estimation and UI display.

    Returns file count, chunk count, token count, and last index timestamp.
    Used by the frontend to calculate reindex costs and show current status.
    """
    sql_store = _app_mod._sql_store
    if sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Get repo
    repo = sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    repo_id = int(repo["id"])
    repo_path = repo["root_path"]
    embed_model = repo.get("default_embed_model", "large")

    try:
        from contextlib import closing

        with sql_store._connect() as conn, closing(conn.cursor()) as cur:
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
        logging.error(f"Failed to get stats for repo {repo_name}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get repo stats: {str(e)}")


@router.post("/v1/repos/{repo_name}/reindex")
async def reindex_repo(repo_name: str, request: ReindexRequest, background_tasks: BackgroundTasks) -> IndexResponse:
    """Trigger a full or incremental reindex of the repository.

    Full reindex clears existing index and reprocesses all files.
    Incremental reindex only processes changed files.

    Requires confirmation for full reindex due to cost implications.
    """
    sql_store = _app_mod._sql_store
    lance_store = _app_mod._lance_store
    pipeline = _app_mod._pipeline

    if sql_store is None or lance_store is None:
        raise HTTPException(status_code=503, detail="Stores not initialized")

    # Pipeline is only required for full reindex with clear_existing
    if request.mode == "full" and request.clear_existing and pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="Pipeline not initialized (required for index clearing)",
        )

    # Get repo
    repo = sql_store.get_repo_by_name(repo_name)
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
            logger = logging.getLogger(__name__)
            repo_id = int(repo["id"])
            root = Path(repo["root_path"])

            # Get all tracked files
            from ...ingest._helpers import get_all_tracked_files

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
            from ...ingest._helpers import git_changed_files_modified_added

            repo_id = int(repo["id"])
            root = Path(repo["root_path"])

            # Get last successful commit
            last_success = sql_store.get_last_successful_commit(repo_id)

            if last_success:
                # Get current commit
                try:
                    from ..utils import GitRepository

                    git_repo = GitRepository(root)
                    commit_sha = git_repo.get_current_commit()

                    # Get changed files
                    changed_files = git_changed_files_modified_added(root, last_success, commit_sha)
                except Exception:
                    # Fallback: queue all tracked files
                    from ...ingest._helpers import get_all_tracked_files

                    changed_files = get_all_tracked_files(root)
            else:
                # No previous index: process all files
                from ...ingest._helpers import get_all_tracked_files

                changed_files = get_all_tracked_files(root)

            if not changed_files:
                raise HTTPException(status_code=400, detail="No files to index (all files up to date)")

            # Create task
            task_queue = get_task_queue()
            task = task_queue.create_task(repo_name, changed_files)

            # Queue background processing
            background_tasks.add_task(process_index_task, task.task_id, repo_name, changed_files)

            return IndexResponse(
                task_id=task.task_id,
                status="queued",
                message=f"Incremental index queued: {len(changed_files)} files to process",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger reindex: {str(e)}")


@router.delete("/v1/repos/{repo_name}/index")
async def clear_repo_index(repo_name: str, confirmed: bool = False) -> dict:
    """Clear all indexed data for a repository.

    This removes all chunks, vectors, and metadata for the repository.
    Requires confirmation due to destructive nature.
    """
    sql_store = _app_mod._sql_store
    lance_store = _app_mod._lance_store
    pipeline = _app_mod._pipeline

    if not confirmed:
        raise HTTPException(status_code=400, detail="Index clearing requires confirmation parameter")

    if sql_store is None or lance_store is None or pipeline is None:
        raise HTTPException(status_code=503, detail="Stores not initialized")

    # Get repo
    repo = sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    repo_id = int(repo["id"])

    try:
        # Use pipeline's _drop_repo_index method
        pipeline._drop_repo_index(repo_id, repo_name)
        _invalidate_search_cache(repo_name)

        return {
            "success": True,
            "message": f"Index cleared for repository '{repo_name}'",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear index: {str(e)}")


# =====================
# File Sync Endpoints (Phase 2)
# =====================


@router.post("/v1/repos/{repo_name}/changes")
async def record_pending_changes(repo_name: str, request: PendingChangeRequest) -> dict:
    """Record pending file changes detected by file watcher.

    This endpoint is called by clients when files are created, modified, or deleted.
    Changes are persisted to survive crashes and restarts.
    """
    sql_store = _app_mod._sql_store
    if sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Get repo
    repo = sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    repo_id = int(repo["id"])

    try:
        change_ids = []
        for change in request.changes:
            change_id = sql_store.record_pending_change(
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


@router.get("/v1/repos/{repo_name}/pending-changes")
async def get_pending_changes(repo_name: str, limit: int = 1000) -> dict:
    """Get unprocessed pending changes for a repository.

    This endpoint returns all file changes that have been detected but not yet indexed.
    Used by the auto-sync manager to process pending changes.
    """
    sql_store = _app_mod._sql_store
    if sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Get repo
    repo = sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    repo_id = int(repo["id"])

    try:
        changes = sql_store.get_pending_changes(repo_id=repo_id, limit=limit)

        # Add processed field to each change for compatibility
        for change in changes:
            change["processed"] = False

        return {"changes": changes, "total": len(changes)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pending changes: {str(e)}")


@router.post("/v1/repos/{repo_name}/changes/mark-processed")
async def mark_changes_processed(repo_name: str, request: MarkProcessedRequest) -> dict:
    """Mark pending changes as processed after indexing.

    This endpoint is called after the auto-sync manager successfully indexes pending changes.
    """
    sql_store = _app_mod._sql_store
    if sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Get repo
    repo = sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    try:
        processed = sql_store.mark_changes_processed(request.change_ids)

        return {
            "processed_count": processed,
            "message": f"Marked {processed} changes as processed",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark changes as processed: {str(e)}")


@router.get("/v1/repos/{repo_name}/drift")
async def detect_drift(repo_name: str) -> DriftDetectionResponse:
    """Detect files that have changed since last indexing (drift detection).

    This endpoint compares current file state with snapshots taken during indexing
    to identify files that were modified while clients were offline or during crashes.
    """
    sql_store = _app_mod._sql_store
    if sql_store is None:
        raise HTTPException(status_code=503, detail="SQL store not initialized")

    # Get repo
    repo = sql_store.get_repo_by_name(repo_name)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    repo_id = int(repo["id"])

    try:
        drift_events = await asyncio.to_thread(sql_store.detect_drift, repo_id)

        return DriftDetectionResponse(drift_events=drift_events, total=len(drift_events))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to detect drift: {str(e)}")
