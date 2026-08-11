"""Exact filtered published-scope counts under retained generation reader leases."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from kb.artifacts import MAX_GENERATION_ARTIFACTS
from kb.generation import GenerationReadLease
from kb.runtime.schema import METADATA_SCHEMA_VERSION
from kb.runtime.storage import StorageLayout, StorageLayoutError
from kb.search_scope import (
    MAX_SEARCH_SCOPE_WORKSPACES,
    ResolvedSearchScope,
    SearchScope,
    SearchScopeError,
    SearchScopeTimeout,
    SearchScopeUnavailable,
    WorkspaceScopeCount,
)

_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 1_000
_SCOPE_QUERY_TIMEOUT_SECONDS = 8.0
_SQLITE_PROGRESS_STEPS = 1_000


class SQLiteSearchScopeStore:
    """Resolve source-free scope statistics from exact immutable publications."""

    def __init__(
        self,
        layout: StorageLayout,
        *,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._layout = layout
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic = monotonic or time.monotonic

    def resolve(
        self,
        leases: Sequence[GenerationReadLease],
        scope: SearchScope,
    ) -> ResolvedSearchScope:
        ordered = _validate_inputs(leases, scope)
        observed_at = _timestamp(self._clock())
        deadline = self._monotonic() + _SCOPE_QUERY_TIMEOUT_SECONDS
        timed_out = False

        def interrupt_after_deadline() -> int:
            nonlocal timed_out
            if self._monotonic() >= deadline:
                timed_out = True
                return 1
            return 0

        def membership_matches(relative_path: object, language: object) -> int:
            if not isinstance(relative_path, str) or not isinstance(language, str):
                raise SearchScopeError("Dolphin published search membership is corrupt")
            return int(scope.matches(relative_path, language))

        counts: list[WorkspaceScopeCount] = []
        with self._connection() as connection:
            connection.set_progress_handler(interrupt_after_deadline, _SQLITE_PROGRESS_STEPS)
            connection.create_function(
                "dolphin_search_scope_matches",
                2,
                membership_matches,
                deterministic=True,
            )
            try:
                connection.execute("BEGIN")
                for lease in ordered:
                    metadata_count = _require_live_validated_scope(connection, lease, observed_at)
                    if scope.filter_shape == "none":
                        searchable_chunks = metadata_count
                    else:
                        row = connection.execute(
                            """
                            SELECT count(*)
                            FROM generation_chunk_memberships
                            WHERE generation_id = ?
                              AND dolphin_search_scope_matches(relative_path, language) = 1
                            """,
                            (lease.snapshot.generation_id,),
                        ).fetchone()
                        if (
                            row is None
                            or not isinstance(row[0], int)
                            or isinstance(row[0], bool)
                            or not 0 <= row[0] <= metadata_count
                        ):
                            raise SearchScopeError("Dolphin filtered published search count is corrupt")
                        searchable_chunks = row[0]
                    counts.append(
                        WorkspaceScopeCount(
                            workspace_id=lease.snapshot.workspace_id,
                            generation_id=lease.snapshot.generation_id,
                            searchable_chunks=searchable_chunks,
                        )
                    )
                connection.commit()
            except sqlite3.OperationalError as exc:
                if timed_out:
                    raise SearchScopeTimeout("Dolphin filtered search scope resolution timed out") from exc
                raise
            finally:
                connection.set_progress_handler(None, 0)
                connection.create_function("dolphin_search_scope_matches", 2, None)

        return ResolvedSearchScope(
            scope_digest=scope.digest,
            filter_shape=scope.filter_shape,
            workspace_counts=tuple(counts),
            searchable_chunks=sum(item.searchable_chunks for item in counts),
        )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            if not self._layout.metadata_database_exists():
                raise SearchScopeUnavailable("Dolphin metadata storage is unavailable")
            target: Path | str = self._layout.metadata_db.as_uri() + "?mode=ro"
            connection = sqlite3.connect(target, uri=True, timeout=1, isolation_level=None)
        except (sqlite3.Error, StorageLayoutError) as exc:
            raise SearchScopeUnavailable("Dolphin metadata storage is unavailable") from exc
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
            connection.execute("PRAGMA query_only = ON")
            version = connection.execute("PRAGMA user_version").fetchone()
            if version is None or int(version[0]) != METADATA_SCHEMA_VERSION:
                raise SearchScopeUnavailable("Dolphin metadata schema is unavailable or incompatible")
            yield connection
        except sqlite3.Error as exc:
            raise SearchScopeError("Dolphin search scope storage is busy, unavailable, or corrupt") from exc
        finally:
            connection.close()


def _validate_inputs(
    leases: Sequence[GenerationReadLease],
    scope: SearchScope,
) -> tuple[GenerationReadLease, ...]:
    if not isinstance(scope, SearchScope):
        raise SearchScopeError("Dolphin search scope is invalid")
    if not isinstance(leases, Sequence) or isinstance(leases, (str, bytes)):
        raise SearchScopeError("Dolphin search reader lease set is invalid")
    if not 1 <= len(leases) <= MAX_SEARCH_SCOPE_WORKSPACES:
        raise SearchScopeError("Dolphin search reader lease set is invalid")
    try:
        ordered = tuple(sorted(leases, key=lambda lease: lease.snapshot.workspace_id))
    except (AttributeError, TypeError) as exc:
        raise SearchScopeError("Dolphin search reader lease set is invalid") from exc
    if (
        any(not isinstance(lease, GenerationReadLease) for lease in ordered)
        or len({lease.lease_id for lease in ordered}) != len(ordered)
        or len({lease.snapshot.workspace_id for lease in ordered}) != len(ordered)
    ):
        raise SearchScopeError("Dolphin search reader lease set is invalid")
    return ordered


def _require_live_validated_scope(
    connection: sqlite3.Connection,
    lease: GenerationReadLease,
    observed_at: str,
) -> int:
    row = connection.execute(
        """
        SELECT g.workspace_id, g.publication_id, g.generation_id, g.manifest_id,
               g.manifest_digest, m.metadata_item_count,
               m.content_revision, m.validated_content_revision
        FROM generation_reader_leases AS l
        JOIN generations AS g
          ON g.generation_id = l.generation_id
         AND g.workspace_id = l.workspace_id
         AND g.publication_id = l.publication_id
        JOIN generation_content_manifests AS m
          ON m.generation_id = g.generation_id
         AND m.manifest_id = g.manifest_id
        WHERE l.lease_id = ?
          AND l.expires_at > ?
          AND g.state = 'published'
        """,
        (lease.lease_id, observed_at),
    ).fetchone()
    snapshot = lease.snapshot
    if row is None or tuple(row[:5]) != (
        snapshot.workspace_id,
        snapshot.publication_id,
        snapshot.generation_id,
        snapshot.manifest_id,
        snapshot.manifest_digest,
    ):
        raise SearchScopeUnavailable("Dolphin published search scope is unavailable or changed")
    metadata_count, content_revision, validated_revision = row[5:]
    if (
        not isinstance(metadata_count, int)
        or isinstance(metadata_count, bool)
        or not 0 <= metadata_count <= MAX_GENERATION_ARTIFACTS
        or metadata_count != snapshot.metadata_item_count
        or not isinstance(content_revision, int)
        or isinstance(content_revision, bool)
        or content_revision < 1
        or content_revision != validated_revision
    ):
        raise SearchScopeError("Dolphin published search scope binding is corrupt")
    return metadata_count


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise SearchScopeError("Dolphin search scope timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()
