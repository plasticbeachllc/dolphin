"""Native macOS storage durability integration tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from kb.runtime.storage import macos_storage_layout
from kb.store.chunk_artifacts import ChunkArtifactStore


@pytest.mark.skipif(sys.platform != "darwin", reason="requires native macOS filesystem semantics")
def test_native_macos_initialization_and_artifact_install_use_real_directory_sync(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    text = "native macOS directory durability\n"

    layout.ensure_private_directories()
    artifact = store.put_exact_text(text)

    assert store.read_verified(artifact.artifact_id) == text
