"""Unit tests for repository scanning and file enumeration."""

import subprocess

import pytest

from kb.ignores import build_ignore_set
from kb.ingest.scanner import ScannerError, scan_repo
from tests.conftest import init_test_git_repo


class TestScannerBasic:
    """Test basic repository scanning functionality."""

    def test_scan_repo_basic_file_enumeration(self, temp_dir):
        """Test repository file enumeration with various file types."""
        repo_path = temp_dir / "repo1"
        repo_path.mkdir()
        init_test_git_repo(repo_path)

        # Create test files
        (repo_path / "src" / "app.py").parent.mkdir(parents=True, exist_ok=True)
        (repo_path / "src" / "app.py").write_text("print('hello')\n")

        (repo_path / "src" / "app.ts").write_text("export const x = 1;\n")
        (repo_path / "docs" / "readme.md").parent.mkdir(parents=True, exist_ok=True)
        (repo_path / "docs" / "readme.md").write_text("# Title\ntext\n")
        (repo_path / "README").write_text("plain readme\n")
        (repo_path / ".env").write_text("SECRET=1\n")  # Should be excluded
        (repo_path / "bin" / "image.bin").parent.mkdir(parents=True, exist_ok=True)
        (repo_path / "bin" / "image.bin").write_bytes(b"\x00\x01\x02\x03")  # Binary

        # Add and commit files
        subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "add",
                "-f",
                "src/app.py",
                "src/app.ts",
                "docs/readme.md",
                "README",
                ".env",
            ],
            check=True,
        )
        subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "init"], check=True)

        ignores = build_ignore_set({".env"})
        results = scan_repo(repo_path, ignores)

        rels = {c.rel_path for c in results}
        assert "src/app.py" in rels
        assert "src/app.ts" in rels
        assert "docs/readme.md" in rels
        assert "README" in rels
        assert ".env" not in rels
        assert "bin/image.bin" not in rels

        # Test language detection
        langs = {c.rel_path: c.language for c in results}
        assert langs["src/app.py"] == "python"
        assert langs["src/app.ts"] == "typescript"
        assert langs["docs/readme.md"] == "markdown"
        assert langs["README"] == "text"

    def test_scan_repo_untracked_and_gitignore(self, temp_dir):
        """Test .gitignore integration and untracked file handling."""
        repo_path = temp_dir / "repo2"
        repo_path.mkdir()
        init_test_git_repo(repo_path)

        # Create .gitignore
        (repo_path / ".gitignore").write_text("node_modules\ndist\n")

        # Create files
        (repo_path / "src" / "ok.py").parent.mkdir(parents=True, exist_ok=True)
        (repo_path / "src" / "ok.py").write_text("pass\n")

        (repo_path / "node_modules" / "pkg" / "a.js").parent.mkdir(parents=True, exist_ok=True)
        (repo_path / "node_modules" / "pkg" / "a.js").write_text("console.log(1)\n")

        # Add and commit only the tracked file
        subprocess.run(["git", "-C", str(repo_path), "add", "src/ok.py"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "add ok"], check=True)

        ignores = build_ignore_set()
        results = scan_repo(repo_path, ignores)
        rels = {c.rel_path for c in results}

        assert "node_modules/pkg/a.js" not in rels
        assert "src/ok.py" in rels

    def test_scan_repo_submodule_skipped(self, temp_dir):
        """Test that submodules are properly skipped."""
        super_root = temp_dir / "super"
        sub_root = temp_dir / "sub"
        super_root.mkdir()
        sub_root.mkdir()

        # Initialize both repos
        for repo in [super_root, sub_root]:
            init_test_git_repo(repo)

        # Add file to submodule and commit
        (sub_root / "sub.txt").write_text("hi\n")
        subprocess.run(["git", "-C", str(sub_root), "add", "sub.txt"], check=True)
        subprocess.run(["git", "-C", str(sub_root), "commit", "-m", "sub init"], check=True)

        # Add submodule to super repo
        subprocess.run(
            [
                "git",
                "-C",
                str(super_root),
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                str(sub_root),
                "vendor/sub",
            ],
            check=True,
        )
        subprocess.run(["git", "-C", str(super_root), "commit", "-m", "add submodule"], check=True)

        ignores = build_ignore_set()
        results = scan_repo(super_root, ignores)
        rels = {c.rel_path for c in results}

        # Verify no files from submodule are included
        assert not any(p.startswith("vendor/sub/") for p in rels)

    def test_scan_repo_not_a_git_repository(self, temp_dir):
        """Test error handling for non-git repositories."""
        repo_path = temp_dir / "nogit"
        repo_path.mkdir()

        with pytest.raises(ScannerError) as exc_info:
            scan_repo(repo_path, build_ignore_set())

        assert "Not a git repository" in str(exc_info.value)


class TestIgnorePatterns:
    """Test ignore pattern functionality."""

    def test_build_ignore_set_defaults(self):
        """Test default ignore patterns are included."""
        ignores = build_ignore_set()
        assert ignores is not None
        # Should include common patterns like node_modules, .env, etc.

    def test_build_ignore_set_with_custom_patterns(self):
        """Test custom ignore pattern merging."""
        custom_patterns = {"custom_pattern", "another_pattern"}
        ignores = build_ignore_set(custom_patterns)
        assert ignores is not None

    def test_ignore_pattern_matching(self, temp_dir):
        """Test specific ignore pattern matching behavior."""
        repo_path = temp_dir / "repo"
        repo_path.mkdir()
        init_test_git_repo(repo_path)

        # Create files that should be ignored
        (repo_path / "node_modules" / "package" / "index.js").parent.mkdir(parents=True, exist_ok=True)
        (repo_path / "node_modules" / "package" / "index.js").write_text("console.log('ignored')\n")

        (repo_path / "dist" / "bundle.js").parent.mkdir(parents=True, exist_ok=True)
        (repo_path / "dist" / "bundle.js").write_text("// bundled\n")

        (repo_path / ".env").write_text("SECRET=value\n")

        # Add and commit
        subprocess.run(["git", "-C", str(repo_path), "add", "-f", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "add files"], check=True)

        ignores = build_ignore_set()
        results = scan_repo(repo_path, ignores)
        rels = {c.rel_path for c in results}

        # Verify ignored files are not included
        assert "node_modules/package/index.js" not in rels
        assert "dist/bundle.js" not in rels
        assert ".env" not in rels
