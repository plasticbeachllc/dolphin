"""Tests for the migration registry module (kb.migrations.registry)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from kb.migrations.registry import LATEST_SCHEMA_VERSION, SCHEMA_MIGRATIONS, SchemaMigration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_db_with_schema_version_table(db_path: Path) -> sqlite3.Connection:
    """Create a fresh SQLite database with only the schema_version table."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        INSERT INTO schema_version (id, version, updated_at)
        VALUES (1, 0, datetime('now'))
        ON CONFLICT(id) DO NOTHING
        """
    )
    conn.commit()
    return conn


def _get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    assert row is not None
    return int(row[0])


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "UPDATE schema_version SET version = ?, updated_at = datetime('now') WHERE id = 1",
        (version,),
    )
    conn.commit()


def _apply_pending_migrations(
    conn: sqlite3.Connection,
    migrations: tuple[SchemaMigration, ...] = SCHEMA_MIGRATIONS,
) -> list[str]:
    """Simplified migration runner that mirrors sqlite_meta._run_pending_schema_migrations."""
    current_version = _get_schema_version(conn)
    applied: list[str] = []
    for migration in migrations:
        if migration.version <= current_version:
            continue
        note = migration.apply(conn)
        conn.execute(
            "UPDATE schema_version SET version = ?, updated_at = datetime('now') WHERE id = 1",
            (migration.version,),
        )
        conn.commit()
        label = f"v{migration.version}:{migration.name}"
        if note:
            label = f"{label} ({note})"
        applied.append(label)
        current_version = migration.version
    return applied


# ---------------------------------------------------------------------------
# Tests — registry metadata
# ---------------------------------------------------------------------------


class TestRegistryMetadata:
    """Verify structural properties of the migration registry."""

    def test_schema_migrations_is_non_empty_tuple(self) -> None:
        assert isinstance(SCHEMA_MIGRATIONS, tuple)
        assert len(SCHEMA_MIGRATIONS) >= 1

    def test_latest_schema_version_matches_last_migration(self) -> None:
        assert LATEST_SCHEMA_VERSION == SCHEMA_MIGRATIONS[-1].version

    def test_migration_versions_are_strictly_increasing(self) -> None:
        versions = [m.version for m in SCHEMA_MIGRATIONS]
        for i in range(1, len(versions)):
            assert versions[i] > versions[i - 1], (
                f"Migration versions must be strictly increasing: v{versions[i - 1]} is not less than v{versions[i]}"
            )

    def test_migration_versions_start_at_one(self) -> None:
        assert SCHEMA_MIGRATIONS[0].version == 1

    def test_each_migration_has_name_and_callable_apply(self) -> None:
        for m in SCHEMA_MIGRATIONS:
            assert isinstance(m.name, str) and len(m.name) > 0
            assert callable(m.apply)

    def test_schema_migration_is_frozen_dataclass(self) -> None:
        m = SCHEMA_MIGRATIONS[0]
        with pytest.raises(AttributeError):
            m.version = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests — version tracking
# ---------------------------------------------------------------------------


class TestVersionTracking:
    """Verify that the migration runner updates schema_version correctly."""

    def test_version_starts_at_zero(self, tmp_path: Path) -> None:
        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            assert _get_schema_version(conn) == 0
        finally:
            conn.close()

    def test_version_advances_after_migration(self, tmp_path: Path) -> None:
        """Running migrations bumps the stored version to LATEST_SCHEMA_VERSION."""
        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            dummy = SchemaMigration(version=1, name="bump_only", apply=lambda c: None)
            _apply_pending_migrations(conn, (dummy,))
            assert _get_schema_version(conn) == 1
        finally:
            conn.close()

    def test_version_advances_through_multiple_migrations(self, tmp_path: Path) -> None:
        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m1 = SchemaMigration(version=1, name="first", apply=lambda c: "done-1")
            m2 = SchemaMigration(version=2, name="second", apply=lambda c: "done-2")
            m3 = SchemaMigration(version=3, name="third", apply=lambda c: "done-3")
            applied = _apply_pending_migrations(conn, (m1, m2, m3))
            assert _get_schema_version(conn) == 3
            assert len(applied) == 3
            assert "v1:first (done-1)" in applied[0]
            assert "v2:second (done-2)" in applied[1]
            assert "v3:third (done-3)" in applied[2]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Tests — migration application
# ---------------------------------------------------------------------------


class TestMigrationApplication:
    """Verify that migration functions are actually invoked."""

    def test_migration_apply_is_called(self, tmp_path: Path) -> None:
        call_log: list[int] = []

        def fake_apply(conn: sqlite3.Connection) -> str:
            call_log.append(1)
            return "applied"

        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m = SchemaMigration(version=1, name="fake", apply=fake_apply)
            applied = _apply_pending_migrations(conn, (m,))
            assert len(call_log) == 1
            assert len(applied) == 1
            assert "applied" in applied[0]
        finally:
            conn.close()

    def test_migration_receives_connection(self, tmp_path: Path) -> None:
        received_conn: list[sqlite3.Connection] = []

        def capture_conn(conn: sqlite3.Connection) -> str | None:
            received_conn.append(conn)
            return None

        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m = SchemaMigration(version=1, name="capture", apply=capture_conn)
            _apply_pending_migrations(conn, (m,))
            assert len(received_conn) == 1
            assert received_conn[0] is conn
        finally:
            conn.close()

    def test_migration_note_none_omits_parenthetical(self, tmp_path: Path) -> None:
        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m = SchemaMigration(version=1, name="silent", apply=lambda c: None)
            applied = _apply_pending_migrations(conn, (m,))
            assert applied == ["v1:silent"]
        finally:
            conn.close()

    def test_migration_note_included_in_label(self, tmp_path: Path) -> None:
        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m = SchemaMigration(version=1, name="loud", apply=lambda c: "hello world")
            applied = _apply_pending_migrations(conn, (m,))
            assert applied == ["v1:loud (hello world)"]
        finally:
            conn.close()

    def test_skips_already_applied_migrations(self, tmp_path: Path) -> None:
        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            _set_schema_version(conn, 2)
            call_count: list[int] = []
            m1 = SchemaMigration(version=1, name="old", apply=lambda c: call_count.append(1) or "x")
            m2 = SchemaMigration(version=2, name="current", apply=lambda c: call_count.append(2) or "x")
            m3 = SchemaMigration(version=3, name="new", apply=lambda c: call_count.append(3) or "y")
            applied = _apply_pending_migrations(conn, (m1, m2, m3))
            assert call_count == [3]
            assert len(applied) == 1
            assert _get_schema_version(conn) == 3
        finally:
            conn.close()

    def test_no_migrations_when_up_to_date(self, tmp_path: Path) -> None:
        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            _set_schema_version(conn, 5)
            m1 = SchemaMigration(version=1, name="a", apply=lambda c: "x")
            m2 = SchemaMigration(version=5, name="e", apply=lambda c: "x")
            applied = _apply_pending_migrations(conn, (m1, m2))
            assert applied == []
            assert _get_schema_version(conn) == 5
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Tests — idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Verify that running migration logic twice does not cause errors or duplicate effects."""

    def test_running_migrations_twice_is_idempotent(self, tmp_path: Path) -> None:
        call_count: list[int] = []

        def counting_apply(conn: sqlite3.Connection) -> str:
            call_count.append(1)
            conn.execute("CREATE TABLE IF NOT EXISTS idempotent_test (id INTEGER PRIMARY KEY)")
            return "created"

        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m = SchemaMigration(version=1, name="idem", apply=counting_apply)

            first_run = _apply_pending_migrations(conn, (m,))
            assert len(first_run) == 1
            assert _get_schema_version(conn) == 1

            second_run = _apply_pending_migrations(conn, (m,))
            assert len(second_run) == 0
            assert _get_schema_version(conn) == 1

            # Apply was only called once because version gating prevents re-running.
            assert len(call_count) == 1
        finally:
            conn.close()

    def test_idempotency_with_multiple_migrations(self, tmp_path: Path) -> None:
        counts = {"m1": 0, "m2": 0}

        def apply_m1(conn: sqlite3.Connection) -> str:
            counts["m1"] += 1
            return "m1"

        def apply_m2(conn: sqlite3.Connection) -> str:
            counts["m2"] += 1
            return "m2"

        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m1 = SchemaMigration(version=1, name="first", apply=apply_m1)
            m2 = SchemaMigration(version=2, name="second", apply=apply_m2)

            first_run = _apply_pending_migrations(conn, (m1, m2))
            assert len(first_run) == 2
            assert counts == {"m1": 1, "m2": 1}

            second_run = _apply_pending_migrations(conn, (m1, m2))
            assert len(second_run) == 0
            assert counts == {"m1": 1, "m2": 1}
        finally:
            conn.close()

    def test_partial_then_complete(self, tmp_path: Path) -> None:
        """Apply v1, then later apply both v1 and v2. Only v2 should run."""
        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m1 = SchemaMigration(version=1, name="first", apply=lambda c: "one")
            m2 = SchemaMigration(version=2, name="second", apply=lambda c: "two")

            first_batch = _apply_pending_migrations(conn, (m1,))
            assert len(first_batch) == 1
            assert _get_schema_version(conn) == 1

            second_batch = _apply_pending_migrations(conn, (m1, m2))
            assert len(second_batch) == 1
            assert "v2:second" in second_batch[0]
            assert _get_schema_version(conn) == 2
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Tests — error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Verify behavior when a migration function raises an exception."""

    def test_error_in_migration_propagates(self, tmp_path: Path) -> None:
        def bad_apply(conn: sqlite3.Connection) -> str:
            raise RuntimeError("migration exploded")

        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m = SchemaMigration(version=1, name="bad", apply=bad_apply)
            with pytest.raises(RuntimeError, match="migration exploded"):
                _apply_pending_migrations(conn, (m,))
        finally:
            conn.close()

    def test_version_not_advanced_on_failure(self, tmp_path: Path) -> None:
        """If a migration raises, the schema version should not have been bumped past it."""

        def fail_at_v2(conn: sqlite3.Connection) -> str:
            raise ValueError("v2 failed")

        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m1 = SchemaMigration(version=1, name="ok", apply=lambda c: "fine")
            m2 = SchemaMigration(version=2, name="broken", apply=fail_at_v2)

            with pytest.raises(ValueError, match="v2 failed"):
                _apply_pending_migrations(conn, (m1, m2))

            # v1 was committed, but v2 was not.
            assert _get_schema_version(conn) == 1
        finally:
            conn.close()

    def test_subsequent_migrations_not_run_after_failure(self, tmp_path: Path) -> None:
        call_log: list[str] = []

        def ok_apply(conn: sqlite3.Connection) -> str:
            call_log.append("v1")
            return "ok"

        def bad_apply(conn: sqlite3.Connection) -> str:
            call_log.append("v2")
            raise RuntimeError("boom")

        def never_apply(conn: sqlite3.Connection) -> str:
            call_log.append("v3")
            return "should not reach"

        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m1 = SchemaMigration(version=1, name="ok", apply=ok_apply)
            m2 = SchemaMigration(version=2, name="bad", apply=bad_apply)
            m3 = SchemaMigration(version=3, name="never", apply=never_apply)

            with pytest.raises(RuntimeError, match="boom"):
                _apply_pending_migrations(conn, (m1, m2, m3))

            assert call_log == ["v1", "v2"]
        finally:
            conn.close()

    def test_retry_after_failure_resumes_from_correct_version(self, tmp_path: Path) -> None:
        attempt = {"count": 0}

        def flaky_apply(conn: sqlite3.Connection) -> str:
            attempt["count"] += 1
            if attempt["count"] == 1:
                raise RuntimeError("transient error")
            return "succeeded on retry"

        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m1 = SchemaMigration(version=1, name="stable", apply=lambda c: "ok")
            m2 = SchemaMigration(version=2, name="flaky", apply=flaky_apply)

            with pytest.raises(RuntimeError, match="transient error"):
                _apply_pending_migrations(conn, (m1, m2))
            assert _get_schema_version(conn) == 1

            # Retry — v1 should be skipped, v2 should now succeed.
            applied = _apply_pending_migrations(conn, (m1, m2))
            assert _get_schema_version(conn) == 2
            assert len(applied) == 1
            assert "flaky" in applied[0]
        finally:
            conn.close()

    def test_migration_with_invalid_sql_raises(self, tmp_path: Path) -> None:
        def sql_error_apply(conn: sqlite3.Connection) -> str:
            conn.execute("THIS IS NOT VALID SQL")
            return "never"

        conn = _create_db_with_schema_version_table(tmp_path / "test.db")
        try:
            m = SchemaMigration(version=1, name="badsql", apply=sql_error_apply)
            with pytest.raises(sqlite3.OperationalError):
                _apply_pending_migrations(conn, (m,))
        finally:
            conn.close()
