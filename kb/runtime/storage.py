"""Private macOS Application Support layout for all Dolphin runtime state."""

from __future__ import annotations

import fcntl
import os
import secrets
import stat
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class StorageLayoutError(RuntimeError):
    """The runtime state root cannot be used safely."""


_QUERY_CACHE_SECRET_NAME = "query-cache.key"
_QUERY_CACHE_SECRET_LOCK_NAME = "query-cache-key.lock"
_QUERY_CACHE_SECRET_TEMPORARY_PREFIX = ".query-cache-key."
_QUERY_CACHE_SECRET_BYTES = 32
_PRIVATE_LOCK_TIMEOUT_SECONDS = 1.0
_PRIVATE_LOCK_RETRY_SECONDS = 0.01


def sync_directory(descriptor: int) -> None:
    """Durably sync a directory or fail closed when the filesystem cannot."""
    os.fsync(descriptor)


@dataclass(frozen=True, slots=True)
class StorageLayout:
    """The only allowed production root for mutable Dolphin runtime state."""

    root: Path
    config_file: Path
    metadata_db: Path
    vectors: Path
    artifacts: Path
    locks: Path
    logs: Path
    temporary: Path

    @property
    def query_cache_secret_file(self) -> Path:
        return self.root / _QUERY_CACHE_SECRET_NAME

    def ensure_private_directories(self) -> None:
        """Create state directories and validate existing sensitive runtime files."""
        with _open_runtime_root(self.root) as root_fd:
            _ensure_runtime_members(self, root_fd)

    def ensure_private_metadata_database(self) -> None:
        """Create the metadata database placeholder privately, or validate it before use."""
        with _open_runtime_root(self.root) as root_fd:
            _ensure_runtime_members(self, root_fd)
            _create_or_validate_private_file(root_fd, self.metadata_db.name, label="metadata database")

    def metadata_database_exists(self) -> bool:
        """Validate existing metadata storage without creating or repairing any state."""
        with _open_existing_runtime_root(self.root) as root_fd:
            if root_fd is None:
                return False
            return _private_file_exists(root_fd, self.metadata_db.name, label="metadata database")

    def load_or_create_query_cache_secret(self, *, allow_create: bool) -> bytes:
        """Read one private per-install cache key through held no-follow descriptors."""
        with _open_runtime_root(self.root) as root_fd:
            _ensure_runtime_members(self, root_fd)
            locks_fd = _open_or_create_directory(root_fd, self.locks.name, private=True)
            try:
                lock_fd = _open_or_create_private_lock(locks_fd, _QUERY_CACHE_SECRET_LOCK_NAME)
                try:
                    _acquire_private_lock(lock_fd)
                    return _read_or_create_query_cache_secret(root_fd, allow_create=allow_create)
                finally:
                    _release_private_lock_preserving_primary_error(lock_fd)
                    os.close(lock_fd)
            finally:
                os.close(locks_fd)

    @contextmanager
    def open_artifacts_directory(self) -> Iterator[int]:
        """Hold a private no-follow descriptor chain through the artifact root."""
        if self.artifacts != self.root / "artifacts":
            raise StorageLayoutError("Dolphin artifact storage has an invalid layout")
        with _open_runtime_root(self.root) as root_fd:
            artifacts_fd = _open_or_create_directory(root_fd, self.artifacts.name, private=True)
            try:
                yield artifacts_fd
            finally:
                os.close(artifacts_fd)

    @contextmanager
    def open_locks_directory(self) -> Iterator[int]:
        """Hold a private no-follow descriptor chain through the lock root."""
        if self.locks != self.root / "locks":
            raise StorageLayoutError("Dolphin lock storage has an invalid layout")
        with _open_runtime_root(self.root) as root_fd:
            locks_fd = _open_or_create_directory(root_fd, self.locks.name, private=True)
            try:
                yield locks_fd
            finally:
                os.close(locks_fd)


def macos_storage_layout(*, home: Path | None = None) -> StorageLayout:
    """Resolve Dolphin's fixed macOS state layout without consulting legacy paths."""
    resolved_home = (home or Path.home()).expanduser().resolve()
    root = resolved_home / "Library" / "Application Support" / "Dolphin"
    return StorageLayout(
        root=root,
        config_file=root / "config.toml",
        metadata_db=root / "metadata.sqlite3",
        vectors=root / "vectors",
        artifacts=root / "artifacts",
        locks=root / "locks",
        logs=root / "logs",
        temporary=root / "tmp",
    )


@contextmanager
def _open_runtime_root(root: Path) -> Iterator[int]:
    """Hold no-follow directory descriptors from the user home through the runtime root."""
    if root.name != "Dolphin" or root.parent.name != "Application Support" or root.parent.parent.name != "Library":
        raise StorageLayoutError("Dolphin runtime root has an invalid layout")

    home = root.parent.parent.parent
    descriptors: list[int] = []
    try:
        home_fd = _open_directory(home, label="home directory", private=False)
        descriptors.append(home_fd)
        library_fd = _open_or_create_directory(home_fd, "Library", private=False)
        descriptors.append(library_fd)
        support_fd = _open_or_create_directory(library_fd, "Application Support", private=False)
        descriptors.append(support_fd)
        root_fd = _open_or_create_directory(support_fd, "Dolphin", private=True)
        descriptors.append(root_fd)
        yield root_fd
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@contextmanager
def _open_existing_runtime_root(root: Path) -> Iterator[int | None]:
    """Hold a validation-only descriptor chain, yielding none when runtime state is absent."""
    if root.name != "Dolphin" or root.parent.name != "Application Support" or root.parent.parent.name != "Library":
        raise StorageLayoutError("Dolphin runtime root has an invalid layout")

    home = root.parent.parent.parent
    descriptors: list[int] = []
    try:
        home_fd = _open_existing_directory(home, label="home directory", private=False)
        if home_fd is None:
            yield None
            return
        descriptors.append(home_fd)
        parent_fd = home_fd
        for name, label, private in (
            ("Library", "Library directory", False),
            ("Application Support", "Application Support directory", False),
            ("Dolphin", "runtime root", True),
        ):
            descriptor = _open_existing_directory(name, parent_fd=parent_fd, label=label, private=private)
            if descriptor is None:
                yield None
                return
            descriptors.append(descriptor)
            parent_fd = descriptor
        yield descriptors[-1]
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _ensure_runtime_members(layout: StorageLayout, root_fd: int) -> None:
    for path in (layout.vectors, layout.artifacts, layout.locks, layout.logs, layout.temporary):
        descriptor = _open_or_create_directory(root_fd, path.name, private=True)
        os.close(descriptor)
    _validate_optional_private_file(root_fd, layout.config_file.name, label="configuration")
    _validate_optional_private_file(root_fd, layout.metadata_db.name, label="metadata database")
    _validate_optional_private_file(root_fd, _QUERY_CACHE_SECRET_NAME, label="query cache secret")


def _open_or_create_directory(parent_fd: int, name: str, *, private: bool) -> int:
    created = False
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        created = True
    except FileExistsError:
        pass
    except OSError as exc:
        raise StorageLayoutError(f"Dolphin runtime directory is unavailable: {name}") from exc
    descriptor = _open_directory(name, parent_fd=parent_fd, label=f"runtime directory {name}", private=private)
    if created:
        try:
            sync_directory(parent_fd)
        except OSError as exc:
            os.close(descriptor)
            raise StorageLayoutError(f"Dolphin runtime directory is unavailable: {name}") from exc
    return descriptor


def _open_directory(path: Path | str, *, label: str, private: bool, parent_fd: int | None = None) -> int:
    try:
        descriptor = os.open(path, _directory_open_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise StorageLayoutError(f"Dolphin {label} is unavailable or is a symbolic link") from exc
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISDIR(status.st_mode):
            raise StorageLayoutError(f"Dolphin {label} is not a directory")
        _validate_directory_descriptor(descriptor, status, label=label, private=private)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _open_existing_directory(
    path: Path | str,
    *,
    label: str,
    private: bool,
    parent_fd: int | None = None,
) -> int | None:
    try:
        descriptor = os.open(path, _directory_open_flags(), dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StorageLayoutError(f"Dolphin {label} is unavailable or is a symbolic link") from exc
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISDIR(status.st_mode):
            raise StorageLayoutError(f"Dolphin {label} is not a directory")
        _validate_owned_descriptor(status, label=label)
        if private and stat.S_IMODE(status.st_mode) != 0o700:
            raise StorageLayoutError(f"Dolphin {label} has unsafe permissions")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _validate_optional_private_file(parent_fd: int, name: str, *, label: str) -> None:
    try:
        descriptor = os.open(name, _file_open_flags(), dir_fd=parent_fd)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise StorageLayoutError(f"Dolphin {label} cannot be inspected safely") from exc
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            raise StorageLayoutError(f"Dolphin {label} must be a regular file")
        _validate_private_descriptor(descriptor, status, label=label, required_mode=0o600)
    finally:
        os.close(descriptor)


def _private_file_exists(parent_fd: int, name: str, *, label: str) -> bool:
    try:
        descriptor = os.open(name, _file_open_flags(), dir_fd=parent_fd)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StorageLayoutError(f"Dolphin {label} cannot be inspected safely") from exc
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            raise StorageLayoutError(f"Dolphin {label} must be a regular file")
        _validate_owned_descriptor(status, label=label)
        if stat.S_IMODE(status.st_mode) != 0o600:
            raise StorageLayoutError(f"Dolphin {label} has unsafe permissions")
    finally:
        os.close(descriptor)
    return True


def _create_or_validate_private_file(parent_fd: int, name: str, *, label: str) -> None:
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _no_follow_flag(),
            0o600,
            dir_fd=parent_fd,
        )
    except FileExistsError:
        _validate_optional_private_file(parent_fd, name, label=label)
        return
    except OSError as exc:
        raise StorageLayoutError(f"Dolphin {label} cannot be created safely") from exc
    try:
        _validate_private_descriptor(descriptor, os.fstat(descriptor), label=label, required_mode=0o600)
    finally:
        os.close(descriptor)


def _open_or_create_private_lock(parent_fd: int, name: str) -> int:
    created = False
    try:
        descriptor = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | _no_follow_flag(),
            0o600,
            dir_fd=parent_fd,
        )
        created = True
    except FileExistsError:
        try:
            descriptor = os.open(name, os.O_RDWR | _no_follow_flag(), dir_fd=parent_fd)
        except OSError as exc:
            raise StorageLayoutError("Dolphin query cache secret lock is unavailable") from exc
    except OSError as exc:
        raise StorageLayoutError("Dolphin query cache secret lock is unavailable") from exc
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            raise StorageLayoutError("Dolphin query cache secret lock is invalid")
        _validate_private_descriptor(descriptor, status, label="query cache secret lock", required_mode=0o600)
        if created:
            sync_directory(parent_fd)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _acquire_private_lock(descriptor: int) -> None:
    deadline = time.monotonic() + _PRIVATE_LOCK_TIMEOUT_SECONDS
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise StorageLayoutError("Dolphin query cache secret lock is unavailable") from None
            time.sleep(min(_PRIVATE_LOCK_RETRY_SECONDS, remaining))
        except OSError as exc:
            raise StorageLayoutError("Dolphin query cache secret lock is unavailable") from exc


def _release_private_lock_preserving_primary_error(descriptor: int) -> None:
    primary_error_active = sys.exc_info()[0] is not None
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError as exc:
        if not primary_error_active:
            raise StorageLayoutError("Dolphin query cache secret lock is unavailable") from exc


def _read_or_create_query_cache_secret(root_fd: int, *, allow_create: bool) -> bytes:
    existing = _read_query_cache_secret(root_fd)
    if existing is not None:
        return existing
    if not allow_create:
        raise StorageLayoutError("Dolphin query cache secret is missing")

    secret = secrets.token_bytes(_QUERY_CACHE_SECRET_BYTES)
    temporary_name = _QUERY_CACHE_SECRET_TEMPORARY_PREFIX + secrets.token_hex(16)
    temporary_fd: int | None = None
    try:
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _no_follow_flag(),
            0o600,
            dir_fd=root_fd,
        )
        _write_all(temporary_fd, secret)
        os.fsync(temporary_fd)
        status = os.fstat(temporary_fd)
        if not stat.S_ISREG(status.st_mode) or status.st_size != _QUERY_CACHE_SECRET_BYTES:
            raise StorageLayoutError("Dolphin query cache secret could not be created safely")
        _validate_private_descriptor(temporary_fd, status, label="query cache secret", required_mode=0o600)
        try:
            os.link(
                temporary_name,
                _QUERY_CACHE_SECRET_NAME,
                src_dir_fd=root_fd,
                dst_dir_fd=root_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            winner = _read_query_cache_secret(root_fd)
            if winner is None:
                raise StorageLayoutError("Dolphin query cache secret is unavailable") from None
            return winner
        os.unlink(temporary_name, dir_fd=root_fd)
        sync_directory(root_fd)
        return secret
    except StorageLayoutError:
        raise
    except OSError as exc:
        raise StorageLayoutError("Dolphin query cache secret could not be created safely") from exc
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        try:
            os.unlink(temporary_name, dir_fd=root_fd)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _read_query_cache_secret(root_fd: int) -> bytes | None:
    try:
        descriptor = os.open(_QUERY_CACHE_SECRET_NAME, _file_open_flags(), dir_fd=root_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StorageLayoutError("Dolphin query cache secret is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size != _QUERY_CACHE_SECRET_BYTES:
            raise StorageLayoutError("Dolphin query cache secret is invalid")
        _validate_private_descriptor(descriptor, before, label="query cache secret", required_mode=0o600)
        secret = os.read(descriptor, _QUERY_CACHE_SECRET_BYTES + 1)
        after = os.fstat(descriptor)
        if len(secret) != _QUERY_CACHE_SECRET_BYTES or _stable_file_identity(before) != _stable_file_identity(after):
            raise StorageLayoutError("Dolphin query cache secret is invalid")
        return secret
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, payload: bytes) -> None:
    written = 0
    while written < len(payload):
        count = os.write(descriptor, payload[written:])
        if count <= 0:
            raise StorageLayoutError("Dolphin query cache secret could not be created safely")
        written += count


def _stable_file_identity(status: os.stat_result) -> tuple[int, int, int, int, int]:
    return status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns, status.st_ctime_ns


def _validate_directory_descriptor(descriptor: int, status: os.stat_result, *, label: str, private: bool) -> None:
    _validate_owned_descriptor(status, label=label)
    if private:
        _validate_private_descriptor(descriptor, status, label=label, required_mode=0o700)


def _validate_private_descriptor(descriptor: int, status: os.stat_result, *, label: str, required_mode: int) -> None:
    _validate_owned_descriptor(status, label=label)
    if stat.S_IMODE(status.st_mode) & 0o077:
        raise StorageLayoutError(f"Dolphin {label} has unsafe permissions")
    if stat.S_IMODE(status.st_mode) != required_mode:
        try:
            os.fchmod(descriptor, required_mode)
        except OSError as exc:
            raise StorageLayoutError(f"Dolphin {label} permissions cannot be repaired") from exc
        if stat.S_IMODE(os.fstat(descriptor).st_mode) != required_mode:
            raise StorageLayoutError(f"Dolphin {label} permissions remain unsafe")


def _validate_owned_descriptor(status: os.stat_result, *, label: str) -> None:
    if status.st_uid != os.getuid():
        raise StorageLayoutError(f"Dolphin {label} is not owned by the current user")


def _directory_open_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | _no_follow_flag()


def _file_open_flags() -> int:
    return os.O_RDONLY | _no_follow_flag()


def _no_follow_flag() -> int:
    try:
        return os.O_NOFOLLOW
    except AttributeError as exc:  # pragma: no cover - Dolphin production is macOS-only.
        raise StorageLayoutError("Dolphin requires no-follow filesystem support") from exc
