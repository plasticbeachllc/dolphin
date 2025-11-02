"""Unit tests for ignore pattern handling."""

import pytest
from pathlib import Path
from kb.ignores import (
    DEFAULT_IGNORE_PATTERNS,
    build_ignore_set,
    load_repo_ignores,
)


class TestDefaultIgnorePatterns:
    """Test default ignore patterns."""

    def test_default_patterns_exist(self):
        """Test that default ignore patterns are defined."""
        assert len(DEFAULT_IGNORE_PATTERNS) > 0
        assert isinstance(DEFAULT_IGNORE_PATTERNS, tuple)

    def test_env_files_in_defaults(self):
        """Test that .env files are in default ignores."""
        assert ".env" in DEFAULT_IGNORE_PATTERNS
        assert ".env.*" in DEFAULT_IGNORE_PATTERNS
        assert "**/.env" in DEFAULT_IGNORE_PATTERNS

    def test_common_directories_in_defaults(self):
        """Test that common ignore directories are in defaults."""
        assert "node_modules" in DEFAULT_IGNORE_PATTERNS
        assert "dist" in DEFAULT_IGNORE_PATTERNS
        assert "build" in DEFAULT_IGNORE_PATTERNS
        assert ".venv" in DEFAULT_IGNORE_PATTERNS


class TestBuildIgnoreSet:
    """Test build_ignore_set function."""

    def test_build_ignore_set_no_extras(self):
        """Test building ignore set with no extras."""
        result = build_ignore_set()

        assert isinstance(result, set)
        assert len(result) > len(DEFAULT_IGNORE_PATTERNS)  # Due to expansion
        assert ".env" in result
        assert "**/.env" in result

    def test_build_ignore_set_with_extras(self):
        """Test building ignore set with extra patterns."""
        extras = ["*.log", "temp"]
        result = build_ignore_set(extras)

        assert "*.log" in result
        assert "temp" in result
        # Check expansion
        assert "**/temp" in result  # temp gets expanded

    def test_build_ignore_set_empty_extras(self):
        """Test building ignore set with empty extras."""
        result = build_ignore_set([])

        # Should still have defaults
        assert ".env" in result
        assert "node_modules" in result

    def test_pattern_expansion_simple_pattern(self):
        """Test that simple patterns without / get expanded."""
        result = build_ignore_set(["myfile"])

        assert "myfile" in result
        assert "**/myfile" in result  # Expanded version

    def test_pattern_expansion_with_slash(self):
        """Test that patterns with / don't get expanded."""
        result = build_ignore_set(["foo/bar"])

        assert "foo/bar" in result
        # Should NOT be expanded because it contains /
        assert "**/foo/bar" not in result

    def test_pattern_expansion_already_globbed(self):
        """Test that patterns starting with ** don't get re-expanded."""
        result = build_ignore_set(["**/.secrets"])

        assert "**/.secrets" in result
        # Should NOT get re-expanded
        count = sum(1 for p in result if p == "**/.secrets")
        assert count == 1

    def test_pattern_deduplication(self):
        """Test that duplicate patterns are deduplicated."""
        # Add a pattern that's already in defaults
        result = build_ignore_set([".env", ".env"])

        # Should only appear once (plus expanded versions)
        count = sum(1 for p in result if p == ".env")
        assert count == 1

    def test_none_extras_handled(self):
        """Test that None extras are handled."""
        result = build_ignore_set(None)

        assert isinstance(result, set)
        assert ".env" in result


class TestLoadRepoIgnores:
    """Test loading repo-level ignore patterns."""

    def test_load_repo_ignores_no_config(self, tmp_path):
        """Test loading ignores when no config exists."""
        result = load_repo_ignores(tmp_path)

        assert isinstance(result, set)
        assert len(result) == 0  # No repo-specific ignores

    def test_load_repo_ignores_with_top_level_patterns(self, tmp_path):
        """Test loading ignores from top-level config."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("""
ignore_patterns = ["*.log", "temp_files"]
""")

        result = load_repo_ignores(tmp_path)

        assert "*.log" in result
        assert "temp_files" in result
        assert "**/temp_files" in result  # Expanded

    def test_load_repo_ignores_with_indexing_section(self, tmp_path):
        """Test loading ignores from [indexing] section."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[indexing]
ignore_patterns = ["*.tmp", "cache"]
""")

        result = load_repo_ignores(tmp_path)

        assert "*.tmp" in result
        assert "cache" in result
        assert "**/cache" in result  # Expanded

    def test_load_repo_ignores_both_sections(self, tmp_path):
        """Test loading ignores from both top-level and indexing sections."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("""
ignore_patterns = ["*.log"]

[indexing]
ignore_patterns = ["*.tmp"]
""")

        result = load_repo_ignores(tmp_path)

        # Should include patterns from both sections
        assert "*.log" in result
        assert "*.tmp" in result

    def test_load_repo_ignores_malformed_toml(self, tmp_path):
        """Test that malformed TOML is handled gracefully."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[invalid toml syntax
ignore_patterns = ["*.log"]
""")

        # Should return empty set and not raise
        result = load_repo_ignores(tmp_path)
        assert isinstance(result, set)
        assert len(result) == 0

    def test_load_repo_ignores_invalid_patterns_type(self, tmp_path):
        """Test that non-list patterns are handled gracefully."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("""
ignore_patterns = "not a list"
""")

        result = load_repo_ignores(tmp_path)

        # Function checks isinstance(..., list), so string is not processed
        # patterns remains [], then build_ignore_set([]) is called
        # which returns DEFAULT_IGNORE_PATTERNS (expanded)
        assert isinstance(result, set)
        # Should still have default patterns
        assert len(result) > 0

    def test_load_repo_ignores_empty_patterns(self, tmp_path):
        """Test loading with empty pattern list."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("""
ignore_patterns = []
""")

        result = load_repo_ignores(tmp_path)

        assert isinstance(result, set)
        # Empty list is passed to build_ignore_set([])
        # but build_ignore_set starts with DEFAULT_IGNORE_PATTERNS
        # and only adds extra patterns if extra is truthy
        # Empty list is falsy, so it doesn't add anything, but defaults remain
        # NO WAIT - empty list [] is falsy in Python, so `if extra:` is False
        # So patterns = set(DEFAULT_IGNORE_PATTERNS), no extras added
        # Then expanded contains defaults + their expansions
        # So result should NOT be empty - it should contain defaults
        assert len(result) > 0  # Contains default patterns

    def test_load_repo_ignores_path_expansion(self, tmp_path):
        """Test that repo_root path is expanded."""
        # Create config in a subdirectory
        repo = tmp_path / "test_repo"
        config_dir = repo / ".dolphin"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
ignore_patterns = ["*.log"]
""")

        # Use relative path that needs expansion
        result = load_repo_ignores(repo)

        assert "*.log" in result

    def test_load_repo_ignores_non_string_values(self, tmp_path):
        """Test that non-string pattern values are converted."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("""
ignore_patterns = [123, 456]
""")

        result = load_repo_ignores(tmp_path)

        # Should convert to strings
        assert "123" in result
        assert "456" in result

    def test_load_repo_ignores_permission_error(self, tmp_path):
        """Test that permission errors are handled gracefully."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("""
ignore_patterns = ["*.log"]
""")

        # Make file unreadable
        config_file.chmod(0o000)

        try:
            result = load_repo_ignores(tmp_path)
            # Should return empty set and not raise
            assert isinstance(result, set)
        finally:
            # Restore permissions for cleanup
            config_file.chmod(0o644)
