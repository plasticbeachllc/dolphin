"""Search endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..app import SearchRequest, search

router = APIRouter()


@router.post("/v1/search")
async def search_v1(request: SearchRequest) -> dict[str, object]:
    """Dispatch the search request to the configured backend (v1)."""
    return await search(request)
