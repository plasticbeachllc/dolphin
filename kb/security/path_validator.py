"""
kb/security/path_validator.py

Secure path validator to prevent directory traversal attacks.

Key security features:
- Rejects absolute paths outside base_dir
- Detects path traversal attempts (../)
- Optionally validates symlinks
- Extension and pattern filtering
- URL-encoding attack prevention
"""

import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote


class PathValidationError(Exception):
    """Custom exception for path validation failures."""

    def __init__(self, message: str, attempted_path: str, reason: str):
        super().__init__(message)
        self.attempted_path = attempted_path
        self.reason = reason


class PathValidator:
    """
    Secure path validator to prevent directory traversal attacks.

    Example:
        >>> validator = PathValidator(base_dir="/workspace")
        >>> safe_path = validator.validate("data/file.txt")  # OK
        >>> validator.validate("../etc/passwd")  # Raises PathValidationError
    """

    def __init__(
        self,
        base_dir: str | Path,
        allow_symlinks: bool = False,
        must_exist: bool = False,
        allowed_extensions: list[str] | None = None,
        disallowed_patterns: list[str] | None = None,
        error_prefix: str = "Access denied",
    ):
        """
        Initialize path validator.

        Args:
            base_dir: Base directory - paths must resolve within this directory
            allow_symlinks: Allow symlinks (default: False for security)
            must_exist: Require path to exist (default: False)
            allowed_extensions: Allowed file extensions (e.g., [".txt", ".json"])
            disallowed_patterns: Disallowed filename patterns (regex strings)
            error_prefix: Custom error message prefix
        """
        self.base_dir = Path(base_dir).resolve()
        self.allow_symlinks = allow_symlinks
        self.must_exist = must_exist
        self.allowed_extensions = (
            [ext.lower() for ext in allowed_extensions] if allowed_extensions else None
        )
        self.disallowed_patterns = disallowed_patterns
        self.error_prefix = error_prefix

        # Validate base directory exists
        if not self.base_dir.exists():
            raise ValueError(f"Base directory does not exist: {self.base_dir}")

        if not self.base_dir.is_dir():
            raise ValueError(f"Base directory is not a directory: {self.base_dir}")

    def validate(self, input_path: str | Path) -> Path:
        """
        Validate a single path and return the absolute resolved path.

        Args:
            input_path: Path to validate (relative or absolute)

        Returns:
            Absolute Path object within base_dir

        Raises:
            PathValidationError: If validation fails
        """
        input_str = str(input_path)

        # Reject UNC paths (Windows network paths)
        if input_str.startswith("\\\\") or input_str.startswith("//"):
            raise PathValidationError(
                f"{self.error_prefix}: UNC paths not allowed",
                input_str,
                "unc_path",
            )

        # Normalize backslashes to forward slashes
        normalized = input_str.replace("\\", "/")

        # Unicode normalization to prevent homoglyph attacks
        normalized = unicodedata.normalize("NFKC", normalized)

        # Check for suspicious Unicode characters that might be used in attacks
        # Unicode dot leader (U+2024), for example, should not be in file paths
        suspicious_chars = ["\u2024", "\u2025", "\u2026"]  # Various dot characters
        for char in suspicious_chars:
            if char in normalized:
                raise PathValidationError(
                    f"{self.error_prefix}: suspicious Unicode character in path",
                    input_str,
                    "suspicious_unicode",
                )

        # Decode URL-encoded paths multiple times to prevent double encoding bypass
        decoded_path = normalized
        for _ in range(3):  # Decode up to 3 times to catch double/triple encoding
            try:
                prev = decoded_path
                decoded_path = unquote(decoded_path)
                if decoded_path == prev:
                    break  # No more decoding needed
            except Exception:
                break

        # Reject paths with null bytes (directory traversal technique)
        if "\0" in decoded_path:
            raise PathValidationError(
                f"{self.error_prefix}: null byte in path",
                input_str,
                "null_byte",
            )

        # Convert to Path object
        path_obj = Path(decoded_path)

        # Reject absolute paths that don't start with base_dir
        if path_obj.is_absolute():
            try:
                # Check if absolute path is within workspace
                path_obj.relative_to(self.base_dir)
            except ValueError:
                raise PathValidationError(
                    f"{self.error_prefix}: absolute paths outside workspace not allowed",
                    input_str,
                    "absolute_path_outside_workspace",
                )

        # Resolve path relative to base_dir
        try:
            resolved_path = (self.base_dir / path_obj).resolve()
        except (OSError, RuntimeError) as e:
            raise PathValidationError(
                f"{self.error_prefix}: failed to resolve path: {e}",
                input_str,
                "resolution_failed",
            )

        # Critical: Check if resolved path escapes base_dir
        try:
            resolved_path.relative_to(self.base_dir)
        except ValueError:
            raise PathValidationError(
                f"{self.error_prefix}: path resolves outside workspace (attempted: {input_str})",
                input_str,
                "path_traversal",
            )

        # Check if path exists (if required)
        if self.must_exist and not resolved_path.exists():
            raise PathValidationError(
                f"{self.error_prefix}: path does not exist",
                input_str,
                "not_found",
            )

        # Check for symlinks (if not allowed)
        if not self.allow_symlinks and resolved_path.exists():
            if resolved_path.is_symlink():
                raise PathValidationError(
                    f"{self.error_prefix}: symlinks not allowed",
                    input_str,
                    "symlink",
                )

        # Check file extension (if specified)
        if self.allowed_extensions:
            ext = resolved_path.suffix.lower()
            if ext not in self.allowed_extensions:
                raise PathValidationError(
                    f"{self.error_prefix}: file extension '{ext}' not allowed",
                    input_str,
                    "invalid_extension",
                )

        # Check disallowed patterns (if specified)
        if self.disallowed_patterns:
            filename = resolved_path.name
            for pattern in self.disallowed_patterns:
                if re.match(pattern, filename):
                    raise PathValidationError(
                        f"{self.error_prefix}: filename matches disallowed pattern",
                        input_str,
                        "disallowed_pattern",
                    )

        return resolved_path

    def validate_batch(self, paths: list[str | Path]) -> list[Path]:
        """
        Validate multiple paths in batch.

        Args:
            paths: List of paths to validate

        Returns:
            List of absolute Path objects

        Raises:
            PathValidationError: If any validation fails
        """
        return [self.validate(p) for p in paths]

    def check(self, input_path: str | Path) -> bool:
        """
        Check if a path would be valid without raising an exception.

        Args:
            input_path: Path to check

        Returns:
            True if valid, False otherwise
        """
        try:
            self.validate(input_path)
            return True
        except PathValidationError:
            return False

    @staticmethod
    def validate_static(
        input_path: str | Path,
        base_dir: str | Path,
        **kwargs,
    ) -> Path:
        """
        Static convenience method for one-off validation.

        Args:
            input_path: Path to validate
            base_dir: Base directory for validation
            **kwargs: Additional options (allow_symlinks, must_exist, etc.)

        Returns:
            Absolute Path object within base_dir

        Raises:
            PathValidationError: If validation fails
        """
        validator = PathValidator(base_dir=base_dir, **kwargs)
        return validator.validate(input_path)
