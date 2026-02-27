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


def _make_multiline_hit(num_lines: int) -> dict:
    """Helper to build a hit with a multi-line content field."""
    content = "\n".join(f"line{i}" for i in range(1, num_lines + 1))
    return {
        "chunk_id": "c1",
        "repo": "demo",
        "path": "src/main.py",
        "start_line": 1,
        "end_line": num_lines,
        "score": 0.80,
        "content": content,
    }


def test_search_max_lines_truncates_snippet(monkeypatch) -> None:
    """Fake hit with 20-line content; --max-lines 3 output shows 3 lines and '17 more lines'."""

    def fake_search_remote(**_kwargs):
        return ([_make_multiline_hit(20)], {"top_k": 8}, None)

    monkeypatch.setattr(cli, "_search_remote", fake_search_remote)
    result = runner.invoke(cli.app, ["search", "query", "--verbose", "--max-lines", "3"])

    assert result.exit_code == 0
    assert "line1" in result.stdout
    assert "line3" in result.stdout
    assert "line4" not in result.stdout
    assert "17 more lines" in result.stdout


def test_search_max_lines_default_is_8(monkeypatch) -> None:
    """Fake hit with 15-line content; default invocation shows 8 lines and '7 more lines'."""

    def fake_search_remote(**_kwargs):
        return ([_make_multiline_hit(15)], {"top_k": 8}, None)

    monkeypatch.setattr(cli, "_search_remote", fake_search_remote)
    result = runner.invoke(cli.app, ["search", "query", "--verbose"])

    assert result.exit_code == 0
    assert "line8" in result.stdout
    assert "line9" not in result.stdout
    assert "7 more lines" in result.stdout


def test_search_max_lines_no_truncation_when_content_fits(monkeypatch) -> None:
    """Content with 4 lines; --max-lines 8 shows all 4 lines, no 'more lines' suffix."""

    def fake_search_remote(**_kwargs):
        return ([_make_multiline_hit(4)], {"top_k": 8}, None)

    monkeypatch.setattr(cli, "_search_remote", fake_search_remote)
    result = runner.invoke(cli.app, ["search", "query", "--verbose", "--max-lines", "8"])

    assert result.exit_code == 0
    assert "line4" in result.stdout
    assert "more lines" not in result.stdout


def test_search_max_lines_clipped_to_1(monkeypatch) -> None:
    """--max-lines 0 is guarded to max(1, ...) — at least 1 line shown."""

    def fake_search_remote(**_kwargs):
        return ([_make_multiline_hit(5)], {"top_k": 8}, None)

    monkeypatch.setattr(cli, "_search_remote", fake_search_remote)
    result = runner.invoke(cli.app, ["search", "query", "--verbose", "--max-lines", "0"])

    assert result.exit_code == 0
    assert "line1" in result.stdout
    assert "4 more lines" in result.stdout


def test_display_results_no_hits(monkeypatch) -> None:
    """_display_results with empty list prints 'No results found.'."""

    def fake_search_remote(**_kwargs):
        return ([], {"top_k": 8}, None)

    monkeypatch.setattr(cli, "_search_remote", fake_search_remote)
    result = runner.invoke(cli.app, ["search", "nothing here"])

    assert result.exit_code == 0
    assert "No results found." in result.stdout


def test_display_results_verbose_shows_chunk_id(monkeypatch) -> None:
    """Hit with chunk_id; verbose=True output contains chunk_id=..."""

    def fake_search_remote(**_kwargs):
        return (
            [
                {
                    "chunk_id": "abc-123-def",
                    "repo": "demo",
                    "path": "src/main.py",
                    "start_line": 1,
                    "end_line": 3,
                    "score": 0.80,
                    "content": "line1\nline2",
                }
            ],
            {"top_k": 8, "model": "small", "latency_ms": 5},
            None,
        )

    monkeypatch.setattr(cli, "_search_remote", fake_search_remote)
    result = runner.invoke(cli.app, ["search", "query", "--verbose"])

    assert result.exit_code == 0
    assert "chunk_id=abc-123-def" in result.stdout


# --- Tests for rich display helpers ---


def test_rich_lexer_for_language() -> None:
    """Language to lexer mapping should handle known and unknown languages."""
    assert cli._rich_lexer_for_language("python") == "python"
    assert cli._rich_lexer_for_language("typescript") == "typescript"
    assert cli._rich_lexer_for_language("Python") == "python"  # case insensitive
    assert cli._rich_lexer_for_language("svelte") == "html"  # closest lexer
    assert cli._rich_lexer_for_language("unknown_lang") == "unknown_lang"  # pass-through for Pygments
    assert cli._rich_lexer_for_language("shell") == "bash"  # override


def test_extract_snippet_text_from_snippet_obj() -> None:
    """Should extract text from snippet dict."""
    hit: dict[str, object] = {"snippet": {"text": "def foo(): pass"}}
    assert cli._extract_snippet_text(hit, show_content=True, verbose=False) == "def foo(): pass"


def test_extract_snippet_text_from_content() -> None:
    """Should fall back to content field when snippet is absent."""
    hit: dict[str, object] = {"content": "class Bar: pass"}
    assert cli._extract_snippet_text(hit, show_content=True, verbose=False) == "class Bar: pass"


def test_extract_snippet_text_not_shown_without_flags() -> None:
    """Should return None when neither show_content nor verbose is set."""
    hit: dict[str, object] = {"snippet": {"text": "def foo(): pass"}}
    assert cli._extract_snippet_text(hit, show_content=False, verbose=False) is None


def test_extract_snippet_text_empty_content() -> None:
    """Should return None for empty/whitespace-only content."""
    assert cli._extract_snippet_text({"content": ""}, show_content=True, verbose=False) is None
    assert cli._extract_snippet_text({"content": "   "}, show_content=True, verbose=False) is None


def test_score_style() -> None:
    """Score style should return appropriate color for score ranges."""
    assert "cyan" in cli._score_style(0.85)
    assert "cyan" in cli._score_style(0.55)
    assert "dim" in cli._score_style(0.2)
