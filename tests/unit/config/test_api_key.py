from __future__ import annotations

from pathlib import Path

import pytest

from kb import api_key


@pytest.fixture()
def temp_home(monkeypatch, tmp_path: Path) -> Path:
    """Point Path.home() to a temporary directory for isolation."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # On Windows, Path.home may consult USERPROFILE
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    for name in ("DOLPHIN_API_KEY", "DOLPHIN_KB_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_env_override_wins(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOLPHIN_API_KEY", "env-key")

    key = api_key.get_or_create_kb_api_key()

    assert key == "env-key"
    assert not api_key.get_kb_key_path().exists()


def test_get_or_create_creates_file(temp_home: Path) -> None:
    key = api_key.get_or_create_kb_api_key()

    key_path = api_key.get_kb_key_path()
    assert key_path.exists()
    assert key_path.read_text(encoding="utf-8").strip() == key
    assert len(key) == 64


def test_get_or_create_reuses_existing_key(temp_home: Path) -> None:
    first = api_key.get_or_create_kb_api_key()
    second = api_key.get_or_create_kb_api_key()

    assert first == second


def test_load_kb_api_key_none_when_missing(temp_home: Path) -> None:
    assert api_key.load_kb_api_key() is None


def test_load_kb_api_key_prefers_env(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_path = api_key.get_kb_key_path()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text("file-key\n", encoding="utf-8")

    monkeypatch.setenv("DOLPHIN_KB_API_KEY", "env-key")

    assert api_key.load_kb_api_key() == "env-key"
