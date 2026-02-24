"""Tests for `dolphin repos` and `dolphin chunk` CLI commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from kb.cli import app

runner = CliRunner()


class TestReposCommand:
    """Test the `repos` command."""

    def test_repos_empty(self, isolated_kb_env):
        """repos --json returns empty list when no repos registered."""
        result = runner.invoke(app, ["repos", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data == {"repos": []}

    def test_repos_empty_text(self, isolated_kb_env):
        """repos (text mode) prints a message when no repos registered."""
        result = runner.invoke(app, ["repos"])

        assert result.exit_code == 0
        assert "no repositories" in result.stdout.lower()

    def test_repos_with_data(self, git_repo, isolated_kb_env):
        """repos --json lists registered repositories with counts."""
        from kb.ingest.cli import app as ingest_app

        ingest_runner = CliRunner()
        ingest_runner.invoke(ingest_app, ["init", "--config-path", str(isolated_kb_env.config_path)])
        ingest_runner.invoke(ingest_app, ["add-repo", "testrepo", str(git_repo)])

        result = runner.invoke(app, ["repos", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data["repos"]) == 1
        repo = data["repos"][0]
        assert repo["name"] == "testrepo"
        # macOS resolves /var → /private/var, so compare resolved paths
        from pathlib import Path

        assert Path(repo["root_path"]).resolve() == Path(str(git_repo)).resolve()
        assert "files" in repo
        assert "chunks" in repo

    def test_repos_text_with_data(self, git_repo, isolated_kb_env):
        """repos (text mode) shows repo details."""
        from kb.ingest.cli import app as ingest_app

        ingest_runner = CliRunner()
        ingest_runner.invoke(ingest_app, ["init", "--config-path", str(isolated_kb_env.config_path)])
        ingest_runner.invoke(ingest_app, ["add-repo", "testrepo", str(git_repo)])

        result = runner.invoke(app, ["repos"])

        assert result.exit_code == 0
        assert "testrepo" in result.stdout


class TestChunkCommand:
    """Test the `chunk` command."""

    def test_chunk_not_found_json(self, isolated_kb_env):
        """chunk --json returns error for non-existent chunk ID."""
        result = runner.invoke(app, ["chunk", "nonexistent-id", "--json"])

        assert result.exit_code != 0
        data = json.loads(result.stdout)
        assert "error" in data

    def test_chunk_not_found_text(self, isolated_kb_env):
        """chunk (text mode) prints error for non-existent chunk ID."""
        result = runner.invoke(app, ["chunk", "nonexistent-id"])

        assert result.exit_code != 0

    def test_chunk_requires_id(self):
        """chunk command requires a chunk_id argument."""
        result = runner.invoke(app, ["chunk"])

        assert result.exit_code != 0
