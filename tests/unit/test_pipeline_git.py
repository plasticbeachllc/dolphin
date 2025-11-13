"""Unit tests for pipeline git operations."""

import subprocess
from pathlib import Path

import pytest

from kb.config import KBConfig
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore


class TestPipelineGitOperations:
    """Test pipeline git-related methods."""

    @pytest.fixture
    def pipeline(self, tmp_path):
        """Create a pipeline instance for testing."""
        config = KBConfig(store_root=tmp_path, embedding_provider="stub")
        metadata = SQLiteMetadataStore(tmp_path / "test.db")
        metadata.initialize()
        lancedb = LanceDBStore(tmp_path / "lancedb")
        return IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

    def test_git_rev_parse_head(self, pipeline, git_repo):
        """Test _git can get current commit."""
        # Create a commit
        file1 = git_repo / "test.txt"
        file1.write_text("content")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(git_repo), "commit", "-m", "test"], check=True)

        result = pipeline._git(git_repo, "rev-parse", "HEAD")

        assert len(result.strip()) == 40  # SHA1 hash
        assert result.strip().isalnum()

    def test_git_branch_name(self, pipeline, git_repo):
        """Test _git can get current branch."""
        # Need at least one commit for HEAD to exist
        file1 = git_repo / "test.txt"
        file1.write_text("content")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(git_repo), "commit", "-m", "test"], check=True)

        result = pipeline._git(git_repo, "rev-parse", "--abbrev-ref", "HEAD")

        assert result.strip() in ["main", "master"]  # Default branches

    def test_git_invalid_command_raises_error(self, pipeline, git_repo):
        """Test that invalid git commands raise RuntimeError."""
        with pytest.raises(RuntimeError):
            pipeline._git(git_repo, "invalid-command")

    def test_git_nonexistent_repo_raises_error(self, pipeline, tmp_path):
        """Test that git commands on non-repo raise error."""
        non_repo = tmp_path / "not_a_repo"
        non_repo.mkdir()

        with pytest.raises(RuntimeError):
            pipeline._git(non_repo, "status")

    def test_ensure_clean_working_tree_success(self, pipeline, git_repo):
        """Test _ensure_clean_working_tree passes for clean repo."""
        # Create initial commit
        file1 = git_repo / "test.txt"
        file1.write_text("content")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(git_repo), "commit", "-m", "test"], check=True)

        # Should not raise
        pipeline._ensure_clean_working_tree(git_repo)

    def test_ensure_clean_working_tree_fails_with_changes(self, pipeline, git_repo):
        """Test _ensure_clean_working_tree fails with uncommitted changes."""
        # Create initial commit
        file1 = git_repo / "test.txt"
        file1.write_text("content")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(git_repo), "commit", "-m", "test"], check=True)

        # Make a change
        file1.write_text("modified content")

        with pytest.raises(RuntimeError, match="Working tree has tracked changes"):
            pipeline._ensure_clean_working_tree(git_repo)

    def test_ensure_clean_working_tree_fails_with_staged_changes(
        self, pipeline, git_repo
    ):
        """Test _ensure_clean_working_tree fails with staged changes."""
        # Create initial commit
        file1 = git_repo / "test.txt"
        file1.write_text("content")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(git_repo), "commit", "-m", "test"], check=True)

        # Stage a change
        file1.write_text("modified")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)

        with pytest.raises(RuntimeError, match="Working tree has tracked changes"):
            pipeline._ensure_clean_working_tree(git_repo)

    def test_ensure_clean_working_tree_allows_untracked(self, pipeline, git_repo):
        """Test _ensure_clean_working_tree allows untracked files."""
        # Create initial commit
        file1 = git_repo / "tracked.txt"
        file1.write_text("content")
        subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(git_repo), "commit", "-m", "test"], check=True)

        # Add untracked file (not staged)
        file2 = git_repo / "untracked.txt"
        file2.write_text("untracked")

        # Should not raise for untracked files
        pipeline._ensure_clean_working_tree(git_repo)


class TestPipelineRepoValidation:
    """Test pipeline repository validation."""

    @pytest.fixture
    def pipeline(self, tmp_path):
        """Create a pipeline instance for testing."""
        config = KBConfig(store_root=tmp_path, embedding_provider="stub")
        metadata = SQLiteMetadataStore(tmp_path / "test.db")
        metadata.initialize()
        lancedb = LanceDBStore(tmp_path / "lancedb")
        return IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

    def test_scan_nonexistent_repo_raises_error(self, pipeline):
        """Test that scanning non-existent repo raises ValueError."""
        with pytest.raises(ValueError, match="Repository not registered"):
            pipeline.scan("nonexistent-repo")

    def test_index_nonexistent_repo_raises_error(self, pipeline):
        """Test that indexing non-existent repo raises ValueError."""
        with pytest.raises(ValueError, match="Repository not registered"):
            pipeline.index("nonexistent-repo")


class TestPipelineIgnorePatterns:
    """Test pipeline ignore pattern handling."""

    @pytest.fixture
    def pipeline(self, tmp_path):
        """Create a pipeline instance for testing."""
        config = KBConfig(
            store_root=tmp_path, embedding_provider="stub", ignore=["*.log", "tmp"]
        )
        metadata = SQLiteMetadataStore(tmp_path / "test.db")
        metadata.initialize()
        lancedb = LanceDBStore(tmp_path / "lancedb")
        return IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

    def test_pipeline_uses_config_ignore_patterns(self, pipeline):
        """Test that pipeline uses ignore patterns from config."""
        # Config should have ignore patterns
        assert "*.log" in pipeline.config.ignore
        assert "tmp" in pipeline.config.ignore
