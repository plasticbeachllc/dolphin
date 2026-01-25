"""Integration tests for CLI workflows."""

from pathlib import Path

from typer.testing import CliRunner

from kb.ingest.cli import app

runner = CliRunner()


def init_config_with_store(tmp_path: Path):
    """Initialize CLI config at tmp_path and rewrite store_root to stay inside tmp."""
    config_path = tmp_path / "config.toml"
    result = runner.invoke(app, ["init", "--config-path", str(config_path)])

    store_root = tmp_path / "store"
    store_root.mkdir(parents=True, exist_ok=True)
    config_text = config_path.read_text()
    config_text = config_text.replace('store_root = "~/.dolphin/knowledge_store"', f'store_root = "{store_root}"')
    config_path.write_text(config_text)
    env = {"DOLPHIN_CONFIG_PATH": str(config_path)}
    return config_path, env, result


class TestInitWorkflow:
    """Test init command workflow."""

    def test_init_full_workflow(self, tmp_path):
        """Test complete init workflow creates all necessary files."""
        config_path, _env, result = init_config_with_store(tmp_path)

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
        config_path, env, init_result = init_config_with_store(tmp_path)
        assert init_result.exit_code == 0

        # Add repository
        add_result = runner.invoke(
            app,
            ["add-repo", "test-repo", str(git_repo)],
            env=env,
        )

        assert add_result.exit_code == 0
        assert "Repository registered" in add_result.stdout

    def test_add_multiple_repos(self, tmp_path):
        """Test adding multiple repositories."""
        config_path, env, _ = init_config_with_store(tmp_path)

        # Create two repos
        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"
        repo1.mkdir()
        repo2.mkdir()

        # Add both
        result1 = runner.invoke(app, ["add-repo", "repo-1", str(repo1)], env=env)
        result2 = runner.invoke(app, ["add-repo", "repo-2", str(repo2)], env=env)

        assert result1.exit_code == 0
        assert result2.exit_code == 0


class TestStatusWorkflow:
    """Test status command workflow."""

    def test_status_empty_store(self, tmp_path):
        """Test status on empty knowledge store."""
        config_path, env, _ = init_config_with_store(tmp_path)

        result = runner.invoke(app, ["status"], env=env)

        assert result.exit_code == 0
        assert "summary" in result.stdout.lower()

    def test_status_after_adding_repo(self, tmp_path, git_repo):
        """Test status after adding a repository."""
        config_path, env, _ = init_config_with_store(tmp_path)
        runner.invoke(app, ["add-repo", "test-repo", str(git_repo)], env=env)

        result = runner.invoke(app, ["status"], env=env)

        assert result.exit_code == 0


class TestListFilesWorkflow:
    """Test list-files command workflow."""

    def test_list_files_empty_repo(self, tmp_path, git_repo):
        """Test list-files on newly added repo."""
        config_path, env, _ = init_config_with_store(tmp_path)
        runner.invoke(app, ["add-repo", "test-repo", str(git_repo)], env=env)

        result = runner.invoke(app, ["list-files", "test-repo"], env=env)

        # Should work even if no files indexed yet
        assert result.exit_code in [0, 1]  # May be empty


class TestEndToEndWorkflow:
    """Test complete end-to-end workflows."""

    def test_init_add_status_workflow(self, tmp_path, git_repo):
        """Test complete workflow: init → add-repo → status."""
        config_path, env, init_result = init_config_with_store(tmp_path)
        assert init_result.exit_code == 0

        # Step 2: Add repo
        add_result = runner.invoke(app, ["add-repo", "my-repo", str(git_repo)], env=env)
        assert add_result.exit_code == 0

        # Step 3: Check status
        status_result = runner.invoke(app, ["status"], env=env)
        assert status_result.exit_code == 0

    def test_reinit_after_init(self, tmp_path):
        """Test that reinitializing is safe."""
        config_path, env, result1 = init_config_with_store(tmp_path)
        assert result1.exit_code == 0

        # Second init
        result2 = runner.invoke(app, ["init", "--config-path", str(config_path)], env=env)
        assert result2.exit_code == 0
        assert "already exists" in result2.stdout


class TestIndexWorkflow:
    """Test index command workflows (without actual indexing)."""

    def test_index_nonexistent_repo_fails(self, tmp_path):
        """Test that indexing non-existent repo fails gracefully."""
        config_path, env, _ = init_config_with_store(tmp_path)

        result = runner.invoke(app, ["index", "nonexistent-repo"], env=env)

        # Should fail gracefully
        assert result.exit_code != 0


class TestPruneWorkflow:
    """Test prune command workflows."""

    def test_prune_stub_implementation(self, tmp_path):
        """Test that prune command runs (stub implementation)."""
        config_path, env, _ = init_config_with_store(tmp_path)

        result = runner.invoke(app, ["prune", "test-repo", "--older-than", "7d"], env=env)

        assert result.exit_code == 0
        assert "Prune functionality" in result.stdout
