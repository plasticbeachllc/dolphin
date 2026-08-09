"""Private macOS Application Support layout for all Dolphin runtime state."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path


class StorageLayoutError(RuntimeError):
    """The runtime state root cannot be used safely."""


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
        _ensure_private_directory(self.root)
        for path in (self.vectors, self.artifacts, self.locks, self.logs, self.temporary):
            _ensure_private_directory(path)
        _validate_optional_private_file(self.config_file, label="configuration")
        _validate_optional_private_file(self.metadata_db, label="metadata database")

    def ensure_private_metadata_database(self) -> None:
        """Create the metadata database placeholder privately, or validate it before use."""
        self.ensure_private_directories()
        _create_or_validate_private_file(self.metadata_db, label="metadata database")


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


def _ensure_private_directory(path: Path) -> None:
    """Create or validate one owned, non-link, private directory."""
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        status = path.lstat()
    except OSError as exc:
        raise StorageLayoutError(f"Dolphin runtime directory is unavailable: {path}") from exc

    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise StorageLayoutError(f"Dolphin runtime path is not a directory: {path}")
    _validate_ownership_and_mode(path, status, required_mode=0o700)


def _validate_optional_private_file(path: Path, *, label: str) -> None:
    """Validate an existing private file without creating it."""
    try:
        status = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise StorageLayoutError(f"Dolphin {label} cannot be inspected: {path}") from exc

    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
        raise StorageLayoutError(f"Dolphin {label} must be a regular file")
    _validate_ownership_and_mode(path, status, required_mode=0o600)


def _create_or_validate_private_file(path: Path, *, label: str) -> None:
    """Create exactly one regular private file without following a pre-existing link."""
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        _validate_optional_private_file(path, label=label)
        return
    except OSError as exc:
        raise StorageLayoutError(f"Dolphin {label} cannot be created: {path}") from exc
    else:
        os.close(descriptor)
    _validate_optional_private_file(path, label=label)


def _validate_ownership_and_mode(path: Path, status: os.stat_result, *, required_mode: int) -> None:
    if status.st_uid != os.getuid():
        raise StorageLayoutError(f"Dolphin runtime path is not owned by the current user: {path}")
    if stat.S_IMODE(status.st_mode) & 0o077:
        raise StorageLayoutError(f"Dolphin runtime path has unsafe permissions: {path}")
    if stat.S_IMODE(status.st_mode) != required_mode:
        try:
            path.chmod(required_mode, follow_symlinks=False)
        except OSError as exc:
            raise StorageLayoutError(f"Dolphin runtime path permissions cannot be repaired: {path}") from exc
        repaired = path.lstat()
        if stat.S_ISLNK(repaired.st_mode) or stat.S_IMODE(repaired.st_mode) != required_mode:
            raise StorageLayoutError(f"Dolphin runtime path permissions remain unsafe: {path}")
