from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from kb import cli
from kb.api_key import get_kb_key_path


@pytest.fixture()
def temp_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolate HOME/USERPROFILE for the test run."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    for name in ("DOLPHIN_API_KEY", "DOLPHIN_KB_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_serve_sets_api_key_when_missing(monkeypatch: pytest.MonkeyPatch, temp_home: Path) -> None:
    """serve should ensure DOLPHIN_API_KEY is set even when env is empty."""
    captured: dict[str, Any] = {}

    def fake_run(app_path: str, host: str, port: int, reload: bool) -> None:  # pragma: no cover - shim
        captured["app_path"] = app_path
        captured["host"] = host
        captured["port"] = port
        captured["reload"] = reload
        captured["env_key"] = os.environ.get("DOLPHIN_API_KEY")

    # Use unittest.mock.patch to avoid uvicorn's logging configuration
    from unittest.mock import patch

    with patch("uvicorn.run", side_effect=fake_run):
        cli.serve()

    key_path = get_kb_key_path()
    assert key_path.exists(), "serve should create the per-user key file"

    file_key = key_path.read_text(encoding="utf-8").strip()
    env_key = captured.get("env_key")

    assert env_key, "DOLPHIN_API_KEY must be populated before starting uvicorn"
    assert env_key == file_key, "serve should set env using the managed key"
    assert captured["app_path"] == "kb.api.server:app_with_lifespan"


def test_serve_respects_env_override(monkeypatch: pytest.MonkeyPatch, temp_home: Path) -> None:
    """If an API key is already set, serve must not overwrite it."""
    monkeypatch.setenv("DOLPHIN_API_KEY", "existing-key")

    def fake_run(app_path: str, host: str, port: int, reload: bool) -> None:  # pragma: no cover - shim
        assert os.environ.get("DOLPHIN_API_KEY") == "existing-key"
        assert not get_kb_key_path().exists(), "No file should be created when env override is present"

    # Use unittest.mock.patch to avoid uvicorn's logging configuration
    from unittest.mock import patch

    with patch("uvicorn.run", side_effect=fake_run):
        cli.serve()
