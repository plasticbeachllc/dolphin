"""Unit tests for ingestion helper functions."""

import pytest
import subprocess
from pathlib import Path
from dataclasses import dataclass
from kb.ingest._helpers import (
    build_desired_map,
    git_changed_files_modified_added,
    git_changed_files_deleted,
    get_all_tracked_files,
    representative_text_for_hash,
)


# Simple test chunk class
@dataclass
class ChunkTestData:
    """Test chunk for testing."""
    text: str
    text_hash: str
    start_line: int
    end_line: int
    symbol_kind: str = None
    symbol_name: str = None
    symbol_path: str = None
    heading_h1: str = None
    heading_h2: str = None
    heading_h3: str = None


class TestBuildDesiredMap:
    """Test build_desired_map function."""

    def test_build_desired_map_empty_chunks(self):
        """Test with empty chunk list."""
        result = build_desired_map([])
        assert result == {}

    def test_build_desired_map_single_chunk(self):
        """Test with single chunk."""
        chunk = ChunkTestData(
            text="def foo(): pass",
            text_hash="hash123",
            start_line=1,
            end_line=5,
            symbol_kind="function",
            symbol_name="foo",
            symbol_path="module.foo",
        )
        result = build_desired_map([chunk])

        assert "hash123" in result
        assert len(result["hash123"]) == 1
        occurrence = result["hash123"][0]
        assert occurrence["start_line"] == 1
        assert occurrence["end_line"] == 5
        assert occurrence["symbol_kind"] == "function"
        assert occurrence["symbol_name"] == "foo"
        assert occurrence["symbol_path"] == "module.foo"

    def test_build_desired_map_multiple_chunks_same_hash(self):
        """Test multiple chunks with same hash (duplicates)."""
        chunk1 = ChunkTestData(
            text="common code",
            text_hash="hash_dup",
            start_line=1,
            end_line=3,
            symbol_kind="function",
            symbol_name="func1",
        )
        chunk2 = ChunkTestData(
            text="common code",
            text_hash="hash_dup",
            start_line=10,
            end_line=12,
            symbol_kind="function",
            symbol_name="func2",
        )
        result = build_desired_map([chunk1, chunk2])

        assert "hash_dup" in result
        assert len(result["hash_dup"]) == 2
        assert result["hash_dup"][0]["start_line"] == 1
        assert result["hash_dup"][1]["start_line"] == 10

    def test_build_desired_map_multiple_different_hashes(self):
        """Test multiple chunks with different hashes."""
        chunk1 = ChunkTestData(
            text="code1", text_hash="hash1", start_line=1, end_line=2
        )
        chunk2 = ChunkTestData(
            text="code2", text_hash="hash2", start_line=5, end_line=6
        )
        result = build_desired_map([chunk1, chunk2])

        assert "hash1" in result
        assert "hash2" in result
        assert len(result["hash1"]) == 1
        assert len(result["hash2"]) == 1

    def test_build_desired_map_with_headings(self):
        """Test with markdown headings."""
        chunk = ChunkTestData(
            text="# Title\nContent",
            text_hash="md_hash",
            start_line=1,
            end_line=10,
            heading_h1="Title",
            heading_h2="Subtitle",
            heading_h3="Section",
        )
        result = build_desired_map([chunk])

        occurrence = result["md_hash"][0]
        assert occurrence["heading_h1"] == "Title"
        assert occurrence["heading_h2"] == "Subtitle"
        assert occurrence["heading_h3"] == "Section"

    def test_build_desired_map_missing_text_hash(self):
        """Test chunk without text_hash is skipped."""
        @dataclass
        class ChunkNoHash:
            text: str
            start_line: int
            end_line: int

        chunk = ChunkNoHash(text="code", start_line=1, end_line=2)
        result = build_desired_map([chunk])

        assert result == {}

    def test_build_desired_map_none_text_hash(self):
        """Test chunk with None text_hash is skipped."""
        chunk = ChunkTestData(
            text="code", text_hash=None, start_line=1, end_line=2
        )
        result = build_desired_map([chunk])

        assert result == {}

    def test_build_desired_map_optional_fields_none(self):
        """Test that None optional fields are included."""
        chunk = ChunkTestData(
            text="code",
            text_hash="hash1",
            start_line=1,
            end_line=2,
            symbol_kind=None,
            symbol_name=None,
            symbol_path=None,
        )
        result = build_desired_map([chunk])

        occurrence = result["hash1"][0]
        assert occurrence["symbol_kind"] is None
        assert occurrence["symbol_name"] is None
        assert occurrence["symbol_path"] is None


class TestGitHelpers:
    """Test git helper functions."""

    def test_git_changed_files_modified_added(self, git_repo):
        """Test getting modified and added files."""
        # Create initial commit
        file1 = git_repo / "file1.txt"
        file1.write_text("initial")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "Initial"],
            check=True,
        )
        initial_commit = subprocess.run(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Modify file and add new file
        file1.write_text("modified")
        file2 = git_repo / "file2.txt"
        file2.write_text("new")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "Second"],
            check=True,
        )

        # Get changed files
        changed = git_changed_files_modified_added(
            git_repo, initial_commit, "HEAD"
        )

        assert "file1.txt" in changed
        assert "file2.txt" in changed
        assert len(changed) == 2

    def test_git_changed_files_deleted(self, git_repo):
        """Test getting deleted files."""
        # Create initial commit with two files
        file1 = git_repo / "file1.txt"
        file2 = git_repo / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "Initial"],
            check=True,
        )
        initial_commit = subprocess.run(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Delete one file
        file1.unlink()
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "Delete file1"],
            check=True,
        )

        # Get deleted files
        deleted = git_changed_files_deleted(git_repo, initial_commit, "HEAD")

        assert "file1.txt" in deleted
        assert "file2.txt" not in deleted
        assert len(deleted) == 1

    def test_get_all_tracked_files(self, git_repo):
        """Test getting all tracked files."""
        # Create some files and commit
        (git_repo / "file1.txt").write_text("content1")
        (git_repo / "file2.py").write_text("content2")
        subdir = git_repo / "subdir"
        subdir.mkdir()
        (subdir / "file3.md").write_text("content3")

        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "Add files"],
            check=True,
        )

        # Get all tracked files
        tracked = get_all_tracked_files(git_repo)

        assert "file1.txt" in tracked
        assert "file2.py" in tracked
        assert "subdir/file3.md" in tracked
        assert len(tracked) == 3

    def test_get_all_tracked_files_empty_repo(self, git_repo):
        """Test getting tracked files from empty repo."""
        # No commits yet
        tracked = get_all_tracked_files(git_repo)

        assert tracked == []

    def test_git_changed_files_no_changes(self, git_repo):
        """Test getting changed files when there are no changes."""
        # Create initial commit
        file1 = git_repo / "file1.txt"
        file1.write_text("content")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "Initial"],
            check=True,
        )
        commit = subprocess.run(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # No changes between commit and itself
        changed = git_changed_files_modified_added(git_repo, commit, commit)

        assert changed == []

    def test_git_helpers_invalid_commit(self, git_repo):
        """Test that invalid commit raises error."""
        with pytest.raises(RuntimeError, match="Failed to get git diff"):
            git_changed_files_modified_added(
                git_repo, "invalid_commit", "HEAD"
            )

    def test_git_helpers_nonexistent_repo(self, tmp_path):
        """Test that non-git directory raises error."""
        non_repo = tmp_path / "not_a_repo"
        non_repo.mkdir()

        with pytest.raises(RuntimeError):
            get_all_tracked_files(non_repo)


class TestRepresentativeTextForHash:
    """Test representative_text_for_hash function."""

    def test_representative_text_found(self):
        """Test finding text for existing hash."""
        chunks = [
            ChunkTestData("text1", "hash1", 1, 5),
            ChunkTestData("text2", "hash2", 10, 15),
            ChunkTestData("text3", "hash3", 20, 25),
        ]

        text = representative_text_for_hash("hash2", chunks)
        assert text == "text2"

    def test_representative_text_first_match(self):
        """Test that first matching chunk is returned."""
        chunks = [
            ChunkTestData("first", "hash_dup", 1, 5),
            ChunkTestData("second", "hash_dup", 10, 15),
        ]

        text = representative_text_for_hash("hash_dup", chunks)
        assert text == "first"

    def test_representative_text_not_found(self):
        """Test that missing hash raises ValueError."""
        chunks = [
            ChunkTestData("text1", "hash1", 1, 5),
            ChunkTestData("text2", "hash2", 10, 15),
        ]

        with pytest.raises(ValueError, match="No chunk found with text_hash"):
            representative_text_for_hash("nonexistent", chunks)

    def test_representative_text_empty_chunks(self):
        """Test with empty chunk list."""
        with pytest.raises(ValueError, match="No chunk found"):
            representative_text_for_hash("any_hash", [])

    def test_representative_text_chunk_without_hash(self):
        """Test chunk without text_hash attribute is skipped."""
        @dataclass
        class ChunkNoHash:
            text: str
            start_line: int
            end_line: int

        chunks = [
            ChunkNoHash("text1", 1, 5),
            ChunkTestData("text2", "hash2", 10, 15),
        ]

        # Should skip first chunk and find second
        text = representative_text_for_hash("hash2", chunks)
        assert text == "text2"
