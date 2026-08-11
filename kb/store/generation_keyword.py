"""SQLite FTS5 retrieval scoped to one live published-generation reader lease."""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from itertools import groupby
from pathlib import Path

from pydantic import ValidationError

from kb.generation_keyword import (
    MAX_KEYWORD_POSTINGS_PER_QUERY,
    MAX_KEYWORD_QUERY_LENGTH,
    MAX_KEYWORD_QUERY_TERMS,
    MAX_KEYWORD_RESULTS,
    GenerationKeywordError,
    GenerationKeywordQueryTooBroad,
    GenerationKeywordTimeout,
    GenerationKeywordUnavailable,
    KeywordSearchHit,
    identify_generation_keyword_index,
)
from kb.runtime.schema import METADATA_SCHEMA_VERSION
from kb.runtime.storage import StorageLayout, StorageLayoutError
from kb.search_scope import SearchScope

_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 1_000
_KEYWORD_QUERY_TIMEOUT_SECONDS = 8.0
_SQLITE_PROGRESS_STEPS = 1_000
_PRIVATE_ID_MAX_LENGTH = 128
_WORD_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
_UNFILTERED_SCOPE = SearchScope(paths=(), exclude_paths=(), languages=())

type _KeywordPostingRow = tuple[str, str, str, int] | tuple[str, str, str, int, str, str]


class SQLiteGenerationKeywordStore:
    """Return lexical candidates only from an exact live published snapshot."""

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

    def search(
        self,
        read_lease_id: str,
        query: str,
        *,
        scope: SearchScope = _UNFILTERED_SCOPE,
        limit: int,
    ) -> tuple[KeywordSearchHit, ...]:
        _bounded_id(read_lease_id, "generation read lease ID")
        if not isinstance(scope, SearchScope):
            raise GenerationKeywordError("Dolphin keyword search scope is invalid")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_KEYWORD_RESULTS:
            raise GenerationKeywordError("Dolphin keyword result limit is invalid")
        query_terms = _prepare_query(query)
        observed_at = _timestamp(self._clock())
        deadline = self._monotonic() + _KEYWORD_QUERY_TIMEOUT_SECONDS
        timed_out = False

        def interrupt_after_deadline() -> int:
            nonlocal timed_out
            if self._monotonic() >= deadline:
                timed_out = True
                return 1
            return 0

        with self._connection() as connection:
            connection.set_progress_handler(interrupt_after_deadline, _SQLITE_PROGRESS_STEPS)
            try:
                connection.execute("BEGIN")
                published_scope = _require_live_published_scope(connection, read_lease_id, observed_at)
                _require_validated_keyword_binding(connection, published_scope)
                if not query_terms:
                    connection.commit()
                    return ()
                postings = _verified_query_postings(
                    connection,
                    published_scope.generation_id,
                    query_terms,
                    search_scope=scope,
                )
                connection.commit()
            except sqlite3.OperationalError as exc:
                if timed_out:
                    raise GenerationKeywordTimeout("Dolphin keyword retrieval timed out") from exc
                raise
            finally:
                connection.set_progress_handler(None, 0)
        try:
            scores: dict[str, int] = {}
            for _term, chunk_instance_id, _column, _offset in postings:
                scores[chunk_instance_id] = scores.get(chunk_instance_id, 0) + 1
            return tuple(
                KeywordSearchHit(
                    chunk_instance_id=chunk_instance_id,
                    score=float(score),
                )
                for chunk_instance_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
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
               keyword_revision, validated_keyword_revision, validated_commit_digest, validated_fts_digest
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
    validated_commit_digest = row[6]
    validated_fts_digest = row[7]
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
        or validated_commit_digest != commit_digest
        or not isinstance(validated_fts_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", validated_fts_digest) is None
    ):
        raise GenerationKeywordError("Dolphin published keyword binding is corrupt")


def _verified_query_postings(
    connection: sqlite3.Connection,
    generation_id: str,
    query_terms: tuple[str, ...],
    *,
    search_scope: SearchScope,
) -> tuple[tuple[str, str, str, int], ...]:
    placeholders = ", ".join("?" for _term in query_terms)
    rows = connection.execute(
        f"""
        SELECT v.term, d.chunk_instance_id, v.col, v.offset, d.relative_path, d.language
        FROM generation_keyword_vocabulary AS v
        JOIN generation_keyword_documents AS d ON d.document_rowid = v.doc
        WHERE d.generation_id = ? AND v.term IN ({placeholders})
        LIMIT ?
        """,
        (generation_id, *query_terms, MAX_KEYWORD_POSTINGS_PER_QUERY + 1),
    ).fetchall()
    if len(rows) > MAX_KEYWORD_POSTINGS_PER_QUERY:
        raise GenerationKeywordQueryTooBroad("Dolphin keyword query is too broad; use rarer or more specific terms")
    scoped_rows = tuple(
        sorted(
            (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                int(row[3]),
                str(row[4]),
                str(row[5]),
            )
            for row in rows
        )
    )
    observed = _term_commits_from_rows(generation_id, iter(scoped_rows))
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
    return tuple(row[:4] for row in scoped_rows if search_scope.matches(row[4], row[5]))


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
        if len(terms) > MAX_KEYWORD_QUERY_TERMS:
            raise GenerationKeywordQueryTooBroad(
                "Dolphin keyword query has too many unique terms; use fewer or more specific terms"
            )
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
            prepared = tuple(
                str(row[0]) for row in tokenizer.execute("SELECT term FROM query_vocabulary ORDER BY term")
            )
            if len(prepared) > MAX_KEYWORD_QUERY_TERMS:
                raise GenerationKeywordQueryTooBroad(
                    "Dolphin keyword query has too many unique terms; use fewer or more specific terms"
                )
            return prepared
    except sqlite3.Error as exc:
        raise GenerationKeywordError("Dolphin keyword query tokenizer is unavailable") from exc


def _term_commits_from_rows(
    generation_id: str,
    rows: Iterable[_KeywordPostingRow] | sqlite3.Cursor,
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
