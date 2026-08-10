"""Exact immutable SQLite cache for fixed-contract embedding vectors."""

from __future__ import annotations

import hashlib
import sqlite3
import struct
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from kb.artifacts import EMBEDDING_INPUT_FORMAT, EmbeddingInputIdentity
from kb.generation import EMBEDDING_CONTRACT_VERSION, EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, EMBEDDING_PROVIDER
from kb.generation_vector import canonicalize_embedding_vector
from kb.query_embedding import CachedEmbedding
from kb.runtime.schema import METADATA_SCHEMA_VERSION
from kb.runtime.storage import StorageLayout, StorageLayoutError

_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 250
_VECTOR_BYTES = struct.Struct(f"!{EMBEDDING_DIMENSIONS}f")
_VECTOR_DIGEST_DOMAIN = b"dolphin:embedding-cache-vector:v1\x00"


class EmbeddingCacheError(RuntimeError):
    """Embedding cache state could not be used safely."""


class EmbeddingCacheCorrupt(EmbeddingCacheError):
    """A persisted cache entry violates its exact immutable contract."""


class EmbeddingCacheUnavailable(EmbeddingCacheError):
    """Optional embedding cache storage is currently unavailable."""


class SQLiteEmbeddingCache:
    """Store no source text: only exact input identity and canonical vector bytes."""

    def __init__(
        self,
        layout: StorageLayout,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._layout = layout
        self._clock = clock or (lambda: datetime.now(UTC))

    def get(self, identity: EmbeddingInputIdentity) -> CachedEmbedding | None:
        _require_fixed_identity(identity)
        with self._connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT cache_key, format, provider, model, dimensions, contract_version,
                       input_utf8_bytes, vector, vector_digest, created_at
                FROM embedding_cache_entries
                WHERE cache_key = ?
                """,
                (identity.cache_key,),
            ).fetchone()
        if row is None:
            return None
        return _cached_embedding(identity, row)

    def put(self, identity: EmbeddingInputIdentity, vector: Sequence[float]) -> CachedEmbedding:
        """Install once and return the immutable winner of a concurrent insertion."""
        _require_fixed_identity(identity)
        try:
            canonical = canonicalize_embedding_vector(vector)
        except (TypeError, ValueError):
            raise EmbeddingCacheError("Dolphin embedding cache vector is invalid") from None
        payload = _VECTOR_BYTES.pack(*canonical)
        digest = _vector_digest(identity.cache_key, payload)
        created_at = _timestamp(self._clock())
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT OR IGNORE INTO embedding_cache_entries (
                        cache_key, format, provider, model, dimensions, contract_version,
                        input_utf8_bytes, vector, vector_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identity.cache_key,
                        identity.format,
                        identity.provider,
                        identity.model,
                        identity.dimensions,
                        identity.contract_version,
                        identity.utf8_bytes,
                        payload,
                        digest,
                        created_at,
                    ),
                )
                row = connection.execute(
                    """
                    SELECT cache_key, format, provider, model, dimensions, contract_version,
                           input_utf8_bytes, vector, vector_digest, created_at
                    FROM embedding_cache_entries
                    WHERE cache_key = ?
                    """,
                    (identity.cache_key,),
                ).fetchone()
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if row is None:
            raise EmbeddingCacheCorrupt("Dolphin embedding cache installation is missing")
        return _cached_embedding(identity, row)

    @contextmanager
    def _connection(self, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            if not self._layout.metadata_database_exists():
                raise EmbeddingCacheUnavailable("Dolphin embedding cache is unavailable")
            target: Path | str = self._layout.metadata_db
            if read_only:
                target = self._layout.metadata_db.as_uri() + "?mode=ro"
            connection = sqlite3.connect(target, uri=read_only, timeout=0.25, isolation_level=None)
            connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
            if read_only:
                connection.execute("PRAGMA query_only = ON")
            version = connection.execute("PRAGMA user_version").fetchone()
            if version is None or int(version[0]) != METADATA_SCHEMA_VERSION:
                raise EmbeddingCacheUnavailable("Dolphin embedding cache schema is unavailable")
            yield connection
        except EmbeddingCacheError:
            raise
        except (sqlite3.Error, StorageLayoutError) as exc:
            raise EmbeddingCacheUnavailable("Dolphin embedding cache is unavailable") from exc
        finally:
            if connection is not None:
                connection.close()


def _cached_embedding(identity: EmbeddingInputIdentity, row: tuple[object, ...]) -> CachedEmbedding:
    if len(row) != 10 or tuple(row[:7]) != (
        identity.cache_key,
        identity.format,
        identity.provider,
        identity.model,
        identity.dimensions,
        identity.contract_version,
        identity.utf8_bytes,
    ):
        raise EmbeddingCacheCorrupt("Dolphin embedding cache identity is corrupt")
    raw_payload = row[7]
    if not isinstance(raw_payload, bytes) or len(raw_payload) != _VECTOR_BYTES.size:
        raise EmbeddingCacheCorrupt("Dolphin embedding cache vector is corrupt")
    if row[8] != _vector_digest(identity.cache_key, raw_payload):
        raise EmbeddingCacheCorrupt("Dolphin embedding cache vector digest is corrupt")
    _require_persisted_timestamp(row[9])
    try:
        vector = canonicalize_embedding_vector(_VECTOR_BYTES.unpack(raw_payload))
        return CachedEmbedding(identity=identity, vector=vector)
    except (TypeError, ValueError, ValidationError):
        raise EmbeddingCacheCorrupt("Dolphin embedding cache vector is corrupt") from None


def _require_fixed_identity(identity: EmbeddingInputIdentity) -> None:
    if not isinstance(identity, EmbeddingInputIdentity) or (
        identity.format,
        identity.provider,
        identity.model,
        identity.dimensions,
        identity.contract_version,
    ) != (
        EMBEDDING_INPUT_FORMAT,
        EMBEDDING_PROVIDER,
        EMBEDDING_MODEL,
        EMBEDDING_DIMENSIONS,
        EMBEDDING_CONTRACT_VERSION,
    ):
        raise EmbeddingCacheError("Dolphin embedding cache identity is incompatible")


def _vector_digest(cache_key: str, payload: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(_VECTOR_DIGEST_DOMAIN)
    digest.update(cache_key.encode("ascii"))
    digest.update(payload)
    return digest.hexdigest()


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise EmbeddingCacheError("Dolphin embedding cache clock must return an aware timestamp")
    return value.astimezone(UTC).isoformat()


def _require_persisted_timestamp(value: object) -> None:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        raise EmbeddingCacheCorrupt("Dolphin embedding cache timestamp is corrupt")
