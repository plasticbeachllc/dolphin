"""Tests for the initial transport-independent runtime status service."""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

import pytest

from kb.mcp.contracts import StatusInput
from kb.services import status as status_module
from kb.services.status import StatusService


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
