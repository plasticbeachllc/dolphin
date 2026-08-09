"""Safe Git worktree identity discovery for explicit repository enrollment."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorktreeDiscoveryError(ValueError):
    """The requested path cannot safely identify one concrete Git worktree."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class GitWorktree:
    """The stable Git identity required before Dolphin can register a workspace."""

    root: Path
    common_git_dir: Path
    common_git_dir_identity: str
    head_commit: str
    branch: str | None


async def discover_git_worktree(path: Path) -> GitWorktree:
    """Resolve one absolute input path to its concrete Git worktree identity."""
    return await asyncio.to_thread(_discover_git_worktree, path)


def _discover_git_worktree(path: Path) -> GitWorktree:
    if not path.is_absolute():
        raise WorktreeDiscoveryError("WORKTREE_PATH_NOT_ABSOLUTE")
    if not path.is_dir():
        raise WorktreeDiscoveryError("WORKTREE_PATH_INVALID")

    snapshot = _git_snapshot(path)
    root, common_git_dir, _head_commit, _branch = snapshot
    root_path = Path(root)
    common_git_dir_path = Path(common_git_dir)
    common_git_dir_identity = _directory_identity(common_git_dir_path)
    if _git_snapshot(root_path) != snapshot or _directory_identity(common_git_dir_path) != common_git_dir_identity:
        raise WorktreeDiscoveryError("WORKTREE_SNAPSHOT_CHANGED")

    return GitWorktree(
        root=root_path,
        common_git_dir=common_git_dir_path,
        common_git_dir_identity=common_git_dir_identity,
        head_commit=_head_commit,
        branch=_branch,
    )


def _git_snapshot(path: Path) -> tuple[str, str, str, str | None]:
    """Read one complete worktree identity snapshot from a single Git invocation."""
    result = _run_git(
        path,
        "rev-parse",
        "--path-format=absolute",
        "--show-toplevel",
        "--git-common-dir",
        "HEAD",
        "--symbolic-full-name",
        "HEAD",
    )
    if result.returncode != 0:
        raise WorktreeDiscoveryError("WORKTREE_NOT_GIT")
    values = result.stdout.splitlines()
    if len(values) != 4 or any(not value for value in values):
        raise WorktreeDiscoveryError("WORKTREE_NOT_GIT")
    symbolic_head = values[3]
    branch = None if symbolic_head == "HEAD" else symbolic_head.removeprefix("refs/heads/")
    return values[0], values[1], values[2], branch


def _directory_identity(path: Path) -> str:
    """Bind an on-disk Git directory, not merely its reusable pathname."""
    try:
        status = path.stat()
    except OSError as exc:
        raise WorktreeDiscoveryError("WORKTREE_SNAPSHOT_CHANGED") from exc
    return f"{status.st_dev}:{status.st_ino}"


def _run_git(path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(path), *arguments],
            capture_output=True,
            check=False,
            text=True,
            timeout=1,
        )
    except FileNotFoundError as exc:
        raise WorktreeDiscoveryError("GIT_UNAVAILABLE") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorktreeDiscoveryError("WORKTREE_PROBE_TIMEOUT") from exc
    except OSError as exc:
        raise WorktreeDiscoveryError("WORKTREE_PROBE_FAILED") from exc
