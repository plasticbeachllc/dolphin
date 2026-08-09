"""Private macOS Application Support layout for all Dolphin runtime state."""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class StorageLayoutError(RuntimeError):
    """The runtime state root cannot be used safely."""


_UNSUPPORTED_DIRECTORY_SYNC_ERRNOS = frozenset(
    {
        errno.EINVAL,
        errno.ENOTSUP,
        errno.EOPNOTSUPP,
    }
)


def sync_directory(descriptor: int) -> bool:
    """Sync a directory when its macOS filesystem supports that operation."""
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_DIRECTORY_SYNC_ERRNOS:
            return False
        raise
    return True


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
