from __future__ import annotations

import os
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pathspec import PathSpec

from kb.services.repository_boundaries import (
    ParentScanPlan,
    RepositoryBoundaryError,
    path_is_within_boundary,
    plan_parent_scan,
    validate_parent_scan,
)
from kb.services.worktree import WorktreeDiscoveryError, discover_git_worktree_sync, run_git_read_only

from .lang import classify_language


@dataclass(slots=True)
class FileCandidate:
    repo_root: Path
    rel_path: str  # POSIX
    ext: str | None
    language: str
    size_bytes: int
    is_binary: bool


class ScannerError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> bytes:
    try:
        result = run_git_read_only(root, *args)
    except WorktreeDiscoveryError as exc:
        raise ScannerError("Git metadata is unavailable") from exc
    if result.returncode != 0:
        raise ScannerError("Git metadata command failed")
    return result.stdout.encode("utf-8", errors="surrogateescape")


def _list_tracked(root: Path) -> list[str]:
    """List files respecting .gitignore patterns.

    Uses git ls-files with:
    - --cached: Include tracked files
    - --others: Include untracked files
    - --exclude-standard: Respect .gitignore, .git/info/exclude, and global excludes
    - -z: NUL-separated output for safe parsing

    This ensures we respect .gitignore even for files that were previously committed
    but are now in .gitignore.
    """
    out = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    items = [p for p in out.split(b"\x00") if p]
    return [PurePosixPath(p.decode("utf-8", errors="surrogateescape")).as_posix() for p in items]


def _repository_boundary_plan(root: Path) -> ParentScanPlan:
    """Build the immutable boundary plan shared by one parent scan."""
    try:
        worktree = discover_git_worktree_sync(root)
        if worktree.root != root:
            raise ScannerError(f"Not a Git worktree root: {root}")
        return plan_parent_scan(worktree)
    except WorktreeDiscoveryError as exc:
        raise ScannerError(f"Not a Git worktree: {root}") from exc
    except RepositoryBoundaryError as exc:
        raise ScannerError(f"Repository boundary discovery failed: {exc.code}") from exc


def _validate_repository_boundary_plan(plan: ParentScanPlan) -> None:
    try:
        validate_parent_scan(plan)
    except (RepositoryBoundaryError, WorktreeDiscoveryError) as exc:
        raise ScannerError("Repository boundaries changed during scanning") from exc


def _build_pathspec(ignores: Iterable[str]) -> PathSpec:
    patterns = list(ignores or [])
    return PathSpec.from_lines("gitignore", patterns)


def _chunk_is_binary(chunk: bytes) -> bool:
    try:
        # Fast NUL-byte heuristic
        if b"\x00" in chunk:
            return True
        # UTF-8 decode check
        chunk.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def _directory_snapshot(directory_fd: int) -> tuple[int, int, int, int]:
    status = os.fstat(directory_fd)
    return status.st_dev, status.st_ino, status.st_ctime_ns, status.st_mtime_ns


def _directory_has_git_marker(directory_fd: int) -> bool:
    try:
        os.stat(".git", dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _inspect_candidate_file(root: Path, rel_path: str, sniff_bytes: int = 65_536) -> tuple[int, bool] | None:
    """Inspect one repository-relative file without following any symlink component."""
    parts = PurePosixPath(rel_path).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None

    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    directory_fds: list[int] = []
    nested_directory_snapshots: list[tuple[int, tuple[int, int, int, int]]] = []
    file_fd: int | None = None
    try:
        directory_fds.append(os.open(root, directory_flags))
        for part in parts[:-1]:
            directory_fd = os.open(part, directory_flags, dir_fd=directory_fds[-1])
            directory_fds.append(directory_fd)
            if _directory_has_git_marker(directory_fd):
                return None
            nested_directory_snapshots.append((directory_fd, _directory_snapshot(directory_fd)))

        file_fd = os.open(parts[-1], file_flags, dir_fd=directory_fds[-1])
        file_status = os.fstat(file_fd)
        if not stat.S_ISREG(file_status.st_mode):
            return None
        chunk = os.read(file_fd, sniff_bytes)
        if any(
            _directory_has_git_marker(directory_fd) or _directory_snapshot(directory_fd) != snapshot
            for directory_fd, snapshot in nested_directory_snapshots
        ):
            return None
        return file_status.st_size, _chunk_is_binary(chunk)
    except OSError:
        return None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for directory_fd in reversed(directory_fds):
            os.close(directory_fd)


def scan_repo(root: Path, ignores: Iterable[str]) -> list[FileCandidate]:
    """Scan a git repo for candidate files with language tagging.

    - Uses `git ls-files` to respect .gitignore implicitly.
    - Applies additional ignore patterns via pathspec.
    - Skips submodules, symlinks, and binary files.
    """
    root = root.expanduser().resolve()
    if not (root / ".git").exists():
        raise ScannerError(f"Not a git repository: {root}")

    boundary_plan = _repository_boundary_plan(root)
    rel_paths = _list_tracked(root)
    excluded_subtrees = boundary_plan.excluded_subtrees
    spec = _build_pathspec(ignores)

    candidates: list[FileCandidate] = []
    for rel in rel_paths:
        # Repository boundaries are non-overridable, including malformed ones.
        if path_is_within_boundary(rel, excluded_subtrees):
            continue
        # Skip by pathspec
        if spec.match_file(rel):
            continue
        inspection = _inspect_candidate_file(root, rel)
        if inspection is None:
            continue
        size, is_bin = inspection
        if is_bin:
            continue
        # Language
        _, language = classify_language(Path(rel))
        ext = Path(rel).suffix.lower() or None
        candidates.append(
            FileCandidate(
                repo_root=root,
                rel_path=rel,
                ext=ext,
                language=language,
                size_bytes=size,
                is_binary=is_bin,
            )
        )

    _validate_repository_boundary_plan(boundary_plan)
    return candidates
