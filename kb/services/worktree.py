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

    root = Path(_git_value(path, "rev-parse", "--show-toplevel"))
    common_git_dir = Path(_git_value(path, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    head_commit = _git_value(path, "rev-parse", "--verify", "HEAD")
    branch = _git_optional_value(path, "symbolic-ref", "--quiet", "--short", "HEAD")

    return GitWorktree(
        root=root,
        common_git_dir=common_git_dir,
        head_commit=head_commit,
        branch=branch,
    )


def _git_value(path: Path, *arguments: str) -> str:
    result = _run_git(path, *arguments)
    if result.returncode != 0:
        raise WorktreeDiscoveryError("WORKTREE_NOT_GIT")
    value = _single_git_line(result.stdout)
    if not value:
        raise WorktreeDiscoveryError("WORKTREE_NOT_GIT")
    return value


def _git_optional_value(path: Path, *arguments: str) -> str | None:
    result = _run_git(path, *arguments)
    if result.returncode == 1:
        return None
    if result.returncode != 0:
        raise WorktreeDiscoveryError("WORKTREE_NOT_GIT")
    return _single_git_line(result.stdout) or None


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


def _single_git_line(output: str) -> str:
    """Remove Git's protocol terminator without altering valid path whitespace."""
    return output.removesuffix("\n")
