"""Tests for the isolated 0.3.0 Application Support storage layout."""

from __future__ import annotations

import os
import stat
from dataclasses import replace
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

    with pytest.raises(StorageLayoutError, match="symbolic link"):
        layout.ensure_private_directories()


def test_layout_rejects_a_symlinked_application_support_parent(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    library = tmp_path / "Library"
    library.mkdir()
    redirected_support = tmp_path / "redirected-support"
    redirected_support.mkdir()
    os.symlink(redirected_support, library / "Application Support")

    with pytest.raises(StorageLayoutError, match="symbolic link"):
        layout.ensure_private_directories()


def test_layout_rejects_an_exposed_human_config(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    layout.ensure_private_directories()
    layout.config_file.write_text("schema_version = 1\n")
    layout.config_file.chmod(0o644)

    with pytest.raises(StorageLayoutError, match="unsafe permissions"):
        layout.ensure_private_directories()


def test_layout_rejects_an_exposed_metadata_database(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    layout.ensure_private_directories()
    layout.metadata_db.write_text("sensitive derived data")
    layout.metadata_db.chmod(0o644)

    with pytest.raises(StorageLayoutError, match="unsafe permissions"):
        layout.ensure_private_directories()


def test_layout_creates_metadata_database_with_private_permissions(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)

    layout.ensure_private_metadata_database()

    assert layout.metadata_db.is_file()
    assert stat.S_IMODE(layout.metadata_db.stat().st_mode) == 0o600


def test_metadata_inspection_is_observational_when_runtime_state_is_absent(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)

    assert layout.metadata_database_exists() is False
    assert not (tmp_path / "Library").exists()


def test_metadata_inspection_rejects_without_repairing_unsafe_modes(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    layout.ensure_private_metadata_database()
    layout.metadata_db.chmod(0o644)

    with pytest.raises(StorageLayoutError, match="unsafe permissions"):
        layout.metadata_database_exists()

    assert stat.S_IMODE(layout.metadata_db.stat().st_mode) == 0o644


def test_artifact_descriptor_rejects_a_noncanonical_layout_without_creating_it(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    redirected = replace(layout, artifacts=tmp_path / "redirected-artifacts")

    with pytest.raises(StorageLayoutError, match="invalid layout"):
        with redirected.open_artifacts_directory():
            pytest.fail("invalid artifact layout was opened")

    assert not (tmp_path / "Library").exists()
    assert not redirected.artifacts.exists()
