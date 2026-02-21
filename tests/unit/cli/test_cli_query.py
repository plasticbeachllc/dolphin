"""Unit tests for top-level dolphin search query UX."""

from __future__ import annotations

import json

from typer.testing import CliRunner

import kb.cli as cli

runner = CliRunner()


def test_help_command() -> None:
    """CLI help should render."""
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout


def test_search_json_output_schema(monkeypatch) -> None:
    """`dolphin search --json` should return stable top-level keys."""

    def fake_search_remote(**_kwargs):
        return (
            [
                {
                    "chunk_id": "c1",
                    "repo": "demo",
                    "path": "src/main.py",
                    "start_line": 10,
                    "end_line": 20,
                    "score": 0.91,
                    "symbol_name": "main",
                    "symbol_kind": "function",
                    "content": "def main():\n    pass",
                }
            ],
            {"top_k": 8, "latency_ms": 12, "model": "small"},
            None,
        )

    monkeypatch.setattr(cli, "_search_remote", fake_search_remote)
    result = runner.invoke(cli.app, ["search", "main entrypoint", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert sorted(payload.keys()) == ["filters", "hits", "meta", "mode", "query", "result_count"]
    assert payload["mode"] == "remote"
    assert payload["result_count"] == 1
    assert payload["filters"]["top_k"] == 8
    assert payload["hits"][0]["rank"] == 1
    assert payload["hits"][0]["language"] == "python"


def test_search_default_compact_output(monkeypatch) -> None:
    """Default output should be compact and avoid snippet body spam."""

    def fake_search_remote(**_kwargs):
        return (
            [
                {
                    "chunk_id": "c1",
                    "repo": "demo",
                    "path": "src/main.py",
                    "start_line": 1,
                    "end_line": 4,
                    "score": 0.74,
                    "content": "line1\nline2\nline3",
                }
            ],
            {"top_k": 8},
            None,
        )

    monkeypatch.setattr(cli, "_search_remote", fake_search_remote)
    result = runner.invoke(cli.app, ["search", "main entrypoint"])

    assert result.exit_code == 0
    assert 'Found 1 result(s) for "main entrypoint"' in result.stdout
    assert "score=0.7400" in result.stdout
    assert "line1" not in result.stdout
    assert "Tip: pass --verbose" in result.stdout


def test_search_verbose_shows_snippet(monkeypatch) -> None:
    """Verbose mode should display snippet/content lines."""

    def fake_search_remote(**_kwargs):
        return (
            [
                {
                    "chunk_id": "c1",
                    "repo": "demo",
                    "path": "src/main.py",
                    "start_line": 1,
                    "end_line": 3,
                    "score": 0.88,
                    "snippet": {"text": "def main():\n    return 1"},
                }
            ],
            {"top_k": 8, "model": "small", "latency_ms": 7},
            None,
        )

    monkeypatch.setattr(cli, "_search_remote", fake_search_remote)
    result = runner.invoke(cli.app, ["search", "main", "--verbose"])

    assert result.exit_code == 0
    assert "Meta: top_k=8 model=small latency_ms=7" in result.stdout
    assert "def main():" in result.stdout


def test_search_language_filter_alias(monkeypatch) -> None:
    """Language aliases like `py` should filter result hits."""

    def fake_search_remote(**_kwargs):
        return (
            [
                {
                    "chunk_id": "c1",
                    "repo": "demo",
                    "path": "src/main.py",
                    "start_line": 1,
                    "end_line": 3,
                    "score": 0.90,
                },
                {
                    "chunk_id": "c2",
                    "repo": "demo",
                    "path": "src/view.ts",
                    "start_line": 1,
                    "end_line": 3,
                    "score": 0.89,
                },
            ],
            {"top_k": 8},
            None,
        )

    monkeypatch.setattr(cli, "_search_remote", fake_search_remote)
    result = runner.invoke(cli.app, ["search", "main", "--lang", "py"])

    assert result.exit_code == 0
    assert "Language filter: python" in result.stdout
    assert "src/main.py" in result.stdout
    assert "src/view.ts" not in result.stdout
