"""SQLite FTS5 retrieval scoped to one live published-generation reader lease."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from kb.generation_keyword import (
    MAX_KEYWORD_QUERY_LENGTH,
    MAX_KEYWORD_QUERY_TERMS,
    MAX_KEYWORD_RESULTS,
    GenerationKeywordError,
    GenerationKeywordUnavailable,
    KeywordSearchHit,
)
from kb.runtime.schema import METADATA_SCHEMA_VERSION
from kb.runtime.storage import StorageLayout, StorageLayoutError

_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 1_000
_PRIVATE_ID_MAX_LENGTH = 128
_WORD_PATTERN = re.compile(r"\w+", flags=re.UNICODE)


class SQLiteGenerationKeywordStore:
    """Return lexical candidates only from an exact live published snapshot."""

    def __init__(
        self,
        layout: StorageLayout,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._layout = layout
        self._clock = clock or (lambda: datetime.now(UTC))

    def search(self, read_lease_id: str, query: str, *, limit: int) -> tuple[KeywordSearchHit, ...]:
        _bounded_id(read_lease_id, "generation read lease ID")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_KEYWORD_RESULTS:
            raise GenerationKeywordError("Dolphin keyword result limit is invalid")
        fts_query = _prepare_query(query)
        observed_at = _timestamp(self._clock())
        with self._connection() as connection:
            connection.execute("BEGIN")
            scope = _require_live_published_scope(connection, read_lease_id, observed_at)
            _require_validated_keyword_binding(connection, scope)
            _require_fts_integrity(connection)
            if not fts_query:
                connection.rollback()
                return ()
            rows = connection.execute(
                """
                SELECT d.chunk_instance_id, bm25(generation_keyword_fts) AS raw_score
                FROM generation_keyword_fts
                JOIN generation_keyword_documents AS d
                  ON d.document_rowid = generation_keyword_fts.rowid
                WHERE generation_keyword_fts MATCH ?
                  AND d.generation_id = ?
                ORDER BY raw_score ASC, d.chunk_instance_id ASC
                LIMIT ?
                """,
                (fts_query, scope.generation_id, limit),
            ).fetchall()
            connection.rollback()
        try:
            return tuple(
                KeywordSearchHit(
                    chunk_instance_id=row[0],
                    score=max(0.0, -float(row[1])),
                )
                for row in rows
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise GenerationKeywordError("Dolphin keyword result metadata is corrupt") from exc

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            if not self._layout.metadata_database_exists():
                raise GenerationKeywordUnavailable("Dolphin metadata storage is unavailable")
            # FTS5 exposes its non-mutating integrity check through INSERT syntax,
            # so this connection must permit that command without creating a
            # missing database after the existence check above.
            target: Path | str = self._layout.metadata_db.as_uri() + "?mode=rw"
            connection = sqlite3.connect(target, uri=True, timeout=1, isolation_level=None)
        except (sqlite3.Error, StorageLayoutError) as exc:
            raise GenerationKeywordUnavailable("Dolphin metadata storage is unavailable") from exc
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
            version = connection.execute("PRAGMA user_version").fetchone()
            if version is None or int(version[0]) != METADATA_SCHEMA_VERSION:
                raise GenerationKeywordUnavailable("Dolphin metadata schema is unavailable or incompatible")
            yield connection
        except sqlite3.Error as exc:
            raise GenerationKeywordError("Dolphin keyword storage is busy, unavailable, or corrupt") from exc
        finally:
            connection.close()


class _PublishedKeywordScope:
    __slots__ = ("generation_id", "manifest_id", "manifest_digest", "keyword_item_count")

    def __init__(
        self,
        generation_id: str,
        manifest_id: str,
        manifest_digest: str,
        keyword_item_count: int,
    ) -> None:
        self.generation_id = generation_id
        self.manifest_id = manifest_id
        self.manifest_digest = manifest_digest
        self.keyword_item_count = keyword_item_count


def _require_live_published_scope(
    connection: sqlite3.Connection,
    lease_id: str,
    observed_at: str,
) -> _PublishedKeywordScope:
    row = connection.execute(
        """
        SELECT g.generation_id, g.manifest_id, g.manifest_digest, g.keyword_item_count
        FROM generation_reader_leases AS l
        JOIN generations AS g
          ON g.generation_id = l.generation_id
         AND g.workspace_id = l.workspace_id
         AND g.publication_id = l.publication_id
        WHERE l.lease_id = ?
          AND l.expires_at > ?
          AND g.state = 'published'
        """,
        (lease_id, observed_at),
    ).fetchone()
    if row is None:
        raise GenerationKeywordUnavailable("Dolphin generation read lease is unavailable or expired")
    if (
        not isinstance(row[0], str)
        or not row[0]
        or not isinstance(row[1], str)
        or not row[1]
        or not isinstance(row[2], str)
        or len(row[2]) != 64
        or not isinstance(row[3], int)
        or isinstance(row[3], bool)
        or row[3] < 0
    ):
        raise GenerationKeywordError("Dolphin published keyword scope is corrupt")
    return _PublishedKeywordScope(row[0], row[1], row[2], row[3])


def _require_validated_keyword_binding(
    connection: sqlite3.Connection,
    scope: _PublishedKeywordScope,
) -> None:
    row = connection.execute(
        """
        SELECT manifest_id, manifest_digest, item_count,
               keyword_revision, validated_keyword_revision
        FROM generation_keyword_commits
        WHERE generation_id = ?
        """,
        (scope.generation_id,),
    ).fetchone()
    if row is None or tuple(row[:3]) != (
        scope.manifest_id,
        scope.manifest_digest,
        scope.keyword_item_count,
    ):
        raise GenerationKeywordError("Dolphin published keyword binding is corrupt")
    revision = row[3]
    validated_revision = row[4]
    if (
        not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 1
        or not isinstance(validated_revision, int)
        or isinstance(validated_revision, bool)
        or validated_revision < 1
        or revision != validated_revision
    ):
        raise GenerationKeywordError("Dolphin published keyword binding is corrupt")


def _require_fts_integrity(connection: sqlite3.Connection) -> None:
    """Fail closed unless FTS5 exactly matches its external content table."""
    connection.execute(
        """
        INSERT INTO generation_keyword_fts(generation_keyword_fts, rank)
        VALUES('integrity-check', 1)
        """
    )


def _prepare_query(query: str) -> str:
    if (
        not isinstance(query, str)
        or "\x00" in query
        or len(query) > MAX_KEYWORD_QUERY_LENGTH
        or len(query.encode("utf-8")) > MAX_KEYWORD_QUERY_LENGTH
    ):
        raise GenerationKeywordError("Dolphin keyword query is invalid")
    terms = []
    seen = set()
    for match in _WORD_PATTERN.finditer(query):
        term = match.group(0)
        folded = term.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        terms.append(term)
        if len(terms) == MAX_KEYWORD_QUERY_TERMS:
            break
    return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


def _bounded_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or len(value) > _PRIVATE_ID_MAX_LENGTH or "\x00" in value:
        raise GenerationKeywordError(f"Dolphin {label} is invalid")


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise GenerationKeywordError("Dolphin generation keyword timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()
