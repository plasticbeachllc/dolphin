"""Utility functions for API endpoints."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import HTTPException

from kb.security import PathValidator, PathValidationError


def validate_path_within_repo(file_path: Path, repo_root: Path) -> Path:
    """Validate that file_path is within repo_root, return resolved path.

    Args:
        file_path: The file path to validate
        repo_root: The repository root directory

    Returns:
        The resolved absolute path

    Raises:
        HTTPException: If path is outside repository or invalid
    """
    try:
        # Use PathValidator for secure path validation
        validator = PathValidator(base_dir=repo_root)
        resolved_path = validator.validate(file_path)
        return resolved_path
    except PathValidationError as e:
        raise HTTPException(
            status_code=403, detail=f"Path validation failed: {e.reason} - {file_path}"
        )
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid file path: {file_path}")


class GitRepository:
    """Helper class for Git operations on a repository."""

    def __init__(self, root: Path):
        """Initialize GitRepository with a root path.

        Args:
            root: The root directory of the Git repository
        """
        self.root = root

    def _run_command(self, *args: str) -> str:
        """Run a git command and return its output.

        Args:
            *args: Git command arguments (e.g., 'rev-parse', 'HEAD')

        Returns:
            The command output as a string

        Raises:
            RuntimeError: If the git command fails
        """
        try:
            result = subprocess.check_output(
                ["git", "-C", str(self.root), *args], stderr=subprocess.STDOUT
            )
            return result.decode("utf-8").strip()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Git command failed: {' '.join(args)}\n"
                f"{e.output.decode('utf-8', errors='ignore')}"
            )

    def get_current_commit(self) -> str:
        """Get the current commit SHA.

        Returns:
            The current commit SHA
        """
        return self._run_command("rev-parse", "HEAD")

    def get_current_branch(self) -> str:
        """Get the current branch name.

        Returns:
            The current branch name
        """
        return self._run_command("rev-parse", "--abbrev-ref", "HEAD")

    def get_commit_and_branch(self) -> tuple[str, str]:
        """Get both commit SHA and branch name.

        Returns:
            Tuple of (commit_sha, branch_name)
        """
        try:
            commit_sha = self.get_current_commit()
            branch = self.get_current_branch()
            return commit_sha, branch
        except RuntimeError:
            # Non-git repo or git not available
            return "unknown", "unknown"
