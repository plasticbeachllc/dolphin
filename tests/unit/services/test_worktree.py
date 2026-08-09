"""Tests for explicit concrete Git worktree discovery."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

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
    assert worktree.worktree_git_dir == tmp_path / ".git"
    assert worktree.worktree_git_dir_identity == worktree.common_git_dir_identity
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
async def test_discovery_ignores_ambient_git_repository_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    requested_root = tmp_path / "requested"
    ambient_root = tmp_path / "ambient"
    requested_root.mkdir()
    ambient_root.mkdir()
    _commit_repository(requested_root)
    _commit_repository(ambient_root)
    monkeypatch.setenv("GIT_DIR", str(ambient_root / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(ambient_root))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(ambient_root))

    worktree = await discover_git_worktree(requested_root)

    assert worktree.root == requested_root
    assert worktree.common_git_dir == requested_root / ".git"
    assert worktree.worktree_git_dir == requested_root / ".git"
    assert worktree.head_commit == _git(requested_root, "rev-parse", "HEAD", sanitized=True)


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
                f"{root}\n{root / '.git'}\n{root / '.git'}\ninitial-head\nrefs/heads/main\n",
                "",
            ),
            subprocess.CompletedProcess(
                [],
                0,
                f"{root}\n{root / '.git'}\n{root / '.git'}\nreplacement-head\nrefs/heads/main\n",
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


@pytest.mark.asyncio
async def test_linked_worktrees_share_repository_identity_but_have_distinct_git_directories(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    linked = tmp_path / "linked"
    primary.mkdir()
    _commit_repository(primary)
    _git(primary, "worktree", "add", "-q", "-b", "linked-branch", str(linked))

    primary_snapshot = await discover_git_worktree(primary)
    linked_snapshot = await discover_git_worktree(linked)

    assert linked_snapshot.common_git_dir == primary_snapshot.common_git_dir
    assert linked_snapshot.common_git_dir_identity == primary_snapshot.common_git_dir_identity
    assert linked_snapshot.worktree_git_dir != primary_snapshot.worktree_git_dir
    assert linked_snapshot.worktree_git_dir_identity != primary_snapshot.worktree_git_dir_identity
    assert linked_snapshot.worktree_git_dir.parent == primary / ".git" / "worktrees"


@pytest.mark.asyncio
async def test_worktree_git_directory_identity_survives_a_git_managed_move(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    linked = tmp_path / "linked"
    moved = tmp_path / "moved"
    primary.mkdir()
    _commit_repository(primary)
    _git(primary, "worktree", "add", "-q", "-b", "linked-branch", str(linked))
    before = await discover_git_worktree(linked)

    _git(primary, "worktree", "move", str(linked), str(moved))
    after = await discover_git_worktree(moved)

    assert after.root == moved
    assert after.common_git_dir_identity == before.common_git_dir_identity
    assert after.worktree_git_dir_identity == before.worktree_git_dir_identity


def test_git_directory_identity_uses_birth_time_and_rejects_symlinks(tmp_path: Path) -> None:
    directory = tmp_path / "git-directory"
    directory.mkdir()
    symlink = tmp_path / "git-directory-link"
    symlink.symlink_to(directory, target_is_directory=True)

    identity = worktree_module.git_directory_identity(directory)

    kind, device, inode, birth_time_ns = identity.split(":")
    assert kind == "directory"
    assert int(device) >= 0
    assert int(inode) > 0
    assert int(birth_time_ns) > 0 if sys.platform == "darwin" else int(birth_time_ns) == 0
    with pytest.raises(WorktreeDiscoveryError, match="WORKTREE_SNAPSHOT_CHANGED"):
        worktree_module.git_directory_identity(symlink)


def test_macos_directory_identity_rejects_missing_birth_time(monkeypatch: pytest.MonkeyPatch) -> None:
    status = cast(
        os.stat_result,
        SimpleNamespace(st_mode=0o040700, st_dev=1, st_ino=2),
    )
    monkeypatch.setattr(worktree_module.sys, "platform", "darwin")

    with pytest.raises(WorktreeDiscoveryError, match="WORKTREE_SNAPSHOT_CHANGED"):
        worktree_module._directory_identity_components(status)


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


def test_git_probe_environment_removes_every_git_variable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed_environment: dict[str, str] = {}

    def run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        observed_environment.update(cast(dict[str, str], environment))
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(worktree_module.subprocess, "run", run)
    monkeypatch.setenv("GIT_DIR", "/wrong/repository")
    monkeypatch.setenv("GIT_CUSTOM_SELECTOR", "must-also-be-removed")
    monkeypatch.setenv("DOLPHIN_TEST_SENTINEL", "preserved")

    worktree_module._run_git(tmp_path, "status")

    assert not any(name.startswith("GIT_") for name in observed_environment)
    assert observed_environment["DOLPHIN_TEST_SENTINEL"] == "preserved"


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


def _git(path: Path, *arguments: str, sanitized: bool = False) -> str:
    environment = None
    if sanitized:
        environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    result = subprocess.run(
        ["git", "-C", str(path), *arguments],
        capture_output=True,
        check=True,
        env=environment,
        text=True,
    )
    return result.stdout.removesuffix("\n")
