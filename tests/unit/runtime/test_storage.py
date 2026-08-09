"""Tests for the isolated 0.3.0 Application Support storage layout."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from kb.runtime.storage import StorageLayoutError, macos_storage_layout


def test_layout_uses_only_the_fixed_application_support_root(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)

    assert layout.root == tmp_path / "Library" / "Application Support" / "Dolphin"
    assert layout.metadata_db == layout.root / "metadata.sqlite3"
    assert layout.config_file == layout.root / "config.toml"
    assert not (tmp_path / ".dolphin").exists()


def test_layout_creates_private_state_directories_but_not_human_config(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)

    layout.ensure_private_directories()

    for path in (layout.root, layout.vectors, layout.artifacts, layout.locks, layout.logs, layout.temporary):
        assert path.is_dir()
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert not layout.config_file.exists()
    assert not layout.metadata_db.exists()


def test_layout_rejects_a_symlinked_runtime_root(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    layout.root.parent.mkdir(parents=True)
    target = tmp_path / "elsewhere"
    target.mkdir()
    os.symlink(target, layout.root)

    with pytest.raises(StorageLayoutError, match="not a directory"):
        layout.ensure_private_directories()


def test_layout_rejects_an_exposed_human_config(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    layout.ensure_private_directories()
    layout.config_file.write_text("schema_version = 1\n")
    layout.config_file.chmod(0o644)

    with pytest.raises(StorageLayoutError, match="unsafe permissions"):
        layout.ensure_private_directories()
