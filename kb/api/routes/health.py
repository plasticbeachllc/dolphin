"""Health check and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..app import health

router = APIRouter()


@router.get("/v1/health")
async def health_v1(check: str = Query(default="shallow")) -> dict[str, object]:
    """Health check endpoint (v1)."""
    return await health(check)
