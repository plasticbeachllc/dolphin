"""Native macOS storage durability integration tests."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from kb.runtime.storage import macos_storage_layout
from kb.store.chunk_artifacts import ChunkArtifactStore


@pytest.mark.skipif(sys.platform != "darwin", reason="requires native macOS filesystem semantics")
def test_native_macos_initialization_and_artifact_install_sync_real_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    text = "native macOS directory durability\n"
    real_fsync = os.fsync
    synced_directories = 0

    def record_successful_directory_sync(descriptor: int) -> None:
        nonlocal synced_directories
        is_directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        real_fsync(descriptor)
        if is_directory:
            synced_directories += 1

    monkeypatch.setattr(os, "fsync", record_successful_directory_sync)

    layout.ensure_private_directories()
    artifact = store.put_exact_text(text)

    assert store.read_verified(artifact.artifact_id) == text
    assert synced_directories >= 10
