"""Tests for explicit concrete Git worktree discovery."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from kb.services import worktree as worktree_module
from kb.services.worktree import WorktreeDiscoveryError, discover_git_worktree


@pytest.mark.asyncio
async def test_discovery_canonicalizes_an_absolute_path_inside_a_worktree(tmp_path: Path) -> None:
    _commit_repository(tmp_path)
    nested = tmp_path / "nested" / "path"
    nested.mkdir(parents=True)

    worktree = await discover_git_worktree(nested)

    assert worktree.root == tmp_path
    assert worktree.common_git_dir == tmp_path / ".git"
    assert worktree.head_commit == _git(tmp_path, "rev-parse", "HEAD")
    assert worktree.branch == _git(tmp_path, "symbolic-ref", "--short", "HEAD")


@pytest.mark.asyncio
async def test_discovery_preserves_worktree_root_whitespace(tmp_path: Path) -> None:
    root = tmp_path / " worktree with spaces "
    root.mkdir()
    _commit_repository(root)

    worktree = await discover_git_worktree(root)

    assert worktree.root == root


@pytest.mark.asyncio
async def test_discovery_rejects_relative_and_non_git_paths(tmp_path: Path) -> None:
    with pytest.raises(WorktreeDiscoveryError, match="WORKTREE_PATH_NOT_ABSOLUTE"):
        await discover_git_worktree(Path("."))
    with pytest.raises(WorktreeDiscoveryError, match="WORKTREE_NOT_GIT"):
        await discover_git_worktree(tmp_path)


@pytest.mark.asyncio
async def test_discovery_rejects_a_head_that_changes_during_the_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    caller_path = tmp_path / "caller"
    caller_path.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / ".git").mkdir()
    calls: list[Path] = []
    responses = iter(
        [
            subprocess.CompletedProcess(
                [],
                0,
                f"{root}\n{root / '.git'}\ninitial-head\nrefs/heads/main\n",
                "",
            ),
            subprocess.CompletedProcess(
                [],
                0,
                f"{root}\n{root / '.git'}\nreplacement-head\nrefs/heads/main\n",
                "",
            ),
        ]
    )

    def run_git(path: Path, *_args: str) -> subprocess.CompletedProcess[str]:
        calls.append(path)
        return next(responses)

    monkeypatch.setattr(worktree_module, "_run_git", run_git)

    with pytest.raises(WorktreeDiscoveryError, match="WORKTREE_SNAPSHOT_CHANGED"):
        await discover_git_worktree(caller_path)
    assert calls == [caller_path, root]


def _commit_repository(path: Path) -> None:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "dolphin-tests@example.invalid")
    _git(path, "config", "user.name", "Dolphin Tests")
    (path / "example.py").write_text("print('dolphin')\n")
    _git(path, "add", "example.py")
    _git(path, "commit", "-qm", "Initial test commit")


def _git(path: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *arguments], capture_output=True, check=True, text=True)
    return result.stdout.removesuffix("\n")
