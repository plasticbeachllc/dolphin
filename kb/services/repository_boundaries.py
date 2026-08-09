"""Bounded, non-mutating repository-boundary discovery for one Git worktree."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from kb.services.worktree import (
    GitWorktree,
    WorktreeDiscoveryError,
    discover_git_worktree_sync,
    run_git_read_only,
    validate_git_worktree_snapshot,
)

_GITLINK_MODE = "160000"
_MAX_INDEX_OUTPUT_CHARACTERS = 256 * 1024 * 1024
_MAX_DISCOVERED_BOUNDARIES = 100_000
_MAX_WALKED_ENTRIES = 1_000_000
_MAX_REPOSITORY_RELATIVE_PATH = 4_096
_MAX_GIT_FILE_BYTES = 16 * 1024


class RepositoryBoundaryError(RuntimeError):
    """A parent repository cannot be scanned without risking a boundary crossing."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RepositoryBoundaryKind(StrEnum):
    SUBMODULE = "submodule"
    NESTED_GIT = "nested_git"


class RepositoryBoundaryState(StrEnum):
    ENROLLABLE = "enrollable"
    UNINITIALIZED = "uninitialized"
    MISSING = "missing"
    CONFLICTED = "conflicted"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class RepositoryBoundary:
    kind: RepositoryBoundaryKind
    relative_path: str
    state: RepositoryBoundaryState
    root: Path | None = None
    expected_commit: str | None = None
    observed_commit: str | None = None
    dirty: bool | None = None
    common_git_dir_identity: str | None = None
    worktree_git_dir_identity: str | None = None


@dataclass(frozen=True, slots=True)
class ParentScanPlan:
    worktree: GitWorktree
    excluded_subtrees: frozenset[str]
    repository_boundaries: tuple[RepositoryBoundary, ...]


@dataclass(frozen=True, slots=True)
class _GitlinkEntry:
    relative_path: str
    object_id: str | None
    conflicted: bool


def plan_parent_scan(worktree: GitWorktree) -> ParentScanPlan:
    """Discover every immediate child repository boundary without mutation or descent."""
    validate_git_worktree_snapshot(worktree)
    index_before = _index_signature(worktree)
    boundaries: dict[str, RepositoryBoundary] = {}
    for gitlink in _read_gitlinks(worktree):
        candidate = _contained_candidate(worktree.root, gitlink.relative_path)
        boundaries[gitlink.relative_path] = _inspect_submodule(worktree, gitlink, candidate)
        _require_boundary_capacity(boundaries)

    for relative_path, marker in _discover_nested_markers(
        worktree.root,
        excluded_subtrees=frozenset(boundaries),
    ):
        boundaries.setdefault(relative_path, _inspect_nested_marker(relative_path, marker))
        _require_boundary_capacity(boundaries)

    ordered = tuple(boundaries[path] for path in sorted(boundaries))
    if _index_signature(worktree) != index_before:
        raise RepositoryBoundaryError("BOUNDARY_SNAPSHOT_CHANGED")
    validate_git_worktree_snapshot(worktree)
    return ParentScanPlan(
        worktree=worktree,
        excluded_subtrees=frozenset(boundaries),
        repository_boundaries=ordered,
    )


def validate_parent_scan(plan: ParentScanPlan) -> None:
    """Fail if repository boundaries changed while a caller used the plan."""
    if plan_parent_scan(plan.worktree) != plan:
        raise RepositoryBoundaryError("BOUNDARY_SNAPSHOT_CHANGED")


def path_is_within_boundary(relative_path: str, excluded_subtrees: frozenset[str] | set[str]) -> bool:
    """Return whether a POSIX repository path is at or beneath one excluded subtree."""
    return any(
        relative_path == boundary.rstrip("/") or relative_path.startswith(f"{boundary.rstrip('/')}/")
        for boundary in excluded_subtrees
    )


def _read_gitlinks(worktree: GitWorktree) -> tuple[_GitlinkEntry, ...]:
    try:
        result = run_git_read_only(worktree.root, "ls-files", "--stage", "-z", "--")
    except WorktreeDiscoveryError as exc:
        raise RepositoryBoundaryError("BOUNDARY_GIT_UNAVAILABLE") from exc
    if result.returncode != 0:
        raise RepositoryBoundaryError("BOUNDARY_GIT_FAILED")
    if len(result.stdout) > _MAX_INDEX_OUTPUT_CHARACTERS:
        raise RepositoryBoundaryError("BOUNDARY_INDEX_TOO_LARGE")

    entries: dict[str, list[tuple[str, str]]] = {}
    for record in result.stdout.split("\0"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition("\t")
        fields = metadata.split(" ")
        if not separator or len(fields) != 3:
            raise RepositoryBoundaryError("BOUNDARY_INDEX_INVALID")
        mode, object_id, stage = fields
        if mode != _GITLINK_MODE:
            continue
        if stage not in {"0", "1", "2", "3"} or not _is_git_object_id(object_id):
            raise RepositoryBoundaryError("BOUNDARY_INDEX_INVALID")
        relative_path = _validate_relative_path(raw_path)
        entries.setdefault(relative_path, []).append((object_id, stage))
        if len(entries) > _MAX_DISCOVERED_BOUNDARIES:
            raise RepositoryBoundaryError("BOUNDARY_LIMIT_EXCEEDED")

    gitlinks: list[_GitlinkEntry] = []
    for relative_path, staged_entries in entries.items():
        stage_zero = [object_id for object_id, stage in staged_entries if stage == "0"]
        conflicted = len(staged_entries) != 1 or len(stage_zero) != 1
        gitlinks.append(
            _GitlinkEntry(
                relative_path=relative_path,
                object_id=stage_zero[0] if not conflicted else None,
                conflicted=conflicted,
            )
        )
    return tuple(sorted(gitlinks, key=lambda entry: entry.relative_path))


def _inspect_submodule(parent: GitWorktree, gitlink: _GitlinkEntry, candidate: Path) -> RepositoryBoundary:
    if gitlink.conflicted:
        return RepositoryBoundary(
            kind=RepositoryBoundaryKind.SUBMODULE,
            relative_path=gitlink.relative_path,
            state=RepositoryBoundaryState.CONFLICTED,
        )
    candidate_status = _lstat_or_none(candidate)
    if candidate_status is None:
        return RepositoryBoundary(
            kind=RepositoryBoundaryKind.SUBMODULE,
            relative_path=gitlink.relative_path,
            state=RepositoryBoundaryState.MISSING,
            expected_commit=gitlink.object_id,
        )
    if not stat.S_ISDIR(candidate_status.st_mode):
        return RepositoryBoundary(
            kind=RepositoryBoundaryKind.SUBMODULE,
            relative_path=gitlink.relative_path,
            state=RepositoryBoundaryState.INVALID,
            expected_commit=gitlink.object_id,
        )

    marker_status = _lstat_or_none(candidate / ".git")
    if marker_status is None:
        return RepositoryBoundary(
            kind=RepositoryBoundaryKind.SUBMODULE,
            relative_path=gitlink.relative_path,
            state=RepositoryBoundaryState.UNINITIALIZED,
            expected_commit=gitlink.object_id,
        )
    child = _discover_child(
        candidate,
        marker_status,
        allowed_git_file_root=parent.common_git_dir / "modules",
    )
    if child is None:
        return RepositoryBoundary(
            kind=RepositoryBoundaryKind.SUBMODULE,
            relative_path=gitlink.relative_path,
            state=RepositoryBoundaryState.INVALID,
            expected_commit=gitlink.object_id,
        )
    return RepositoryBoundary(
        kind=RepositoryBoundaryKind.SUBMODULE,
        relative_path=gitlink.relative_path,
        root=child.root,
        state=RepositoryBoundaryState.ENROLLABLE,
        expected_commit=gitlink.object_id,
        observed_commit=child.head_commit,
        common_git_dir_identity=child.common_git_dir_identity,
        worktree_git_dir_identity=child.worktree_git_dir_identity,
    )


def _discover_nested_markers(
    root: Path,
    *,
    excluded_subtrees: frozenset[str],
) -> tuple[tuple[str, Path], ...]:
    markers: list[tuple[str, Path]] = []
    pending: list[tuple[Path, tuple[str, ...]]] = [(root, ())]
    walked_entries = 0
    while pending:
        directory, relative_parts = pending.pop()
        try:
            with os.scandir(directory) as entries:
                children: list[os.DirEntry[str]] = []
                for entry in entries:
                    walked_entries += 1
                    if walked_entries > _MAX_WALKED_ENTRIES:
                        raise RepositoryBoundaryError("BOUNDARY_WALK_LIMIT_EXCEEDED")
                    children.append(entry)
        except OSError as exc:
            raise RepositoryBoundaryError("BOUNDARY_WALK_UNAVAILABLE") from exc

        marker = next((entry for entry in children if entry.name == ".git"), None)
        if relative_parts and marker is not None:
            relative_path = PurePosixPath(*relative_parts).as_posix()
            markers.append((relative_path, Path(marker.path)))
            if len(markers) > _MAX_DISCOVERED_BOUNDARIES:
                raise RepositoryBoundaryError("BOUNDARY_LIMIT_EXCEEDED")
            continue

        for entry in children:
            if entry.name == ".git":
                continue
            child_parts = (*relative_parts, entry.name)
            relative_path = PurePosixPath(*child_parts).as_posix()
            if relative_path in excluded_subtrees:
                continue
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
            except OSError as exc:
                raise RepositoryBoundaryError("BOUNDARY_WALK_UNAVAILABLE") from exc
            if is_directory:
                pending.append((Path(entry.path), child_parts))
    return tuple(markers)


def _inspect_nested_marker(relative_path: str, marker: Path) -> RepositoryBoundary:
    validated_relative_path = _validate_relative_path(relative_path)
    marker_status = _lstat_or_none(marker)
    child = _discover_child(marker.parent, marker_status) if marker_status is not None else None
    if child is None:
        return RepositoryBoundary(
            kind=RepositoryBoundaryKind.NESTED_GIT,
            relative_path=validated_relative_path,
            state=RepositoryBoundaryState.INVALID,
        )
    return RepositoryBoundary(
        kind=RepositoryBoundaryKind.NESTED_GIT,
        relative_path=validated_relative_path,
        root=child.root,
        state=RepositoryBoundaryState.ENROLLABLE,
        observed_commit=child.head_commit,
        common_git_dir_identity=child.common_git_dir_identity,
        worktree_git_dir_identity=child.worktree_git_dir_identity,
    )


def _discover_child(
    candidate: Path,
    marker_status: os.stat_result,
    *,
    allowed_git_file_root: Path | None = None,
) -> GitWorktree | None:
    if stat.S_ISLNK(marker_status.st_mode):
        return None
    if stat.S_ISREG(marker_status.st_mode) and marker_status.st_size > _MAX_GIT_FILE_BYTES:
        return None
    if not (stat.S_ISREG(marker_status.st_mode) or stat.S_ISDIR(marker_status.st_mode)):
        return None
    marker = candidate / ".git"
    git_file_target = _read_git_file_target(marker) if stat.S_ISREG(marker_status.st_mode) else None
    if stat.S_ISREG(marker_status.st_mode) and git_file_target is None:
        return None
    try:
        child = discover_git_worktree_sync(candidate)
    except WorktreeDiscoveryError:
        return None
    if child.root != candidate:
        return None
    if git_file_target is None:
        return child if child.worktree_git_dir == marker else None
    if child.worktree_git_dir != git_file_target:
        return None
    if allowed_git_file_root is not None:
        return child if _is_contained_path(git_file_target, allowed_git_file_root) else None
    return child if _linked_worktree_marker_is_reciprocal(child, marker) else None


def _read_git_file_target(marker: Path) -> Path | None:
    content = _read_bounded_regular_file(marker)
    if content is None or not content.startswith("gitdir: "):
        return None
    raw_target = content.removeprefix("gitdir: ")
    if not raw_target or "\n" in raw_target or "\r" in raw_target or "\0" in raw_target:
        return None
    target = Path(raw_target)
    if not target.is_absolute():
        target = marker.parent / target
    return Path(os.path.abspath(target))


def _linked_worktree_marker_is_reciprocal(child: GitWorktree, marker: Path) -> bool:
    gitdir_reference = _read_bounded_regular_file(child.worktree_git_dir / "gitdir")
    common_reference = _read_bounded_regular_file(child.worktree_git_dir / "commondir")
    if gitdir_reference is None or common_reference is None:
        return False
    referenced_marker = Path(gitdir_reference)
    if not referenced_marker.is_absolute():
        referenced_marker = child.worktree_git_dir / referenced_marker
    referenced_common = Path(common_reference)
    if not referenced_common.is_absolute():
        referenced_common = child.worktree_git_dir / referenced_common
    return (
        Path(os.path.abspath(referenced_marker)) == marker
        and Path(os.path.abspath(referenced_common)) == child.common_git_dir
    )


def _read_bounded_regular_file(path: Path) -> str | None:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode) or status.st_size > _MAX_GIT_FILE_BYTES:
            return None
        payload = os.read(descriptor, _MAX_GIT_FILE_BYTES + 1)
    except OSError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(payload) > _MAX_GIT_FILE_BYTES:
        return None
    try:
        return os.fsdecode(payload).removesuffix("\n").removesuffix("\r")
    except UnicodeError:
        return None


def _is_contained_path(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return candidate != root


def _contained_candidate(root: Path, relative_path: str) -> Path:
    parts = PurePosixPath(relative_path).parts
    candidate = root.joinpath(*parts)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RepositoryBoundaryError("BOUNDARY_PATH_INVALID") from exc
    return candidate


def _validate_relative_path(raw_path: str) -> str:
    if not raw_path or len(raw_path) > _MAX_REPOSITORY_RELATIVE_PATH or "\0" in raw_path:
        raise RepositoryBoundaryError("BOUNDARY_PATH_INVALID")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or raw_path != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise RepositoryBoundaryError("BOUNDARY_PATH_INVALID")
    return path.as_posix()


def _is_git_object_id(value: str) -> bool:
    return len(value) in {40, 64} and all(character in "0123456789abcdef" for character in value)


def _lstat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RepositoryBoundaryError("BOUNDARY_FILESYSTEM_UNAVAILABLE") from exc


def _require_boundary_capacity(boundaries: dict[str, RepositoryBoundary]) -> None:
    if len(boundaries) > _MAX_DISCOVERED_BOUNDARIES:
        raise RepositoryBoundaryError("BOUNDARY_LIMIT_EXCEEDED")


def _index_signature(worktree: GitWorktree) -> tuple[int, int, int, int] | None:
    index = worktree.worktree_git_dir / "index"
    try:
        status = index.stat(follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RepositoryBoundaryError("BOUNDARY_FILESYSTEM_UNAVAILABLE") from exc
    if not stat.S_ISREG(status.st_mode):
        raise RepositoryBoundaryError("BOUNDARY_INDEX_INVALID")
    return status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns
