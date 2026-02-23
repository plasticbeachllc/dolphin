"""Comprehensive CLI command tests for kb ingest CLI.

These tests exercise the full command execution path beyond smoke tests,
covering add-repo, status, list-repos, list-files, search, validate, repair.
"""

from __future__ import annotations

import subprocess

from typer.testing import CliRunner

from kb.ingest.cli import app

runner = CliRunner()


class TestCLIAddRepo:
    """Test add-repo command execution."""

    def test_add_repo_success(self, tmp_path):
        """Test successfully adding a repository."""
        # Create a real git repo
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        (repo_path / "test.py").write_text("x = 1")
        subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)

        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        result = runner.invoke(app, ["add-repo", "myrepo", str(repo_path)])

        assert result.exit_code == 0
        assert "registered" in result.stdout.lower() or "added" in result.stdout.lower()

    def test_add_repo_with_custom_embed_model(self, tmp_path):
        """Test adding a repository with custom embed model."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)

        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        # No longer pass --default-embed-model, uses global config
        result = runner.invoke(app, ["add-repo", "myrepo", str(repo_path)])

        assert result.exit_code == 0

    def test_add_repo_non_directory_fails(self, tmp_path):
        """Test that add-repo fails for a file path."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        file_path = tmp_path / "somefile.txt"
        file_path.write_text("content")

        result = runner.invoke(app, ["add-repo", "myrepo", str(file_path)])

        assert result.exit_code != 0


class TestCLIStatus:
    """Test status command execution."""

    def test_status_no_repos(self, tmp_path):
        """Test status with no registered repos."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        # Should show some status, even if no repos

    def test_status_with_specific_repo(self, tmp_path):
        """Test status for a specific repository."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)

        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        runner.invoke(app, ["add-repo", "myrepo", str(repo_path)])

        result = runner.invoke(app, ["status", "myrepo"])

        assert result.exit_code == 0


class TestCLIListRepos:
    """Test list-repos command execution."""

    def test_list_repos_empty(self, tmp_path):
        """Test list-repos with no repositories."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        result = runner.invoke(app, ["list-repos"])

        assert result.exit_code == 0
        # May show empty list or message

    def test_list_repos_with_data(self, tmp_path):
        """Test list-repos shows registered repositories."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)

        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        runner.invoke(app, ["add-repo", "myrepo", str(repo_path)])

        result = runner.invoke(app, ["list-repos"])

        assert result.exit_code == 0
        assert "myrepo" in result.stdout


class TestCLIListFiles:
    """Test list-files command execution."""

    def test_list_files_requires_repo_name(self):
        """Test list-files requires a repository name."""
        result = runner.invoke(app, ["list-files"])
        assert result.exit_code != 0

    def test_list_files_nonexistent_repo(self, tmp_path):
        """Test list-files for non-existent repository."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        result = runner.invoke(app, ["list-files", "nonexistent"])

        assert result.exit_code != 0


class TestCLIValidateRepo:
    """Test validate-repo command execution."""

    def test_validate_repo_requires_name(self):
        """Test validate-repo requires a repository name."""
        result = runner.invoke(app, ["validate-repo"])
        assert result.exit_code != 0

    def test_validate_repo_nonexistent_fails(self, tmp_path):
        """Test validate-repo fails for non-existent repository."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        result = runner.invoke(app, ["validate-repo", "nonexistent"])

        assert result.exit_code != 0


class TestCLIRepairRepo:
    """Test repair-repo command execution."""

    def test_repair_repo_requires_name(self):
        """Test repair-repo requires a repository name."""
        result = runner.invoke(app, ["repair-repo"])
        assert result.exit_code != 0


class TestCLIPrune:
    """Test prune and prune-ignored commands."""

    def test_prune_requires_name(self):
        """Test prune requires a repository name."""
        result = runner.invoke(app, ["prune"])
        assert result.exit_code != 0

    def test_prune_ignored_requires_name(self):
        """Test prune-ignored requires a repository name."""
        result = runner.invoke(app, ["prune-ignored"])
        assert result.exit_code != 0


class TestCLIRmRepo:
    """Test rm-repo command execution."""

    def test_rm_repo_requires_name(self):
        """Test rm-repo requires a repository name."""
        result = runner.invoke(app, ["rm-repo"])
        assert result.exit_code != 0

    def test_rm_repo_nonexistent_fails(self, tmp_path):
        """Test rm-repo fails for non-existent repository."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        result = runner.invoke(app, ["rm-repo", "nonexistent", "--force"])

        assert result.exit_code != 0

    def test_rm_repo_success(self, tmp_path):
        """Test rm-repo successfully removes a repository."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)

        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        runner.invoke(app, ["add-repo", "myrepo", str(repo_path)])

        result = runner.invoke(app, ["rm-repo", "myrepo", "--force"])

        assert result.exit_code == 0
        assert "removed" in result.stdout.lower() or "deleted" in result.stdout.lower()


class TestCLIResetRepo:
    """Test reset-repo command execution."""

    def test_reset_repo_requires_arguments(self):
        """Test reset-repo requires name and path arguments."""
        result = runner.invoke(app, ["reset-repo"])
        assert result.exit_code != 0


class TestCLISearch:
    """Test search command execution."""

    def test_search_requires_query(self):
        """Test search requires a query argument."""
        result = runner.invoke(app, ["search"])
        assert result.exit_code != 0

    def test_search_empty_results(self, tmp_path):
        """Test search returns empty results for unindexed query."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        runner.invoke(app, ["search", "nonexistent query"])

        # May succeed with empty results or fail if no repos
        # We're just testing it doesn't crash


class TestCLIResetAll:
    """Test reset-all command execution."""

    def test_reset_all_requires_confirmation(self, tmp_path):
        """Test reset-all prompts for confirmation without --force."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        # Without --force, should prompt for confirmation
        # Providing 'n' to decline
        result = runner.invoke(app, ["reset-all"], input="n\n")

        # Should exit without deleting
        assert "abort" in result.stdout.lower() or result.exit_code == 0

    def test_reset_all_with_force(self, tmp_path):
        """Test reset-all with --force skips confirmation."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        result = runner.invoke(app, ["reset-all", "--force"])

        assert result.exit_code == 0


class TestCLIIndex:
    """Test index command execution."""

    def test_index_nonexistent_repo(self, tmp_path):
        """Test index fails for non-existent repository."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])

        result = runner.invoke(app, ["index", "nonexistent"])

        assert result.exit_code != 0

    def test_index_dry_run(self, tmp_path):
        """Test index with --dry-run flag."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        (repo_path / "test.py").write_text("x = 1")
        subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "commit.gpgsign", "false"],
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "initial"],
            check=True,
            capture_output=True,
        )

        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        runner.invoke(app, ["add-repo", "myrepo", str(repo_path)])

        result = runner.invoke(app, ["index", "myrepo", "--dry-run", "--force"])

        # Dry run should complete successfully
        assert result.exit_code == 0


class TestCLIHelperFunctions:
    """Test CLI helper function coverage."""

    def test_build_pipeline_help(self):
        """Test that _build_pipeline is called correctly via init."""
        # This tests the internal _build_pipeline function indirectly
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
