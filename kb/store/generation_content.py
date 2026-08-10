"""SQLite-authoritative generation membership and verified artifact materialization."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from kb.artifacts import MAX_GENERATION_ARTIFACTS, ArtifactCorrupt, identify_chunk_artifact_set
from kb.generation import PublishedSnapshot, StagingGeneration, VerifiedGenerationManifest
from kb.generation_content import (
    GenerationContentConflict,
    GenerationContentError,
    PublishedChunkMembership,
    PublishedChunkUnavailable,
    StagedChunkMembership,
    identify_chunk_membership,
    identify_generation_content_manifest,
)
from kb.generation_keyword import (
    GenerationKeywordDocument,
    VerifiedGenerationKeywordCommit,
    identify_generation_keyword_commit,
)
from kb.runtime.schema import METADATA_SCHEMA_VERSION
from kb.runtime.storage import StorageLayout, StorageLayoutError
from kb.services.workspace_registry import OperationLease
from kb.store.chunk_artifacts import ChunkArtifactStore

_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 1_000
_WRITE_LOCK_DEADLINE_SECONDS = 3.0
_WRITE_LOCK_INITIAL_BACKOFF_SECONDS = 0.025
_WRITE_LOCK_MAX_BACKOFF_SECONDS = 0.25


class SQLiteGenerationContentStore:
    """Bind verified immutable artifacts to staging and published generations."""

    def __init__(
        self,
        layout: StorageLayout,
        artifacts: ChunkArtifactStore | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._layout = layout
        self._artifacts = artifacts or ChunkArtifactStore(layout)
        self._clock = clock or (lambda: datetime.now(UTC))

    def stage_manifest(
        self,
        lease: OperationLease,
        generation: StagingGeneration,
        memberships: Sequence[StagedChunkMembership],
    ) -> VerifiedGenerationManifest:
        preflight_at = _timestamp(self._clock())
        if isinstance(memberships, (str, bytes)):
            raise GenerationContentError("Dolphin generation chunk membership is invalid")
        staged = tuple(memberships)
        if len(staged) > MAX_GENERATION_ARTIFACTS:
            raise GenerationContentError("Dolphin generation chunk membership is too large")
        if any(not isinstance(membership, StagedChunkMembership) for membership in staged):
            raise GenerationContentError("Dolphin generation chunk membership is invalid")
        ordered = tuple(sorted(staged, key=lambda membership: membership.chunk_instance_id))
        if len({membership.chunk_instance_id for membership in ordered}) != len(ordered):
            raise GenerationContentError("Dolphin generation chunk membership contains duplicate identities")

        with self._connection(read_only=True) as connection:
            _require_generation_identity(connection, generation, lease, preflight_at)

        verified_artifacts = {}
        verified_texts = {}
        for membership in ordered:
            artifact_id = membership.artifact.artifact_id
            observed = verified_artifacts.get(artifact_id)
            if observed is None:
                text, observed = self._artifacts.read_verified_artifact(artifact_id)
                verified_artifacts[artifact_id] = observed
                verified_texts[artifact_id] = text
            if observed != membership.artifact:
                raise ArtifactCorrupt("Dolphin chunk artifact descriptor does not match generation membership")
        artifact_set = identify_chunk_artifact_set(
            tuple(verified_artifacts),
            total_utf8_bytes=sum(artifact.utf8_bytes for artifact in verified_artifacts.values()),
        )
        manifest = identify_generation_content_manifest(generation.generation_id, ordered, artifact_set)
        keyword_documents = tuple(
            _keyword_document(membership, verified_texts[membership.artifact.artifact_id]) for membership in ordered
        )
        keyword_commit = identify_generation_keyword_commit(
            generation.generation_id,
            manifest.manifest_id,
            manifest.manifest_digest,
            keyword_documents,
        )
        commit_at = _timestamp(self._clock())

        with self._connection() as connection:
            _begin_write(connection)
            try:
                generation_state = _require_generation_identity(
                    connection,
                    generation,
                    lease,
                    commit_at,
                )
                existing = _manifest_for_generation(connection, generation.generation_id)
                if existing is not None:
                    memberships_match = _persisted_memberships_match(
                        connection,
                        generation.generation_id,
                        ordered,
                    )
                    keyword_matches = _persisted_keyword_state_matches(
                        connection,
                        keyword_commit,
                        keyword_documents,
                    )
                    if existing != manifest or not memberships_match or not keyword_matches:
                        raise GenerationContentConflict("Dolphin generation already records different chunk content")
                    connection.commit()
                    return existing
                if generation_state != "staging":
                    raise GenerationContentConflict("Dolphin generation content is already immutable")
                connection.execute(
                    """
                    INSERT INTO generation_content_manifests (
                        generation_id, manifest_id, manifest_digest, artifact_set_digest,
                        artifact_count, artifact_utf8_bytes, metadata_item_count,
                        keyword_item_count, vector_row_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        manifest.generation_id,
                        manifest.manifest_id,
                        manifest.manifest_digest,
                        manifest.artifact_set_digest,
                        manifest.artifact_count,
                        manifest.artifact_utf8_bytes,
                        manifest.metadata_item_count,
                        manifest.keyword_item_count,
                        manifest.vector_row_count,
                        commit_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO generation_keyword_commits (
                        generation_id, manifest_id, manifest_digest, commit_digest,
                        item_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        keyword_commit.generation_id,
                        keyword_commit.manifest_id,
                        keyword_commit.manifest_digest,
                        keyword_commit.commit_digest,
                        keyword_commit.item_count,
                        commit_at,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO generation_chunk_memberships (
                        chunk_instance_id, generation_id, artifact_id, artifact_utf8_bytes,
                        artifact_characters, artifact_lines, relative_path, source_file_fingerprint,
                        start_line, end_line, language, chunker_key, embedding_cache_key,
                        membership_digest
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [_membership_row(generation.generation_id, membership) for membership in ordered],
                )
                connection.executemany(
                    """
                    INSERT INTO generation_keyword_documents (
                        generation_id, chunk_instance_id, artifact_id,
                        relative_path, language, text
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            keyword_commit.generation_id,
                            document.chunk_instance_id,
                            document.artifact_id,
                            document.relative_path,
                            document.language,
                            document.text,
                        )
                        for document in keyword_documents
                    ],
                )
            except Exception:
                connection.rollback()
                raise
            connection.commit()
        return manifest

    def materialize_published_chunk(self, read_lease_id: str, chunk_instance_id: str) -> str:
        _bounded_id(read_lease_id, "generation read lease ID")
        _bounded_id(chunk_instance_id, "chunk instance ID")
        observed_at = _timestamp(self._clock())
        with self._connection(read_only=True) as connection:
            connection.execute("BEGIN")
            canonical = _snapshot_for_live_reader_lease(connection, read_lease_id, observed_at)
            current_manifest = _validated_manifest_for_generation(connection, canonical.generation_id)
            if (
                current_manifest.manifest_id != canonical.manifest_id
                or current_manifest.manifest_digest != canonical.manifest_digest
            ):
                raise GenerationContentError("Dolphin published chunk manifest is corrupt")
            membership = _require_published_membership(connection, canonical, chunk_instance_id)
            connection.commit()
        text, artifact = self._artifacts.read_verified_artifact(membership.artifact.artifact_id)
        if artifact != membership.artifact:
            raise ArtifactCorrupt("Dolphin published chunk artifact does not match its membership")
        return text

    @contextmanager
    def _connection(self, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
        try:
            if not self._layout.metadata_database_exists():
                raise GenerationContentError("Dolphin metadata storage is unavailable")
            target: Path | str = self._layout.metadata_db
            if read_only:
                target = self._layout.metadata_db.as_uri() + "?mode=ro"
            connection = sqlite3.connect(target, uri=read_only, timeout=1, isolation_level=None)
        except (sqlite3.Error, StorageLayoutError) as exc:
            raise GenerationContentError("Dolphin metadata storage is unavailable") from exc
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
            if read_only:
                connection.execute("PRAGMA query_only = ON")
            version = connection.execute("PRAGMA user_version").fetchone()
            if version is None or int(version[0]) != METADATA_SCHEMA_VERSION:
                raise GenerationContentError("Dolphin metadata schema is unavailable or incompatible")
            yield connection
        except sqlite3.Error as exc:
            raise GenerationContentError("Dolphin generation content storage is busy or unavailable") from exc
        finally:
            connection.close()


def _membership_row(generation_id: str, membership: StagedChunkMembership) -> tuple[object, ...]:
    return (
        membership.chunk_instance_id,
        generation_id,
        membership.artifact.artifact_id,
        membership.artifact.utf8_bytes,
        membership.artifact.characters,
        membership.artifact.lines,
        membership.relative_path,
        membership.source_file_fingerprint,
        membership.start_line,
        membership.end_line,
        membership.language,
        membership.chunker_key,
        membership.embedding_cache_key,
        identify_chunk_membership(generation_id, membership),
    )


def _keyword_document(membership: StagedChunkMembership, text: str) -> GenerationKeywordDocument:
    try:
        return GenerationKeywordDocument(
            chunk_instance_id=membership.chunk_instance_id,
            artifact_id=membership.artifact.artifact_id,
            relative_path=membership.relative_path,
            language=membership.language,
            text=text,
        )
    except ValidationError as exc:
        raise GenerationContentError("Dolphin generation keyword document is invalid") from exc


def _require_generation_identity(
    connection: sqlite3.Connection,
    generation: StagingGeneration,
    lease: OperationLease,
    observed_at: str,
) -> str:
    row = connection.execute(
        """
        SELECT g.operation_id, g.workspace_id, g.target_fingerprint, g.pipeline_key, g.state,
               o.state, l.lease_id, l.runtime_id, l.expires_at, r.state, r.expires_at
        FROM generations AS g
        JOIN workspace_operations AS o ON o.operation_id = g.operation_id
        JOIN operation_leases AS l ON l.operation_id = o.operation_id
        JOIN runtime_instances AS r ON r.runtime_id = l.runtime_id
        WHERE g.generation_id = ?
        """,
        (generation.generation_id,),
    ).fetchone()
    if row is None:
        raise GenerationContentError("Dolphin staging generation is unavailable")
    if tuple(row[:4]) != (
        generation.operation_id,
        generation.workspace_id,
        generation.target_fingerprint,
        generation.pipeline_key,
    ):
        raise GenerationContentError("Dolphin staging generation identity is invalid")
    if (
        lease.operation.operation_id != generation.operation_id
        or lease.operation.workspace_id != generation.workspace_id
        or row[5] != "running"
        or row[6] != lease.lease_id
        or row[7] != lease.runtime_id
        or str(row[8]) <= observed_at
        or row[9] != "active"
        or str(row[10]) <= observed_at
    ):
        raise GenerationContentError("Dolphin operation lease is unavailable or expired")
    state = str(row[4])
    if state not in {"staging", "ready", "published"}:
        raise GenerationContentError("Dolphin staging generation state is invalid")
    return state


def _manifest_for_generation(
    connection: sqlite3.Connection,
    generation_id: str,
) -> VerifiedGenerationManifest | None:
    row = connection.execute(
        """
        SELECT generation_id, manifest_id, manifest_digest, artifact_set_digest,
               artifact_count, artifact_utf8_bytes, metadata_item_count,
               keyword_item_count, vector_row_count
        FROM generation_content_manifests WHERE generation_id = ?
        """,
        (generation_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return VerifiedGenerationManifest(
            generation_id=row[0],
            manifest_id=row[1],
            manifest_digest=row[2],
            artifact_set_digest=row[3],
            artifact_count=row[4],
            artifact_utf8_bytes=row[5],
            metadata_item_count=row[6],
            keyword_item_count=row[7],
            vector_row_count=row[8],
        )
    except ValidationError as exc:
        raise GenerationContentError("Dolphin generation content manifest is corrupt") from exc


def _persisted_memberships_match(
    connection: sqlite3.Connection,
    generation_id: str,
    memberships: tuple[StagedChunkMembership, ...],
) -> bool:
    rows = connection.execute(
        """
        SELECT chunk_instance_id, artifact_id, artifact_utf8_bytes, artifact_characters,
               artifact_lines, relative_path, source_file_fingerprint, start_line, end_line,
               language, chunker_key, embedding_cache_key, membership_digest
        FROM generation_chunk_memberships WHERE generation_id = ? ORDER BY chunk_instance_id
        """,
        (generation_id,),
    ).fetchall()
    return rows == [
        (
            membership.chunk_instance_id,
            membership.artifact.artifact_id,
            membership.artifact.utf8_bytes,
            membership.artifact.characters,
            membership.artifact.lines,
            membership.relative_path,
            membership.source_file_fingerprint,
            membership.start_line,
            membership.end_line,
            membership.language,
            membership.chunker_key,
            membership.embedding_cache_key,
            identify_chunk_membership(generation_id, membership),
        )
        for membership in memberships
    ]


def _persisted_keyword_state_matches(
    connection: sqlite3.Connection,
    commit: VerifiedGenerationKeywordCommit,
    documents: tuple[GenerationKeywordDocument, ...],
) -> bool:
    row = connection.execute(
        """
        SELECT generation_id, manifest_id, manifest_digest, commit_digest, item_count
        FROM generation_keyword_commits
        WHERE generation_id = ?
        """,
        (commit.generation_id,),
    ).fetchone()
    expected_commit = (
        commit.generation_id,
        commit.manifest_id,
        commit.manifest_digest,
        commit.commit_digest,
        commit.item_count,
    )
    if row != expected_commit:
        return False
    rows = connection.execute(
        """
        SELECT chunk_instance_id, artifact_id, relative_path, language, text
        FROM generation_keyword_documents
        WHERE generation_id = ?
        ORDER BY chunk_instance_id
        """,
        (commit.generation_id,),
    ).fetchall()
    return rows == [
        (
            document.chunk_instance_id,
            document.artifact_id,
            document.relative_path,
            document.language,
            document.text,
        )
        for document in documents
    ]


def _published_membership(
    snapshot: PublishedSnapshot,
    chunk_instance_id: str,
    row: tuple[object, ...],
) -> PublishedChunkMembership:
    try:
        return PublishedChunkMembership.model_validate(
            {
                "chunk_instance_id": chunk_instance_id,
                "artifact": {
                    "artifact_id": row[0],
                    "format": "dolphin-chunk-text-v1",
                    "utf8_bytes": row[1],
                    "characters": row[2],
                    "lines": row[3],
                },
                "relative_path": row[4],
                "source_file_fingerprint": row[5],
                "start_line": row[6],
                "end_line": row[7],
                "language": row[8],
                "chunker_key": row[9],
                "embedding_cache_key": row[10],
                "generation_id": snapshot.generation_id,
                "workspace_id": snapshot.workspace_id,
                "publication_id": snapshot.publication_id,
                "manifest_id": snapshot.manifest_id,
                "manifest_digest": snapshot.manifest_digest,
            }
        )
    except ValidationError as exc:
        raise GenerationContentError("Dolphin published chunk membership is corrupt") from exc


def _require_published_membership(
    connection: sqlite3.Connection,
    snapshot: PublishedSnapshot,
    chunk_instance_id: str,
) -> PublishedChunkMembership:
    row = connection.execute(
        """
        SELECT artifact_id, artifact_utf8_bytes, artifact_characters, artifact_lines,
               relative_path, source_file_fingerprint, start_line, end_line, language,
               chunker_key, embedding_cache_key, membership_digest
        FROM generation_chunk_memberships
        WHERE generation_id = ? AND chunk_instance_id = ?
        """,
        (snapshot.generation_id, chunk_instance_id),
    ).fetchone()
    if row is None:
        raise PublishedChunkUnavailable("Dolphin published chunk membership is unavailable")
    membership = _published_membership(snapshot, chunk_instance_id, row)
    if identify_chunk_membership(snapshot.generation_id, membership) != row[11]:
        raise GenerationContentError("Dolphin published chunk membership is corrupt")
    return membership


def _validated_manifest_for_generation(
    connection: sqlite3.Connection,
    generation_id: str,
) -> VerifiedGenerationManifest:
    manifest = _manifest_for_generation(connection, generation_id)
    row = connection.execute(
        """
        SELECT content_revision, validated_content_revision
        FROM generation_content_manifests
        WHERE generation_id = ?
        """,
        (generation_id,),
    ).fetchone()
    if manifest is None or row is None:
        raise GenerationContentError("Dolphin published chunk manifest is corrupt")
    revision = row[0]
    validated_revision = row[1]
    if (
        not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 1
        or not isinstance(validated_revision, int)
        or isinstance(validated_revision, bool)
        or validated_revision < 1
    ):
        raise GenerationContentError("Dolphin published chunk manifest revision is corrupt")
    if revision != validated_revision:
        raise GenerationContentError("Dolphin published chunk manifest binding is corrupt")
    return manifest


_CANONICAL_SNAPSHOT_BY_GENERATION = """
SELECT publication_id, generation_id, workspace_id, operation_id, target_fingerprint,
       pipeline_key, manifest_id, manifest_digest, vector_commit_token, vector_digest,
       vector_row_count, vector_provider, vector_model, vector_dimensions,
       embedding_contract_version, metadata_item_count, keyword_item_count,
       publication_revision, published_at
FROM generations
WHERE generation_id = ? AND state = 'published'
"""


def _snapshot_for_live_reader_lease(
    connection: sqlite3.Connection,
    lease_id: str,
    observed_at: str,
) -> PublishedSnapshot:
    row = connection.execute(
        """
        SELECT workspace_id, generation_id, publication_id
        FROM generation_reader_leases
        WHERE lease_id = ? AND expires_at > ?
        """,
        (lease_id, observed_at),
    ).fetchone()
    if row is None:
        raise PublishedChunkUnavailable("Dolphin generation read lease is unavailable or expired")
    canonical = _canonical_published_snapshot(connection, str(row[1]))
    if canonical is None or canonical.workspace_id != row[0] or canonical.publication_id != row[2]:
        raise PublishedChunkUnavailable("Dolphin generation read lease no longer matches its snapshot")
    return canonical


def _canonical_published_snapshot(
    connection: sqlite3.Connection,
    generation_id: str,
) -> PublishedSnapshot | None:
    row = connection.execute(_CANONICAL_SNAPSHOT_BY_GENERATION, (generation_id,)).fetchone()
    if row is None:
        return None
    try:
        return PublishedSnapshot.model_validate(
            {
                "publication_id": row[0],
                "generation_id": row[1],
                "workspace_id": row[2],
                "operation_id": row[3],
                "target_fingerprint": row[4],
                "pipeline_key": row[5],
                "manifest_id": row[6],
                "manifest_digest": row[7],
                "vector_commit_token": row[8],
                "vector_digest": row[9],
                "vector_row_count": row[10],
                "vector_provider": row[11],
                "vector_model": row[12],
                "vector_dimensions": row[13],
                "embedding_contract_version": row[14],
                "metadata_item_count": row[15],
                "keyword_item_count": row[16],
                "revision": row[17],
                "published_at": _parse_stored_timestamp(row[18]),
            }
        )
    except ValidationError as exc:
        raise GenerationContentError("Dolphin published snapshot metadata is corrupt") from exc


def _parse_stored_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64 or "\x00" in value:
        raise GenerationContentError("Dolphin published snapshot timestamp is corrupt")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise GenerationContentError("Dolphin published snapshot timestamp is corrupt") from None
    if parsed.tzinfo is None:
        raise GenerationContentError("Dolphin published snapshot timestamp is corrupt")
    return parsed.astimezone(UTC)


def _bounded_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 128 or "\x00" in value:
        raise GenerationContentError(f"Dolphin {label} is invalid")


def _begin_write(connection: sqlite3.Connection) -> None:
    deadline = time.monotonic() + _WRITE_LOCK_DEADLINE_SECONDS
    backoff = _WRITE_LOCK_INITIAL_BACKOFF_SECONDS
    while True:
        try:
            connection.execute("BEGIN IMMEDIATE")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GenerationContentError("Dolphin generation content storage is busy or unavailable") from exc
            time.sleep(min(backoff, remaining))
            backoff = min(backoff * 2, _WRITE_LOCK_MAX_BACKOFF_SECONDS)


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise GenerationContentError("Dolphin generation content timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()
