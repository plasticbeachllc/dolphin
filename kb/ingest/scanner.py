from __future__ import annotations

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
    abs_path: Path
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


def _is_binary(path: Path, sniff_bytes: int = 65536) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(sniff_bytes)
        # Fast NUL-byte heuristic
        if b"\x00" in chunk:
            return True
        # UTF-8 decode check
        chunk.decode("utf-8")
        return False
    except Exception:
        return True


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
        abs_path = root.joinpath(*PurePosixPath(rel).parts)
        try:
            path_status = abs_path.stat(follow_symlinks=False)
        except OSError:
            continue
        if not stat.S_ISREG(path_status.st_mode):
            continue
        # Binary detection
        is_bin = _is_binary(abs_path)
        if is_bin:
            continue
        size = path_status.st_size
        # Language
        _, language = classify_language(Path(rel))
        ext = Path(rel).suffix.lower() or None
        candidates.append(
            FileCandidate(
                repo_root=root,
                rel_path=rel,
                abs_path=abs_path,
                ext=ext,
                language=language,
                size_bytes=size,
                is_binary=is_bin,
            )
        )

    _validate_repository_boundary_plan(boundary_plan)
    return candidates
