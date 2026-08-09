"""SQLite visibility authority for atomic workspace generations."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from kb.generation import (
    GenerationConflict,
    GenerationCoordinatorError,
    GenerationReadLease,
    GenerationReadLeaseUnavailable,
    GenerationState,
    PublishedSnapshot,
    StagingGeneration,
    VerifiedGenerationManifest,
    VerifiedVectorCommit,
)
from kb.runtime.schema import METADATA_SCHEMA_VERSION
from kb.runtime.storage import StorageLayout, StorageLayoutError
from kb.services.workspace_registry import OperationLease

_READ_LEASE_MAXIMUM = timedelta(seconds=60)
_PRIVATE_ID_MAX_LENGTH = 128
_PRIVATE_VALUE_MAX_LENGTH = 256


class SQLiteGenerationCoordinator:
    """Publish complete generations through one SQLite compare-and-swap pointer."""

    def __init__(self, layout: StorageLayout) -> None:
        self._layout = layout

    def create_staging(self, lease: OperationLease, *, now: datetime) -> StagingGeneration:
        observed_at = _timestamp(now)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                authority = _require_operation_authority(connection, lease, observed_at)
                existing = connection.execute(_GENERATION_BY_OPERATION, (lease.operation.operation_id,)).fetchone()
                if existing is not None:
                    generation = _generation_from_row(existing)
                    _require_generation_identity(
                        generation, lease, authority.target_fingerprint, authority.pipeline_key
                    )
                    connection.commit()
                    return generation
                generation_id = f"gen_{uuid.uuid4().hex}"
                connection.execute(
                    """
                    INSERT INTO generations (
                        generation_id, operation_id, workspace_id, target_fingerprint, pipeline_key,
                        state, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'staging', ?)
                    """,
                    (
                        generation_id,
                        lease.operation.operation_id,
                        lease.operation.workspace_id,
                        authority.target_fingerprint,
                        authority.pipeline_key,
                        observed_at,
                    ),
                )
                row = connection.execute(_GENERATION_BY_ID, (generation_id,)).fetchone()
                if row is None:
                    raise GenerationCoordinatorError("Dolphin staging generation was not persisted")
                generation = _generation_from_row(row)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return generation

    def record_vector_ready(
        self,
        lease: OperationLease,
        commit: VerifiedVectorCommit,
        *,
        now: datetime,
    ) -> StagingGeneration:
        observed_at = _timestamp(now)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                _require_operation_authority(connection, lease, observed_at)
                generation = _require_generation(connection, commit.generation_id, lease)
                existing = (
                    generation.vector_commit_token,
                    generation.vector_digest,
                    generation.vector_row_count,
                    generation.vector_provider,
                    generation.vector_model,
                    generation.vector_dimensions,
                    generation.embedding_contract_version,
                )
                supplied = (
                    commit.backend_token,
                    commit.manifest_digest,
                    commit.row_count,
                    commit.provider,
                    commit.model,
                    commit.dimensions,
                    commit.contract_version,
                )
                if all(value is not None for value in existing):
                    if existing != supplied:
                        raise GenerationConflict("Dolphin generation already records different vector readiness")
                    connection.commit()
                    return generation
                connection.execute(
                    """
                    UPDATE generations
                    SET vector_commit_token = ?, vector_digest = ?, vector_row_count = ?,
                        vector_provider = ?, vector_model = ?, vector_dimensions = ?,
                        embedding_contract_version = ?
                    WHERE generation_id = ? AND state = 'staging'
                    """,
                    (*supplied, commit.generation_id),
                )
                row = connection.execute(_GENERATION_BY_ID, (commit.generation_id,)).fetchone()
                if row is None:
                    raise GenerationCoordinatorError("Dolphin generation disappeared during vector readiness")
                generation = _generation_from_row(row)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return generation

    def mark_ready(
        self,
        lease: OperationLease,
        manifest: VerifiedGenerationManifest,
        *,
        now: datetime,
    ) -> StagingGeneration:
        observed_at = _timestamp(now)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                _require_operation_authority(connection, lease, observed_at)
                generation = _require_generation(connection, manifest.generation_id, lease)
                supplied = (
                    manifest.manifest_id,
                    manifest.manifest_digest,
                    manifest.metadata_item_count,
                    manifest.keyword_item_count,
                )
                existing = (
                    generation.manifest_id,
                    generation.manifest_digest,
                    generation.metadata_item_count,
                    generation.keyword_item_count,
                )
                if generation.state in {"ready", "published"}:
                    if existing != supplied or generation.vector_row_count != manifest.vector_row_count:
                        raise GenerationConflict("Dolphin generation already records a different complete manifest")
                    connection.commit()
                    return generation
                if generation.vector_commit_token is None or generation.vector_digest is None:
                    raise GenerationCoordinatorError("Dolphin generation vectors are not durably verified")
                if generation.vector_row_count != manifest.vector_row_count:
                    raise GenerationConflict("Dolphin manifest vector count does not match verified vectors")
                connection.execute(
                    """
                    UPDATE generations
                    SET state = 'ready', manifest_id = ?, manifest_digest = ?,
                        metadata_item_count = ?, keyword_item_count = ?, ready_at = ?
                    WHERE generation_id = ? AND state = 'staging'
                    """,
                    (
                        manifest.manifest_id,
                        manifest.manifest_digest,
                        manifest.metadata_item_count,
                        manifest.keyword_item_count,
                        observed_at,
                        manifest.generation_id,
                    ),
                )
                row = connection.execute(_GENERATION_BY_ID, (manifest.generation_id,)).fetchone()
                if row is None:
                    raise GenerationCoordinatorError("Dolphin generation disappeared while becoming ready")
                generation = _generation_from_row(row)
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return generation

    def publish(
        self,
        lease: OperationLease,
        generation_id: str,
        *,
        expected_previous_generation_id: str | None,
        now: datetime,
    ) -> PublishedSnapshot:
        if expected_previous_generation_id is not None:
            _bounded(expected_previous_generation_id, "expected generation ID", maximum=_PRIVATE_ID_MAX_LENGTH)
        observed_at = _timestamp(now)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                authority = _require_operation_authority(connection, lease, observed_at)
                generation = _require_generation(connection, generation_id, lease)
                current_row = connection.execute(
                    "SELECT generation_id, revision FROM workspace_publications WHERE workspace_id = ?",
                    (generation.workspace_id,),
                ).fetchone()
                current_generation_id = str(current_row[0]) if current_row is not None else None
                if generation.state == "published" and current_generation_id == generation_id:
                    snapshot = _snapshot_by_generation(connection, generation_id)
                    if snapshot is None:
                        raise GenerationCoordinatorError("Dolphin published generation pointer is invalid")
                    connection.commit()
                    return snapshot
                if current_generation_id != expected_previous_generation_id:
                    raise GenerationConflict("Dolphin published generation changed before pointer swap")
                if generation.state != "ready":
                    raise GenerationCoordinatorError("Dolphin generation is not ready for publication")
                head_row = connection.execute(
                    "SELECT head_commit FROM workspace_registrations WHERE workspace_id = ?",
                    (generation.workspace_id,),
                ).fetchone()
                if head_row is None or str(head_row[0]) != authority.target_head_commit:
                    raise GenerationConflict("Dolphin workspace target changed before publication")
                revision = 1 if current_row is None else int(current_row[1]) + 1
                publication_id = f"pub_{uuid.uuid4().hex}"
                connection.execute(
                    """
                    UPDATE generations
                    SET state = 'published', publication_id = ?, publication_revision = ?, published_at = ?
                    WHERE generation_id = ? AND state = 'ready'
                    """,
                    (publication_id, revision, observed_at, generation_id),
                )
                connection.execute(
                    """
                    INSERT INTO workspace_publications (
                        workspace_id, generation_id, publication_id, revision, published_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(workspace_id) DO UPDATE SET
                        generation_id = excluded.generation_id,
                        publication_id = excluded.publication_id,
                        revision = excluded.revision,
                        published_at = excluded.published_at
                    """,
                    (generation.workspace_id, generation_id, publication_id, revision, observed_at),
                )
                connection.execute(
                    """
                    UPDATE operation_checkpoints
                    SET phase = 'publish', staging_generation_id = ?, completed_manifest_id = ?,
                        checkpointed_at = ?
                    WHERE operation_id = ?
                    """,
                    (generation_id, generation.manifest_id, observed_at, lease.operation.operation_id),
                )
                snapshot = _snapshot_by_generation(connection, generation_id)
                if snapshot is None:
                    raise GenerationCoordinatorError("Dolphin publication pointer was not persisted")
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return snapshot

    def current_snapshot(self, workspace_id: str) -> PublishedSnapshot | None:
        _bounded(workspace_id, "workspace ID", maximum=_PRIVATE_ID_MAX_LENGTH)
        with self._connection(read_only=True) as connection:
            return _current_snapshot(connection, workspace_id)

    def acquire_read(
        self,
        workspace_id: str,
        *,
        now: datetime,
        expires_at: datetime,
    ) -> GenerationReadLease:
        _bounded(workspace_id, "workspace ID", maximum=_PRIVATE_ID_MAX_LENGTH)
        acquired = _utc(now)
        expiry = _utc(expires_at)
        if expiry <= acquired or expiry - acquired > _READ_LEASE_MAXIMUM:
            raise GenerationCoordinatorError("Dolphin generation read lease window is invalid")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                snapshot = _current_snapshot(connection, workspace_id)
                if snapshot is None:
                    raise GenerationReadLeaseUnavailable("Dolphin workspace has no published snapshot")
                lease_id = f"read_{uuid.uuid4().hex}"
                connection.execute(
                    """
                    INSERT INTO generation_reader_leases (
                        lease_id, generation_id, publication_id, acquired_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        lease_id,
                        snapshot.generation_id,
                        snapshot.publication_id,
                        acquired.isoformat(),
                        expiry.isoformat(),
                    ),
                )
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return GenerationReadLease(
            lease_id=lease_id,
            snapshot=snapshot,
            acquired_at=acquired,
            expires_at=expiry,
        )

    def snapshot_for_lease(self, lease_id: str, *, now: datetime) -> PublishedSnapshot:
        _bounded(lease_id, "generation read lease ID", maximum=_PRIVATE_ID_MAX_LENGTH)
        observed_at = _timestamp(now)
        with self._connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT generation_id, publication_id
                FROM generation_reader_leases
                WHERE lease_id = ? AND expires_at > ?
                """,
                (lease_id, observed_at),
            ).fetchone()
            if row is None:
                raise GenerationReadLeaseUnavailable("Dolphin generation read lease is unavailable or expired")
            snapshot = _snapshot_by_generation(connection, str(row[0]))
            if snapshot is None or snapshot.publication_id != row[1]:
                raise GenerationReadLeaseUnavailable("Dolphin generation read lease no longer matches its snapshot")
            return snapshot

    def release_read(self, lease: GenerationReadLease) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    DELETE FROM generation_reader_leases
                    WHERE lease_id = ? AND generation_id = ? AND publication_id = ?
                    """,
                    (lease.lease_id, lease.snapshot.generation_id, lease.snapshot.publication_id),
                )
            except Exception:
                connection.rollback()
                raise
            connection.commit()

    @contextmanager
    def _connection(self, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
        try:
            if not self._layout.metadata_database_exists():
                raise GenerationCoordinatorError("Dolphin metadata storage is unavailable")
            target: Path | str = self._layout.metadata_db
            if read_only:
                target = self._layout.metadata_db.as_uri() + "?mode=ro"
            connection = sqlite3.connect(target, uri=read_only, timeout=1, isolation_level=None)
        except (sqlite3.Error, StorageLayoutError) as exc:
            raise GenerationCoordinatorError("Dolphin metadata storage is unavailable") from exc
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 1000")
            if read_only:
                connection.execute("PRAGMA query_only = ON")
            version_row = connection.execute("PRAGMA user_version").fetchone()
            if version_row is None or int(version_row[0]) != METADATA_SCHEMA_VERSION:
                raise GenerationCoordinatorError("Dolphin metadata schema is unavailable or incompatible")
            yield connection
        except sqlite3.Error as exc:
            raise GenerationCoordinatorError("Dolphin generation storage is busy or unavailable") from exc
        finally:
            connection.close()


class _OperationAuthority:
    def __init__(self, target_head_commit: str, target_fingerprint: str, pipeline_key: str) -> None:
        self.target_head_commit = target_head_commit
        self.target_fingerprint = target_fingerprint
        self.pipeline_key = pipeline_key


def _require_operation_authority(
    connection: sqlite3.Connection,
    lease: OperationLease,
    observed_at: str,
) -> _OperationAuthority:
    row = connection.execute(
        """
        SELECT o.workspace_id, o.state, o.target_head_commit, c.target_fingerprint,
               c.pipeline_key, l.expires_at
        FROM operation_leases AS l
        JOIN workspace_operations AS o ON o.operation_id = l.operation_id
        JOIN operation_checkpoints AS c ON c.operation_id = o.operation_id
        JOIN runtime_instances AS r ON r.runtime_id = l.runtime_id
        WHERE l.operation_id = ? AND l.lease_id = ? AND l.runtime_id = ?
          AND r.state = 'active' AND r.expires_at > ?
        """,
        (lease.operation.operation_id, lease.lease_id, lease.runtime_id, observed_at),
    ).fetchone()
    if row is None or row[0] != lease.operation.workspace_id or row[1] != "running" or row[5] <= observed_at:
        raise GenerationCoordinatorError("Dolphin operation lease is unavailable or expired")
    target_head_commit = _bounded_text(row[2], "operation target commit")
    target_fingerprint = _bounded_text(row[3], "target fingerprint")
    pipeline_key = _bounded_text(row[4], "pipeline key")
    if target_fingerprint != f"git-head-v1:{target_head_commit}":
        raise GenerationCoordinatorError("Dolphin operation target fingerprint is incompatible")
    return _OperationAuthority(target_head_commit, target_fingerprint, pipeline_key)


def _require_generation(
    connection: sqlite3.Connection,
    generation_id: str,
    lease: OperationLease,
) -> StagingGeneration:
    _bounded(generation_id, "generation ID", maximum=_PRIVATE_ID_MAX_LENGTH)
    row = connection.execute(_GENERATION_BY_ID, (generation_id,)).fetchone()
    if row is None:
        raise GenerationCoordinatorError("Dolphin generation is unavailable")
    generation = _generation_from_row(row)
    if (
        generation.operation_id != lease.operation.operation_id
        or generation.workspace_id != lease.operation.workspace_id
    ):
        raise GenerationCoordinatorError("Dolphin generation belongs to another operation")
    return generation


def _require_generation_identity(
    generation: StagingGeneration,
    lease: OperationLease,
    target_fingerprint: str,
    pipeline_key: str,
) -> None:
    if (
        generation.operation_id != lease.operation.operation_id
        or generation.workspace_id != lease.operation.workspace_id
        or generation.target_fingerprint != target_fingerprint
        or generation.pipeline_key != pipeline_key
    ):
        raise GenerationConflict("Dolphin operation already links to an incompatible generation")


_GENERATION_COLUMNS = """
generation_id, operation_id, workspace_id, target_fingerprint, pipeline_key, state,
vector_commit_token, vector_digest, vector_row_count, vector_provider, vector_model,
vector_dimensions, embedding_contract_version, manifest_id, manifest_digest,
metadata_item_count, keyword_item_count, publication_id, publication_revision, created_at,
ready_at, published_at
"""
_GENERATION_BY_ID = f"SELECT {_GENERATION_COLUMNS} FROM generations WHERE generation_id = ?"
_GENERATION_BY_OPERATION = f"SELECT {_GENERATION_COLUMNS} FROM generations WHERE operation_id = ?"


def _generation_from_row(row: tuple[object, ...]) -> StagingGeneration:
    try:
        return StagingGeneration(
            generation_id=_bounded_text(row[0], "generation ID"),
            operation_id=_bounded_text(row[1], "operation ID"),
            workspace_id=_bounded_text(row[2], "workspace ID"),
            target_fingerprint=_bounded_text(row[3], "target fingerprint"),
            pipeline_key=_bounded_text(row[4], "pipeline key"),
            state=_state(row[5]),
            vector_commit_token=_optional_text(row[6], "vector commit token"),
            vector_digest=_optional_text(row[7], "vector digest"),
            vector_row_count=_optional_count(row[8], "vector row count"),
            vector_provider=cast(Literal["openai"] | None, _optional_text(row[9], "vector provider")),
            vector_model=cast(
                Literal["text-embedding-3-small"] | None,
                _optional_text(row[10], "vector model"),
            ),
            vector_dimensions=cast(Literal[1_536] | None, _optional_count(row[11], "vector dimensions")),
            embedding_contract_version=cast(
                Literal[1] | None,
                _optional_count(row[12], "embedding contract version"),
            ),
            manifest_id=_optional_text(row[13], "manifest ID"),
            manifest_digest=_optional_text(row[14], "manifest digest"),
            metadata_item_count=_optional_count(row[15], "metadata item count"),
            keyword_item_count=_optional_count(row[16], "keyword item count"),
            created_at=_parse_timestamp(row[19], "generation creation timestamp"),
            ready_at=_optional_timestamp(row[20], "generation ready timestamp"),
            published_at=_optional_timestamp(row[21], "generation publication timestamp"),
        )
    except ValidationError as exc:
        raise GenerationCoordinatorError("Dolphin generation metadata is invalid") from exc


_SNAPSHOT_BY_GENERATION = """
SELECT g.publication_id, g.generation_id, g.workspace_id, g.operation_id,
       g.target_fingerprint, g.pipeline_key, g.manifest_id, g.manifest_digest,
       g.vector_commit_token, g.vector_digest, g.vector_row_count,
       g.vector_provider, g.vector_model, g.vector_dimensions, g.embedding_contract_version,
       g.metadata_item_count, g.keyword_item_count, g.publication_revision, g.published_at
FROM generations AS g
WHERE g.generation_id = ? AND g.state = 'published'
"""


def _snapshot_by_generation(connection: sqlite3.Connection, generation_id: str) -> PublishedSnapshot | None:
    row = connection.execute(_SNAPSHOT_BY_GENERATION, (generation_id,)).fetchone()
    return None if row is None else _snapshot_from_row(row)


def _current_snapshot(connection: sqlite3.Connection, workspace_id: str) -> PublishedSnapshot | None:
    row = connection.execute(
        """
        SELECT g.publication_id, g.generation_id, g.workspace_id, g.operation_id,
               g.target_fingerprint, g.pipeline_key, g.manifest_id, g.manifest_digest,
               g.vector_commit_token, g.vector_digest, g.vector_row_count,
               g.vector_provider, g.vector_model, g.vector_dimensions, g.embedding_contract_version,
               g.metadata_item_count, g.keyword_item_count, g.publication_revision, g.published_at
        FROM workspace_publications AS p
        JOIN generations AS g
          ON g.generation_id = p.generation_id AND g.publication_id = p.publication_id
        WHERE p.workspace_id = ? AND g.state = 'published'
        """,
        (workspace_id,),
    ).fetchone()
    return None if row is None else _snapshot_from_row(row)


def _snapshot_from_row(row: tuple[object, ...]) -> PublishedSnapshot:
    try:
        return PublishedSnapshot(
            publication_id=_bounded_text(row[0], "publication ID"),
            generation_id=_bounded_text(row[1], "generation ID"),
            workspace_id=_bounded_text(row[2], "workspace ID"),
            operation_id=_bounded_text(row[3], "operation ID"),
            target_fingerprint=_bounded_text(row[4], "target fingerprint"),
            pipeline_key=_bounded_text(row[5], "pipeline key"),
            manifest_id=_bounded_text(row[6], "manifest ID"),
            manifest_digest=_bounded_text(row[7], "manifest digest"),
            vector_commit_token=_bounded_text(row[8], "vector commit token"),
            vector_digest=_bounded_text(row[9], "vector digest"),
            vector_row_count=_count_value(row[10], "vector row count"),
            vector_provider=cast(Literal["openai"], _bounded_text(row[11], "vector provider")),
            vector_model=cast(
                Literal["text-embedding-3-small"],
                _bounded_text(row[12], "vector model"),
            ),
            vector_dimensions=cast(Literal[1_536], _count_value(row[13], "vector dimensions")),
            embedding_contract_version=cast(
                Literal[1],
                _count_value(row[14], "embedding contract version"),
            ),
            metadata_item_count=_count_value(row[15], "metadata item count"),
            keyword_item_count=_count_value(row[16], "keyword item count"),
            revision=_positive_count_value(row[17], "publication revision"),
            published_at=_parse_timestamp(row[18], "publication timestamp"),
        )
    except ValidationError as exc:
        raise GenerationCoordinatorError("Dolphin published snapshot metadata is invalid") from exc


def _state(value: object) -> GenerationState:
    state = _bounded_text(value, "generation state")
    if state not in {"staging", "ready", "published"}:
        raise GenerationCoordinatorError("Dolphin generation state is invalid")
    return cast(GenerationState, state)


def _bounded(value: str, label: str, *, maximum: int = _PRIVATE_VALUE_MAX_LENGTH) -> None:
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise GenerationCoordinatorError(f"Dolphin {label} is invalid")


def _bounded_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise GenerationCoordinatorError(f"Dolphin {label} is invalid")
    _bounded(value, label)
    return value


def _optional_text(value: object, label: str) -> str | None:
    return None if value is None else _bounded_text(value, label)


def _count(value: int, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise GenerationCoordinatorError(f"Dolphin {label} is invalid")


def _count_value(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise GenerationCoordinatorError(f"Dolphin {label} is invalid")
    return value


def _positive_count_value(value: object, label: str) -> int:
    result = _count_value(value, label)
    if result < 1:
        raise GenerationCoordinatorError(f"Dolphin {label} is invalid")
    return result


def _optional_count(value: object, label: str) -> int | None:
    return None if value is None else _count_value(value, label)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise GenerationCoordinatorError("Dolphin generation timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat()


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise GenerationCoordinatorError(f"Dolphin {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GenerationCoordinatorError(f"Dolphin {label} is invalid") from exc
    if parsed.tzinfo is None:
        raise GenerationCoordinatorError(f"Dolphin {label} is invalid")
    return parsed.astimezone(UTC)


def _optional_timestamp(value: object, label: str) -> datetime | None:
    return None if value is None else _parse_timestamp(value, label)
