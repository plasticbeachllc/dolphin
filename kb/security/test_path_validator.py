"""
kb/security/test_path_validator.py

Comprehensive security tests for PathValidator.
"""

import tempfile
from pathlib import Path

import pytest

from .path_validator import PathValidationError, PathValidator


@pytest.fixture
def test_dir():
    """Create a temporary test directory with files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_path = Path(tmpdir)

        # Create test structure
        (test_path / "subdir").mkdir()
        (test_path / "file.txt").write_text("test content")
        (test_path / "file.json").write_text('{"test": true}')
        (test_path / "subdir" / "nested.txt").write_text("nested")

        # Create a symlink for testing
        try:
            (test_path / "symlink.txt").symlink_to(test_path / "file.txt")
        except (OSError, NotImplementedError):
            # Symlink creation might fail on some systems
            pass

        yield test_path


@pytest.fixture
def validator(test_dir):
    """Create a PathValidator instance."""
    return PathValidator(base_dir=test_dir)


class TestPathValidatorConstructor:
    """Test PathValidator constructor."""

    def test_create_validator_with_valid_base_dir(self, test_dir):
        """Should create validator with valid base_dir."""
        validator = PathValidator(base_dir=test_dir)
        assert validator.base_dir == test_dir

    def test_throw_if_base_dir_does_not_exist(self):
        """Should raise if base_dir does not exist."""
        with pytest.raises(ValueError, match="Base directory does not exist"):
            PathValidator(base_dir="/nonexistent/path")

    def test_normalize_base_dir(self, test_dir):
        """Should normalize base_dir."""
        # Add extra slashes
        v = PathValidator(base_dir=str(test_dir) + "///")
        result = v.validate("file.txt")
        assert result.exists()


class TestPathValidatorBasicFunctionality:
    """Test basic path validation functionality."""

    def test_validate_simple_relative_path(self, validator, test_dir):
        """Should validate simple relative path."""
        result = validator.validate("file.txt")
        assert result == test_dir / "file.txt"

    def test_validate_nested_relative_path(self, validator, test_dir):
        """Should validate nested relative path."""
        result = validator.validate("subdir/nested.txt")
        assert result == test_dir / "subdir" / "nested.txt"

    def test_validate_path_with_dot_prefix(self, validator, test_dir):
        """Should validate path with ./ prefix."""
        result = validator.validate("./file.txt")
        assert result == test_dir / "file.txt"

    def test_validate_absolute_path_within_workspace(self, validator, test_dir):
        """Should validate absolute path within workspace."""
        absolute_path = test_dir / "file.txt"
        result = validator.validate(str(absolute_path))
        assert result == absolute_path


class TestPathTraversalAttacks:
    """Test defense against path traversal attacks."""

    def test_reject_simple_parent_directory_traversal(self, validator):
        """Should reject simple parent directory traversal."""
        with pytest.raises(PathValidationError) as exc_info:
            validator.validate("../etc/passwd")
        assert isinstance(exc_info.value, PathValidationError)
        assert exc_info.value.reason == "path_traversal"

    def test_reject_multiple_parent_directory_traversal(self, validator):
        """Should reject multiple parent directory traversal."""
        with pytest.raises(PathValidationError):
            validator.validate("../../etc/passwd")

    def test_reject_traversal_in_middle_of_path(self, validator):
        """Should reject traversal in middle of path."""
        with pytest.raises(PathValidationError):
            validator.validate("subdir/../../etc/passwd")

    def test_reject_complex_traversal_attempt(self, validator):
        """Should reject complex traversal attempt."""
        with pytest.raises(PathValidationError):
            validator.validate("subdir/../../../etc/passwd")

    def test_allow_valid_parent_reference_in_workspace(self, validator, test_dir):
        """Should allow valid parent reference that stays in workspace."""
        result = validator.validate("subdir/../file.txt")
        assert result == test_dir / "file.txt"

    def test_reject_absolute_path_outside_workspace(self, validator):
        """Should reject absolute path outside workspace."""
        with pytest.raises(PathValidationError):
            validator.validate("/etc/passwd")


class TestURLEncodingAttacks:
    """Test defense against URL-encoding attacks."""

    def test_reject_url_encoded_path_traversal(self, validator):
        """Should reject URL-encoded path traversal (%2e%2e/)."""
        with pytest.raises(PathValidationError):
            validator.validate("%2e%2e/etc/passwd")

    def test_reject_double_url_encoded_traversal(self, validator):
        """Should reject double URL-encoded traversal."""
        with pytest.raises(PathValidationError):
            validator.validate("%252e%252e/etc/passwd")

    def test_reject_mixed_encoding_traversal(self, validator):
        """Should reject mixed encoding traversal."""
        with pytest.raises(PathValidationError):
            validator.validate("..%2f..%2fetc/passwd")

    def test_handle_valid_url_encoded_filename(self, validator, test_dir):
        """Should handle valid URL-encoded filename."""
        # Create file with space in name
        file_with_space = test_dir / "file with space.txt"
        file_with_space.write_text("content")

        result = validator.validate("file%20with%20space.txt")
        assert result == file_with_space


class TestNullByteAttacks:
    """Test defense against null byte attacks."""

    def test_reject_path_with_null_byte(self, validator):
        """Should reject path with null byte."""
        with pytest.raises(PathValidationError) as exc_info:
            validator.validate("file.txt\0.jpg")
        assert isinstance(exc_info.value, PathValidationError)
        assert exc_info.value.reason == "null_byte"

    def test_reject_path_with_null_byte_in_middle(self, validator):
        """Should reject path with null byte in middle."""
        with pytest.raises(PathValidationError):
            validator.validate("sub\0dir/file.txt")


class TestSymlinkHandling:
    """Test symlink handling."""

    def test_reject_symlinks_by_default(self, validator, test_dir):
        """Should reject symlinks by default."""
        symlink_path = test_dir / "symlink.txt"
        if not symlink_path.exists():
            pytest.skip("Symlink creation not supported on this system")

        with pytest.raises(PathValidationError) as exc_info:
            validator.validate("symlink.txt")
        assert isinstance(exc_info.value, PathValidationError)
        assert exc_info.value.reason == "symlink"

    def test_allow_symlinks_when_enabled(self, test_dir):
        """Should allow symlinks when enabled."""
        symlink_path = test_dir / "symlink.txt"
        if not symlink_path.exists():
            pytest.skip("Symlink creation not supported on this system")

        v = PathValidator(base_dir=test_dir, allow_symlinks=True)
        result = v.validate("symlink.txt")
        assert result == symlink_path


class TestExistenceChecking:
    """Test path existence checking."""

    def test_allow_nonexistent_paths_by_default(self, validator):
        """Should allow non-existent paths by default."""
        result = validator.validate("nonexistent.txt")
        assert result.name == "nonexistent.txt"

    def test_reject_nonexistent_paths_when_must_exist(self, test_dir):
        """Should reject non-existent paths when must_exist=True."""
        v = PathValidator(base_dir=test_dir, must_exist=True)
        with pytest.raises(PathValidationError) as exc_info:
            v.validate("nonexistent.txt")
        assert isinstance(exc_info.value, PathValidationError)
        assert exc_info.value.reason == "not_found"

    def test_allow_existing_paths_when_must_exist(self, test_dir):
        """Should allow existing paths when must_exist=True."""
        v = PathValidator(base_dir=test_dir, must_exist=True)
        result = v.validate("file.txt")
        assert result == test_dir / "file.txt"


class TestExtensionFiltering:
    """Test file extension filtering."""

    def test_allow_files_with_permitted_extensions(self, test_dir):
        """Should allow files with permitted extensions."""
        v = PathValidator(base_dir=test_dir, allowed_extensions=[".txt", ".json"])

        # Should not raise
        v.validate("file.txt")
        v.validate("file.json")

    def test_reject_files_with_non_permitted_extensions(self, test_dir):
        """Should reject files with non-permitted extensions."""
        v = PathValidator(base_dir=test_dir, allowed_extensions=[".txt"])

        with pytest.raises(PathValidationError) as exc_info:
            v.validate("file.json")
        assert isinstance(exc_info.value, PathValidationError)
        assert exc_info.value.reason == "invalid_extension"

    def test_case_insensitive_for_extensions(self, test_dir):
        """Should be case-insensitive for extensions."""
        v = PathValidator(base_dir=test_dir, allowed_extensions=[".TXT"])
        # Should not raise
        v.validate("file.txt")

    def test_reject_files_with_no_extension_when_extensions_required(self, test_dir):
        """Should reject files with no extension when extensions required."""
        v = PathValidator(base_dir=test_dir, allowed_extensions=[".txt"])

        with pytest.raises(PathValidationError):
            v.validate("noextension")


class TestPatternFiltering:
    """Test filename pattern filtering."""

    def test_reject_filenames_matching_disallowed_patterns(self, test_dir):
        """Should reject filenames matching disallowed patterns."""
        v = PathValidator(base_dir=test_dir, disallowed_patterns=[r"^\.", r".*\.backup$"])

        with pytest.raises(PathValidationError) as exc_info:
            v.validate(".hidden")
        assert isinstance(exc_info.value, PathValidationError)
        assert exc_info.value.reason == "disallowed_pattern"

        with pytest.raises(PathValidationError):
            v.validate("file.backup")

    def test_allow_filenames_not_matching_disallowed_patterns(self, test_dir):
        """Should allow filenames not matching disallowed patterns."""
        v = PathValidator(base_dir=test_dir, disallowed_patterns=[r"^\.", r".*\.backup$"])

        # Should not raise
        v.validate("file.txt")

    def test_check_patterns_against_filename_only(self, test_dir):
        """Should check patterns against filename only, not full path."""
        v = PathValidator(base_dir=test_dir, disallowed_patterns=[r"^subdir$"])

        # Should allow because "nested.txt" doesn't match, even though path contains "subdir"
        result = v.validate("subdir/nested.txt")
        assert result.name == "nested.txt"


class TestCustomErrorMessages:
    """Test custom error messages."""

    def test_use_custom_error_prefix(self, test_dir):
        """Should use custom error prefix."""
        v = PathValidator(base_dir=test_dir, error_prefix="Security violation")

        with pytest.raises(PathValidationError) as exc_info:
            v.validate("../etc/passwd")
        assert "Security violation" in str(exc_info.value)


class TestErrorDetails:
    """Test error details."""

    def test_include_attempted_path_in_error(self, validator):
        """Should include attempted path in error."""
        with pytest.raises(PathValidationError) as exc_info:
            validator.validate("../etc/passwd")
        assert isinstance(exc_info.value, PathValidationError)
        assert exc_info.value.attempted_path == "../etc/passwd"

    def test_include_reason_in_error(self, validator):
        """Should include reason in error."""
        with pytest.raises(PathValidationError) as exc_info:
            validator.validate("../etc/passwd")
        assert isinstance(exc_info.value, PathValidationError)
        assert exc_info.value.reason == "path_traversal"


class TestValidateBatch:
    """Test batch validation."""

    def test_validate_multiple_paths(self, validator, test_dir):
        """Should validate multiple paths."""
        paths = ["file.txt", "subdir/nested.txt", "file.json"]
        results = validator.validate_batch(paths)

        assert len(results) == 3
        assert results[0] == test_dir / "file.txt"
        assert results[1] == test_dir / "subdir" / "nested.txt"
        assert results[2] == test_dir / "file.json"

    def test_raise_on_first_invalid_path(self, validator):
        """Should raise on first invalid path."""
        paths = ["file.txt", "../etc/passwd", "file.json"]

        with pytest.raises(PathValidationError):
            validator.validate_batch(paths)

    def test_handle_empty_array(self, validator):
        """Should handle empty array."""
        results = validator.validate_batch([])
        assert len(results) == 0


class TestCheck:
    """Test check method."""

    def test_return_true_for_valid_path(self, validator):
        """Should return True for valid path."""
        assert validator.check("file.txt") is True

    def test_return_false_for_invalid_path(self, validator):
        """Should return False for invalid path."""
        assert validator.check("../etc/passwd") is False

    def test_not_raise_on_invalid_path(self, validator):
        """Should not raise on invalid path."""
        # Should not raise
        validator.check("../etc/passwd")


class TestStaticValidate:
    """Test static validate method."""

    def test_validate_path_with_oneoff_call(self, test_dir):
        """Should validate path with one-off call."""
        result = PathValidator.validate_static("file.txt", base_dir=test_dir)
        assert result == test_dir / "file.txt"

    def test_raise_on_invalid_path(self, test_dir):
        """Should raise on invalid path."""
        with pytest.raises(PathValidationError):
            PathValidator.validate_static("../etc/passwd", base_dir=test_dir)


class TestRealWorldAttackVectors:
    """Test defense against real-world attack vectors."""

    def test_reject_windows_style_unc_paths(self, validator):
        """Should reject Windows-style UNC paths."""
        # On Unix systems, this will be treated as a relative path with backslashes
        # On Windows, it would be an absolute path
        with pytest.raises(PathValidationError):
            validator.validate("\\\\server\\share\\file")

    def test_reject_unicode_normalization_attacks(self, validator):
        """Should reject Unicode normalization attacks."""
        # U+2024 (one dot leader) looks like "." but is different
        with pytest.raises(PathValidationError):
            validator.validate("\u2024\u2024/etc/passwd")

    def test_handle_paths_with_consecutive_slashes(self, validator, test_dir):
        """Should handle paths with consecutive slashes."""
        # This should resolve correctly
        result = validator.validate("subdir//nested.txt")
        assert result == test_dir / "subdir" / "nested.txt"


class TestEdgeCases:
    """Test edge cases."""

    def test_handle_empty_string(self, validator, test_dir):
        """Should handle empty string."""
        result = validator.validate("")
        # Empty string resolves to base_dir
        assert result == test_dir

    def test_handle_dot_current_directory(self, validator, test_dir):
        """Should handle dot (current directory)."""
        result = validator.validate(".")
        assert result == test_dir

    def test_handle_paths_with_spaces(self, validator, test_dir):
        """Should handle paths with spaces."""
        file_with_spaces = test_dir / "file with spaces.txt"
        file_with_spaces.write_text("content")

        result = validator.validate("file with spaces.txt")
        assert result == file_with_spaces

    def test_handle_paths_with_special_characters(self, validator, test_dir):
        """Should handle paths with special characters."""
        special_file = test_dir / "file-_@#.txt"
        special_file.write_text("content")

        result = validator.validate("file-_@#.txt")
        assert result == special_file

    def test_handle_very_long_paths(self, validator, test_dir):
        """Should handle very long paths."""
        long_name = "a" * 200 + ".txt"
        result = validator.validate(long_name)
        assert result == test_dir / long_name
