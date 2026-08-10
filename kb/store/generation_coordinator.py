"""SQLite visibility authority for atomic workspace generations."""

from __future__ import annotations

import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import groupby
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from kb.artifacts import ArtifactCorrupt, identify_chunk_artifact_set
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
from kb.generation_content import StagedChunkMembership, identify_chunk_membership, identify_generation_content_manifest
from kb.generation_keyword import (
    GenerationKeywordDocument,
    GenerationKeywordError,
    VerifiedGenerationKeywordCommit,
    identify_generation_keyword_commit,
    identify_generation_keyword_index,
)
from kb.runtime.schema import METADATA_SCHEMA_VERSION
from kb.runtime.storage import StorageLayout, StorageLayoutError
from kb.services.workspace_registry import OperationLease
from kb.store.chunk_artifacts import ChunkArtifactStore, VerifiedArtifactObservation

_READ_LEASE_MAXIMUM = timedelta(seconds=60)
_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 1_000
_WRITE_LOCK_DEADLINE_SECONDS = 3.0
_WRITE_LOCK_INITIAL_BACKOFF_SECONDS = 0.025
_WRITE_LOCK_MAX_BACKOFF_SECONDS = 0.25
_EXPIRED_READ_LEASE_PRUNE_LIMIT = 256
_PRIVATE_ID_MAX_LENGTH = 128
_PRIVATE_VALUE_MAX_LENGTH = 256


@dataclass(frozen=True, slots=True)
class _VerifiedGenerationArtifacts:
    manifest: VerifiedGenerationManifest
    observations: tuple[VerifiedArtifactObservation, ...]


class SQLiteGenerationCoordinator:
    """Publish complete generations through one SQLite compare-and-swap pointer."""

    def __init__(self, layout: StorageLayout, *, clock: Callable[[], datetime] | None = None) -> None:
        self._layout = layout
        self._clock = clock or _system_utc_now

    def create_staging(self, lease: OperationLease) -> StagingGeneration:
        observed_at = _timestamp(self._clock())
        with self._connection() as connection:
            _begin_write(connection)
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
    ) -> StagingGeneration:
        observed_at = _timestamp(self._clock())
        with self._connection() as connection:
            _begin_write(connection)
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
    ) -> StagingGeneration:
        preflight = self._preflight_generation_authority(lease, manifest.generation_id)
        if preflight.vector_commit_token is None or preflight.vector_digest is None:
            raise GenerationCoordinatorError("Dolphin generation vectors are not durably verified")
        verified_artifacts = self._verify_generation_artifacts(manifest.generation_id)
        observed_at = _timestamp(self._clock())
        with self._connection() as connection:
            _begin_write(connection)
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
                keyword_index_digest = _require_persisted_content_manifest(
                    connection,
                    manifest,
                    verify_expected_keyword_index=generation.state == "staging",
                )
                self._require_verified_artifacts_unchanged(
                    connection,
                    manifest.generation_id,
                    verified_artifacts,
                )
                _require_operation_authority(connection, lease, _timestamp(self._clock()))
                if generation.state in {"ready", "published"}:
                    if existing != supplied or generation.vector_row_count != manifest.vector_row_count:
                        raise GenerationConflict("Dolphin generation already records a different complete manifest")
                    _mark_generation_bindings_validated(
                        connection,
                        manifest.generation_id,
                        keyword_index_digest,
                    )
                    connection.commit()
                    return generation
                if generation.vector_commit_token is None or generation.vector_digest is None:
                    raise GenerationCoordinatorError("Dolphin generation vectors are not durably verified")
                if generation.vector_row_count != manifest.vector_row_count:
                    raise GenerationConflict("Dolphin manifest vector count does not match verified vectors")
                _mark_generation_bindings_validated(
                    connection,
                    manifest.generation_id,
                    keyword_index_digest,
                )
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
    ) -> PublishedSnapshot:
        if expected_previous_generation_id is not None:
            _bounded(expected_previous_generation_id, "expected generation ID", maximum=_PRIVATE_ID_MAX_LENGTH)
        preflight = self._preflight_generation_authority(lease, generation_id)
        if preflight.state not in {"ready", "published"}:
            raise GenerationCoordinatorError("Dolphin generation is not ready for publication")
        verified_artifacts = self._verify_generation_artifacts(generation_id)
        observed_at = _timestamp(self._clock())
        with self._connection() as connection:
            _begin_write(connection)
            try:
                authority = _require_operation_authority(connection, lease, observed_at)
                generation = _require_generation(connection, generation_id, lease)
                self._require_verified_artifacts_unchanged(
                    connection,
                    generation_id,
                    verified_artifacts,
                )
                authority = _require_operation_authority(
                    connection,
                    lease,
                    _timestamp(self._clock()),
                )
                current_row = connection.execute(
                    "SELECT generation_id, revision FROM workspace_publications WHERE workspace_id = ?",
                    (generation.workspace_id,),
                ).fetchone()
                current_generation_id = str(current_row[0]) if current_row is not None else None
                if generation.state == "published" and current_generation_id == generation_id:
                    keyword_index_digest = _require_generation_content_binding(connection, generation)
                    if generation.previous_generation_id != expected_previous_generation_id:
                        raise GenerationConflict("Dolphin publication replay has a different predecessor")
                    _mark_generation_bindings_validated(connection, generation_id, keyword_index_digest)
                    snapshot = _snapshot_by_generation(connection, generation_id)
                    if snapshot is None:
                        raise GenerationCoordinatorError("Dolphin published generation pointer is invalid")
                    connection.commit()
                    return snapshot
                if current_generation_id != expected_previous_generation_id:
                    raise GenerationConflict("Dolphin published generation changed before pointer swap")
                if generation.state != "ready":
                    raise GenerationCoordinatorError("Dolphin generation is not ready for publication")
                keyword_index_digest = _require_generation_content_binding(connection, generation)
                _mark_generation_bindings_validated(connection, generation_id, keyword_index_digest)
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
                    SET state = 'published', publication_id = ?, publication_revision = ?,
                        previous_generation_id = ?, published_at = ?
                    WHERE generation_id = ? AND state = 'ready'
                    """,
                    (publication_id, revision, expected_previous_generation_id, observed_at, generation_id),
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

    def _preflight_generation_authority(
        self,
        lease: OperationLease,
        generation_id: str,
    ) -> StagingGeneration:
        observed_at = _timestamp(self._clock())
        with self._connection(read_only=True) as connection:
            _require_operation_authority(connection, lease, observed_at)
            return _require_generation(connection, generation_id, lease)

    def _verify_generation_artifacts(self, generation_id: str) -> _VerifiedGenerationArtifacts | None:
        _bounded(generation_id, "generation ID", maximum=_PRIVATE_ID_MAX_LENGTH)
        with self._connection(read_only=True) as connection:
            manifest = _content_manifest_for_generation(connection, generation_id)
            if manifest is None:
                return None
            rows = connection.execute(
                """
                SELECT artifact_id, artifact_utf8_bytes, artifact_characters, artifact_lines
                FROM generation_chunk_memberships
                WHERE generation_id = ?
                GROUP BY artifact_id, artifact_utf8_bytes, artifact_characters, artifact_lines
                ORDER BY artifact_id
                """,
                (generation_id,),
            ).fetchall()
        artifacts = ChunkArtifactStore(self._layout)
        observed = {}
        observations = []
        for row in rows:
            _text, descriptor, observation = artifacts.read_verified_artifact_observation(str(row[0]))
            expected = (str(row[0]), int(row[1]), int(row[2]), int(row[3]))
            actual = (
                descriptor.artifact_id,
                descriptor.utf8_bytes,
                descriptor.characters,
                descriptor.lines,
            )
            if actual != expected:
                raise ArtifactCorrupt("Dolphin generation artifact does not match its manifest")
            observed[descriptor.artifact_id] = descriptor
            observations.append(observation)
        artifact_set = identify_chunk_artifact_set(
            tuple(observed),
            total_utf8_bytes=sum(artifact.utf8_bytes for artifact in observed.values()),
        )
        if (
            artifact_set.set_digest != manifest.artifact_set_digest
            or artifact_set.artifact_count != manifest.artifact_count
            or artifact_set.total_utf8_bytes != manifest.artifact_utf8_bytes
        ):
            raise ArtifactCorrupt("Dolphin generation artifact set does not match its manifest")
        return _VerifiedGenerationArtifacts(manifest=manifest, observations=tuple(observations))

    def _require_verified_artifacts_unchanged(
        self,
        connection: sqlite3.Connection,
        generation_id: str,
        verified: _VerifiedGenerationArtifacts | None,
    ) -> None:
        current = _content_manifest_for_generation(connection, generation_id)
        if verified is None or current != verified.manifest:
            raise GenerationCoordinatorError("Dolphin generation artifacts changed before visibility transition")
        ChunkArtifactStore(self._layout).require_unchanged(verified.observations)

    def current_snapshot(self, workspace_id: str) -> PublishedSnapshot | None:
        _bounded(workspace_id, "workspace ID", maximum=_PRIVATE_ID_MAX_LENGTH)
        with self._connection(read_only=True) as connection:
            return _current_snapshot(connection, workspace_id)

    def acquire_read(
        self,
        workspace_id: str,
        *,
        lease_duration: timedelta,
    ) -> GenerationReadLease:
        _bounded(workspace_id, "workspace ID", maximum=_PRIVATE_ID_MAX_LENGTH)
        if not isinstance(lease_duration, timedelta) or lease_duration <= timedelta(0):
            raise GenerationCoordinatorError("Dolphin generation read lease window is invalid")
        if lease_duration > _READ_LEASE_MAXIMUM:
            raise GenerationCoordinatorError("Dolphin generation read lease window is invalid")
        acquired = _utc(self._clock())
        expiry = acquired + lease_duration
        with self._connection() as connection:
            _begin_write(connection)
            try:
                connection.execute(
                    """
                    DELETE FROM generation_reader_leases
                    WHERE lease_id IN (
                        SELECT lease_id
                        FROM generation_reader_leases
                        WHERE expires_at <= ?
                        ORDER BY expires_at, lease_id
                        LIMIT ?
                    )
                    """,
                    (acquired.isoformat(), _EXPIRED_READ_LEASE_PRUNE_LIMIT),
                )
                snapshot = _current_snapshot(connection, workspace_id)
                if snapshot is None:
                    raise GenerationReadLeaseUnavailable("Dolphin workspace has no published snapshot")
                lease_id = f"read_{uuid.uuid4().hex}"
                connection.execute(
                    """
                    INSERT INTO generation_reader_leases (
                        lease_id, workspace_id, generation_id, publication_id, acquired_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lease_id,
                        snapshot.workspace_id,
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

    def snapshot_for_lease(self, lease_id: str) -> PublishedSnapshot:
        _bounded(lease_id, "generation read lease ID", maximum=_PRIVATE_ID_MAX_LENGTH)
        observed_at = _timestamp(self._clock())
        with self._connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT workspace_id, generation_id, publication_id
                FROM generation_reader_leases
                WHERE lease_id = ? AND expires_at > ?
                """,
                (lease_id, observed_at),
            ).fetchone()
            if row is None:
                raise GenerationReadLeaseUnavailable("Dolphin generation read lease is unavailable or expired")
            snapshot = _snapshot_by_generation(connection, str(row[1]))
            if snapshot is None or snapshot.workspace_id != row[0] or snapshot.publication_id != row[2]:
                raise GenerationReadLeaseUnavailable("Dolphin generation read lease no longer matches its snapshot")
            return snapshot

    def release_read(self, lease: GenerationReadLease) -> None:
        with self._connection() as connection:
            _begin_write(connection)
            try:
                connection.execute(
                    """
                    DELETE FROM generation_reader_leases
                    WHERE lease_id = ? AND workspace_id = ? AND generation_id = ? AND publication_id = ?
                    """,
                    (
                        lease.lease_id,
                        lease.snapshot.workspace_id,
                        lease.snapshot.generation_id,
                        lease.snapshot.publication_id,
                    ),
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
            connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
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


def _require_persisted_content_manifest(
    connection: sqlite3.Connection,
    manifest: VerifiedGenerationManifest,
    *,
    verify_expected_keyword_index: bool,
) -> str:
    persisted = _content_manifest_for_generation(connection, manifest.generation_id)
    if persisted != manifest:
        raise GenerationCoordinatorError("Dolphin generation content manifest is unavailable or incompatible")
    _require_content_counts(connection, manifest)
    return _require_generation_keyword_binding(
        connection,
        manifest,
        verify_expected_index=verify_expected_keyword_index,
    )


def _content_manifest_for_generation(
    connection: sqlite3.Connection,
    generation_id: str,
) -> VerifiedGenerationManifest | None:
    row = connection.execute(
        """
        SELECT manifest_id, manifest_digest, artifact_set_digest, artifact_count,
               artifact_utf8_bytes, metadata_item_count, keyword_item_count, vector_row_count
        FROM generation_content_manifests WHERE generation_id = ?
        """,
        (generation_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return VerifiedGenerationManifest(
            generation_id=generation_id,
            manifest_id=str(row[0]),
            manifest_digest=str(row[1]),
            artifact_set_digest=str(row[2]),
            artifact_count=int(row[3]),
            artifact_utf8_bytes=int(row[4]),
            metadata_item_count=int(row[5]),
            keyword_item_count=int(row[6]),
            vector_row_count=int(row[7]),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise GenerationCoordinatorError("Dolphin generation content manifest is invalid") from exc


def _require_generation_content_binding(
    connection: sqlite3.Connection,
    generation: StagingGeneration,
) -> str:
    row = connection.execute(
        """
        SELECT manifest_id, manifest_digest, metadata_item_count, keyword_item_count,
               vector_row_count, artifact_set_digest, artifact_count, artifact_utf8_bytes
        FROM generation_content_manifests WHERE generation_id = ?
        """,
        (generation.generation_id,),
    ).fetchone()
    if row is None or tuple(row[:5]) != (
        generation.manifest_id,
        generation.manifest_digest,
        generation.metadata_item_count,
        generation.keyword_item_count,
        generation.vector_row_count,
    ):
        raise GenerationCoordinatorError("Dolphin generation content binding is unavailable or incompatible")
    manifest = _content_manifest_for_generation(connection, generation.generation_id)
    if manifest is None:
        raise GenerationCoordinatorError("Dolphin generation content binding is unavailable or incompatible")
    _require_content_counts(connection, manifest)
    return _require_generation_keyword_binding(connection, manifest, verify_expected_index=False)


def _mark_generation_bindings_validated(
    connection: sqlite3.Connection,
    generation_id: str,
    keyword_index_digest: str,
) -> None:
    cursor = connection.execute(
        """
        UPDATE generation_content_manifests
        SET validated_content_revision = content_revision
        WHERE generation_id = ?
        """,
        (generation_id,),
    )
    if cursor.rowcount != 1:
        raise GenerationCoordinatorError("Dolphin generation content revision is unavailable")
    cursor = connection.execute(
        """
        UPDATE generation_keyword_commits
        SET validated_keyword_revision = keyword_revision,
            validated_fts_digest = ?
        WHERE generation_id = ?
        """,
        (keyword_index_digest, generation_id),
    )
    if cursor.rowcount != 1:
        raise GenerationCoordinatorError("Dolphin generation keyword revision is unavailable")


def _require_generation_keyword_binding(
    connection: sqlite3.Connection,
    manifest: VerifiedGenerationManifest,
    *,
    verify_expected_index: bool,
) -> str:
    row = connection.execute(
        """
        SELECT generation_id, manifest_id, manifest_digest, commit_digest, item_count,
               keyword_revision, validated_keyword_revision, validated_fts_digest
        FROM generation_keyword_commits
        WHERE generation_id = ?
        """,
        (manifest.generation_id,),
    ).fetchone()
    if row is None:
        raise GenerationCoordinatorError("Dolphin generation keyword commit is unavailable")
    try:
        commit = VerifiedGenerationKeywordCommit(
            generation_id=row[0],
            manifest_id=row[1],
            manifest_digest=row[2],
            commit_digest=row[3],
            item_count=row[4],
        )
    except ValidationError as exc:
        raise GenerationCoordinatorError("Dolphin generation keyword commit is invalid") from exc
    if (
        commit.manifest_id != manifest.manifest_id
        or commit.manifest_digest != manifest.manifest_digest
        or commit.item_count != manifest.keyword_item_count
    ):
        raise GenerationCoordinatorError("Dolphin generation keyword commit is incompatible")
    rows = connection.execute(
        """
        SELECT d.document_rowid, d.chunk_instance_id, d.artifact_id, d.relative_path, d.language, d.text,
               m.artifact_id, m.relative_path, m.language
        FROM generation_keyword_documents AS d
        JOIN generation_chunk_memberships AS m
          ON m.generation_id = d.generation_id
         AND m.chunk_instance_id = d.chunk_instance_id
        WHERE d.generation_id = ?
        ORDER BY d.chunk_instance_id
        """,
        (manifest.generation_id,),
    ).fetchall()
    documents: list[GenerationKeywordDocument] = []
    document_rowids: list[tuple[int, GenerationKeywordDocument]] = []
    for document_row in rows:
        if tuple(document_row[2:5]) != tuple(document_row[6:9]):
            raise GenerationCoordinatorError("Dolphin generation keyword document is incompatible")
        try:
            document = GenerationKeywordDocument(
                chunk_instance_id=document_row[1],
                artifact_id=document_row[2],
                relative_path=document_row[3],
                language=document_row[4],
                text=document_row[5],
            )
            document_rowid = int(document_row[0])
        except (TypeError, ValueError, ValidationError) as exc:
            raise GenerationCoordinatorError("Dolphin generation keyword document is invalid") from exc
        documents.append(document)
        document_rowids.append((document_rowid, document))
    observed = identify_generation_keyword_commit(
        manifest.generation_id,
        manifest.manifest_id,
        manifest.manifest_digest,
        documents,
    )
    if observed != commit:
        raise GenerationCoordinatorError("Dolphin generation keyword binding is invalid")
    if verify_expected_index:
        actual_index_digest = _generation_fts_digest(connection, manifest.generation_id)
        actual_terms = _generation_fts_term_commits(connection, manifest.generation_id)
        expected_index_digest, expected_terms = _expected_fts_state(manifest.generation_id, document_rowids)
        if actual_index_digest != expected_index_digest or actual_terms != expected_terms:
            raise GenerationCoordinatorError("Dolphin generation keyword index is invalid")
        connection.executemany(
            """
            INSERT INTO generation_keyword_term_commits (
                generation_id, term, posting_digest, posting_count
            ) VALUES (?, ?, ?, ?)
            """,
            ((manifest.generation_id, term, digest, count) for term, (digest, count) in sorted(expected_terms.items())),
        )
    elif row[5] != row[6] or not isinstance(row[7], str) or len(row[7]) != 64:
        raise GenerationCoordinatorError("Dolphin generation keyword index is invalid")
    else:
        actual_index_digest = row[7]
    return actual_index_digest


def _generation_fts_digest(connection: sqlite3.Connection, generation_id: str) -> str:
    postings = connection.execute(
        """
        SELECT d.chunk_instance_id, v.term, v.col, v.offset
        FROM generation_keyword_vocabulary AS v
        JOIN generation_keyword_documents AS d ON d.document_rowid = v.doc
        WHERE d.generation_id = ?
        ORDER BY d.chunk_instance_id, v.term, v.col, v.offset
        """,
        (generation_id,),
    )
    try:
        return identify_generation_keyword_index(generation_id, (tuple(row) for row in postings))
    except GenerationKeywordError as exc:
        raise GenerationCoordinatorError("Dolphin generation keyword index is invalid") from exc


def _generation_fts_term_commits(
    connection: sqlite3.Connection,
    generation_id: str,
) -> dict[str, tuple[str, int]]:
    rows = connection.execute(
        """
        SELECT v.term, d.chunk_instance_id, v.col, v.offset
        FROM generation_keyword_vocabulary AS v
        JOIN generation_keyword_documents AS d ON d.document_rowid = v.doc
        WHERE d.generation_id = ?
        ORDER BY v.term, d.chunk_instance_id, v.col, v.offset
        """,
        (generation_id,),
    )
    try:
        return _term_commits_from_rows(generation_id, rows)
    except GenerationKeywordError as exc:
        raise GenerationCoordinatorError("Dolphin generation keyword index is invalid") from exc


def _expected_fts_state(
    generation_id: str,
    documents: list[tuple[int, GenerationKeywordDocument]],
) -> tuple[str, dict[str, tuple[str, int]]]:
    try:
        with sqlite3.connect(":memory:") as expected:
            expected.execute(
                """
                CREATE TABLE expected_keyword_documents (
                    document_rowid INTEGER PRIMARY KEY,
                    chunk_instance_id TEXT NOT NULL UNIQUE
                )
                """
            )
            expected.execute(
                """
                CREATE VIRTUAL TABLE expected_keyword_fts USING fts5(
                    text,
                    relative_path,
                    language,
                    tokenize = 'unicode61 remove_diacritics 2'
                )
                """
            )
            expected.execute(
                "CREATE VIRTUAL TABLE expected_keyword_vocabulary USING fts5vocab(expected_keyword_fts, 'instance')"
            )
            expected.executemany(
                "INSERT INTO expected_keyword_documents(document_rowid, chunk_instance_id) VALUES (?, ?)",
                ((rowid, document.chunk_instance_id) for rowid, document in documents),
            )
            expected.executemany(
                """
                INSERT INTO expected_keyword_fts(rowid, text, relative_path, language)
                VALUES (?, ?, ?, ?)
                """,
                ((rowid, document.text, document.relative_path, document.language) for rowid, document in documents),
            )
            rows = expected.execute(
                """
                SELECT d.chunk_instance_id, v.term, v.col, v.offset
                FROM expected_keyword_vocabulary AS v
                JOIN expected_keyword_documents AS d ON d.document_rowid = v.doc
                ORDER BY d.chunk_instance_id, v.term, v.col, v.offset
                """
            )
            index_digest = identify_generation_keyword_index(generation_id, (tuple(row) for row in rows))
            term_rows = expected.execute(
                """
                SELECT v.term, d.chunk_instance_id, v.col, v.offset
                FROM expected_keyword_vocabulary AS v
                JOIN expected_keyword_documents AS d ON d.document_rowid = v.doc
                ORDER BY v.term, d.chunk_instance_id, v.col, v.offset
                """
            )
            return index_digest, _term_commits_from_rows(generation_id, term_rows)
    except (KeyError, TypeError, ValueError, sqlite3.Error, GenerationKeywordError) as exc:
        raise GenerationCoordinatorError("Dolphin generation keyword index is invalid") from exc


def _term_commits_from_rows(
    generation_id: str,
    rows: Iterator[sqlite3.Row] | sqlite3.Cursor,
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


def _require_content_counts(
    connection: sqlite3.Connection,
    manifest: VerifiedGenerationManifest,
) -> None:
    rows = connection.execute(
        """
        SELECT chunk_instance_id, artifact_id, artifact_utf8_bytes, artifact_characters,
               artifact_lines, relative_path, source_file_fingerprint, start_line, end_line,
               language, chunker_key, embedding_cache_key, membership_digest
        FROM generation_chunk_memberships
        WHERE generation_id = ?
        ORDER BY chunk_instance_id
        """,
        (manifest.generation_id,),
    ).fetchall()
    try:
        memberships = tuple(_membership_from_row(row) for row in rows)
    except ValidationError as exc:
        raise GenerationCoordinatorError("Dolphin generation chunk membership is invalid") from exc
    artifacts = {}
    for membership, row in zip(memberships, rows, strict=True):
        if identify_chunk_membership(manifest.generation_id, membership) != row[12]:
            raise GenerationCoordinatorError("Dolphin generation chunk membership digest is invalid")
        existing = artifacts.setdefault(membership.artifact.artifact_id, membership.artifact)
        if existing != membership.artifact:
            raise GenerationCoordinatorError("Dolphin generation artifact metadata is inconsistent")
    artifact_set = identify_chunk_artifact_set(
        tuple(artifacts),
        total_utf8_bytes=sum(artifact.utf8_bytes for artifact in artifacts.values()),
    )
    observed = identify_generation_content_manifest(manifest.generation_id, memberships, artifact_set)
    if observed != manifest:
        raise GenerationCoordinatorError("Dolphin generation chunk membership counts are incompatible")


def _membership_from_row(row: tuple[object, ...]) -> StagedChunkMembership:
    return StagedChunkMembership.model_validate(
        {
            "chunk_instance_id": row[0],
            "artifact": {
                "artifact_id": row[1],
                "format": "dolphin-chunk-text-v1",
                "utf8_bytes": row[2],
                "characters": row[3],
                "lines": row[4],
            },
            "relative_path": row[5],
            "source_file_fingerprint": row[6],
            "start_line": row[7],
            "end_line": row[8],
            "language": row[9],
            "chunker_key": row[10],
            "embedding_cache_key": row[11],
        }
    )


_GENERATION_COLUMNS = """
generation_id, operation_id, workspace_id, target_fingerprint, pipeline_key, state,
vector_commit_token, vector_digest, vector_row_count, vector_provider, vector_model,
vector_dimensions, embedding_contract_version, manifest_id, manifest_digest,
metadata_item_count, keyword_item_count, publication_id, publication_revision,
previous_generation_id, created_at, ready_at, published_at
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
            previous_generation_id=_optional_text(row[19], "previous generation ID"),
            created_at=_parse_timestamp(row[20], "generation creation timestamp"),
            ready_at=_optional_timestamp(row[21], "generation ready timestamp"),
            published_at=_optional_timestamp(row[22], "generation publication timestamp"),
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


def _system_utc_now() -> datetime:
    return datetime.now(UTC)


def _begin_write(connection: sqlite3.Connection) -> None:
    """Acquire SQLite's writer slot with short bounded contention backoff."""
    deadline = time.monotonic() + _WRITE_LOCK_DEADLINE_SECONDS
    backoff = _WRITE_LOCK_INITIAL_BACKOFF_SECONDS
    connection.execute("PRAGMA busy_timeout = 0")
    try:
        while True:
            try:
                connection.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                remaining = deadline - time.monotonic()
                if remaining <= 0 or ("locked" not in message and "busy" not in message):
                    raise
                time.sleep(min(backoff, remaining))
                backoff = min(backoff * 2, _WRITE_LOCK_MAX_BACKOFF_SECONDS)
    finally:
        connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
