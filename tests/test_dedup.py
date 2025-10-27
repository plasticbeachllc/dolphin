from __future__ import annotations

import tempfile
from pathlib import Path

from pb_kb.chunkers.types import Chunk
from pb_kb.hashing import hash_text
from pb_kb.ingest.dedup import ChunkDeduplicator
from pb_kb.store.sqlite_meta import SQLiteMetadataStore


def _make_chunk(text: str, start: int) -> Chunk:
    return Chunk(text=text, start_line=start, end_line=start, token_count=len(text))


def run_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "kb.db"
        store = SQLiteMetadataStore(db_path)
        store.initialize()

        repo_root = Path(td) / "repo"
        repo_root.mkdir()
        store.record_repo("sample", repo_root)
        repo = store.get_repo_by_name("sample")
        assert repo is not None
        repo_id = int(repo["id"])
        file_id = store.upsert_file(
            repo_id,
            path="src/main.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=42,
        )

        dedup = ChunkDeduplicator(store)
        embed_model = "small"

        chunk_new = _make_chunk("print('hi')\n", 1)
        chunk_new.text_hash = hash_text(chunk_new.text)
        chunk_without_hash = _make_chunk("print('bye')\n", 2)

        changed, unchanged = dedup.filter_unchanged_chunks(
            [chunk_new, chunk_without_hash], repo_id, file_id, embed_model
        )
        assert len(changed) == 2
        assert len(unchanged) == 0
        assert chunk_without_hash.text_hash == hash_text(chunk_without_hash.text)

        # Persist one chunk hash and ensure it is recognized as unchanged
        store.upsert_chunk_content_row(repo_id, file_id, chunk_new.text_hash, embed_model)
        changed, unchanged = dedup.filter_unchanged_chunks(
            [chunk_new, chunk_without_hash], repo_id, file_id, embed_model
        )
        assert unchanged == [chunk_new]
        assert chunk_without_hash in changed

        # Simulate store failure and ensure fallback treats everything as changed
        original = store.get_existing_content_hashes_for_file

        def boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        store.get_existing_content_hashes_for_file = boom  # type: ignore[assignment]
        try:
            changed, unchanged = dedup.filter_unchanged_chunks(
                [chunk_new], repo_id, file_id, embed_model
            )
        finally:
            store.get_existing_content_hashes_for_file = original  # type: ignore[assignment]
        assert len(changed) == 1 and len(unchanged) == 0

    print("ChunkDeduplicator tests passed")
