"""Safe Git worktree identity discovery for explicit repository enrollment."""

from __future__ import annotations

import asyncio
import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_GIT_PROBE_TIMEOUT_SECONDS = 5.0
_MAX_GIT_PROBE_TIMEOUT_SECONDS = 30.0


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


def validate_git_worktree_snapshot(worktree: GitWorktree) -> None:
    """Reject a worktree whose on-disk Git identity changed after discovery."""
    if _read_git_worktree_snapshot(worktree.root) != worktree:
        raise WorktreeDiscoveryError("WORKTREE_SNAPSHOT_CHANGED")


def _discover_git_worktree(path: Path) -> GitWorktree:
    if not path.is_absolute():
        raise WorktreeDiscoveryError("WORKTREE_PATH_NOT_ABSOLUTE")
    if "\n" in str(path) or "\r" in str(path):
        raise WorktreeDiscoveryError("WORKTREE_PATH_LINEBREAK")
    if not path.is_dir():
        raise WorktreeDiscoveryError("WORKTREE_PATH_INVALID")

    worktree = _read_git_worktree_snapshot(path)
    if _read_git_worktree_snapshot(worktree.root) != worktree:
        raise WorktreeDiscoveryError("WORKTREE_SNAPSHOT_CHANGED")
    return worktree


def _read_git_worktree_snapshot(path: Path) -> GitWorktree:
    """Read one coherent Git identity snapshot rooted at an already-validated path."""
    root, common_git_dir, head_commit, branch = _git_snapshot(path)
    common_git_dir_path = Path(common_git_dir)
    return GitWorktree(
        root=Path(root),
        common_git_dir=common_git_dir_path,
        common_git_dir_identity=git_directory_identity(common_git_dir_path),
        head_commit=head_commit,
        branch=branch,
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


def git_directory_identity(path: Path) -> str:
    """Bind a Git directory to its filesystem generation, not merely its reusable pathname."""
    try:
        status = path.stat()
    except OSError as exc:
        raise WorktreeDiscoveryError("WORKTREE_SNAPSHOT_CHANGED") from exc
    birth_time = getattr(status, "st_birthtime", None)
    if birth_time is None:
        return f"{status.st_dev}:{status.st_ino}"
    return f"{status.st_dev}:{status.st_ino}:{int(birth_time * 1_000_000_000)}"


def _run_git(path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(path), *arguments],
            capture_output=True,
            check=False,
            text=True,
            timeout=_git_probe_timeout_seconds(),
        )
    except FileNotFoundError as exc:
        raise WorktreeDiscoveryError("GIT_UNAVAILABLE") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorktreeDiscoveryError("WORKTREE_PROBE_TIMEOUT") from exc
    except OSError as exc:
        raise WorktreeDiscoveryError("WORKTREE_PROBE_FAILED") from exc


def _git_probe_timeout_seconds() -> float:
    """Resolve a finite override, clamped to the documented 30-second enrollment maximum."""
    raw = os.environ.get("DOLPHIN_GIT_PROBE_TIMEOUT_SECONDS")
    if raw is None:
        return _DEFAULT_GIT_PROBE_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        return _DEFAULT_GIT_PROBE_TIMEOUT_SECONDS
    if not math.isfinite(timeout) or timeout <= 0:
        return _DEFAULT_GIT_PROBE_TIMEOUT_SECONDS
    return min(timeout, _MAX_GIT_PROBE_TIMEOUT_SECONDS)
