"""Safe Git worktree identity discovery for explicit repository enrollment."""

from __future__ import annotations

import asyncio
import math
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_GIT_PROBE_TIMEOUT_SECONDS = 5.0
_MAX_GIT_PROBE_TIMEOUT_SECONDS = 30.0
_MAX_FILESYSTEM_IDENTITY_COMPONENT = (1 << 64) - 1


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
    worktree_git_dir: Path
    worktree_git_dir_identity: str
    head_commit: str
    branch: str | None


async def discover_git_worktree(path: Path) -> GitWorktree:
    """Resolve one absolute input path to its concrete Git worktree identity."""
    return await asyncio.to_thread(discover_git_worktree_sync, path)


def discover_git_worktree_sync(path: Path) -> GitWorktree:
    """Synchronous worktree discovery for local worker and scanner threads."""
    return _discover_git_worktree(path)


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
    root, common_git_dir, worktree_git_dir, head_commit, branch = _git_snapshot(path)
    common_git_dir_path = Path(common_git_dir)
    worktree_git_dir_path = Path(worktree_git_dir)
    return GitWorktree(
        root=Path(root),
        common_git_dir=common_git_dir_path,
        common_git_dir_identity=git_directory_identity(common_git_dir_path),
        worktree_git_dir=worktree_git_dir_path,
        worktree_git_dir_identity=git_directory_identity(worktree_git_dir_path),
        head_commit=head_commit,
        branch=branch,
    )


def _git_snapshot(path: Path) -> tuple[str, str, str, str, str | None]:
    """Read one complete worktree identity snapshot from a single Git invocation."""
    result = _run_git(
        path,
        "rev-parse",
        "--path-format=absolute",
        "--show-toplevel",
        "--git-common-dir",
        "--git-dir",
        "HEAD",
        "--symbolic-full-name",
        "HEAD",
    )
    if result.returncode != 0:
        raise WorktreeDiscoveryError("WORKTREE_NOT_GIT")
    values = result.stdout.splitlines()
    if len(values) != 5 or any(not value for value in values):
        raise WorktreeDiscoveryError("WORKTREE_NOT_GIT")
    symbolic_head = values[4]
    branch = None if symbolic_head == "HEAD" else symbolic_head.removeprefix("refs/heads/")
    return values[0], values[1], values[2], values[3], branch


def git_directory_identity(path: Path) -> str:
    """Bind a Git directory to its filesystem generation, not merely its reusable pathname."""
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
        )
        descriptor_status = os.fstat(descriptor)
        path_status = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise WorktreeDiscoveryError("WORKTREE_SNAPSHOT_CHANGED") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    descriptor_identity = _directory_identity_components(descriptor_status)
    path_identity = _directory_identity_components(path_status)
    if descriptor_identity != path_identity:
        raise WorktreeDiscoveryError("WORKTREE_SNAPSHOT_CHANGED")
    device, inode, birth_time_ns = descriptor_identity
    return f"directory:{device}:{inode}:{birth_time_ns}"


def _directory_identity_components(status: os.stat_result) -> tuple[int, int, int]:
    birth_time = getattr(status, "st_birthtime", None)
    if birth_time is None and sys.platform != "darwin":
        # Linux remains a test/development host while 0.3.0 is macOS-only. It
        # cannot authorize production continuity, but a stable sentinel keeps
        # transport-independent unit tests useful on existing Linux CI.
        birth_time = 0
    if (
        not stat.S_ISDIR(status.st_mode)
        or not isinstance(status.st_dev, int)
        or not isinstance(status.st_ino, int)
        or not isinstance(birth_time, float | int)
        or not math.isfinite(birth_time)
    ):
        raise WorktreeDiscoveryError("WORKTREE_SNAPSHOT_CHANGED")
    birth_time_ns = int(birth_time * 1_000_000_000)
    if any(
        component < 0 or component > _MAX_FILESYSTEM_IDENTITY_COMPONENT
        for component in (status.st_dev, status.st_ino, birth_time_ns)
    ):
        raise WorktreeDiscoveryError("WORKTREE_SNAPSHOT_CHANGED")
    return status.st_dev, status.st_ino, birth_time_ns


def _run_git(path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(path), *arguments],
            capture_output=True,
            check=False,
            encoding="utf-8",
            env=sanitized_git_environment(),
            errors="surrogateescape",
            text=True,
            timeout=_git_probe_timeout_seconds(),
        )
    except FileNotFoundError as exc:
        raise WorktreeDiscoveryError("GIT_UNAVAILABLE") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorktreeDiscoveryError("WORKTREE_PROBE_TIMEOUT") from exc
    except OSError as exc:
        raise WorktreeDiscoveryError("WORKTREE_PROBE_FAILED") from exc


def run_git_read_only(path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run one bounded, sanitized Git metadata command without a shell."""
    return _run_git(path, *arguments)


def sanitized_git_environment() -> dict[str, str]:
    """Keep ambient Git repository/config selectors from overriding the explicit path."""
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}


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
