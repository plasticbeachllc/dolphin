"""Unit tests for path validation security."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from kb.api.utils import GitRepository, normalize_repo_registration_path, validate_path_within_repo


class TestPathValidationSecurity:
    """Test path validation against security vulnerabilities."""

    def test_valid_path_within_repo(self, tmp_path):
        """Test that valid paths within repo are accepted."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        test_file = repo_root / "test.py"
        test_file.write_text("# test")

        result = validate_path_within_repo(test_file, repo_root)
        assert result == test_file.resolve()

    def test_valid_nested_path_within_repo(self, tmp_path):
        """Test that nested paths within repo are accepted."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        nested_dir = repo_root / "src" / "module"
        nested_dir.mkdir(parents=True)

        test_file = nested_dir / "test.py"
        test_file.write_text("# test")

        result = validate_path_within_repo(test_file, repo_root)
        assert result == test_file.resolve()

    def test_reject_path_outside_repo(self, tmp_path):
        """Test that paths outside repo are rejected."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        outside_file = tmp_path / "outside.py"
        outside_file.write_text("# outside")

        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(outside_file, repo_root)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 403
        # PathValidator rejects with "absolute_path_outside_workspace" or "outside workspace"
        assert (
            "workspace" in exc_info.value.detail.lower()
            or "absolute_path_outside_workspace" in exc_info.value.detail.lower()
        )

    def test_reject_parent_directory_traversal(self, tmp_path):
        """Test that parent directory traversal is rejected."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Try to access parent directory using ../
        malicious_path = repo_root / ".." / "secret.txt"

        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(malicious_path, repo_root)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 403

    def test_reject_prefix_attack_similar_names(self, tmp_path):
        """Test rejection of paths with similar prefix names.

        This is the critical security fix: /data/repoA2/secret.txt
        should NOT be accepted for repo root /data/repoA
        """
        # Create two repos with similar names
        repo_a = tmp_path / "repoA"
        repo_a.mkdir()

        repo_a2 = tmp_path / "repoA2"
        repo_a2.mkdir()

        secret_file = repo_a2 / "secret.txt"
        secret_file.write_text("secret data")

        # Try to access repoA2/secret.txt with repoA as root
        # This should be rejected
        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(secret_file, repo_a)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 403
        # PathValidator rejects with "absolute_path_outside_workspace" or "outside workspace"
        assert (
            "workspace" in exc_info.value.detail.lower()
            or "absolute_path_outside_workspace" in exc_info.value.detail.lower()
        )

    def test_reject_prefix_attack_with_suffix(self, tmp_path):
        """Test rejection of paths with prefix plus suffix.

        e.g., /data/repo-backup/file.txt should be rejected
        for repo root /data/repo
        """
        repo = tmp_path / "repo"
        repo.mkdir()

        repo_backup = tmp_path / "repo-backup"
        repo_backup.mkdir()

        backup_file = repo_backup / "file.txt"
        backup_file.write_text("backup")

        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(backup_file, repo)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 403

    def test_reject_prefix_attack_underscore(self, tmp_path):
        """Test rejection with underscore suffix.

        e.g., /data/repo_old/file.txt should be rejected
        for repo root /data/repo
        """
        repo = tmp_path / "repo"
        repo.mkdir()

        repo_old = tmp_path / "repo_old"
        repo_old.mkdir()

        old_file = repo_old / "file.txt"
        old_file.write_text("old")

        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(old_file, repo)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 403

    def test_reject_symlink_outside_repo(self, tmp_path):
        """Test that symlinks pointing outside repo are rejected."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()

        outside_file = outside_dir / "secret.txt"
        outside_file.write_text("secret")

        # Create symlink inside repo pointing to outside file
        symlink = repo_root / "link.txt"
        symlink.symlink_to(outside_file)

        # Should reject because resolved path is outside repo
        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(symlink, repo_root)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 403

    def test_reject_symlink_within_repo(self, tmp_path):
        """Test that symlinks within repo are rejected (allow_symlinks=False by default).

        Even symlinks whose target is within the repo are rejected: the default
        allow_symlinks=False policy eliminates a whole class of symlink-race and
        TOCTOU attacks regardless of where the target currently lives.
        """
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        target_file = repo_root / "target.txt"
        target_file.write_text("target")

        symlink = repo_root / "link.txt"
        symlink.symlink_to(target_file)

        # Should reject because allow_symlinks=False is the secure default
        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(symlink, repo_root)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 403

    def test_reject_absolute_path_outside_repo(self, tmp_path):
        """Test that absolute paths outside repo are rejected."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Try to access /etc/passwd or similar
        system_file = Path("/etc/passwd")

        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(system_file, repo_root)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code in [400, 403]

    def test_reject_nonexistent_path_outside_repo(self, tmp_path):
        """Test that nonexistent paths outside repo are rejected."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        nonexistent = tmp_path / "nonexistent" / "file.txt"

        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(nonexistent, repo_root)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code in [400, 403]

    def test_repo_root_itself_is_valid(self, tmp_path):
        """Test that the repo root itself is a valid path."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        result = validate_path_within_repo(repo_root, repo_root)
        assert result == repo_root.resolve()

    def test_reject_path_with_null_bytes(self, tmp_path):
        """Test that paths with null bytes are rejected."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Path with null byte
        malicious_path = repo_root / "file\x00.txt"

        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(malicious_path, repo_root)

        # PathValidator returns 403 for all validation errors
        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 403

    def test_case_sensitive_path_validation(self, tmp_path):
        """Test path validation respects case sensitivity on case-sensitive filesystems."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        test_file = repo_root / "Test.py"
        test_file.write_text("# test")

        # Should work with exact case
        result = validate_path_within_repo(test_file, repo_root)
        assert result == test_file.resolve()


class TestRepoRegistrationPathNormalization:
    """Test normalization logic used by /v1/repos registration."""

    def test_normalize_repo_path_relative_to_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        normalized = normalize_repo_registration_path("repo")
        assert normalized == (tmp_path / "repo").absolute()

    def test_normalize_repo_path_rejects_traversal_segment(self):
        with pytest.raises(HTTPException) as exc_info:
            normalize_repo_registration_path("../repo")
        assert exc_info.value.status_code == 400

    def test_normalize_repo_path_rejects_null_byte(self):
        with pytest.raises(HTTPException) as exc_info:
            normalize_repo_registration_path("bad\x00path")
        assert exc_info.value.status_code == 400

    def test_normalize_repo_path_expands_user(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        normalized = normalize_repo_registration_path("~/repo")
        assert normalized == (tmp_path / "repo").absolute()

    def test_normalize_path_rejects_non_string(self):
        """normalize_repo_registration_path(123) raises HTTPException(400)."""
        with pytest.raises(HTTPException) as exc_info:
            normalize_repo_registration_path(123)
        assert exc_info.value.status_code == 400

    def test_normalize_path_rejects_whitespace_only(self):
        """normalize_repo_registration_path('   ') raises HTTPException(400)."""
        with pytest.raises(HTTPException) as exc_info:
            normalize_repo_registration_path("   ")
        assert exc_info.value.status_code == 400


class TestValidatePathGenericException:
    """Test generic exception handling in validate_path_within_repo."""

    def test_validate_path_generic_exception_returns_400(self, tmp_path):
        """Patch PathValidator.validate to raise a plain Exception; returns HTTPException(400)."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        test_file = repo_root / "test.py"
        test_file.write_text("# test")

        with patch("kb.api.utils.PathValidator") as mock_validator_class:
            mock_validator_class.return_value.validate.side_effect = Exception("generic error")

            with pytest.raises(HTTPException) as exc_info:
                validate_path_within_repo(test_file, repo_root)
            assert exc_info.value.status_code == 400
            assert "Invalid file path" in exc_info.value.detail


class TestGitRepository:
    """Test GitRepository error paths."""

    def test_git_repository_run_command_failure(self, tmp_path):
        """Patch subprocess.check_output to raise CalledProcessError; _run_command raises RuntimeError."""
        import subprocess

        git_repo = GitRepository(tmp_path)

        with patch("subprocess.check_output") as mock_check:
            mock_check.side_effect = subprocess.CalledProcessError(
                1, ["git", "rev-parse", "HEAD"], output=b"fatal: not a git repo"
            )

            with pytest.raises(RuntimeError, match="Git command failed"):
                git_repo._run_command("rev-parse", "HEAD")

    def test_git_repository_get_commit_and_branch_non_git(self, tmp_path):
        """GitRepository on a non-git dir; get_commit_and_branch returns ('unknown', 'unknown')."""
        git_repo = GitRepository(tmp_path)
        commit, branch = git_repo.get_commit_and_branch()
        assert commit == "unknown"
        assert branch == "unknown"
