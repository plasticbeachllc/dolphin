"""Tests for exact immutable embedding cache persistence."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kb.artifacts import EmbeddingContract, identify_embedding_input
from kb.generation import EMBEDDING_DIMENSIONS
from kb.runtime.storage import macos_storage_layout
from kb.services.workspace_registry import WorkspaceRegistry
from kb.store import embedding_cache as embedding_cache_module
from kb.store.embedding_cache import (
    EmbeddingCacheCorrupt,
    EmbeddingCacheError,
    EmbeddingCacheUnavailable,
    SQLiteEmbeddingCache,
)


def _cache(
    tmp_path: Path,
    *,
    clock: Callable[[], datetime] | None = None,
) -> tuple[SQLiteEmbeddingCache, Path]:
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
    return SQLiteEmbeddingCache(layout, clock=clock or (lambda: now)), layout.metadata_db


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
            "SELECT cache_key, provider, model, dimensions, contract_version, length(vector) "
            "FROM embedding_cache_entries"
        ).fetchone()
        eviction_index = connection.execute(
            "SELECT name FROM pragma_index_list('embedding_cache_entries') "
            "WHERE name = 'embedding_cache_entries_created'"
        ).fetchone()
        eviction_columns = connection.execute(
            "SELECT name FROM pragma_index_info('embedding_cache_entries_created') ORDER BY seqno"
        ).fetchall()
        columns = {column[1] for column in connection.execute("PRAGMA table_info(embedding_cache_entries)")}
    assert row is not None
    assert row[1:] == ("openai", "text-embedding-3-small", 1536, 1, 6144)
    assert row[0] != identity.cache_key
    assert database.parent.joinpath("query-cache.key").stat().st_mode & 0o077 == 0
    assert database.parent.joinpath("query-cache.key").read_bytes() not in database.read_bytes()
    assert "input_utf8_bytes" not in columns
    assert eviction_index == ("embedding_cache_entries_created",)
    assert eviction_columns == [("created_at",), ("cache_key",)]


def test_exact_miss_does_not_accept_another_input(tmp_path: Path) -> None:
    cache, _database = _cache(tmp_path)
    first = identify_embedding_input("first query")
    second = identify_embedding_input("second query")
    cache.put(first, _vector())

    assert cache.get(second) is None


def test_same_query_has_unlinkable_durable_keys_across_installations(tmp_path: Path) -> None:
    roots = (tmp_path / "first", tmp_path / "second")
    for root in roots:
        root.mkdir()
    first_cache, first_database = _cache(roots[0])
    second_cache, second_database = _cache(roots[1])
    identity = identify_embedding_input("likely sensitive query")

    first_cache.put(identity, _vector())
    second_cache.put(identity, _vector())

    with sqlite3.connect(first_database) as connection:
        first_key = connection.execute("SELECT cache_key FROM embedding_cache_entries").fetchone()[0]
    with sqlite3.connect(second_database) as connection:
        second_key = connection.execute("SELECT cache_key FROM embedding_cache_entries").fetchone()[0]
    assert first_key != identity.cache_key
    assert second_key != identity.cache_key
    assert first_key != second_key


def test_missing_secret_for_populated_cache_fails_closed(tmp_path: Path) -> None:
    cache, database = _cache(tmp_path)
    identity = identify_embedding_input("query")
    cache.put(identity, _vector())
    database.parent.joinpath("query-cache.key").unlink()
    fresh = SQLiteEmbeddingCache(macos_storage_layout(home=database.parents[3]))

    with pytest.raises(EmbeddingCacheCorrupt, match="identity secret is corrupt"):
        fresh.get(identity)


def test_first_valid_writer_wins_an_idempotent_or_racing_put(tmp_path: Path) -> None:
    cache, _database = _cache(tmp_path)
    identity = identify_embedding_input("same exact query")

    first = cache.put(identity, _vector(0.125))
    repeated = cache.put(identity, _vector(0.25))

    assert repeated == first
    assert repeated.vector != _vector(0.25)


def test_new_entries_transactionally_prune_expired_and_oldest_cache_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(embedding_cache_module, "_MAX_CACHE_ENTRIES", 2)
    times = iter(
        (
            datetime(2026, 8, 1, tzinfo=UTC),
            datetime(2026, 8, 2, tzinfo=UTC),
            datetime(2026, 8, 3, tzinfo=UTC),
            datetime(2026, 8, 3, tzinfo=UTC),
            datetime(2026, 8, 3, tzinfo=UTC),
            datetime(2026, 8, 3, tzinfo=UTC),
        )
    )
    cache, database = _cache(tmp_path, clock=lambda: next(times))
    identities = tuple(identify_embedding_input(f"query {index}") for index in range(3))

    for identity in identities:
        cache.put(identity, _vector())

    assert cache.get(identities[0]) is None
    assert cache.get(identities[1]) is not None
    assert cache.get(identities[2]) is not None
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM embedding_cache_entries").fetchone() == (2,)


def test_new_entry_prunes_expired_cache_rows(tmp_path: Path) -> None:
    times = iter(
        (
            datetime(2026, 6, 1, tzinfo=UTC),
            datetime(2026, 8, 1, tzinfo=UTC),
            datetime(2026, 8, 1, tzinfo=UTC),
            datetime(2026, 8, 1, tzinfo=UTC),
        )
    )
    cache, database = _cache(tmp_path, clock=lambda: next(times))
    expired = identify_embedding_input("expired query")
    current = identify_embedding_input("current query")

    cache.put(expired, _vector())
    cache.put(current, _vector())

    assert cache.get(expired) is None
    assert cache.get(current) is not None
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM embedding_cache_entries").fetchone() == (1,)


def test_expired_entry_is_a_read_miss_without_mutating_cache_state(tmp_path: Path) -> None:
    observed_at = [datetime(2026, 6, 1, tzinfo=UTC)]
    cache, database = _cache(tmp_path, clock=lambda: observed_at[0])
    identity = identify_embedding_input("expired query")
    cache.put(identity, _vector())
    observed_at[0] = datetime(2026, 7, 2, tzinfo=UTC)

    assert cache.get(identity) is None
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM embedding_cache_entries").fetchone() == (1,)


@pytest.mark.parametrize("column", ["vector_digest", "model", "contract_version", "created_at"])
def test_corrupt_persisted_binding_fails_closed(tmp_path: Path, column: str) -> None:
    cache, database = _cache(tmp_path)
    identity = identify_embedding_input("query")
    cache.put(identity, _vector())
    values: dict[str, object] = {
        "vector_digest": "0" * 64,
        "model": "text-embedding-3-large",
        "contract_version": identity.contract_version + 1,
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


def test_bounded_sqlite_contention_is_optional_unavailability(tmp_path: Path) -> None:
    cache, database = _cache(tmp_path)
    with sqlite3.connect(database, isolation_level=None) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        with pytest.raises(EmbeddingCacheUnavailable):
            cache.put(identify_embedding_input("query"), _vector())


def test_missing_cache_table_is_structural_corruption_not_optional_unavailability(tmp_path: Path) -> None:
    cache, database = _cache(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE embedding_cache_entries")
        connection.commit()

    with pytest.raises(EmbeddingCacheCorrupt, match="database is corrupt"):
        cache.get(identify_embedding_input("query"))


def test_malformed_database_is_structural_corruption_not_optional_unavailability(tmp_path: Path) -> None:
    cache, database = _cache(tmp_path)
    database.write_bytes(b"not a sqlite database")

    with pytest.raises(EmbeddingCacheCorrupt, match="database is corrupt"):
        cache.get(identify_embedding_input("query"))
