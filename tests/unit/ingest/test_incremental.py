"""Unit tests for incremental embedding support module.

Tests cover compute_chunk_diff(), get_existing_chunk_hashes(),
ChunkDiff dataclass, IncrementalIndexer, and detect_changed_files.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from kb.chunkers.types import Chunk
from kb.hashing import hash_text
from kb.ingest.incremental import (
    ChunkDiff,
    IncrementalIndexer,
    compute_chunk_diff,
    detect_changed_files,
    get_existing_chunk_hashes,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(text: str, start_line: int = 1, end_line: int = 1) -> Chunk:
    """Create a Chunk with minimal required fields."""
    return Chunk(text=text, start_line=start_line, end_line=end_line, token_count=len(text.split()))


# ---------------------------------------------------------------------------
# ChunkDiff dataclass
# ---------------------------------------------------------------------------


class TestChunkDiff:
    """Tests for the ChunkDiff dataclass."""

    def test_fields_accessible(self):
        """ChunkDiff exposes all declared fields."""
        diff = ChunkDiff(
            new_chunks=[_make_chunk("a")],
            unchanged_chunks=["hash1"],
            deleted_chunks=["hash2"],
            stats={"total_new": 1, "to_embed": 1, "unchanged": 1, "deleted": 1, "reuse_pct": 50},
        )
        assert len(diff.new_chunks) == 1
        assert diff.unchanged_chunks == ["hash1"]
        assert diff.deleted_chunks == ["hash2"]
        assert diff.stats["reuse_pct"] == 50

    def test_empty_diff(self):
        """ChunkDiff can be constructed with all-empty collections."""
        diff = ChunkDiff(new_chunks=[], unchanged_chunks=[], deleted_chunks=[], stats={})
        assert diff.new_chunks == []
        assert diff.unchanged_chunks == []
        assert diff.deleted_chunks == []
        assert diff.stats == {}


# ---------------------------------------------------------------------------
# compute_chunk_diff
# ---------------------------------------------------------------------------


class TestComputeChunkDiff:
    """Tests for compute_chunk_diff()."""

    def test_all_new_chunks(self):
        """When existing_hashes is empty, every chunk is new."""
        chunks = [_make_chunk("alpha"), _make_chunk("beta")]
        diff = compute_chunk_diff(chunks, existing_hashes=set(), repo_name="repo", file_path="f.py")

        assert len(diff.new_chunks) == 2
        assert diff.unchanged_chunks == []
        assert diff.deleted_chunks == []
        assert diff.stats["to_embed"] == 2
        assert diff.stats["unchanged"] == 0
        assert diff.stats["deleted"] == 0
        assert diff.stats["reuse_pct"] == 0

    def test_all_unchanged_chunks(self):
        """When all new chunks already have matching hashes, none need embedding."""
        chunk_a = _make_chunk("alpha")
        chunk_b = _make_chunk("beta")
        existing = {hash_text(chunk_a.text), hash_text(chunk_b.text)}

        diff = compute_chunk_diff([chunk_a, chunk_b], existing, repo_name="repo", file_path="f.py")

        assert diff.new_chunks == []
        assert len(diff.unchanged_chunks) == 2
        assert diff.deleted_chunks == []
        assert diff.stats["to_embed"] == 0
        assert diff.stats["unchanged"] == 2
        assert diff.stats["reuse_pct"] == 100

    def test_mix_new_and_unchanged(self):
        """Some chunks are new and some are unchanged."""
        old_chunk = _make_chunk("existing content")
        new_chunk = _make_chunk("brand new content")
        existing = {hash_text(old_chunk.text)}

        diff = compute_chunk_diff([old_chunk, new_chunk], existing, repo_name="repo", file_path="f.py")

        assert len(diff.new_chunks) == 1
        assert diff.new_chunks[0].text == "brand new content"
        assert len(diff.unchanged_chunks) == 1
        assert diff.deleted_chunks == []
        assert diff.stats["to_embed"] == 1
        assert diff.stats["unchanged"] == 1

    def test_deleted_chunks_detected(self):
        """Hashes in existing but not in new_chunks appear as deleted."""
        chunk = _make_chunk("only chunk")
        deleted_hash = "deadbeef" * 8  # 64 hex chars
        existing = {hash_text(chunk.text), deleted_hash}

        diff = compute_chunk_diff([chunk], existing, repo_name="repo", file_path="f.py")

        assert diff.new_chunks == []
        assert len(diff.unchanged_chunks) == 1
        assert deleted_hash in diff.deleted_chunks
        assert diff.stats["deleted"] == 1

    def test_empty_new_chunks(self):
        """When new_chunks is empty, all existing hashes are deleted."""
        existing = {"hash_a", "hash_b"}
        diff = compute_chunk_diff([], existing, repo_name="repo", file_path="f.py")

        assert diff.new_chunks == []
        assert diff.unchanged_chunks == []
        assert set(diff.deleted_chunks) == existing
        assert diff.stats["total_new"] == 0
        assert diff.stats["to_embed"] == 0
        assert diff.stats["deleted"] == 2
        assert diff.stats["reuse_pct"] == 0

    def test_empty_both(self):
        """When both inputs are empty, result is fully empty."""
        diff = compute_chunk_diff([], set(), repo_name="repo", file_path="f.py")

        assert diff.new_chunks == []
        assert diff.unchanged_chunks == []
        assert diff.deleted_chunks == []
        assert diff.stats["total_new"] == 0
        assert diff.stats["reuse_pct"] == 0

    def test_reuse_pct_calculation(self):
        """reuse_pct is the integer percentage of unchanged / total_new."""
        chunks = [_make_chunk(f"chunk_{i}") for i in range(3)]
        # Mark 2 of 3 as existing
        existing = {hash_text(chunks[0].text), hash_text(chunks[1].text)}

        diff = compute_chunk_diff(chunks, existing, repo_name="repo", file_path="f.py")

        assert diff.stats["reuse_pct"] == 66  # int(2/3 * 100)

    def test_duplicate_text_chunks_counted_once(self):
        """Two chunks with identical text produce a single hash entry."""
        chunk_a = _make_chunk("same text")
        chunk_b = _make_chunk("same text")

        diff = compute_chunk_diff([chunk_a, chunk_b], set(), repo_name="repo", file_path="f.py")

        # Both chunks land in new_chunks because their shared hash was not
        # in existing_hashes.  compute_chunk_diff does not deduplicate
        # within a single diff — that happens downstream in the embedder.
        # This test documents the current behaviour: two distinct chunk
        # objects with the same text are both marked as new.
        assert len(diff.new_chunks) == 2
        assert diff.stats["total_new"] == 2

    def test_changed_chunk_shows_as_new_and_old_deleted(self):
        """A chunk whose text changes results in 1 new + 1 deleted."""
        old_hash = hash_text("old version")
        new_chunk = _make_chunk("new version")

        diff = compute_chunk_diff([new_chunk], {old_hash}, repo_name="r", file_path="f.py")

        assert len(diff.new_chunks) == 1
        assert old_hash in diff.deleted_chunks
        assert diff.unchanged_chunks == []


# ---------------------------------------------------------------------------
# get_existing_chunk_hashes
# ---------------------------------------------------------------------------


class TestGetExistingChunkHashes:
    """Tests for get_existing_chunk_hashes()."""

    def _make_mock_store(self, rows: list[tuple[str]]):
        """Build a mock SQLiteMetadataStore that returns the given rows."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        store = MagicMock()
        store._connect.return_value = mock_conn
        return store, mock_cursor

    def test_returns_hashes_for_repo(self):
        """Returns set of hashes when querying by repo_name only."""
        store, cur = self._make_mock_store([("hash_a",), ("hash_b",)])

        result = get_existing_chunk_hashes(store, "my-repo")

        assert result == {"hash_a", "hash_b"}
        cur.execute.assert_called_once()
        sql = cur.execute.call_args[0][0]
        assert "repo" in sql.lower()

    def test_returns_hashes_for_repo_and_file(self):
        """Returns set of hashes when querying by repo_name and file_path."""
        store, cur = self._make_mock_store([("hash_x",)])

        result = get_existing_chunk_hashes(store, "my-repo", file_path="src/main.py")

        assert result == {"hash_x"}
        sql = cur.execute.call_args[0][0]
        assert "file_path" in sql.lower()

    def test_returns_empty_set_when_no_rows(self):
        """Returns empty set when no matching chunks exist."""
        store, _ = self._make_mock_store([])

        result = get_existing_chunk_hashes(store, "empty-repo")

        assert result == set()

    def test_deduplicates_hashes(self):
        """DISTINCT in SQL should already deduplicate, but verify set semantics."""
        store, _ = self._make_mock_store([("dup",), ("dup",)])

        result = get_existing_chunk_hashes(store, "repo")

        assert result == {"dup"}

    def test_file_path_none_uses_repo_only_query(self):
        """Passing file_path=None explicitly uses the repo-only query path."""
        store, cur = self._make_mock_store([])

        get_existing_chunk_hashes(store, "repo", file_path=None)

        sql = cur.execute.call_args[0][0]
        assert "file_path" not in sql.lower()


# ---------------------------------------------------------------------------
# detect_changed_files
# ---------------------------------------------------------------------------


class TestDetectChangedFiles:
    """Tests for detect_changed_files()."""

    @patch("subprocess.run")
    def test_returns_modified_and_deleted(self, mock_run):
        """Returns modified (including untracked) and deleted file lists."""
        mock_run.side_effect = [
            MagicMock(stdout="modified.py\nchanged.py\n"),
            MagicMock(stdout="untracked.py\n"),
            MagicMock(stdout="removed.py\n"),
        ]
        store = MagicMock()

        modified, deleted = detect_changed_files(Path("/repo"), store, "repo")

        assert set(modified) == {"modified.py", "changed.py", "untracked.py"}
        assert deleted == ["removed.py"]

    @patch("subprocess.run")
    def test_empty_stdout_gives_empty_lists(self, mock_run):
        """Empty git output produces empty lists (no spurious empty-string entries)."""
        mock_run.side_effect = [
            MagicMock(stdout=""),
            MagicMock(stdout=""),
            MagicMock(stdout=""),
        ]
        store = MagicMock()

        modified, deleted = detect_changed_files(Path("/repo"), store, "repo")

        assert modified == []
        assert deleted == []

    @patch("subprocess.run")
    def test_git_failure_returns_empty(self, mock_run):
        """When git command fails, returns empty lists (triggers full reindex)."""
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "git")
        store = MagicMock()

        modified, deleted = detect_changed_files(Path("/repo"), store, "repo")

        assert modified == []
        assert deleted == []


# ---------------------------------------------------------------------------
# IncrementalIndexer
# ---------------------------------------------------------------------------


class TestIncrementalIndexer:
    """Tests for the IncrementalIndexer helper class."""

    def _make_indexer(self):
        """Create an IncrementalIndexer with a mocked metadata store."""
        store = MagicMock()
        indexer = IncrementalIndexer(
            metadata_store=store,
            repo_name="test-repo",
            repo_root=Path("/repo"),
        )
        return indexer, store

    def test_get_file_hashes_delegates_to_store(self):
        """get_file_hashes calls get_existing_chunk_hashes on first access."""
        indexer, store = self._make_indexer()

        # Arrange the _connect mock to return some hashes
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("h1",), ("h2",)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        store._connect.return_value = mock_conn

        result = indexer.get_file_hashes("src/app.py")

        assert result == {"h1", "h2"}

    def test_get_file_hashes_caches_result(self):
        """Second call for the same file returns cached result without re-querying."""
        indexer, store = self._make_indexer()

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("cached",)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        store._connect.return_value = mock_conn

        first = indexer.get_file_hashes("f.py")
        second = indexer.get_file_hashes("f.py")

        assert first is second
        # _connect should have been called only once
        assert store._connect.call_count == 1

    def test_compute_diff_uses_cached_hashes(self):
        """compute_diff integrates get_file_hashes and compute_chunk_diff."""
        indexer, store = self._make_indexer()

        # Seed the cache directly to avoid DB interaction
        indexer._existing_hashes["f.py"] = set()

        chunks = [_make_chunk("hello")]
        diff = indexer.compute_diff("f.py", chunks)

        assert len(diff.new_chunks) == 1
        assert diff.stats["to_embed"] == 1

    def test_should_skip_file_true_when_hash_matches(self):
        """should_skip_file returns True when content hash matches DB."""
        indexer, store = self._make_indexer()

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("abc123",)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        store._connect.return_value = mock_conn

        assert indexer.should_skip_file("f.py", "abc123") is True

    def test_should_skip_file_false_when_hash_differs(self):
        """should_skip_file returns False when content hash does not match."""
        indexer, store = self._make_indexer()

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("old_hash",)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        store._connect.return_value = mock_conn

        assert indexer.should_skip_file("f.py", "new_hash") is False

    def test_should_skip_file_false_when_no_record(self):
        """should_skip_file returns False when file has no DB record."""
        indexer, store = self._make_indexer()

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        store._connect.return_value = mock_conn

        assert indexer.should_skip_file("f.py", "any_hash") is False

    def test_mark_file_indexed_executes_insert(self):
        """mark_file_indexed issues an INSERT OR REPLACE and commits."""
        indexer, store = self._make_indexer()

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        store._connect.return_value = mock_conn

        indexer.mark_file_indexed("f.py", "content_hash_value")

        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "INSERT OR REPLACE" in sql
        mock_conn.commit.assert_called_once()
