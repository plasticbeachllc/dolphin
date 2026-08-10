"""Tests for exact immutable embedding cache persistence."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kb.artifacts import EmbeddingContract, identify_embedding_input
from kb.generation import EMBEDDING_DIMENSIONS
from kb.runtime.storage import macos_storage_layout
from kb.services.workspace_registry import WorkspaceRegistry
from kb.store.embedding_cache import (
    EmbeddingCacheCorrupt,
    EmbeddingCacheError,
    EmbeddingCacheUnavailable,
    SQLiteEmbeddingCache,
)


def _cache(tmp_path: Path) -> tuple[SQLiteEmbeddingCache, Path]:
    home = tmp_path / "home"
    home.mkdir()
    layout = macos_storage_layout(home=home)
    now = datetime(2026, 8, 10, tzinfo=UTC)
    WorkspaceRegistry(layout).register_runtime(
        runtime_id="runtime_cache_test",
        pid=1,
        process_start_identity="cache-test-process",
        mode="mcp",
        operation_capable=False,
        pipeline_key=None,
        now=now,
        expires_at=now + timedelta(minutes=1),
    )
    return SQLiteEmbeddingCache(layout, clock=lambda: datetime(2026, 8, 10, tzinfo=UTC)), layout.metadata_db


def _vector(component: float = 0.125) -> tuple[float, ...]:
    return (component,) * EMBEDDING_DIMENSIONS


def test_round_trip_persists_no_raw_embedding_input(tmp_path: Path) -> None:
    cache, database = _cache(tmp_path)
    query = "where does the cleanup receipt get validated?"
    identity = identify_embedding_input(query)

    installed = cache.put(identity, _vector())
    recovered = cache.get(identity)

    assert recovered == installed
    assert recovered is not None
    assert recovered.identity == identity
    assert len(recovered.vector) == EMBEDDING_DIMENSIONS
    assert query.encode() not in database.read_bytes()
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT provider, model, dimensions, contract_version, length(vector) FROM embedding_cache_entries"
        ).fetchone()
    assert row == ("openai", "text-embedding-3-small", 1536, 1, 6144)


def test_exact_miss_does_not_accept_another_input(tmp_path: Path) -> None:
    cache, _database = _cache(tmp_path)
    first = identify_embedding_input("first query")
    second = identify_embedding_input("second query")
    cache.put(first, _vector())

    assert cache.get(second) is None


def test_first_valid_writer_wins_an_idempotent_or_racing_put(tmp_path: Path) -> None:
    cache, _database = _cache(tmp_path)
    identity = identify_embedding_input("same exact query")

    first = cache.put(identity, _vector(0.125))
    repeated = cache.put(identity, _vector(0.25))

    assert repeated == first
    assert repeated.vector != _vector(0.25)


@pytest.mark.parametrize("column", ["vector_digest", "model", "input_utf8_bytes", "created_at"])
def test_corrupt_persisted_binding_fails_closed(tmp_path: Path, column: str) -> None:
    cache, database = _cache(tmp_path)
    identity = identify_embedding_input("query")
    cache.put(identity, _vector())
    values: dict[str, object] = {
        "vector_digest": "0" * 64,
        "model": "text-embedding-3-large",
        "input_utf8_bytes": identity.utf8_bytes + 1,
        "created_at": "not-a-timestamp",
    }
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(f"UPDATE embedding_cache_entries SET {column} = ?", (values[column],))
        connection.commit()

    with pytest.raises(EmbeddingCacheCorrupt):
        cache.get(identity)


def test_invalid_vector_is_rejected_before_storage(tmp_path: Path) -> None:
    cache, _database = _cache(tmp_path)
    identity = identify_embedding_input("query")

    with pytest.raises(EmbeddingCacheError, match="vector is invalid"):
        cache.put(identity, (0.0,) * EMBEDDING_DIMENSIONS)


def test_nonfixed_identity_is_rejected(tmp_path: Path) -> None:
    cache, _database = _cache(tmp_path)
    identity = identify_embedding_input(
        "query",
        contract=EmbeddingContract(
            provider="openai",
            model="text-embedding-3-large",
            dimensions=3072,
            contract_version=1,
        ),
    )

    with pytest.raises(EmbeddingCacheError, match="incompatible"):
        cache.get(identity)


def test_absent_metadata_store_is_optional_unavailable_state(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cache = SQLiteEmbeddingCache(macos_storage_layout(home=home))

    with pytest.raises(EmbeddingCacheUnavailable):
        cache.get(identify_embedding_input("query"))
