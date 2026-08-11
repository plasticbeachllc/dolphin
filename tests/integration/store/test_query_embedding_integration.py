"""Integration coverage for async admission over the real SQLite embedding cache."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kb.generation import EMBEDDING_DIMENSIONS
from kb.runtime.storage import macos_storage_layout
from kb.services.query_embedding import QueryEmbeddingService
from kb.services.workspace_registry import WorkspaceRegistry
from kb.store.embedding_cache import SQLiteEmbeddingCache


class _Provider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def embed_query(self, query: str) -> tuple[float, ...]:
        self.calls.append(query)
        return (0.125,) * EMBEDDING_DIMENSIONS


@pytest.mark.asyncio
async def test_second_identical_query_uses_durable_cache_without_provider(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    now = datetime(2026, 8, 10, tzinfo=UTC)
    WorkspaceRegistry(layout).register_runtime(
        runtime_id="runtime_query_integration",
        pid=1,
        process_start_identity="query-integration-process",
        mode="mcp",
        operation_capable=False,
        pipeline_key=None,
        now=now,
        expires_at=now + timedelta(minutes=1),
    )
    provider = _Provider()
    query = "where is publication authority validated?"

    first = await QueryEmbeddingService(SQLiteEmbeddingCache(layout), provider).resolve(query)
    second = await QueryEmbeddingService(SQLiteEmbeddingCache(layout), provider).resolve(query)

    assert first.source == "live"
    assert first.cache_write == "persisted"
    assert second.source == "cache"
    assert second.vector == first.vector
    assert provider.calls == [query]
    assert query.encode() not in layout.metadata_db.read_bytes()
