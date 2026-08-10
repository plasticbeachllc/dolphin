"""Local LanceDB adapter for immutable generation-scoped vector projections."""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import sqlite3
import stat
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from kb.artifacts import MAX_GENERATION_ARTIFACTS
from kb.generation import EMBEDDING_DIMENSIONS, StagingGeneration, VerifiedVectorCommit
from kb.generation_vector import (
    MAX_VECTOR_RESULTS,
    GenerationVectorConflict,
    GenerationVectorCorrupt,
    GenerationVectorError,
    GenerationVectorUnavailable,
    StagedGenerationVector,
    VectorSearchHit,
    canonicalize_embedding_vector,
    identify_generation_vector_commit,
    identify_generation_vector_row,
)
from kb.runtime.schema import METADATA_SCHEMA_VERSION
from kb.runtime.storage import StorageLayout, StorageLayoutError
from kb.services.workspace_registry import OperationLease

_TABLE_PREFIX = "generation_vectors_v1_"
_TOKEN_PREFIX = "lance-generation-vector-v1"
_WRITER_LOCK_FILE = "generation-vectors-v1.lock"
_WRITER_LOCK_TIMEOUT_SECONDS = 5.0
_WRITER_LOCK_RETRY_SECONDS = 0.025
_QUERY_TIMEOUT = timedelta(seconds=10)
_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 1_000
_VERIFIED_COMMIT_CACHE_SIZE = 128
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class _StagingScope:
    state: str
    manifest_id: str
    manifest_digest: str
    memberships: tuple[tuple[str, str], ...]
    persisted_commit: VerifiedVectorCommit | None


@dataclass(frozen=True, slots=True)
class _PublishedVectorScope:
    workspace_id: str
    publication_id: str
    generation_id: str
    manifest_id: str
    manifest_digest: str
    commit: VerifiedVectorCommit


class LanceGenerationVectorStore:
    """Stage and search one immutable Lance table per SQLite generation."""

    def __init__(
        self,
        layout: StorageLayout,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._layout = layout
        self._clock = clock or (lambda: datetime.now(UTC))
        self._connection_lock = threading.Lock()
        self._database: Any | None = None
        self._verified_lock = threading.Lock()
        self._verified: OrderedDict[tuple[str, str], None] = OrderedDict()

    def stage_and_commit(
        self,
        lease: OperationLease,
        generation: StagingGeneration,
        vectors: Sequence[StagedGenerationVector],
    ) -> VerifiedVectorCommit:
        ordered = _validate_staged_vectors(vectors)
        preflight = self._staging_scope(lease, generation)
        _require_vector_membership(preflight, ordered)
        table_name = _table_name(generation.generation_id)

        with self._writer_lock():
            database = self._connect()
            table = _open_table(database, table_name)
            if table is not None:
                try:
                    observed_vectors = _vectors_from_table(table, generation.generation_id)
                    token = _backend_token(table_name, _table_version(table))
                    observed = identify_generation_vector_commit(generation.generation_id, token, observed_vectors)
                except GenerationVectorUnavailable:
                    raise
                except GenerationVectorError:
                    if preflight.persisted_commit is not None or preflight.state != "staging":
                        raise GenerationVectorCorrupt("Dolphin committed generation vectors are corrupt") from None
                    _drop_table(database, table_name)
                else:
                    if preflight.persisted_commit is not None and observed != preflight.persisted_commit:
                        raise GenerationVectorCorrupt("Dolphin persisted vector commit does not match LanceDB")
                    if observed_vectors != ordered:
                        raise GenerationVectorConflict("Dolphin generation already records different vectors")
                    self.verify_commit(observed)
                    self._require_scope_unchanged(lease, generation, preflight, observed)
                    return observed

            table = _create_table(database, table_name, generation.generation_id, ordered)
            commit = identify_generation_vector_commit(
                generation.generation_id,
                _backend_token(table_name, _table_version(table)),
                ordered,
            )
            self.verify_commit(commit)

        self._require_scope_unchanged(lease, generation, preflight, commit)
        return commit

    def verify_commit(self, commit: VerifiedVectorCommit) -> None:
        table_name, version = _parse_backend_token(commit)
        table = _require_table(self._connect(), table_name)
        if _table_version(table) != version:
            raise GenerationVectorCorrupt("Dolphin vector commit version is unavailable")
        vectors = _vectors_from_table(table, commit.generation_id)
        observed = identify_generation_vector_commit(commit.generation_id, commit.backend_token, vectors)
        if observed != commit:
            raise GenerationVectorCorrupt("Dolphin vector commit digest or row count is corrupt")
        self._remember_verified(commit)

    def require_unchanged(self, commit: VerifiedVectorCommit) -> None:
        table_name, version = _parse_backend_token(commit)
        table = _require_table(self._connect(), table_name)
        if _table_version(table) != version or not _schema_matches(table) or _count_rows(table) != commit.row_count:
            self._forget_verified(commit)
            raise GenerationVectorCorrupt("Dolphin vector commit changed after verification")

    @contextmanager
    def hold_commit(self, commit: VerifiedVectorCommit) -> Iterator[None]:
        """Prevent Dolphin writers from changing a verified commit during a visibility operation."""
        with self._store_lock(fcntl.LOCK_SH, unavailable_message="Dolphin vector commit lock is unavailable"):
            self.require_unchanged(commit)
            yield

    def search(
        self,
        read_lease_id: str,
        query_vector: Sequence[float],
        *,
        limit: int,
    ) -> tuple[VectorSearchHit, ...]:
        _bounded_id(read_lease_id, "generation read lease ID")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_VECTOR_RESULTS:
            raise GenerationVectorError("Dolphin vector result limit is invalid")
        try:
            query = canonicalize_embedding_vector(query_vector)
        except (TypeError, ValueError) as exc:
            raise GenerationVectorError("Dolphin query embedding is invalid") from exc
        scope = self._published_scope(read_lease_id)
        if not self._is_verified(scope.commit):
            self.verify_commit(scope.commit)
        with self.hold_commit(scope.commit):
            if scope.commit.row_count == 0:
                self._require_hits_authorized(read_lease_id, scope, ())
                return ()

            table_name, version = _parse_backend_token(scope.commit)
            table = _require_table(self._connect(), table_name)
            if _table_version(table) != version:
                raise GenerationVectorCorrupt("Dolphin vector commit changed before search")
            try:
                rows = (
                    table.search(list(query), vector_column_name="vector")
                    .metric("cosine")
                    .select(["generation_id", "chunk_instance_id", "embedding_cache_key", "_distance"])
                    .limit(limit)
                    .to_list(timeout=_QUERY_TIMEOUT)
                )
            except Exception as exc:
                raise GenerationVectorUnavailable("Dolphin vector search is unavailable") from exc
            hits, identities = _hits_from_rows(rows, scope.generation_id, limit)
            self._require_hits_authorized(read_lease_id, scope, identities)
            self.require_unchanged(scope.commit)
            return hits

    def _connect(self) -> Any:
        _validate_layout(self._layout)
        if self._database is not None:
            return self._database
        with self._connection_lock:
            if self._database is not None:
                return self._database
            try:
                import lancedb

                self._database = lancedb.connect(self._layout.vectors.as_posix())
            except Exception as exc:
                raise GenerationVectorUnavailable("Dolphin local vector storage is unavailable") from exc
        return self._database

    @contextmanager
    def _writer_lock(self) -> Iterator[None]:
        with self._store_lock(fcntl.LOCK_EX, unavailable_message="Dolphin vector writer lock is unavailable"):
            yield

    @contextmanager
    def _store_lock(self, operation: int, *, unavailable_message: str) -> Iterator[None]:
        descriptor: int | None = None
        locked = False
        try:
            with self._layout.open_locks_directory() as locks_fd:
                descriptor = os.open(
                    _WRITER_LOCK_FILE,
                    os.O_RDWR | os.O_CREAT | _no_follow_flag() | _close_on_exec_flag(),
                    0o600,
                    dir_fd=locks_fd,
                )
                os.fchmod(descriptor, 0o600)
                status = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(status.st_mode)
                    or status.st_uid != os.getuid()
                    or stat.S_IMODE(status.st_mode) != 0o600
                ):
                    raise GenerationVectorUnavailable("Dolphin vector writer lock is unsafe")
                deadline = time.monotonic() + _WRITER_LOCK_TIMEOUT_SECONDS
                while True:
                    try:
                        fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
                        locked = True
                        break
                    except BlockingIOError:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise GenerationVectorUnavailable(unavailable_message) from None
                        time.sleep(min(_WRITER_LOCK_RETRY_SECONDS, remaining))
                yield
        except StorageLayoutError as exc:
            raise GenerationVectorUnavailable(unavailable_message) from exc
        except OSError as exc:
            raise GenerationVectorUnavailable(unavailable_message) from exc
        finally:
            if descriptor is not None:
                primary_error_active = sys.exc_info()[0] is not None
                unlock_failed = False
                if locked:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                    except OSError:
                        unlock_failed = True
                os.close(descriptor)
                if unlock_failed and not primary_error_active:
                    raise GenerationVectorUnavailable("Dolphin vector writer lock could not be released")

    def _staging_scope(self, lease: OperationLease, generation: StagingGeneration) -> _StagingScope:
        observed_at = _timestamp(self._clock())
        with _metadata_connection(self._layout) as connection:
            row = connection.execute(
                """
                SELECT g.operation_id, g.workspace_id, g.target_fingerprint, g.pipeline_key, g.state,
                       g.vector_commit_token, g.vector_digest, g.vector_row_count,
                       g.vector_provider, g.vector_model, g.vector_dimensions,
                       g.embedding_contract_version, o.state, l.lease_id, l.runtime_id,
                       l.expires_at, r.state, r.expires_at, m.manifest_id, m.manifest_digest
                FROM generations AS g
                JOIN workspace_operations AS o ON o.operation_id = g.operation_id
                JOIN operation_leases AS l ON l.operation_id = o.operation_id
                JOIN runtime_instances AS r ON r.runtime_id = l.runtime_id
                JOIN generation_content_manifests AS m ON m.generation_id = g.generation_id
                WHERE g.generation_id = ?
                """,
                (generation.generation_id,),
            ).fetchone()
            if row is None or tuple(row[:4]) != (
                generation.operation_id,
                generation.workspace_id,
                generation.target_fingerprint,
                generation.pipeline_key,
            ):
                raise GenerationVectorUnavailable("Dolphin staging generation is unavailable")
            if (
                lease.operation.operation_id != generation.operation_id
                or lease.operation.workspace_id != generation.workspace_id
                or row[12] != "running"
                or row[13] != lease.lease_id
                or row[14] != lease.runtime_id
                or str(row[15]) <= observed_at
                or row[16] != "active"
                or str(row[17]) <= observed_at
            ):
                raise GenerationVectorUnavailable("Dolphin operation lease is unavailable or expired")
            state = str(row[4])
            if state not in {"staging", "ready", "published"}:
                raise GenerationVectorCorrupt("Dolphin staging generation state is corrupt")
            persisted = _optional_commit(generation.generation_id, tuple(row[5:12]))
            memberships = connection.execute(
                """
                SELECT chunk_instance_id, embedding_cache_key
                FROM generation_chunk_memberships
                WHERE generation_id = ?
                ORDER BY chunk_instance_id
                """,
                (generation.generation_id,),
            ).fetchall()
        return _StagingScope(
            state=state,
            manifest_id=_bounded_id(row[18], "generation manifest ID"),
            manifest_digest=_digest(row[19], "generation manifest digest"),
            memberships=tuple(
                (_bounded_id(item[0], "chunk instance ID"), _digest(item[1], "embedding cache key"))
                for item in memberships
            ),
            persisted_commit=persisted,
        )

    def _require_scope_unchanged(
        self,
        lease: OperationLease,
        generation: StagingGeneration,
        expected: _StagingScope,
        commit: VerifiedVectorCommit,
    ) -> None:
        current = self._staging_scope(lease, generation)
        if (
            current.manifest_id != expected.manifest_id
            or current.manifest_digest != expected.manifest_digest
            or current.memberships != expected.memberships
            or current.state != expected.state
            or (current.persisted_commit is not None and current.persisted_commit != commit)
        ):
            raise GenerationVectorConflict("Dolphin generation changed during vector staging")
        self.require_unchanged(commit)

    def _published_scope(self, read_lease_id: str) -> _PublishedVectorScope:
        observed_at = _timestamp(self._clock())
        with _metadata_connection(self._layout) as connection:
            row = connection.execute(
                """
                SELECT g.workspace_id, g.publication_id, g.generation_id, g.manifest_id,
                       g.manifest_digest, g.vector_commit_token, g.vector_digest,
                       g.vector_row_count, g.vector_provider, g.vector_model,
                       g.vector_dimensions, g.embedding_contract_version,
                       m.content_revision, m.validated_content_revision
                FROM generation_reader_leases AS l
                JOIN generations AS g
                  ON g.generation_id = l.generation_id
                 AND g.workspace_id = l.workspace_id
                 AND g.publication_id = l.publication_id
                JOIN generation_content_manifests AS m ON m.generation_id = g.generation_id
                WHERE l.lease_id = ? AND l.expires_at > ? AND g.state = 'published'
                """,
                (read_lease_id, observed_at),
            ).fetchone()
        if row is None:
            raise GenerationVectorUnavailable("Dolphin generation read lease is unavailable or expired")
        if row[12] != row[13]:
            raise GenerationVectorCorrupt("Dolphin published generation membership is corrupt")
        commit = _optional_commit(str(row[2]), tuple(row[5:12]))
        if commit is None:
            raise GenerationVectorCorrupt("Dolphin published vector commit is unavailable")
        return _PublishedVectorScope(
            workspace_id=_bounded_id(row[0], "workspace ID"),
            publication_id=_bounded_id(row[1], "publication ID"),
            generation_id=_bounded_id(row[2], "generation ID"),
            manifest_id=_bounded_id(row[3], "manifest ID"),
            manifest_digest=_digest(row[4], "manifest digest"),
            commit=commit,
        )

    def _require_hits_authorized(
        self,
        read_lease_id: str,
        scope: _PublishedVectorScope,
        identities: tuple[tuple[str, str], ...],
    ) -> None:
        current = self._published_scope(read_lease_id)
        if current != scope:
            raise GenerationVectorUnavailable("Dolphin published vector scope changed during search")
        if not identities:
            return
        placeholders = ", ".join("?" for _identity in identities)
        with _metadata_connection(self._layout) as connection:
            rows = connection.execute(
                f"""
                SELECT chunk_instance_id, embedding_cache_key
                FROM generation_chunk_memberships
                WHERE generation_id = ? AND chunk_instance_id IN ({placeholders})
                """,
                (scope.generation_id, *(identity[0] for identity in identities)),
            ).fetchall()
        expected = {(_bounded_id(row[0], "chunk instance ID"), _digest(row[1], "embedding cache key")) for row in rows}
        if expected != set(identities) or len(expected) != len(identities):
            raise GenerationVectorCorrupt("Dolphin vector result is not authorized by its published snapshot")

    def _remember_verified(self, commit: VerifiedVectorCommit) -> None:
        key = (commit.backend_token, commit.manifest_digest)
        with self._verified_lock:
            self._verified.pop(key, None)
            self._verified[key] = None
            while len(self._verified) > _VERIFIED_COMMIT_CACHE_SIZE:
                self._verified.popitem(last=False)

    def _forget_verified(self, commit: VerifiedVectorCommit) -> None:
        with self._verified_lock:
            self._verified.pop((commit.backend_token, commit.manifest_digest), None)

    def _is_verified(self, commit: VerifiedVectorCommit) -> bool:
        key = (commit.backend_token, commit.manifest_digest)
        with self._verified_lock:
            if key not in self._verified:
                return False
            self._verified.move_to_end(key)
            return True


def _validate_staged_vectors(vectors: Sequence[StagedGenerationVector]) -> tuple[StagedGenerationVector, ...]:
    if isinstance(vectors, (str, bytes)):
        raise GenerationVectorError("Dolphin generation vector input is invalid")
    staged = tuple(vectors)
    if len(staged) > MAX_GENERATION_ARTIFACTS:
        raise GenerationVectorError("Dolphin generation vector input is too large")
    if any(not isinstance(vector, StagedGenerationVector) for vector in staged):
        raise GenerationVectorError("Dolphin generation vector input is invalid")
    ordered = tuple(sorted(staged, key=lambda vector: vector.chunk_instance_id))
    if len({vector.chunk_instance_id for vector in ordered}) != len(ordered):
        raise GenerationVectorError("Dolphin generation vector input contains duplicate identities")
    return ordered


def _require_vector_membership(scope: _StagingScope, vectors: tuple[StagedGenerationVector, ...]) -> None:
    supplied = tuple((vector.chunk_instance_id, vector.embedding_cache_key) for vector in vectors)
    if supplied != scope.memberships:
        raise GenerationVectorConflict("Dolphin vectors do not match the staged chunk manifest")


def _table_name(generation_id: str) -> str:
    _bounded_id(generation_id, "generation ID")
    return _TABLE_PREFIX + hashlib.sha256(generation_id.encode("utf-8")).hexdigest()


def _backend_token(table_name: str, version: int) -> str:
    return f"{_TOKEN_PREFIX}:{table_name}:{version}"


def _parse_backend_token(commit: VerifiedVectorCommit) -> tuple[str, int]:
    parts = commit.backend_token.split(":")
    expected_table = _table_name(commit.generation_id)
    if len(parts) != 3 or parts[0] != _TOKEN_PREFIX or parts[1] != expected_table:
        raise GenerationVectorCorrupt("Dolphin vector commit token is invalid")
    try:
        version = int(parts[2])
    except ValueError:
        raise GenerationVectorCorrupt("Dolphin vector commit token is invalid") from None
    if version < 1 or str(version) != parts[2]:
        raise GenerationVectorCorrupt("Dolphin vector commit token is invalid")
    return expected_table, version


def _vector_schema() -> Any:
    import pyarrow as pa

    return pa.schema(
        [
            pa.field("generation_id", pa.string(), nullable=False),
            pa.field("chunk_instance_id", pa.string(), nullable=False),
            pa.field("embedding_cache_key", pa.string(), nullable=False),
            pa.field("vector_digest", pa.string(), nullable=False),
            pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIMENSIONS), nullable=False),
        ]
    )


def _create_table(
    database: Any,
    table_name: str,
    generation_id: str,
    vectors: tuple[StagedGenerationVector, ...],
) -> Any:
    try:
        import pyarrow as pa

        schema = _vector_schema()
        rows = [
            {
                "generation_id": generation_id,
                "chunk_instance_id": vector.chunk_instance_id,
                "embedding_cache_key": vector.embedding_cache_key,
                "vector_digest": identify_generation_vector_row(vector),
                "vector": list(vector.vector),
            }
            for vector in vectors
        ]
        data = pa.Table.from_pylist(rows, schema=schema)
        return database.create_table(table_name, data=data, mode="create")
    except GenerationVectorError:
        raise
    except Exception as exc:
        raise GenerationVectorUnavailable("Dolphin generation vectors could not be committed") from exc


def _vectors_from_table(table: Any, generation_id: str) -> tuple[StagedGenerationVector, ...]:
    if not _schema_matches(table):
        raise GenerationVectorCorrupt("Dolphin generation vector schema is incompatible")
    count = _count_rows(table)
    if count > MAX_GENERATION_ARTIFACTS:
        raise GenerationVectorCorrupt("Dolphin generation vector table is too large")
    try:
        rows = table.to_arrow().to_pylist()
    except Exception as exc:
        raise GenerationVectorUnavailable("Dolphin generation vectors could not be read") from exc
    if len(rows) != count:
        raise GenerationVectorCorrupt("Dolphin generation vector row count is unstable")
    vectors: list[StagedGenerationVector] = []
    try:
        for row in rows:
            if row.get("generation_id") != generation_id:
                raise GenerationVectorCorrupt("Dolphin generation vector scope is corrupt")
            vector = StagedGenerationVector(
                chunk_instance_id=row.get("chunk_instance_id"),
                embedding_cache_key=row.get("embedding_cache_key"),
                vector=tuple(row.get("vector", ())),
            )
            if row.get("vector_digest") != identify_generation_vector_row(vector):
                raise GenerationVectorCorrupt("Dolphin generation vector row digest is corrupt")
            vectors.append(vector)
    except (TypeError, ValueError, ValidationError) as exc:
        raise GenerationVectorCorrupt("Dolphin generation vector row is corrupt") from exc
    ordered = tuple(sorted(vectors, key=lambda vector: vector.chunk_instance_id))
    if len({vector.chunk_instance_id for vector in ordered}) != len(ordered):
        raise GenerationVectorCorrupt("Dolphin generation vector identities are duplicated")
    return ordered


def _schema_matches(table: Any) -> bool:
    try:
        return table.schema == _vector_schema()
    except Exception:
        return False


def _table_version(table: Any) -> int:
    try:
        version = table.version
    except Exception as exc:
        raise GenerationVectorUnavailable("Dolphin vector commit version is unavailable") from exc
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise GenerationVectorCorrupt("Dolphin vector commit version is corrupt")
    return version


def _count_rows(table: Any) -> int:
    try:
        count = table.count_rows()
    except Exception as exc:
        raise GenerationVectorUnavailable("Dolphin generation vector row count is unavailable") from exc
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise GenerationVectorCorrupt("Dolphin generation vector row count is corrupt")
    return count


def _open_table(database: Any, table_name: str) -> Any | None:
    try:
        return database.open_table(table_name)
    except Exception:
        try:
            listing = database.list_tables()
            names = getattr(listing, "tables", listing)
            if table_name in names:
                raise GenerationVectorUnavailable("Dolphin generation vector table is unavailable") from None
        except GenerationVectorUnavailable:
            raise
        except Exception as exc:
            raise GenerationVectorUnavailable("Dolphin local vector storage is unavailable") from exc
        return None


def _require_table(database: Any, table_name: str) -> Any:
    table = _open_table(database, table_name)
    if table is None:
        raise GenerationVectorCorrupt("Dolphin committed generation vectors are missing")
    return table


def _drop_table(database: Any, table_name: str) -> None:
    try:
        database.drop_table(table_name)
    except Exception as exc:
        raise GenerationVectorUnavailable("Dolphin incomplete generation vectors could not be reconciled") from exc


def _hits_from_rows(
    rows: Any,
    generation_id: str,
    limit: int,
) -> tuple[tuple[VectorSearchHit, ...], tuple[tuple[str, str], ...]]:
    if not isinstance(rows, list) or len(rows) > limit:
        raise GenerationVectorCorrupt("Dolphin vector search returned invalid results")
    hits: list[VectorSearchHit] = []
    identities: list[tuple[str, str]] = []
    seen: set[str] = set()
    try:
        for row in rows:
            if not isinstance(row, dict) or row.get("generation_id") != generation_id:
                raise GenerationVectorCorrupt("Dolphin vector search crossed its generation scope")
            chunk_instance_id = _bounded_id(row.get("chunk_instance_id"), "chunk instance ID")
            cache_key = _digest(row.get("embedding_cache_key"), "embedding cache key")
            if chunk_instance_id in seen:
                raise GenerationVectorCorrupt("Dolphin vector search returned duplicate results")
            seen.add(chunk_instance_id)
            raw_distance = row.get("_distance")
            if isinstance(raw_distance, bool) or not isinstance(raw_distance, (int, float)):
                raise GenerationVectorCorrupt("Dolphin vector search distance is corrupt")
            distance = float(raw_distance)
            if not 0 <= distance <= 2 or not (distance < float("inf")):
                raise GenerationVectorCorrupt("Dolphin vector search distance is corrupt")
            hits.append(
                VectorSearchHit(
                    chunk_instance_id=chunk_instance_id,
                    distance=distance,
                    score=1.0 - (distance / 2.0),
                )
            )
            identities.append((chunk_instance_id, cache_key))
    except (TypeError, ValueError, ValidationError) as exc:
        raise GenerationVectorCorrupt("Dolphin vector search result is corrupt") from exc
    return tuple(hits), tuple(identities)


def _optional_commit(generation_id: str, values: tuple[object, ...]) -> VerifiedVectorCommit | None:
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise GenerationVectorCorrupt("Dolphin persisted vector commit is incomplete")
    try:
        return VerifiedVectorCommit.model_validate(
            {
                "generation_id": generation_id,
                "backend_token": values[0],
                "manifest_digest": values[1],
                "row_count": values[2],
                "provider": values[3],
                "model": values[4],
                "dimensions": values[5],
                "contract_version": values[6],
            }
        )
    except ValidationError as exc:
        raise GenerationVectorCorrupt("Dolphin persisted vector commit is corrupt") from exc


@contextmanager
def _metadata_connection(layout: StorageLayout) -> Iterator[sqlite3.Connection]:
    try:
        if not layout.metadata_database_exists():
            raise GenerationVectorUnavailable("Dolphin metadata storage is unavailable")
        connection = sqlite3.connect(
            layout.metadata_db.as_uri() + "?mode=ro",
            uri=True,
            timeout=1,
            isolation_level=None,
        )
    except (sqlite3.Error, StorageLayoutError) as exc:
        raise GenerationVectorUnavailable("Dolphin metadata storage is unavailable") from exc
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
        connection.execute("PRAGMA query_only = ON")
        version = connection.execute("PRAGMA user_version").fetchone()
        if version is None or int(version[0]) != METADATA_SCHEMA_VERSION:
            raise GenerationVectorUnavailable("Dolphin metadata schema is unavailable or incompatible")
        yield connection
    except sqlite3.Error as exc:
        raise GenerationVectorUnavailable("Dolphin vector metadata is busy or unavailable") from exc
    finally:
        connection.close()


def _validate_layout(layout: StorageLayout) -> None:
    if layout.vectors != layout.root / "vectors":
        raise GenerationVectorUnavailable("Dolphin vector storage has an invalid layout")
    try:
        layout.ensure_private_directories()
    except StorageLayoutError as exc:
        raise GenerationVectorUnavailable("Dolphin local vector storage is unavailable") from exc


def _bounded_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or "\x00" in value:
        raise GenerationVectorCorrupt(f"Dolphin {label} is corrupt")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise GenerationVectorCorrupt(f"Dolphin {label} is corrupt")
    return value


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise GenerationVectorError("Dolphin vector clock must return a timezone-aware timestamp")
    return value.astimezone(UTC).isoformat()


def _no_follow_flag() -> int:
    return getattr(os, "O_NOFOLLOW", 0)


def _close_on_exec_flag() -> int:
    return getattr(os, "O_CLOEXEC", 0)
