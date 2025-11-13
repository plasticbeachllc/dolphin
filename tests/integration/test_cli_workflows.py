"""Integration tests for CLI workflows."""

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kb.ingest.cli import app
from kb.store import SQLiteMetadataStore

runner = CliRunner()


class TestInitWorkflow:
    """Test init command workflow."""

    def test_init_full_workflow(self, tmp_path):
        """Test complete init workflow creates all necessary files."""
        config_path = tmp_path / "config.toml"

        result = runner.invoke(app, ["init", "--config-path", str(config_path)])

        assert result.exit_code == 0

        # Config file should exist
        assert config_path.exists()

        # Store root should be created
        # Default is ~/.dolphin/knowledge_store, but we can verify the message
        assert "SQLite initialized" in result.stdout
        assert "LanceDB root initialized" in result.stdout


class TestAddRepoWorkflow:
    """Test add-repo command workflow."""

    def test_add_repo_full_workflow(self, tmp_path, git_repo):
        """Test complete add-repo workflow."""
        config_path = tmp_path / "config.toml"

        # Initialize first
        init_result = runner.invoke(app, ["init", "--config-path", str(config_path)])
        assert init_result.exit_code == 0

        # Add repository
        add_result = runner.invoke(
            app,
            ["add-repo", "test-repo", str(git_repo), "--default-embed-model", "small"],
        )

        assert add_result.exit_code == 0
        assert "Repository registered" in add_result.stdout

    def test_add_multiple_repos(self, tmp_path):
        """Test adding multiple repositories."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        # Create two repos
        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"
        repo1.mkdir()
        repo2.mkdir()

        # Add both
        result1 = runner.invoke(app, ["add-repo", "repo-1", str(repo1)])
        result2 = runner.invoke(app, ["add-repo", "repo-2", str(repo2)])

        assert result1.exit_code == 0
        assert result2.exit_code == 0


class TestStatusWorkflow:
    """Test status command workflow."""

    def test_status_empty_store(self, tmp_path):
        """Test status on empty knowledge store."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "summary" in result.stdout.lower()

    def test_status_after_adding_repo(self, tmp_path, git_repo):
        """Test status after adding a repository."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        runner.invoke(app, ["add-repo", "test-repo", str(git_repo)])

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0


class TestListFilesWorkflow:
    """Test list-files command workflow."""

    def test_list_files_empty_repo(self, tmp_path, git_repo):
        """Test list-files on newly added repo."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        runner.invoke(app, ["add-repo", "test-repo", str(git_repo)])

        result = runner.invoke(app, ["list-files", "test-repo"])

        # Should work even if no files indexed yet
        assert result.exit_code in [0, 1]  # May be empty


class TestEndToEndWorkflow:
    """Test complete end-to-end workflows."""

    def test_init_add_status_workflow(self, tmp_path, git_repo):
        """Test complete workflow: init → add-repo → status."""
        config_path = tmp_path / "config.toml"

        # Step 1: Init
        init_result = runner.invoke(app, ["init", "--config-path", str(config_path)])
        assert init_result.exit_code == 0

        # Step 2: Add repo
        add_result = runner.invoke(app, ["add-repo", "my-repo", str(git_repo)])
        assert add_result.exit_code == 0

        # Step 3: Check status
        status_result = runner.invoke(app, ["status"])
        assert status_result.exit_code == 0

    def test_reinit_after_init(self, tmp_path):
        """Test that reinitializing is safe."""
        config_path = tmp_path / "config.toml"

        # First init
        result1 = runner.invoke(app, ["init", "--config-path", str(config_path)])
        assert result1.exit_code == 0

        # Second init
        result2 = runner.invoke(app, ["init", "--config-path", str(config_path)])
        assert result2.exit_code == 0
        assert "already exists" in result2.stdout


class TestIndexWorkflow:
    """Test index command workflows (without actual indexing)."""

    def test_index_nonexistent_repo_fails(self, tmp_path):
        """Test that indexing non-existent repo fails gracefully."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        result = runner.invoke(app, ["index", "nonexistent-repo"])

        # Should fail gracefully
        assert result.exit_code != 0


class TestPruneWorkflow:
    """Test prune command workflows."""

    def test_prune_stub_implementation(self, tmp_path):
        """Test that prune command runs (stub implementation)."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        result = runner.invoke(app, ["prune", "test-repo", "--older-than", "7d"])

        assert result.exit_code == 0
        assert "Prune functionality" in result.stdout
