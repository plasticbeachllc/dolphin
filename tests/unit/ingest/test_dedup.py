"""Unit tests for content-based deduplication."""

from pathlib import Path
from unittest.mock import patch

from kb.chunkers.types import Chunk
from kb.hashing import hash_text
from kb.ingest.dedup import ChunkDeduplicator
from kb.store.sqlite_meta import SQLiteMetadataStore


class TestChunkDeduplication:
    """Test content-based deduplication functionality."""

    def test_chunk_deduplication_basic(self, temp_db_path):
        """Test basic chunk deduplication with unchanged chunk detection."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_root = Path("/mock/repo")
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

        def _make_chunk(text: str, start: int) -> Chunk:
            return Chunk(text=text, start_line=start, end_line=start, token_count=len(text))

        chunk_new = _make_chunk("print('hi')\n", 1)
        chunk_new.text_hash = hash_text(chunk_new.text)
        chunk_without_hash = _make_chunk("print('bye')\n", 2)

        # First run: both chunks should be marked as changed
        changed, unchanged = dedup.filter_unchanged_chunks(
            [chunk_new, chunk_without_hash], repo_id, file_id, embed_model
        )
        assert len(changed) == 2
        assert len(unchanged) == 0
        # The chunk without hash should have its hash computed
        assert chunk_without_hash.text_hash == hash_text(chunk_without_hash.text)

    def test_chunk_deduplication_with_persisted_hash(self, temp_db_path):
        """Test deduplication with previously persisted chunk hashes."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_root = Path("/mock/repo")
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

        def _make_chunk(text: str, start: int) -> Chunk:
            return Chunk(text=text, start_line=start, end_line=start, token_count=len(text))

        chunk_new = _make_chunk("print('hi')\n", 1)
        chunk_new.text_hash = hash_text(chunk_new.text)
        chunk_without_hash = _make_chunk("print('bye')\n", 2)

        # Persist one chunk hash and ensure it is recognized as unchanged
        store.upsert_chunk_content_row(repo_id, file_id, chunk_new.text_hash, embed_model)
        changed, unchanged = dedup.filter_unchanged_chunks(
            [chunk_new, chunk_without_hash], repo_id, file_id, embed_model
        )
        assert unchanged == [chunk_new]
        assert chunk_without_hash in changed

    def test_hash_computation_failure_propagates(self, temp_db_path):
        """Test that store errors propagate instead of silently treating all chunks as changed.

        Previously the deduplicator swallowed errors and returned an empty hash set,
        which caused every chunk to look changed and could produce duplicate vectors.
        Now errors propagate so the caller (pipeline) can skip the file entirely and
        increment its error counter.
        """
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_root = Path("/mock/repo")
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

        def _make_chunk(text: str, start: int) -> Chunk:
            return Chunk(text=text, start_line=start, end_line=start, token_count=len(text))

        chunk_new = _make_chunk("print('hi')\n", 1)
        chunk_new.text_hash = hash_text(chunk_new.text)

        # Simulate store failure; exception must propagate so callers skip the file
        with patch.object(store, "get_existing_content_hashes_for_file") as mock_method:
            mock_method.side_effect = RuntimeError("boom")

            import pytest as _pytest

            with _pytest.raises(RuntimeError, match="boom"):
                dedup.filter_unchanged_chunks([chunk_new], repo_id, file_id, embed_model)

    def test_moved_chunk_handling(self, temp_db_path):
        """Test that moved chunks are properly handled (treated as changed)."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_root = Path("/mock/repo")
        store.record_repo("sample", repo_root)
        repo = store.get_repo_by_name("sample")
        assert repo is not None
        repo_id = int(repo["id"])

        # Create two files
        file1_id = store.upsert_file(
            repo_id,
            path="src/file1.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=42,
        )
        file2_id = store.upsert_file(
            repo_id,
            path="src/file2.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=42,
        )

        dedup = ChunkDeduplicator(store)
        embed_model = "small"

        def _make_chunk(text: str, start: int) -> Chunk:
            return Chunk(text=text, start_line=start, end_line=start, token_count=len(text))

        chunk = _make_chunk("print('moved')\n", 1)
        chunk.text_hash = hash_text(chunk.text)

        # Persist the chunk in file1
        store.upsert_chunk_content_row(repo_id, file1_id, chunk.text_hash, embed_model)

        # Now check the same chunk in file2 - should be treated as changed (moved)
        changed, unchanged = dedup.filter_unchanged_chunks([chunk], repo_id, file2_id, embed_model)

        # The chunk is the same content but in a different file, so it should be changed
        assert len(changed) == 1
        assert len(unchanged) == 0

    def test_multiple_embedding_models(self, temp_db_path):
        """Test deduplication with different embedding models."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_root = Path("/mock/repo")
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

        def _make_chunk(text: str, start: int) -> Chunk:
            return Chunk(text=text, start_line=start, end_line=start, token_count=len(text))

        chunk = _make_chunk("print('hi')\n", 1)
        chunk.text_hash = hash_text(chunk.text)

        # Persist with small model
        store.upsert_chunk_content_row(repo_id, file_id, chunk.text_hash, "small")

        # Check with small model - should be unchanged
        changed, unchanged = dedup.filter_unchanged_chunks([chunk], repo_id, file_id, "small")
        assert unchanged == [chunk]
        assert len(changed) == 0

        # Check with large model - should be changed (different embedding model)
        changed, unchanged = dedup.filter_unchanged_chunks([chunk], repo_id, file_id, "large")
        assert len(unchanged) == 0
        assert len(changed) == 1

    def test_chunk_without_text_hash_treated_as_changed(self, temp_db_path):
        """Chunk with text_hash = None always lands in changed, never unchanged."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_root = Path("/mock/repo")
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

        # Create chunk with no text_hash set
        chunk = Chunk(text="print('no hash')\n", start_line=1, end_line=1, token_count=5)
        assert getattr(chunk, "text_hash", None) is None

        changed, unchanged = dedup.filter_unchanged_chunks([chunk], repo_id, file_id, "small")

        # The chunk had no hash, so it was computed and the chunk is treated as changed
        assert len(changed) == 1
        assert len(unchanged) == 0
        # Hash should now be set
        assert chunk.text_hash is not None

    def test_mixed_hashed_and_unhashed_chunks(self, temp_db_path):
        """2 chunks: one with stored hash (unchanged), one without hash (changed)."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_root = Path("/mock/repo")
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

        # Chunk with a pre-computed hash, persisted in the store
        chunk_hashed = Chunk(text="print('hashed')\n", start_line=1, end_line=1, token_count=5)
        chunk_hashed.text_hash = hash_text(chunk_hashed.text)
        store.upsert_chunk_content_row(repo_id, file_id, chunk_hashed.text_hash, "small")

        # Chunk without a hash (will be computed, treated as changed since not in store)
        chunk_unhashed = Chunk(text="print('new content')\n", start_line=2, end_line=2, token_count=5)

        changed, unchanged = dedup.filter_unchanged_chunks([chunk_hashed, chunk_unhashed], repo_id, file_id, "small")

        assert chunk_hashed in unchanged
        assert chunk_unhashed in changed
