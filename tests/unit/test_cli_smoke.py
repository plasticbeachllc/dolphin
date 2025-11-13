"""Basic smoke tests for CLI functionality."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from kb.ingest.cli import app

runner = CliRunner()


class TestCLIBasics:
    """Basic smoke tests for CLI commands."""

    def test_cli_help_works(self):
        """Test that --help flag works."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "knowledge store" in result.stdout.lower()

    def test_init_help_works(self):
        """Test that init --help works."""
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        assert "initialize" in result.stdout.lower()

    def test_add_repo_help_works(self):
        """Test that add-repo --help works."""
        result = runner.invoke(app, ["add-repo", "--help"])
        assert result.exit_code == 0
        assert "register" in result.stdout.lower()

    def test_index_help_works(self):
        """Test that index --help works."""
        result = runner.invoke(app, ["index", "--help"])
        assert result.exit_code == 0
        assert (
            "indexing" in result.stdout.lower() or "pipeline" in result.stdout.lower()
        )

    def test_status_help_works(self):
        """Test that status --help works."""
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0
        assert "status" in result.stdout.lower() or "report" in result.stdout.lower()

    def test_init_creates_config(self, tmp_path):
        """Test that kb init creates a config file."""
        config_path = tmp_path / "test_config.toml"

        result = runner.invoke(app, ["init", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert config_path.exists()
        assert "Created" in result.stdout or "Initialized" in result.stdout

    def test_init_idempotent(self, tmp_path):
        """Test that kb init can be run multiple times safely."""
        config_path = tmp_path / "test_config.toml"

        # First run
        result1 = runner.invoke(app, ["init", "--config-path", str(config_path)])
        assert result1.exit_code == 0

        # Second run should not fail
        result2 = runner.invoke(app, ["init", "--config-path", str(config_path)])
        assert result2.exit_code == 0
        assert (
            "already exists" in result2.stdout.lower()
            or "verified" in result2.stdout.lower()
        )

    def test_add_repo_requires_arguments(self):
        """Test that add-repo requires name and path arguments."""
        result = runner.invoke(app, ["add-repo"])
        assert result.exit_code != 0

    def test_add_repo_invalid_path_fails(self, tmp_path):
        """Test that add-repo fails for non-existent path."""
        config_path = tmp_path / "test_config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        nonexistent = tmp_path / "nonexistent_repo"
        result = runner.invoke(app, ["add-repo", "test-repo", str(nonexistent)])

        assert result.exit_code != 0
        assert (
            "does not exist" in result.stdout.lower()
            or "not a directory" in result.stdout.lower()
        )

    def test_index_requires_repo_name(self):
        """Test that index requires a repository name."""
        result = runner.invoke(app, ["index"])
        assert result.exit_code != 0
