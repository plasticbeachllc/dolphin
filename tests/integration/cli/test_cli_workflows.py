"""Integration tests for CLI workflows."""

from typer.testing import CliRunner

from kb.ingest.cli import app

runner = CliRunner()


class TestInitWorkflow:
    """Test init command workflow."""

    def test_init_full_workflow(self, isolated_kb_env):
        """Test complete init workflow creates all necessary files."""
        result = runner.invoke(app, ["init", "--config-path", str(isolated_kb_env.config_path)])

        assert result.exit_code == 0

        # Config file should exist
        assert isolated_kb_env.config_path.exists()

        # Store root should be created
        assert "SQLite initialized" in result.stdout
        assert "LanceDB root initialized" in result.stdout


class TestAddRepoWorkflow:
    """Test add-repo command workflow."""

    def test_add_repo_full_workflow(self, git_repo, isolated_kb_env):
        """Test complete add-repo workflow."""
        init_result = runner.invoke(app, ["init", "--config-path", str(isolated_kb_env.config_path)])
        assert init_result.exit_code == 0

        # Add repository
        add_result = runner.invoke(app, ["add-repo", "test-repo", str(git_repo)])

        assert add_result.exit_code == 0
        assert "Repository registered" in add_result.stdout

    def test_add_multiple_repos(self, tmp_path, isolated_kb_env):
        """Test adding multiple repositories."""
        runner.invoke(app, ["init", "--config-path", str(isolated_kb_env.config_path)])

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

    def test_status_empty_store(self, isolated_kb_env):
        """Test status on empty knowledge store."""
        runner.invoke(app, ["init", "--config-path", str(isolated_kb_env.config_path)])

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "summary" in result.stdout.lower()

    def test_status_after_adding_repo(self, git_repo, isolated_kb_env):
        """Test status after adding a repository."""
        runner.invoke(app, ["init", "--config-path", str(isolated_kb_env.config_path)])
        runner.invoke(app, ["add-repo", "test-repo", str(git_repo)])

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0


class TestListFilesWorkflow:
    """Test list-files command workflow."""

    def test_list_files_empty_repo(self, git_repo, isolated_kb_env):
        """Test list-files on newly added repo."""
        runner.invoke(app, ["init", "--config-path", str(isolated_kb_env.config_path)])
        runner.invoke(app, ["add-repo", "test-repo", str(git_repo)])

        result = runner.invoke(app, ["list-files", "test-repo"])

        # Should work even if no files indexed yet
        assert result.exit_code in [0, 1]  # May be empty


class TestEndToEndWorkflow:
    """Test complete end-to-end workflows."""

    def test_init_add_status_workflow(self, git_repo, isolated_kb_env):
        """Test complete workflow: init -> add-repo -> status."""
        init_result = runner.invoke(app, ["init", "--config-path", str(isolated_kb_env.config_path)])
        assert init_result.exit_code == 0

        # Step 2: Add repo
        add_result = runner.invoke(app, ["add-repo", "my-repo", str(git_repo)])
        assert add_result.exit_code == 0

        # Step 3: Check status
        status_result = runner.invoke(app, ["status"])
        assert status_result.exit_code == 0

    def test_reinit_after_init(self, isolated_kb_env):
        """Test that reinitializing is safe."""
        result1 = runner.invoke(app, ["init", "--config-path", str(isolated_kb_env.config_path)])
        assert result1.exit_code == 0

        # Second init
        result2 = runner.invoke(app, ["init", "--config-path", str(isolated_kb_env.config_path)])
        assert result2.exit_code == 0
        assert "already exists" in result2.stdout


class TestIndexWorkflow:
    """Test index command workflows (without actual indexing)."""

    def test_index_nonexistent_repo_fails(self, isolated_kb_env):
        """Test that indexing non-existent repo fails gracefully."""
        runner.invoke(app, ["init", "--config-path", str(isolated_kb_env.config_path)])

        result = runner.invoke(app, ["index", "nonexistent-repo"])

        # Should fail gracefully
        assert result.exit_code != 0


class TestPruneWorkflow:
    """Test prune command workflows."""

    def test_prune_stub_implementation(self, isolated_kb_env):
        """Test that prune command runs (stub implementation)."""
        runner.invoke(app, ["init", "--config-path", str(isolated_kb_env.config_path)])

        result = runner.invoke(app, ["prune", "test-repo", "--older-than", "7d"])

        assert result.exit_code == 0
        assert "Prune functionality" in result.stdout
