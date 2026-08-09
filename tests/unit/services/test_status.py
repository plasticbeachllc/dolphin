"""Tests for the initial transport-independent runtime status service."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import subprocess
import time
from pathlib import Path

import pytest

from kb.mcp.contracts import StatusInput
from kb.runtime.storage import macos_storage_layout
from kb.services import status as status_module
from kb.services.repo_add import RepoAddService
from kb.services.status import StatusService
from kb.services.workspace_registry import WorkspaceRegistry
from kb.services.workspace_resolution import WorkspaceSessionScope


@pytest.mark.asyncio
async def test_status_reports_credential_state_without_disclosing_the_value(tmp_path: Path) -> None:
    result = await StatusService(cwd=tmp_path, environment={"DOLPHIN_OPENAI_API_KEY": "secret"})(StatusInput())

    assert result.readiness == "degraded"
    assert result.credential_present is True
    assert result.credential_variable == "DOLPHIN_OPENAI_API_KEY"
    assert "secret" not in result.model_dump_json()
    assert result.current_workspace_resolution == "outside_worktree"


@pytest.mark.asyncio
async def test_status_reports_registration_unavailable_without_generating_credentials(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    result = await StatusService(cwd=tmp_path, environment={})(StatusInput())

    assert result.readiness == "degraded"
    assert result.current_workspace_resolution == "unregistered"
    assert len(result.next_actions) == 1
    assert result.next_actions[0] == status_module.NextAction(
        action="registration_unavailable",
        reason="Dolphin has not registered this Git worktree, but repo_add is unavailable in this runtime.",
    )
    assert "cleanup_receipt" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_status_worktree_probe_ignores_ambient_git_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    requested_root = tmp_path / "requested"
    ambient_root = tmp_path / "ambient"
    subprocess.run(["git", "init", "-q", str(requested_root)], check=True)
    subprocess.run(["git", "init", "-q", str(ambient_root)], check=True)
    monkeypatch.setenv("GIT_DIR", str(ambient_root / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(ambient_root))

    probe = status_module._probe_worktree(requested_root)

    assert probe.resolution == "unregistered"
    assert probe.root == requested_root


def test_worktree_probe_preserves_surrounding_path_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = "/tmp/ Dolphin worktree "
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=f"{expected}\n")
    monkeypatch.setattr(status_module.subprocess, "run", lambda *_args, **_kwargs: completed)

    result = status_module._probe_worktree(Path("/tmp"))

    assert result.root == Path(expected)


@pytest.mark.asyncio
async def test_status_reports_unavailable_when_git_detection_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def missing_git(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(status_module.subprocess, "run", missing_git)

    result = await StatusService(cwd=tmp_path, environment={})(StatusInput())

    assert result.current_workspace_resolution == "unavailable"
    assert result.next_actions == [
        status_module.NextAction(action="inspect_git", reason="Git is unavailable to Dolphin.")
    ]


@pytest.mark.asyncio
async def test_status_runs_git_probe_off_the_event_loop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def slow_probe(_cwd: Path) -> status_module._WorktreeProbe:
        time.sleep(0.05)
        return status_module._WorktreeProbe(resolution="outside_worktree")

    monkeypatch.setattr(status_module, "_probe_worktree", slow_probe)
    status_task = asyncio.create_task(StatusService(cwd=tmp_path, environment={})(StatusInput()))
    ticker = asyncio.create_task(asyncio.sleep(0.005))

    done, _pending = await asyncio.wait({status_task, ticker}, return_when=asyncio.FIRST_COMPLETED)

    assert ticker in done
    assert status_task not in done
    await status_task


@pytest.mark.asyncio
async def test_status_never_resolves_a_new_nested_worktree_as_its_registered_parent(tmp_path: Path) -> None:
    parent = _commit_repository(tmp_path / "parent")
    registry = _registry(tmp_path)
    await RepoAddService(registry).submit(parent, _cleanup_receipt("parent"))
    child = _commit_repository(parent / "created-later")

    result = await StatusService(cwd=child, environment={}, registry=registry)(StatusInput())

    assert result.current_workspace_resolution == "unregistered"
    assert result.current_workspace is None
    assert result.next_actions == [
        status_module.NextAction(
            action="registration_unavailable",
            reason="Dolphin has not registered this Git worktree, but repo_add is unavailable in this runtime.",
        )
    ]


@pytest.mark.asyncio
async def test_status_reports_ambiguous_mcp_roots_without_guessing(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    first = _commit_repository(tmp_path / "first")
    second = _commit_repository(tmp_path / "second")
    await RepoAddService(registry).submit(first, _cleanup_receipt("first"))
    await RepoAddService(registry).submit(second, _cleanup_receipt("second"))

    result = await StatusService(
        cwd=tmp_path,
        environment={},
        registry=registry,
        mcp_roots=(first, second),
    )(StatusInput())

    assert result.current_workspace_resolution == "ambiguous"
    assert result.current_workspace is None
    assert result.next_actions == [
        status_module.NextAction(
            action="inspect_repositories",
            reason="Choose one available Dolphin workspace explicitly.",
            tool="repo_list",
            arguments={"cursor": None},
        )
    ]


@pytest.mark.asyncio
async def test_status_prefers_connection_local_scope_to_process_cwd(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    cwd_root = _commit_repository(tmp_path / "cwd")
    selected_root = _commit_repository(tmp_path / "selected")
    await RepoAddService(registry).submit(cwd_root, _cleanup_receipt("cwd"))
    selected = await RepoAddService(registry).submit(selected_root, _cleanup_receipt("selected"))
    session = WorkspaceSessionScope(selected.registration.workspace_id)

    result = await StatusService(
        cwd=cwd_root,
        environment={},
        registry=registry,
        session_scope=session,
    )(StatusInput())

    assert result.current_workspace_resolution == "resolved"
    assert result.current_workspace is not None
    assert result.current_workspace.id == selected.registration.workspace_id
    assert result.current_workspace.root == str(selected_root)


@pytest.mark.asyncio
async def test_status_returns_typed_remediation_for_an_invalid_nested_boundary(tmp_path: Path) -> None:
    parent = _commit_repository(tmp_path / "parent")
    nested = parent / "nested"
    nested.mkdir()
    (nested / ".git").write_text("not a gitdir\n")
    registry = _registry(tmp_path)
    await RepoAddService(registry).submit(parent, _cleanup_receipt("parent"))

    result = await StatusService(cwd=nested, environment={}, registry=registry)(StatusInput())

    assert result.current_workspace_resolution == "unregistered"
    assert result.current_workspace is None
    assert result.next_actions == [
        status_module.NextAction(
            action="inspect_repository_boundary",
            reason="This nested repository boundary is invalid or conflicted and must be repaired outside Dolphin.",
        )
    ]


@pytest.mark.asyncio
async def test_status_returns_typed_remediation_for_an_uninitialized_submodule(tmp_path: Path) -> None:
    parent = _commit_repository(tmp_path / "parent")
    head = subprocess.run(
        ["git", "-C", str(parent), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.removesuffix("\n")
    _git(parent, "update-index", "--add", "--cacheinfo", f"160000,{head},dependencies/child")
    _git(parent, "commit", "-qm", "Add uninitialized submodule")
    registry = _registry(tmp_path)
    await RepoAddService(registry).submit(parent, _cleanup_receipt("parent"))

    result = await StatusService(
        cwd=tmp_path,
        environment={},
        registry=registry,
        mcp_roots=(parent / "dependencies" / "child",),
    )(StatusInput())

    assert result.current_workspace_resolution == "unregistered"
    assert result.current_workspace is None
    assert result.next_actions == [
        status_module.NextAction(
            action="initialize_submodule",
            reason="This submodule has no usable local worktree; initialize or restore it outside Dolphin.",
        )
    ]


def _registry(tmp_path: Path) -> WorkspaceRegistry:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return WorkspaceRegistry(macos_storage_layout(home=home))


def _commit_repository(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "dolphin-tests@example.invalid")
    _git(path, "config", "user.name", "Dolphin Tests")
    (path / "README.md").write_text(f"# {path.name}\n")
    _git(path, "add", "-f", "README.md")
    _git(path, "commit", "-qm", "Initial commit")
    return path


def _git(path: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(path), *arguments], check=True, capture_output=True, text=True)


def _cleanup_receipt(label: str) -> str:
    payload = hashlib.sha256(label.encode("utf-8")).digest()
    return "dolphin-cleanup-v1_" + base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
