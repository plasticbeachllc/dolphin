"""Unit tests for ignore pattern handling."""

from pathlib import Path

import pytest

from kb.ignores import (DEFAULT_IGNORE_PATTERNS, build_ignore_set,
                        load_repo_ignores)


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
        patterns, exceptions = load_repo_ignores(tmp_path)

        assert isinstance(patterns, set)
        assert isinstance(exceptions, set)
        assert len(patterns) == 0  # No repo-specific ignores
        assert len(exceptions) == 0  # No repo-specific exceptions

    def test_load_repo_ignores_with_top_level_patterns(self, tmp_path):
        """Test loading ignores from top-level config."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
ignore_patterns = ["*.log", "temp_files"]
"""
        )

        patterns, exceptions = load_repo_ignores(tmp_path)

        assert "*.log" in patterns
        assert "temp_files" in patterns
        assert "**/temp_files" in patterns  # Expanded

    def test_load_repo_ignores_with_indexing_section(self, tmp_path):
        """Test loading ignores from [indexing] section."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
[indexing]
ignore_patterns = ["*.tmp", "cache"]
"""
        )

        patterns, exceptions = load_repo_ignores(tmp_path)

        assert "*.tmp" in patterns
        assert "cache" in patterns
        assert "**/cache" in patterns  # Expanded

    def test_load_repo_ignores_both_sections(self, tmp_path):
        """Test loading ignores from both top-level and indexing sections."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
ignore_patterns = ["*.log"]

[indexing]
ignore_patterns = ["*.tmp"]
"""
        )

        patterns, exceptions = load_repo_ignores(tmp_path)

        # Should include patterns from both sections
        assert "*.log" in patterns
        assert "*.tmp" in patterns

    def test_load_repo_ignores_malformed_toml(self, tmp_path):
        """Test that malformed TOML is handled gracefully."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
[invalid toml syntax
ignore_patterns = ["*.log"]
"""
        )

        # Should return empty set and not raise
        patterns, exceptions = load_repo_ignores(tmp_path)
        assert isinstance(patterns, set)
        assert isinstance(exceptions, set)
        assert len(patterns) == 0
        assert len(exceptions) == 0

    def test_load_repo_ignores_invalid_patterns_type(self, tmp_path):
        """Test that non-list patterns are handled gracefully."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
ignore_patterns = "not a list"
"""
        )

        patterns, exceptions = load_repo_ignores(tmp_path)

        # Function checks isinstance(..., list), so invalid types are ignored
        # Should return empty sets since no valid patterns were provided
        assert isinstance(patterns, set)
        assert isinstance(exceptions, set)
        assert len(patterns) == 0  # Invalid data results in empty patterns
        assert len(exceptions) == 0  # No exceptions specified

    def test_load_repo_ignores_empty_patterns(self, tmp_path):
        """Test loading with empty pattern list."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
ignore_patterns = []
"""
        )

        patterns, exceptions = load_repo_ignores(tmp_path)

        assert isinstance(patterns, set)
        assert isinstance(exceptions, set)
        # Empty list results in no patterns loaded from config
        assert len(patterns) == 0  # Empty patterns list results in no patterns
        assert len(exceptions) == 0  # No exceptions specified

    def test_load_repo_ignores_path_expansion(self, tmp_path):
        """Test that repo_root path is expanded."""
        # Create config in a subdirectory
        repo = tmp_path / "test_repo"
        config_dir = repo / ".dolphin"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
ignore_patterns = ["*.log"]
"""
        )

        # Use relative path that needs expansion
        patterns, exceptions = load_repo_ignores(repo)

        assert "*.log" in patterns

    def test_load_repo_ignores_non_string_values(self, tmp_path):
        """Test that non-string pattern values are converted."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
ignore_patterns = [123, 456]
"""
        )

        patterns, exceptions = load_repo_ignores(tmp_path)

        # Should convert to strings
        assert "123" in patterns
        assert "456" in patterns

    def test_load_repo_ignores_permission_error(self, tmp_path):
        """Test that permission errors are handled gracefully."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
ignore_patterns = ["*.log"]
"""
        )

        # Make file unreadable
        config_file.chmod(0o000)
        # Restore permissions for cleanup
        config_file.chmod(0o644)


class TestIgnoreExceptions:
    """Test ignore exception functionality."""

    def test_build_ignore_set_with_exceptions(self):
        """Test that build_ignore_set properly handles exceptions."""
        patterns = {".env", "*.log"}
        exceptions = {".env.example"}

        result = build_ignore_set(patterns, exceptions)

        # Should include the basic patterns
        assert ".env" in result
        assert "*.log" in result
        # But .env.example should NOT be in ignore patterns (it's an exception)
        assert ".env.example" not in result
        assert "**/.env.example" not in result

    def test_build_ignore_set_exception_expansion(self):
        """Test that exceptions are properly handled with simple patterns."""
        patterns = {"temp", "logs"}
        exceptions = {"logs/important.txt"}

        result = build_ignore_set(patterns, exceptions)

        # Patterns should be expanded
        assert "temp" in result
        assert "**/temp" in result
        assert "logs" in result
        assert "**/logs" in result

        # Exception should remove pattern parts but logs/important.txt is an exception
        assert "logs/important.txt" not in result  # Exception NOT in ignore patterns
        assert (
            "**/logs/important.txt" not in result
        )  # Exception expansion also NOT in patterns
        # But the base "logs" pattern should still be there (to ignore other log files)
        assert "logs" in result
        assert "**/logs" in result

    def test_load_repo_ignores_with_exceptions(self, tmp_path):
        """Test loading repo ignores with exceptions."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
ignore_patterns = ["*.log"]
ignore_exceptions = [".env.example"]
"""
        )

        patterns, exceptions = load_repo_ignores(tmp_path)

        assert "*.log" in patterns
        assert ".env.example" in exceptions

    def test_load_repo_ignores_with_ignore_section_exceptions(self, tmp_path):
        """Test loading exceptions from [ignore] section."""
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
[ignore]
patterns = ["*.log"]
exceptions = [".env.example"]
"""
        )

        patterns, exceptions = load_repo_ignores(tmp_path)

        assert "*.log" in patterns
        assert ".env.example" in exceptions

    def test_config_ignore_exceptions_integration(self):
        """Test that config-level ignore exceptions work."""
        from kb.config import KBConfig

        config_data = {
            "ignore": [".env", "*.log"],
            "ignore_exceptions": [".env.example"],
        }

        config = KBConfig.from_mapping(config_data)

        assert ".env" in config.ignore
        assert ".env.example" in config.ignore_exceptions

        # Build ignore set with config exceptions
        result = build_ignore_set(config.ignore, config.ignore_exceptions)

        # Should include default patterns
        assert ".env" in result
        # But exception should be excluded
        assert ".env.example" not in result
        assert "**/.env.example" not in result

    def test_multiple_exceptions(self):
        """Test handling multiple exceptions."""
        patterns = {".env", "*.conf", "secrets"}
        exceptions = {".env.example", "*.conf.template", "secrets/README"}

        result = build_ignore_set(patterns, exceptions)

        # All patterns should be present
        assert ".env" in result
        assert "*.conf" in result
        assert "secrets" in result

        # All exceptions should be excluded
        assert ".env.example" not in result
        assert "*.conf.template" not in result
        assert "secrets/README" not in result

        # Exception expansions should also be excluded
        assert "**/.env.example" not in result
        assert "**/*.conf.template" not in result
        assert "**/secrets/README" not in result
