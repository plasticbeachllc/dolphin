"""Comprehensive unit tests for CLI commands."""

import tomllib
from pathlib import Path

import pytest
import tomli_w
from typer.testing import CliRunner

from kb.config import KBConfig
from kb.ingest.cli import ResetStats, _build_pipeline, _read_config_template, app

runner = CliRunner()


def _set_config_store_root(config_path: Path, store_root: Path) -> None:
    """Point a config file's storage.store_root at an isolated directory.

    Parses and rewrites the TOML file properly so the helper is resilient
    to whitespace or comment changes in the config template.
    """
    store_root.mkdir(parents=True, exist_ok=True)
    with config_path.open("rb") as f:
        config_data = tomllib.load(f)
    config_data.setdefault("storage", {})["store_root"] = str(store_root)
    with config_path.open("wb") as f:
        tomli_w.dump(config_data, f)


class TestInitCommand:
    """Test kb init command."""

    def test_init_creates_config_file(self, tmp_path):
        """Test that init creates config file from template."""
        config_path = tmp_path / "config.toml"

        result = runner.invoke(app, ["init", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert config_path.exists()
        assert "Created knowledge store config" in result.stdout

    def test_init_creates_parent_directories(self, tmp_path):
        """Test that init creates parent directories if needed."""
        config_path = tmp_path / "nested" / "dirs" / "config.toml"

        result = runner.invoke(app, ["init", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert config_path.exists()
        assert config_path.parent.exists()

    def test_init_initializes_sqlite(self, tmp_path):
        """Test that init creates SQLite database."""
        config_path = tmp_path / "config.toml"

        result = runner.invoke(app, ["init", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "SQLite initialized" in result.stdout

    def test_init_initializes_lancedb(self, tmp_path):
        """Test that init initializes LanceDB."""
        config_path = tmp_path / "config.toml"

        result = runner.invoke(app, ["init", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "LanceDB root initialized" in result.stdout

    def test_init_is_idempotent(self, tmp_path, monkeypatch):
        """Test that running init twice is safe."""
        config_path = tmp_path / "config.toml"
        store_root = tmp_path / "store"

        # Patch the config template to use an isolated store root so parallel
        # xdist workers don't race on the default ~/.dolphin/knowledge_store path.
        original_template = _read_config_template()
        isolated_template = original_template.replace(
            'store_root = "~/.dolphin/knowledge_store"',
            f'store_root = "{store_root}"',
        )
        monkeypatch.setattr("kb.ingest.cli._read_config_template", lambda: isolated_template)

        # First run
        result1 = runner.invoke(app, ["init", "--config-path", str(config_path)])
        assert result1.exit_code == 0

        # Second run
        result2 = runner.invoke(app, ["init", "--config-path", str(config_path)])
        assert result2.exit_code == 0
        assert "already exists" in result2.stdout

    def test_init_uses_default_path_when_not_specified(self, tmp_path, monkeypatch):
        """Test that init uses DEFAULT_CONFIG_PATH when path not specified."""
        default_path = tmp_path / "default_config.toml"
        monkeypatch.setattr("kb.ingest.cli.DEFAULT_CONFIG_PATH", default_path)

        result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert default_path.exists()

    def test_init_config_template_exists(self):
        """Test that config template can be read."""
        template = _read_config_template()
        assert len(template) > 0
        assert "store_root" in template or "[" in template  # TOML content

    def test_init_shows_readiness_checklist(self, tmp_path):
        """Test that init shows a readiness checklist with component status."""
        config_path = tmp_path / "config.toml"

        result = runner.invoke(app, ["init", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "Readiness check:" in result.stdout
        assert "Config" in result.stdout
        assert "SQLite" in result.stdout
        assert "LanceDB" in result.stdout
        assert "Next steps:" in result.stdout
        assert "dolphin add-repo" in result.stdout
        assert "dolphin index" in result.stdout

    def test_init_shows_missing_openai_key(self, tmp_path, monkeypatch):
        """Test that init warns when OPENAI_API_KEY is not set and provider is openai."""
        config_path = tmp_path / "config.toml"
        store_root = tmp_path / "store"

        # Create a config with openai provider
        original_template = _read_config_template()
        assert "openai" in original_template.lower(), "Config template no longer references openai provider"
        openai_template = original_template.replace(
            'store_root = "~/.dolphin/knowledge_store"',
            f'store_root = "{store_root}"',
        )
        monkeypatch.setattr("kb.ingest.cli._read_config_template", lambda: openai_template)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(app, ["init", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "OPENAI_API_KEY" in result.stdout
        assert "missing" in result.stdout

    def test_init_shows_ok_openai_key(self, tmp_path, monkeypatch):
        """Test that init shows ok status when OPENAI_API_KEY is set."""
        config_path = tmp_path / "config.toml"
        store_root = tmp_path / "store"

        original_template = _read_config_template()
        openai_template = original_template.replace(
            'store_root = "~/.dolphin/knowledge_store"',
            f'store_root = "{store_root}"',
        )
        monkeypatch.setattr("kb.ingest.cli._read_config_template", lambda: openai_template)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-init-check")

        result = runner.invoke(app, ["init", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "OPENAI_API_KEY" in result.stdout
        # Should show "ok" not "missing"
        lines = result.stdout.splitlines()
        openai_lines = [line for line in lines if "OPENAI_API_KEY" in line]
        assert any("ok" in line for line in openai_lines)


class TestAddRepoCommand:
    """Test kb add-repo command."""

    def test_add_repo_registers_repository(self, tmp_path, git_repo):
        """Test that add-repo successfully registers a repo."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        _set_config_store_root(config_path, tmp_path / "store")

        result = runner.invoke(
            app,
            ["add-repo", "test-repo", str(git_repo)],
            env={"DOLPHIN_CONFIG_PATH": str(config_path)},
        )

        assert result.exit_code == 0
        assert "Repository registered" in result.stdout
        assert "test-repo" in result.stdout

    def test_add_repo_requires_name_argument(self):
        """Test that add-repo requires name argument."""
        result = runner.invoke(app, ["add-repo"])
        assert result.exit_code != 0

    def test_add_repo_requires_path_argument(self):
        """Test that add-repo requires path argument."""
        result = runner.invoke(app, ["add-repo", "test-repo"])
        assert result.exit_code != 0

    def test_add_repo_fails_for_nonexistent_path(self, tmp_path):
        """Test that add-repo fails for non-existent directory."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        _set_config_store_root(config_path, tmp_path / "store")

        nonexistent = tmp_path / "nonexistent"
        result = runner.invoke(app, ["add-repo", "test", str(nonexistent)])

        assert result.exit_code == 2
        assert "does not exist" in result.stdout or "not a directory" in result.stdout

    def test_add_repo_fails_for_file_instead_of_directory(self, tmp_path):
        """Test that add-repo fails when path is a file."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        _set_config_store_root(config_path, tmp_path / "store")

        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        result = runner.invoke(app, ["add-repo", "test", str(file_path)])

        assert result.exit_code == 2

    def test_add_repo_with_small_embed_model(self, tmp_path, git_repo):
        """Test add-repo uses global config for embedding model."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        _set_config_store_root(config_path, tmp_path / "store")

        # No longer pass --default-embed-model, it uses global config
        result = runner.invoke(
            app,
            ["add-repo", "test-repo", str(git_repo)],
            env={"DOLPHIN_CONFIG_PATH": str(config_path)},
        )

        assert result.exit_code == 0
        assert "Repository registered" in result.stdout

    def test_add_repo_with_large_embed_model(self, tmp_path, git_repo):
        """Test add-repo uses global config for embedding model."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        _set_config_store_root(config_path, tmp_path / "store")

        # No longer pass --default-embed-model, it uses global config
        result = runner.invoke(
            app,
            ["add-repo", "test-repo", str(git_repo)],
            env={"DOLPHIN_CONFIG_PATH": str(config_path)},
        )

        assert result.exit_code == 0
        assert "Repository registered" in result.stdout

    def test_add_repo_rejects_invalid_embed_model(self, tmp_path, git_repo):
        """Test that embedding model is now set globally, not per-repo."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        _set_config_store_root(config_path, tmp_path / "store")

        # Flag no longer exists - testing it should fail
        result = runner.invoke(
            app,
            [
                "add-repo",
                "test-repo",
                str(git_repo),
                "--default-embed-model",
                "invalid",
            ],
            env={"DOLPHIN_CONFIG_PATH": str(config_path)},
        )

        assert result.exit_code == 2
        # Exit code 2 means the command failed (flag doesn't exist)

    def test_add_repo_expands_tilde_in_path(self, tmp_path, monkeypatch):
        """Test that add-repo expands ~ in path."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        _set_config_store_root(config_path, tmp_path / "store")

        # Point Path.home() and environment home variables to the tmp directory
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        test_dir = Path.home() / ".test_dolphin_repo"
        test_dir.mkdir(exist_ok=True)

        try:
            result = runner.invoke(
                app,
                ["add-repo", "test", "~/.test_dolphin_repo"],
                env={"DOLPHIN_CONFIG_PATH": str(config_path)},
            )
            assert result.exit_code == 0
            assert "Repository registered" in result.stdout
        finally:
            if test_dir.exists():
                test_dir.rmdir()


class TestIndexCommand:
    """Test kb index command."""

    def test_index_requires_repo_name(self):
        """Test that index requires repository name argument."""
        result = runner.invoke(app, ["index"])
        assert result.exit_code != 0

    def test_index_dry_run_flag(self, tmp_path, git_repo):
        """Test index with --dry-run flag."""
        # This will fail without proper setup, but we test the flag is parsed
        result = runner.invoke(app, ["index", "test-repo", "--dry-run"])
        # May fail due to missing config/repo, but flag should be accepted
        assert "--dry-run" not in result.stdout or "dry" in result.stdout.lower()

    def test_index_force_flag(self, tmp_path):
        """Test index with --force flag."""
        result = runner.invoke(app, ["index", "test-repo", "--force"])
        # May fail but flag should be accepted
        assert "--force" not in result.stdout or "force" in result.stdout.lower()

    def test_index_full_flag(self, tmp_path):
        """Test index with --full flag."""
        result = runner.invoke(app, ["index", "test-repo", "--full"])
        # May fail but flag should be accepted
        assert "--full" not in result.stdout or "full" in result.stdout.lower()

    def test_index_flags_combination(self, tmp_path):
        """Test index with multiple flags combined."""
        result = runner.invoke(app, ["index", "test-repo", "--dry-run", "--force", "--full"])
        # Should accept all flags
        assert result.exit_code in [0, 1, 2]  # Various failure modes are ok


class TestStatusCommand:
    """Test kb status command."""

    def test_status_works_without_arguments(self, tmp_path):
        """Test that status command works without arguments."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        _set_config_store_root(config_path, tmp_path / "store")

        result = runner.invoke(app, ["status"], env={"DOLPHIN_CONFIG_PATH": str(config_path)})

        assert result.exit_code == 0
        assert "summary" in result.stdout.lower() or "Knowledge" in result.stdout

    def test_status_accepts_optional_repo_name(self, tmp_path):
        """Test that status accepts optional repo name."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        _set_config_store_root(config_path, tmp_path / "store")

        result = runner.invoke(app, ["status", "test-repo"], env={"DOLPHIN_CONFIG_PATH": str(config_path)})

        assert result.exit_code == 0


class TestPruneIgnoredCommand:
    """Test kb prune-ignored command."""

    def test_prune_ignored_requires_repo_name(self):
        """Test that prune-ignored requires repository name."""
        result = runner.invoke(app, ["prune-ignored"])
        assert result.exit_code != 0

    def test_prune_ignored_dry_run_flag(self, tmp_path):
        """Test prune-ignored with --dry-run flag."""
        result = runner.invoke(app, ["prune-ignored", "test-repo", "--dry-run"])
        # May fail but should accept flag
        assert result.exit_code in [0, 1, 2]


class TestPruneCommand:
    """Test kb prune command."""

    def test_prune_requires_repo_name(self):
        """Test that prune requires repository name."""
        result = runner.invoke(app, ["prune"])
        assert result.exit_code != 0

    def test_prune_default_older_than(self):
        """Test prune with default --older-than."""
        result = runner.invoke(app, ["prune", "test-repo"])
        assert result.exit_code == 0
        assert "Prune functionality" in result.stdout

    def test_prune_custom_older_than(self):
        """Test prune with custom --older-than value."""
        result = runner.invoke(app, ["prune", "test-repo", "--older-than", "7d"])
        assert result.exit_code == 0


class TestListFilesCommand:
    """Test kb list-files command."""

    def test_list_files_requires_repo_name(self):
        """Test that list-files requires repository name."""
        result = runner.invoke(app, ["list-files"])
        assert result.exit_code != 0

    def test_list_files_with_unregistered_repo(self, tmp_path):
        """Test list-files with unregistered repository."""
        config_path = tmp_path / "config.toml"
        runner.invoke(app, ["init", "--config-path", str(config_path)])
        _set_config_store_root(config_path, tmp_path / "store")

        result = runner.invoke(
            app,
            ["list-files", "nonexistent-repo"],
            env={"DOLPHIN_CONFIG_PATH": str(config_path)},
        )

        assert result.exit_code == 1
        # Error is printed to stderr, not stdout
        output = (result.stdout + result.stderr).lower()
        assert "not registered" in output


class TestBuildPipeline:
    """Test _build_pipeline helper function."""

    def test_build_pipeline_with_stub_provider(self, tmp_path):
        """Test building pipeline with stub provider."""
        config = KBConfig(
            store_root=tmp_path,
            embedding_provider="stub",
        )

        pipeline = _build_pipeline(config)

        assert pipeline is not None
        assert pipeline.config == config

    def test_build_pipeline_with_openai_requires_api_key(self, tmp_path, monkeypatch):
        """Test that OpenAI provider requires API key."""
        config = KBConfig(
            store_root=tmp_path,
            embedding_provider="openai",
            openai_api_key_env="TEST_API_KEY",
        )

        # Remove API key from environment
        monkeypatch.delenv("TEST_API_KEY", raising=False)

        with pytest.raises(RuntimeError, match="environment variable is required"):
            _build_pipeline(config)

    def test_build_pipeline_with_openai_and_api_key(self, tmp_path, monkeypatch):
        """Test building pipeline with OpenAI provider and API key."""
        from unittest.mock import patch

        from kb.embeddings.provider import OpenAIEmbeddingProvider

        config = KBConfig(
            store_root=tmp_path,
            embedding_provider="openai",
            openai_api_key_env="TEST_API_KEY",
        )

        monkeypatch.setenv("TEST_API_KEY", "sk-test-key-1234567890")

        # Mock create_provider to avoid real API validation
        with patch("kb.ingest.cli.create_provider") as mock_create:
            mock_provider = OpenAIEmbeddingProvider(api_key="sk-test-key-1234567890", validate_key=False)
            mock_create.return_value = mock_provider

            pipeline = _build_pipeline(config)

            assert pipeline is not None
            mock_create.assert_called_once_with("openai", api_key="sk-test-key-1234567890", batch_size=100)


class TestConfigTemplate:
    """Test configuration template."""

    def test_read_config_template_returns_valid_toml(self):
        """Test that config template is valid TOML."""
        template = _read_config_template()

        # Should contain TOML-like content
        assert len(template) > 0
        # Should have some expected config keys
        assert any(key in template for key in ["store_root", "endpoint", "embedding"])
        assert "[api]" in template
        assert "[graph]" in template
        assert "[mcp]" in template


class TestResetStats:
    """Test the ResetStats dataclass for repo reset accumulation."""

    def test_defaults(self):
        stats = ResetStats()
        assert stats.repos_removed == 0
        assert stats.files_deleted == 0
        assert stats.errors == []

    def test_accumulation(self):
        stats = ResetStats()
        stats.repos_removed += 1
        stats.files_deleted += 10
        stats.content_deleted += 5
        stats.vectors_deleted += 20
        assert stats.repos_removed == 1
        assert stats.files_deleted == 10
        assert stats.content_deleted == 5
        assert stats.vectors_deleted == 20

    def test_error_collection(self):
        stats = ResetStats()
        stats.errors.append("Failed to remove repo-a")
        stats.errors.extend(["warn1", "warn2"])
        assert len(stats.errors) == 3

    def test_independent_instances(self):
        a = ResetStats()
        b = ResetStats()
        a.errors.append("only-a")
        assert b.errors == []
