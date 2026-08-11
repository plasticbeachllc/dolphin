"""Exact immutable SQLite cache for fixed-contract embedding vectors."""

from __future__ import annotations

import hmac
import sqlite3
import struct
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from kb.artifacts import EMBEDDING_INPUT_FORMAT, EmbeddingInputIdentity
from kb.generation import EMBEDDING_CONTRACT_VERSION, EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, EMBEDDING_PROVIDER
from kb.generation_vector import canonicalize_embedding_vector
from kb.query_embedding import CachedEmbedding
from kb.runtime.schema import METADATA_SCHEMA_VERSION
from kb.runtime.storage import StorageLayout, StorageLayoutError

_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 250
_MAX_CACHE_ENTRIES = 8_192
_CACHE_ENTRY_MAX_AGE = timedelta(days=30)
_VECTOR_BYTES = struct.Struct(f"!{EMBEDDING_DIMENSIONS}f")
_ENTRY_MAC_DOMAIN = b"dolphin:embedding-cache-entry:v2\x00"
_DURABLE_CACHE_KEY_DOMAIN = b"dolphin:query-cache-key:v1\x00"
_MAC_FIELD_LENGTH = struct.Struct("!I")


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
        self._identity_secret: bytes | None = None
        self._identity_secret_guard = threading.Lock()

    def get(self, identity: EmbeddingInputIdentity) -> CachedEmbedding | None:
        _require_fixed_identity(identity)
        with self._connection(read_only=True) as connection:
            secret = self._identity_secret_for(connection)
            durable_cache_key = _durable_cache_key(secret, identity)
            row = connection.execute(
                """
                SELECT cache_key, format, provider, model, dimensions, contract_version,
                       vector, entry_mac, created_at
                FROM embedding_cache_entries
                WHERE cache_key = ?
                """,
                (durable_cache_key,),
            ).fetchone()
        if row is None:
            return None
        cached = _cached_embedding(identity, durable_cache_key, secret, row)
        if _require_persisted_timestamp(row[8]) <= _utc_datetime(self._clock()) - _CACHE_ENTRY_MAX_AGE:
            return None
        return cached

    def put(self, identity: EmbeddingInputIdentity, vector: Sequence[float]) -> CachedEmbedding:
        """Install once and return the immutable winner of a concurrent insertion."""
        _require_fixed_identity(identity)
        try:
            canonical = canonicalize_embedding_vector(vector)
        except (TypeError, ValueError):
            raise EmbeddingCacheError("Dolphin embedding cache vector is invalid") from None
        payload = _VECTOR_BYTES.pack(*canonical)
        now = self._clock()
        created_at = _timestamp(now)
        with self._connection() as connection:
            try:
                secret = self._identity_secret_for(connection)
                durable_cache_key = _durable_cache_key(secret, identity)
                entry_mac = _entry_mac(secret, durable_cache_key, identity, payload, created_at)
                connection.execute("BEGIN IMMEDIATE")
                row = _embedding_row(connection, durable_cache_key)
                if row is not None:
                    cached = _cached_embedding(identity, durable_cache_key, secret, row)
                    if _require_persisted_timestamp(row[8]) > _utc_datetime(now) - _CACHE_ENTRY_MAX_AGE:
                        connection.commit()
                        return cached
                    connection.execute(
                        "DELETE FROM embedding_cache_entries WHERE cache_key = ?",
                        (durable_cache_key,),
                    )
                _prune_cache_for_insert(connection, now)
                connection.execute(
                    """
                    INSERT INTO embedding_cache_entries (
                        cache_key, format, provider, model, dimensions, contract_version,
                        vector, entry_mac, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        durable_cache_key,
                        identity.format,
                        identity.provider,
                        identity.model,
                        identity.dimensions,
                        identity.contract_version,
                        payload,
                        entry_mac,
                        created_at,
                    ),
                )
                row = _embedding_row(connection, durable_cache_key)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if row is None:
            raise EmbeddingCacheCorrupt("Dolphin embedding cache installation is missing")
        return _cached_embedding(identity, durable_cache_key, secret, row)

    def _identity_secret_for(
        self,
        connection: sqlite3.Connection,
    ) -> bytes:
        with self._identity_secret_guard:
            secret = self._identity_secret
            if secret is None:
                row = connection.execute("SELECT EXISTS(SELECT 1 FROM embedding_cache_entries LIMIT 1)").fetchone()
                if row is None or row[0] not in (0, 1):
                    raise EmbeddingCacheCorrupt("Dolphin embedding cache accounting is corrupt")
                try:
                    secret = self._layout.load_or_create_query_cache_secret(allow_create=row[0] == 0)
                except StorageLayoutError:
                    raise EmbeddingCacheCorrupt("Dolphin embedding cache identity secret is corrupt") from None
                self._identity_secret = secret
        return secret

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
        except sqlite3.Error as exc:
            raise _classified_sqlite_error(exc) from exc
        except StorageLayoutError as exc:
            raise EmbeddingCacheUnavailable("Dolphin embedding cache is unavailable") from exc
        finally:
            if connection is not None:
                connection.close()


def _cached_embedding(
    identity: EmbeddingInputIdentity,
    durable_cache_key: str,
    secret: bytes,
    row: tuple[object, ...],
) -> CachedEmbedding:
    if len(row) != 9 or tuple(row[:6]) != (
        durable_cache_key,
        identity.format,
        identity.provider,
        identity.model,
        identity.dimensions,
        identity.contract_version,
    ):
        raise EmbeddingCacheCorrupt("Dolphin embedding cache identity is corrupt")
    raw_payload = row[6]
    if not isinstance(raw_payload, bytes) or len(raw_payload) != _VECTOR_BYTES.size:
        raise EmbeddingCacheCorrupt("Dolphin embedding cache vector is corrupt")
    created_at = row[8]
    _require_persisted_timestamp(created_at)
    if (
        not isinstance(created_at, str)
        or not isinstance(row[7], str)
        or not hmac.compare_digest(
            row[7],
            _entry_mac(secret, durable_cache_key, identity, raw_payload, created_at),
        )
    ):
        raise EmbeddingCacheCorrupt("Dolphin embedding cache entry MAC is corrupt")
    try:
        vector = canonicalize_embedding_vector(_VECTOR_BYTES.unpack(raw_payload))
        return CachedEmbedding(identity=identity, vector=vector)
    except (TypeError, ValueError, ValidationError):
        raise EmbeddingCacheCorrupt("Dolphin embedding cache vector is corrupt") from None


def _embedding_row(connection: sqlite3.Connection, cache_key: str) -> tuple[object, ...] | None:
    return connection.execute(
        """
        SELECT cache_key, format, provider, model, dimensions, contract_version,
               vector, entry_mac, created_at
        FROM embedding_cache_entries
        WHERE cache_key = ?
        """,
        (cache_key,),
    ).fetchone()


def _prune_cache_for_insert(connection: sqlite3.Connection, now: datetime) -> None:
    """Bound optional query cache growth without turning reads into writes."""
    expiry = _timestamp(now - _CACHE_ENTRY_MAX_AGE)
    connection.execute("DELETE FROM embedding_cache_entries WHERE created_at <= ?", (expiry,))
    row = connection.execute("SELECT COUNT(*) FROM embedding_cache_entries").fetchone()
    if row is None or not isinstance(row[0], int) or isinstance(row[0], bool) or row[0] < 0:
        raise EmbeddingCacheCorrupt("Dolphin embedding cache accounting is corrupt")
    excess = max(0, row[0] - (_MAX_CACHE_ENTRIES - 1))
    if excess:
        connection.execute(
            """
            DELETE FROM embedding_cache_entries
            WHERE cache_key IN (
                SELECT cache_key
                FROM embedding_cache_entries
                ORDER BY created_at, cache_key
                LIMIT ?
            )
            """,
            (excess,),
        )


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


def _durable_cache_key(secret: bytes, identity: EmbeddingInputIdentity) -> str:
    return hmac.digest(
        secret,
        _DURABLE_CACHE_KEY_DOMAIN + bytes.fromhex(identity.cache_key),
        "sha256",
    ).hex()


def _entry_mac(
    secret: bytes,
    cache_key: str,
    identity: EmbeddingInputIdentity,
    payload: bytes,
    created_at: str,
) -> str:
    message = bytearray(_ENTRY_MAC_DOMAIN)
    fields = (
        cache_key.encode("ascii"),
        identity.format.encode("utf-8"),
        identity.provider.encode("utf-8"),
        identity.model.encode("utf-8"),
        str(identity.dimensions).encode("ascii"),
        str(identity.contract_version).encode("ascii"),
        payload,
        created_at.encode("ascii"),
    )
    for field in fields:
        message.extend(_MAC_FIELD_LENGTH.pack(len(field)))
        message.extend(field)
    return hmac.digest(secret, message, "sha256").hex()


def _timestamp(value: datetime) -> str:
    return _utc_datetime(value).isoformat()


def _utc_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise EmbeddingCacheError("Dolphin embedding cache clock must return an aware timestamp")
    return value.astimezone(UTC)


def _require_persisted_timestamp(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        raise EmbeddingCacheCorrupt("Dolphin embedding cache timestamp is corrupt")
    return parsed.astimezone(UTC)


def _classified_sqlite_error(exc: sqlite3.Error) -> EmbeddingCacheError:
    error_code = getattr(exc, "sqlite_errorcode", None)
    primary_code = error_code & 0xFF if isinstance(error_code, int) else None
    unavailable_codes = {
        sqlite3.SQLITE_BUSY,
        sqlite3.SQLITE_LOCKED,
        sqlite3.SQLITE_CANTOPEN,
        sqlite3.SQLITE_IOERR,
        sqlite3.SQLITE_FULL,
        sqlite3.SQLITE_READONLY,
        sqlite3.SQLITE_PERM,
    }
    if primary_code in unavailable_codes:
        return EmbeddingCacheUnavailable("Dolphin embedding cache is unavailable")
    return EmbeddingCacheCorrupt("Dolphin embedding cache database is corrupt")
