"""Private immutable content-addressed storage for exact decoded chunk text."""

from __future__ import annotations

import errno
import os
import stat
import struct
import uuid
from collections.abc import Sequence

from kb.artifacts import (
    CHUNK_TEXT_FORMAT,
    MAX_CHUNK_TEXT_UTF8_BYTES,
    MAX_GENERATION_ARTIFACTS,
    ArtifactCorrupt,
    ArtifactInputInvalid,
    ArtifactStoreUnavailable,
    ArtifactUnavailable,
    ChunkTextArtifact,
    VerifiedChunkArtifactSet,
    identify_chunk_artifact_set,
    identify_chunk_text,
    require_artifact_id,
)
from kb.runtime.storage import StorageLayout, StorageLayoutError

_FORMAT_DIRECTORY = CHUNK_TEXT_FORMAT
_ENVELOPE_MAGIC = CHUNK_TEXT_FORMAT.encode("ascii") + b"\x00"
_ENVELOPE_HEADER = struct.Struct(f">{len(_ENVELOPE_MAGIC)}sQQQ32s")
_ARTIFACT_FILE_MODE = 0o600
_ARTIFACT_DIRECTORY_MODE = 0o700


class ChunkArtifactStore:
    """Store exact text once and verify every immutable read."""

    def __init__(self, layout: StorageLayout) -> None:
        self._layout = layout

    def put_exact_text(self, text: str) -> ChunkTextArtifact:
        descriptor = identify_chunk_text(text)
        payload = text.encode("utf-8", errors="strict")
        envelope = _encode_envelope(descriptor, payload)
        try:
            with self._layout.open_artifacts_directory() as artifacts_fd:
                format_fd = _open_or_create_private_directory(artifacts_fd, _FORMAT_DIRECTORY)
                try:
                    shard_fd = _open_or_create_private_directory(format_fd, descriptor.artifact_id[:2])
                    try:
                        _install_no_replace(
                            shard_fd,
                            artifact_id=descriptor.artifact_id,
                            envelope=envelope,
                            expected_text=text,
                        )
                    finally:
                        os.close(shard_fd)
                finally:
                    os.close(format_fd)
        except StorageLayoutError:
            raise ArtifactStoreUnavailable("Dolphin chunk artifact storage is unavailable") from None
        return descriptor

    def read_verified(self, artifact_id: str) -> str:
        require_artifact_id(artifact_id)
        try:
            with self._layout.open_artifacts_directory() as artifacts_fd:
                text, _descriptor = _read_verified_from_root(artifacts_fd, artifact_id)
                return text
        except StorageLayoutError:
            raise ArtifactStoreUnavailable("Dolphin chunk artifact storage is unavailable") from None

    def verify_artifact_set(
        self,
        artifact_ids: Sequence[str],
    ) -> VerifiedChunkArtifactSet:
        if isinstance(artifact_ids, str):
            raise ArtifactInputInvalid("Dolphin chunk artifact manifest is invalid")
        unique_ids: set[str] = set()
        for position, artifact_id in enumerate(artifact_ids):
            if position >= MAX_GENERATION_ARTIFACTS:
                raise ArtifactInputInvalid("Dolphin chunk artifact manifest is too large")
            unique_ids.add(require_artifact_id(artifact_id))
        canonical_ids = tuple(sorted(unique_ids))
        total_utf8_bytes = 0
        try:
            with self._layout.open_artifacts_directory() as artifacts_fd:
                for artifact_id in canonical_ids:
                    _text, descriptor = _read_verified_from_root(artifacts_fd, artifact_id)
                    total_utf8_bytes += descriptor.utf8_bytes
        except StorageLayoutError:
            raise ArtifactStoreUnavailable("Dolphin chunk artifact storage is unavailable") from None
        return identify_chunk_artifact_set(
            canonical_ids,
            total_utf8_bytes=total_utf8_bytes,
        )


def _encode_envelope(descriptor: ChunkTextArtifact, payload: bytes) -> bytes:
    return (
        _ENVELOPE_HEADER.pack(
            _ENVELOPE_MAGIC,
            descriptor.utf8_bytes,
            descriptor.characters,
            descriptor.lines,
            bytes.fromhex(descriptor.artifact_id),
        )
        + payload
    )


def _install_no_replace(
    shard_fd: int,
    *,
    artifact_id: str,
    envelope: bytes,
    expected_text: str,
) -> None:
    final_name = artifact_id[2:]
    temporary_name = f".install-{uuid.uuid4().hex}"
    temporary_fd: int | None = None
    try:
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _no_follow_flag() | _close_on_exec_flag(),
            _ARTIFACT_FILE_MODE,
            dir_fd=shard_fd,
        )
        os.fchmod(temporary_fd, _ARTIFACT_FILE_MODE)
        _write_all(temporary_fd, envelope)
        os.fsync(temporary_fd)
        status = os.fstat(temporary_fd)
        if not stat.S_ISREG(status.st_mode) or status.st_size != len(envelope):
            raise ArtifactStoreUnavailable("Dolphin chunk artifact could not be installed safely")
        os.close(temporary_fd)
        temporary_fd = None
        try:
            os.link(
                temporary_name,
                final_name,
                src_dir_fd=shard_fd,
                dst_dir_fd=shard_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            pass
        os.unlink(temporary_name, dir_fd=shard_fd)
        os.fsync(shard_fd)
        winner_text, _descriptor = _read_verified_file(shard_fd, final_name, artifact_id)
        if winner_text != expected_text:
            raise ArtifactCorrupt("Dolphin chunk artifact is corrupt")
    except ArtifactCorrupt:
        raise
    except OSError:
        raise ArtifactStoreUnavailable("Dolphin chunk artifact could not be installed safely") from None
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        try:
            os.unlink(temporary_name, dir_fd=shard_fd)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _read_verified_from_root(artifacts_fd: int, artifact_id: str) -> tuple[str, ChunkTextArtifact]:
    format_fd = _open_existing_private_directory(artifacts_fd, _FORMAT_DIRECTORY)
    if format_fd is None:
        raise ArtifactUnavailable("Dolphin chunk artifact is unavailable")
    try:
        shard_fd = _open_existing_private_directory(format_fd, artifact_id[:2])
        if shard_fd is None:
            raise ArtifactUnavailable("Dolphin chunk artifact is unavailable")
        try:
            return _read_verified_file(shard_fd, artifact_id[2:], artifact_id)
        finally:
            os.close(shard_fd)
    finally:
        os.close(format_fd)


def _read_verified_file(parent_fd: int, name: str, artifact_id: str) -> tuple[str, ChunkTextArtifact]:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | _no_follow_flag() | _close_on_exec_flag() | _non_blocking_flag(),
            dir_fd=parent_fd,
        )
    except FileNotFoundError:
        raise ArtifactUnavailable("Dolphin chunk artifact is unavailable") from None
    except OSError:
        raise ArtifactCorrupt("Dolphin chunk artifact is corrupt") from None
    try:
        before = os.fstat(descriptor)
        _validate_artifact_file(before)
        maximum_envelope_bytes = _ENVELOPE_HEADER.size + MAX_CHUNK_TEXT_UTF8_BYTES
        if before.st_size < _ENVELOPE_HEADER.size or before.st_size > maximum_envelope_bytes:
            raise ArtifactCorrupt("Dolphin chunk artifact is corrupt")
        header = _read_exact(descriptor, _ENVELOPE_HEADER.size)
        magic, utf8_bytes, characters, lines, stored_digest = _ENVELOPE_HEADER.unpack(header)
        if magic != _ENVELOPE_MAGIC or utf8_bytes > MAX_CHUNK_TEXT_UTF8_BYTES:
            raise ArtifactCorrupt("Dolphin chunk artifact is corrupt")
        if before.st_size != _ENVELOPE_HEADER.size + utf8_bytes:
            raise ArtifactCorrupt("Dolphin chunk artifact is corrupt")
        payload = _read_exact(descriptor, utf8_bytes)
        if os.read(descriptor, 1):
            raise ArtifactCorrupt("Dolphin chunk artifact is corrupt")
        after = os.fstat(descriptor)
        if _stable_file_identity(before) != _stable_file_identity(after):
            raise ArtifactCorrupt("Dolphin chunk artifact changed during verification")
    except ArtifactCorrupt:
        raise
    except (OSError, struct.error):
        raise ArtifactCorrupt("Dolphin chunk artifact is corrupt") from None
    finally:
        os.close(descriptor)
    if stored_digest.hex() != artifact_id:
        raise ArtifactCorrupt("Dolphin chunk artifact is corrupt")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ArtifactCorrupt("Dolphin chunk artifact is corrupt") from None
    identified = identify_chunk_text(text)
    if (
        identified.artifact_id != artifact_id
        or identified.utf8_bytes != utf8_bytes
        or identified.characters != characters
        or identified.lines != lines
    ):
        raise ArtifactCorrupt("Dolphin chunk artifact is corrupt")
    return text, identified


def _validate_artifact_file(status: os.stat_result) -> None:
    if (
        not stat.S_ISREG(status.st_mode)
        or status.st_uid != os.getuid()
        or stat.S_IMODE(status.st_mode) != _ARTIFACT_FILE_MODE
        or status.st_nlink != 1
    ):
        raise ArtifactCorrupt("Dolphin chunk artifact is corrupt")


def _open_or_create_private_directory(parent_fd: int, name: str) -> int:
    created = False
    try:
        os.mkdir(name, _ARTIFACT_DIRECTORY_MODE, dir_fd=parent_fd)
        created = True
    except FileExistsError:
        pass
    except OSError:
        raise ArtifactStoreUnavailable("Dolphin chunk artifact storage is unavailable") from None
    descriptor = _open_existing_private_directory(parent_fd, name)
    if descriptor is None:
        raise ArtifactStoreUnavailable("Dolphin chunk artifact storage is unavailable")
    if created:
        try:
            os.fsync(parent_fd)
        except OSError:
            os.close(descriptor)
            raise ArtifactStoreUnavailable("Dolphin chunk artifact storage is unavailable") from None
    return descriptor


def _open_existing_private_directory(parent_fd: int, name: str) -> int | None:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | _no_follow_flag() | _close_on_exec_flag(),
            dir_fd=parent_fd,
        )
    except FileNotFoundError:
        return None
    except OSError:
        raise ArtifactCorrupt("Dolphin chunk artifact storage is corrupt") from None
    try:
        status = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(status.st_mode)
            or status.st_uid != os.getuid()
            or stat.S_IMODE(status.st_mode) != _ARTIFACT_DIRECTORY_MODE
        ):
            raise ArtifactCorrupt("Dolphin chunk artifact storage is corrupt")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _read_exact(descriptor: int, byte_count: int) -> bytes:
    remaining = byte_count
    chunks: list[bytes] = []
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1024 * 1024))
        if not chunk:
            raise ArtifactCorrupt("Dolphin chunk artifact is corrupt")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "artifact write did not make progress")
        offset += written


def _stable_file_identity(status: os.stat_result) -> tuple[int, int, int, int, int]:
    return (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns, status.st_ctime_ns)


def _no_follow_flag() -> int:
    try:
        return os.O_NOFOLLOW
    except AttributeError:  # pragma: no cover - Dolphin production is macOS-only.
        raise ArtifactStoreUnavailable("Dolphin requires no-follow artifact storage") from None


def _close_on_exec_flag() -> int:
    return getattr(os, "O_CLOEXEC", 0)


def _non_blocking_flag() -> int:
    return getattr(os, "O_NONBLOCK", 0)
