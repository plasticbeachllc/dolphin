"""SQLite FTS5 retrieval scoped to one live published-generation reader lease."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from itertools import groupby
from pathlib import Path

from pydantic import ValidationError

from kb.generation_keyword import (
    MAX_KEYWORD_QUERY_LENGTH,
    MAX_KEYWORD_QUERY_TERMS,
    MAX_KEYWORD_RESULTS,
    GenerationKeywordError,
    GenerationKeywordUnavailable,
    KeywordSearchHit,
    identify_generation_keyword_index,
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
        query_terms = _prepare_query(query)
        observed_at = _timestamp(self._clock())
        with self._connection() as connection:
            connection.execute("BEGIN")
            scope = _require_live_published_scope(connection, read_lease_id, observed_at)
            _require_validated_keyword_binding(connection, scope)
            if not query_terms:
                connection.commit()
                return ()
            _require_query_term_commits(connection, scope.generation_id, query_terms)
            placeholders = ", ".join("?" for _term in query_terms)
            rows = connection.execute(
                f"""
                SELECT d.chunk_instance_id, count(*) AS occurrence_count
                FROM generation_keyword_vocabulary AS v
                JOIN generation_keyword_documents AS d
                  ON d.document_rowid = v.doc
                WHERE d.generation_id = ?
                  AND v.term IN ({placeholders})
                GROUP BY d.chunk_instance_id
                ORDER BY occurrence_count DESC, d.chunk_instance_id ASC
                LIMIT ?
                """,
                (scope.generation_id, *query_terms, limit),
            ).fetchall()
            connection.commit()
        try:
            return tuple(
                KeywordSearchHit(
                    chunk_instance_id=row[0],
                    score=float(row[1]),
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
            target: Path | str = self._layout.metadata_db.as_uri() + "?mode=ro"
            connection = sqlite3.connect(target, uri=True, timeout=1, isolation_level=None)
        except (sqlite3.Error, StorageLayoutError) as exc:
            raise GenerationKeywordUnavailable("Dolphin metadata storage is unavailable") from exc
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
            connection.execute("PRAGMA query_only = ON")
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
        SELECT manifest_id, manifest_digest, item_count, commit_digest,
               keyword_revision, validated_keyword_revision, validated_fts_digest
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
    commit_digest = row[3]
    revision = row[4]
    validated_revision = row[5]
    validated_fts_digest = row[6]
    if (
        not isinstance(commit_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", commit_digest) is None
        or not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 1
        or not isinstance(validated_revision, int)
        or isinstance(validated_revision, bool)
        or validated_revision < 1
        or revision != validated_revision
        or not isinstance(validated_fts_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", validated_fts_digest) is None
    ):
        raise GenerationKeywordError("Dolphin published keyword binding is corrupt")


def _require_query_term_commits(
    connection: sqlite3.Connection,
    generation_id: str,
    query_terms: tuple[str, ...],
) -> None:
    placeholders = ", ".join("?" for _term in query_terms)
    rows = connection.execute(
        f"""
        SELECT v.term, d.chunk_instance_id, v.col, v.offset
        FROM generation_keyword_vocabulary AS v
        JOIN generation_keyword_documents AS d ON d.document_rowid = v.doc
        WHERE d.generation_id = ? AND v.term IN ({placeholders})
        ORDER BY v.term, d.chunk_instance_id, v.col, v.offset
        """,
        (generation_id, *query_terms),
    )
    observed = _term_commits_from_rows(generation_id, rows)
    expected_rows = connection.execute(
        f"""
        SELECT term, posting_digest, posting_count
        FROM generation_keyword_term_commits
        WHERE generation_id = ? AND term IN ({placeholders})
        """,
        (generation_id, *query_terms),
    ).fetchall()
    expected = {str(row[0]): (str(row[1]), int(row[2])) for row in expected_rows}
    if observed != expected:
        raise GenerationKeywordError("Dolphin published keyword index is corrupt")


def _prepare_query(query: str) -> tuple[str, ...]:
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
    if not terms:
        return ()
    try:
        with sqlite3.connect(":memory:") as tokenizer:
            tokenizer.execute(
                """
                CREATE VIRTUAL TABLE query_terms USING fts5(
                    text,
                    tokenize = 'unicode61 remove_diacritics 2'
                )
                """
            )
            tokenizer.execute("CREATE VIRTUAL TABLE query_vocabulary USING fts5vocab(query_terms, 'row')")
            tokenizer.execute("INSERT INTO query_terms(text) VALUES (?)", ("\n".join(terms),))
            return tuple(str(row[0]) for row in tokenizer.execute("SELECT term FROM query_vocabulary ORDER BY term"))
    except sqlite3.Error as exc:
        raise GenerationKeywordError("Dolphin keyword query tokenizer is unavailable") from exc


def _term_commits_from_rows(
    generation_id: str,
    rows: sqlite3.Cursor,
) -> dict[str, tuple[str, int]]:
    commits: dict[str, tuple[str, int]] = {}
    for term, grouped in groupby(rows, key=lambda row: row[0]):
        count = 0

        def postings() -> Iterator[tuple[str, str, str, int]]:
            nonlocal count
            for row in grouped:
                count += 1
                yield (str(row[1]), str(row[0]), str(row[2]), int(row[3]))

        digest = identify_generation_keyword_index(generation_id, postings())
        commits[str(term)] = (digest, count)
    return commits


def _bounded_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or len(value) > _PRIVATE_ID_MAX_LENGTH or "\x00" in value:
        raise GenerationKeywordError(f"Dolphin {label} is invalid")


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise GenerationKeywordError("Dolphin generation keyword timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()
