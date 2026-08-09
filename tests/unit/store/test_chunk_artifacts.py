"""Tests for private immutable exact-text chunk artifacts."""

from __future__ import annotations

import os
import stat
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

import pytest

from kb.artifacts import (
    CHUNK_TEXT_DOMAIN,
    MAX_CHUNK_TEXT_UTF8_BYTES,
    ArtifactCorrupt,
    ArtifactInputInvalid,
    ArtifactStoreUnavailable,
    ArtifactUnavailable,
    EmbeddingContract,
    identify_chunk_text,
    identify_embedding_input,
)
from kb.runtime.storage import macos_storage_layout
from kb.store import chunk_artifacts as implementation
from kb.store.chunk_artifacts import ChunkArtifactStore


def test_chunk_identity_preserves_exact_unicode_and_newlines() -> None:
    text = "alpha\r\nλ\n\n"
    payload = text.encode("utf-8")

    artifact = identify_chunk_text(text)

    assert artifact.artifact_id == sha256(CHUNK_TEXT_DOMAIN + payload).hexdigest()
    assert artifact.utf8_bytes == len(payload)
    assert artifact.characters == len(text)
    assert artifact.lines == 4
    assert identify_chunk_text("alpha\nλ\n\n").artifact_id != artifact.artifact_id


def test_chunk_envelope_uses_explicit_network_byte_order() -> None:
    assert implementation._ENVELOPE_HEADER.format.startswith(">")


def test_embedding_input_identity_binds_exact_text_and_model_contract() -> None:
    text = "def example():\r\n    return 'λ'\n"
    baseline = identify_embedding_input(text)
    repeated = identify_embedding_input(text)
    alternate = identify_embedding_input(
        text,
        contract=EmbeddingContract(
            provider="openai",
            model="future-model",
            dimensions=1_536,
            contract_version=1,
        ),
    )

    assert baseline == repeated
    assert baseline.cache_key != alternate.cache_key
    assert identify_embedding_input(text.replace("\r\n", "\n")).cache_key != baseline.cache_key
    assert baseline.utf8_bytes == len(text.encode("utf-8"))


def test_artifact_store_round_trips_privately_without_replacing_existing_bytes(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    text = "first\r\nsecond λ\n"

    artifact = store.put_exact_text(text)
    path = _artifact_path(layout.artifacts, artifact.artifact_id)
    first_status = path.stat()
    repeated = store.put_exact_text(text)
    second_status = path.stat()

    assert repeated == artifact
    assert store.read_verified(artifact.artifact_id) == text
    assert first_status.st_ino == second_status.st_ino
    assert first_status.st_mtime_ns == second_status.st_mtime_ns
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert not list(_install_directory(layout.artifacts, artifact.artifact_id).glob("install-*"))


def test_artifact_store_round_trips_empty_text_with_zero_lines(tmp_path: Path) -> None:
    store = ChunkArtifactStore(macos_storage_layout(home=tmp_path))

    artifact = store.put_exact_text("")

    assert artifact.utf8_bytes == 0
    assert artifact.characters == 0
    assert artifact.lines == 0
    assert store.read_verified(artifact.artifact_id) == ""


def test_concurrent_identical_writers_converge_on_one_verified_artifact(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    text = "same exact chunk\n" * 100

    with ThreadPoolExecutor(max_workers=12) as executor:
        artifacts = list(executor.map(store.put_exact_text, [text] * 24))

    assert len({artifact.artifact_id for artifact in artifacts}) == 1
    artifact = artifacts[0]
    path = _artifact_path(layout.artifacts, artifact.artifact_id)
    assert path.stat().st_nlink == 1
    assert store.read_verified(artifact.artifact_id) == text
    assert list(_install_directory(layout.artifacts, artifact.artifact_id).glob("install-*")) == []


def test_failed_install_removes_only_its_private_temporary_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    artifact = identify_chunk_text("not installed")

    def fail_link(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected install failure")

    monkeypatch.setattr(os, "link", fail_link)

    with pytest.raises(ArtifactStoreUnavailable, match="could not be installed safely"):
        store.put_exact_text("not installed")

    path = _artifact_path(layout.artifacts, artifact.artifact_id)
    assert not path.exists()
    assert not list(_install_directory(layout.artifacts, artifact.artifact_id).glob("install-*"))


@pytest.mark.parametrize("mutation", ["magic", "count", "digest", "truncate", "payload"])
def test_artifact_store_rejects_corrupt_envelopes(tmp_path: Path, mutation: str) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    artifact = store.put_exact_text("verified text λ\n")
    path = _artifact_path(layout.artifacts, artifact.artifact_id)
    envelope = bytearray(path.read_bytes())

    if mutation == "magic":
        envelope[0] ^= 1
    elif mutation == "count":
        envelope[30] ^= 1
    elif mutation == "digest":
        envelope[-len("verified text λ\n".encode()) - 1] ^= 1
    elif mutation == "truncate":
        envelope.pop()
    else:
        envelope[-1] ^= 1
    path.write_bytes(envelope)

    with pytest.raises(ArtifactCorrupt, match="chunk artifact is corrupt"):
        store.read_verified(artifact.artifact_id)


def test_artifact_store_rejects_invalid_utf8_even_with_matching_envelope_digest(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    layout.ensure_private_directories()
    payload = b"invalid-utf8:\xff"
    artifact_id = sha256(CHUNK_TEXT_DOMAIN + payload).hexdigest()
    path = _artifact_path(layout.artifacts, artifact_id)
    path.parent.mkdir(parents=True, mode=0o700)
    path.parent.parent.chmod(0o700)
    path.parent.chmod(0o700)
    envelope = (
        implementation._ENVELOPE_HEADER.pack(
            implementation._ENVELOPE_MAGIC,
            len(payload),
            len(payload),
            1,
            bytes.fromhex(artifact_id),
        )
        + payload
    )
    path.write_bytes(envelope)
    path.chmod(0o600)

    with pytest.raises(ArtifactCorrupt, match="chunk artifact is corrupt"):
        ChunkArtifactStore(layout).read_verified(artifact_id)


def test_artifact_store_rejects_symlinked_or_hardlinked_payloads(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    first = store.put_exact_text("first")
    second = store.put_exact_text("second")
    first_path = _artifact_path(layout.artifacts, first.artifact_id)
    second_path = _artifact_path(layout.artifacts, second.artifact_id)
    outside = tmp_path / "outside"
    outside.write_text("outside")
    first_path.unlink()
    first_path.symlink_to(outside)
    hardlink = second_path.with_name("hardlink")
    os.link(second_path, hardlink)

    with pytest.raises(ArtifactCorrupt):
        store.read_verified(first.artifact_id)
    with pytest.raises(ArtifactCorrupt):
        store.read_verified(second.artifact_id)


def test_artifact_store_rejects_symlinked_format_directory_without_traversal(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    layout.ensure_private_directories()
    outside = tmp_path / "outside"
    outside.mkdir()
    (layout.artifacts / "dolphin-chunk-text-v1").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ArtifactCorrupt, match="storage is corrupt"):
        ChunkArtifactStore(layout).put_exact_text("must stay contained")

    assert list(outside.iterdir()) == []


def test_artifact_store_rejects_unsafe_payload_permissions_without_repair(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    artifact = store.put_exact_text("private")
    path = _artifact_path(layout.artifacts, artifact.artifact_id)
    path.chmod(0o644)

    with pytest.raises(ArtifactCorrupt):
        store.read_verified(artifact.artifact_id)

    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_artifact_store_rejects_special_files_without_blocking(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    artifact = store.put_exact_text("will become a fifo")
    path = _artifact_path(layout.artifacts, artifact.artifact_id)
    path.unlink()
    os.mkfifo(path, mode=0o600)

    with pytest.raises(ArtifactCorrupt):
        store.read_verified(artifact.artifact_id)


def test_artifact_store_prunes_only_a_bounded_batch_of_stale_install_files(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    artifact = store.put_exact_text("shard seed")
    install_directory = _install_directory(layout.artifacts, artifact.artifact_id)
    for index in range(40):
        orphan = install_directory / f"install-{index:032x}"
        orphan.write_bytes(b"abandoned private installer")
        orphan.chmod(0o600)
        os.utime(orphan, ns=(1, 1))

    store.put_exact_text(_different_text_in_shard(artifact.artifact_id[:2], excluded="shard seed"))

    assert len(list(install_directory.glob("install-*"))) == 8


def test_artifact_store_preserves_fresh_install_files(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    artifact = store.put_exact_text("fresh shard seed")
    install_directory = _install_directory(layout.artifacts, artifact.artifact_id)
    active = install_directory / f"install-{'a' * 32}"
    active.write_bytes(b"active private installer")
    active.chmod(0o600)

    store.put_exact_text(_different_text_in_shard(artifact.artifact_id[:2], excluded="fresh shard seed"))

    assert active.is_file()


def test_artifact_store_refuses_unsafe_stale_installer_entries(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    artifact = store.put_exact_text("unsafe shard seed")
    install_directory = _install_directory(layout.artifacts, artifact.artifact_id)
    outside = tmp_path / "outside-installer"
    outside.write_text("must remain untouched")
    unsafe = install_directory / f"install-{'b' * 32}"
    unsafe.symlink_to(outside)
    os.utime(unsafe, ns=(1, 1), follow_symlinks=False)

    with pytest.raises(ArtifactCorrupt, match="installer storage is corrupt"):
        store.put_exact_text(_different_text_in_shard(artifact.artifact_id[:2], excluded="unsafe shard seed"))

    assert outside.read_text() == "must remain untouched"
    assert unsafe.is_symlink()


def test_artifact_set_is_order_independent_deduplicated_and_fully_verified(tmp_path: Path) -> None:
    store = ChunkArtifactStore(macos_storage_layout(home=tmp_path))
    first = store.put_exact_text("first")
    second = store.put_exact_text("second λ")

    verified = store.verify_artifact_set([second.artifact_id, first.artifact_id, second.artifact_id])
    reordered = store.verify_artifact_set([first.artifact_id, second.artifact_id])

    assert verified == reordered
    assert verified.artifact_count == 2
    assert verified.total_utf8_bytes == first.utf8_bytes + second.utf8_bytes
    assert store.verify_artifact_set([first.artifact_id]).set_digest != verified.set_digest


def test_artifact_set_fails_closed_for_missing_or_corrupt_artifacts(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)
    artifact = store.put_exact_text("manifest member")
    path = _artifact_path(layout.artifacts, artifact.artifact_id)
    path.write_bytes(path.read_bytes()[:-1])

    with pytest.raises(ArtifactCorrupt):
        store.verify_artifact_set([artifact.artifact_id])
    with pytest.raises(ArtifactUnavailable):
        store.verify_artifact_set(["0" * 64])


def test_artifact_inputs_are_strict_and_bounded_without_creating_storage(tmp_path: Path) -> None:
    layout = macos_storage_layout(home=tmp_path)
    store = ChunkArtifactStore(layout)

    with pytest.raises(ArtifactInputInvalid):
        store.read_verified("A" * 64)
    with pytest.raises(ArtifactInputInvalid):
        store.put_exact_text("\ud800")
    with pytest.raises(ArtifactInputInvalid, match="too large"):
        store.put_exact_text("a" * (MAX_CHUNK_TEXT_UTF8_BYTES + 1))

    assert not (tmp_path / "Library").exists()


def _artifact_path(artifacts_root: Path, artifact_id: str) -> Path:
    return artifacts_root / "dolphin-chunk-text-v1" / artifact_id[:2] / artifact_id[2:]


def _install_directory(artifacts_root: Path, artifact_id: str) -> Path:
    return _artifact_path(artifacts_root, artifact_id).parent / ".install"


def _different_text_in_shard(shard: str, *, excluded: str) -> str:
    for index in range(10_000):
        candidate = f"same shard candidate {index}"
        if candidate != excluded and identify_chunk_text(candidate).artifact_id.startswith(shard):
            return candidate
    raise AssertionError("failed to find deterministic same-shard fixture")
