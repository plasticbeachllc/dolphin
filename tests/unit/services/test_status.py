"""Tests for the initial transport-independent runtime status service."""

from __future__ import annotations

import subprocess
from pathlib import Path

from kb.mcp.contracts import StatusInput
from kb.services.status import StatusService


def test_status_reports_credential_state_without_disclosing_the_value(tmp_path: Path) -> None:
    result = StatusService(cwd=tmp_path, environment={"DOLPHIN_OPENAI_API_KEY": "secret"})(StatusInput())

    assert result.readiness == "ready"
    assert result.credential_present is True
    assert result.credential_variable == "DOLPHIN_OPENAI_API_KEY"
    assert "secret" not in result.model_dump_json()
    assert result.current_workspace_resolution == "outside_worktree"


def test_status_recommends_explicit_repo_add_for_the_current_worktree(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    result = StatusService(cwd=tmp_path, environment={})(StatusInput())

    assert result.readiness == "degraded"
    assert result.current_workspace_resolution == "unregistered"
    assert len(result.next_actions) == 1
    assert result.next_actions[0].tool == "repo_add"
    assert result.next_actions[0].arguments == {"path": str(tmp_path)}
