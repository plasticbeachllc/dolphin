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
async def test_discovery_rejects_linebreak_paths_before_using_git(tmp_path: Path) -> None:
    path = tmp_path / "line\nbreak"
    path.mkdir()

    with pytest.raises(WorktreeDiscoveryError, match="WORKTREE_PATH_LINEBREAK"):
        await discover_git_worktree(path)


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


def test_git_probe_timeout_defaults_to_five_seconds_and_allows_an_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed_timeouts: list[float] = []

    def run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        timeout = kwargs["timeout"]
        assert isinstance(timeout, int | float)
        observed_timeouts.append(float(timeout))
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(worktree_module.subprocess, "run", run)
    monkeypatch.delenv("DOLPHIN_GIT_PROBE_TIMEOUT_SECONDS", raising=False)
    worktree_module._run_git(tmp_path, "status")
    monkeypatch.setenv("DOLPHIN_GIT_PROBE_TIMEOUT_SECONDS", "12.5")
    worktree_module._run_git(tmp_path, "status")
    monkeypatch.setenv("DOLPHIN_GIT_PROBE_TIMEOUT_SECONDS", "999")
    worktree_module._run_git(tmp_path, "status")
    monkeypatch.setenv("DOLPHIN_GIT_PROBE_TIMEOUT_SECONDS", "inf")
    worktree_module._run_git(tmp_path, "status")

    assert observed_timeouts == [5.0, 12.5, 30.0, 5.0]


def test_git_probe_timeout_remains_a_distinct_discovery_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("git", 5)

    monkeypatch.setattr(worktree_module.subprocess, "run", timeout)

    with pytest.raises(WorktreeDiscoveryError, match="WORKTREE_PROBE_TIMEOUT"):
        worktree_module._run_git(tmp_path, "status")


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
