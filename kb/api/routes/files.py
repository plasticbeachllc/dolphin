"""File content and chunk listing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..app import fetch_chunk, fetch_file_slice

router = APIRouter()


@router.get("/v1/chunks/{chunk_id}")
async def fetch_chunk_v1(chunk_id: str) -> dict[str, object]:
    """Fetch a specific chunk by ID (v1)."""
    return await fetch_chunk(chunk_id)


@router.get("/v1/file")
async def fetch_file_slice_v1(
    repo: str = Query(..., description="Repository name"),
    path: str = Query(..., description="File path relative to repo root"),
    start: int = Query(1, description="Start line (1-indexed, inclusive)"),
    end: int = Query(..., description="End line (1-indexed, inclusive)"),
) -> dict[str, object]:
    """Fetch a slice of a file by line range (v1)."""
    if start < 1 or end < start:
        raise HTTPException(status_code=422, detail="Invalid line range")
    return await fetch_file_slice(repo=repo, path=path, start=start, end=end)
