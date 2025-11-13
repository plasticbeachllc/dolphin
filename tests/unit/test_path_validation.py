"""Unit tests for path validation security."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from kb.api.utils import validate_path_within_repo


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

        assert exc_info.value.status_code == 403
        assert "outside repository" in exc_info.value.detail.lower()

    def test_reject_parent_directory_traversal(self, tmp_path):
        """Test that parent directory traversal is rejected."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Try to access parent directory using ../
        malicious_path = repo_root / ".." / "secret.txt"

        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(malicious_path, repo_root)

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

        assert exc_info.value.status_code == 403
        assert "outside repository" in exc_info.value.detail.lower()

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

        assert exc_info.value.status_code == 403

    def test_accept_symlink_within_repo(self, tmp_path):
        """Test that symlinks pointing within repo are accepted."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        target_file = repo_root / "target.txt"
        target_file.write_text("target")

        symlink = repo_root / "link.txt"
        symlink.symlink_to(target_file)

        # Should accept because resolved path is within repo
        result = validate_path_within_repo(symlink, repo_root)
        assert result == target_file.resolve()

    def test_reject_absolute_path_outside_repo(self, tmp_path):
        """Test that absolute paths outside repo are rejected."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Try to access /etc/passwd or similar
        system_file = Path("/etc/passwd")

        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(system_file, repo_root)

        assert exc_info.value.status_code in [400, 403]

    def test_reject_nonexistent_path_outside_repo(self, tmp_path):
        """Test that nonexistent paths outside repo are rejected."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        nonexistent = tmp_path / "nonexistent" / "file.txt"

        with pytest.raises(HTTPException) as exc_info:
            validate_path_within_repo(nonexistent, repo_root)

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

        assert exc_info.value.status_code == 400

    def test_case_sensitive_path_validation(self, tmp_path):
        """Test path validation respects case sensitivity on case-sensitive filesystems."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        test_file = repo_root / "Test.py"
        test_file.write_text("# test")

        # Should work with exact case
        result = validate_path_within_repo(test_file, repo_root)
        assert result == test_file.resolve()
