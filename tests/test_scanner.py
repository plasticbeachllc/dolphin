from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from pb_kb.ingest.scanner import ScannerError, scan_repo
from pb_kb.ignores import build_ignore_set


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args]).decode("utf-8")


def _init_git_repo(tmp: Path) -> None:
    _git(tmp, "init")
    _git(tmp, "config", "user.email", "you@example.com")
    _git(tmp, "config", "user.name", "Your Name")


def _write(p: Path, content: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def _test_scanner_basic(root: Path) -> None:
    _init_git_repo(root)
    # Create files
    _write(root / "src" / "app.py", b"print('hello')\n")
    _write(root / "src" / "app.ts", b"export const x = 1;\n")
    _write(root / "docs" / "readme.md", b"# Title\ntext\n")
    _write(root / "README", b"plain readme\n")
    _write(root / ".env", b"SECRET=1\n")  # should be excluded by extra ignores
    _write(root / "bin" / "image.bin", b"\x00\x01\x02\x03")  # binary
    (root / "link.md").symlink_to(root / "docs" / "readme.md")  # symlink

    _git(root, "add", "src/app.py", "src/app.ts", "docs/readme.md", "README", ".env")
    _git(root, "commit", "-m", "init")

    ignores = build_ignore_set({".env"})
    results = scan_repo(root, ignores)

    rels = {c.rel_path for c in results}
    assert "src/app.py" in rels
    assert "src/app.ts" in rels
    assert "docs/readme.md" in rels
    assert "README" in rels
    assert ".env" not in rels
    assert "bin/image.bin" not in rels
    assert "link.md" not in rels

    langs = {c.rel_path: c.language for c in results}
    assert langs["src/app.py"] == "python"
    assert langs["src/app.ts"] == "typescript"
    assert langs["docs/readme.md"] == "markdown"
    assert langs["README"] == "text"


def _test_scanner_untracked_and_gitignore(root: Path) -> None:
    _init_git_repo(root)
    (root / ".gitignore").write_text("node_modules\ndist\n", encoding="utf-8")
    (root / "src" / "ok.py").parent.mkdir(parents=True, exist_ok=True)
    (root / "src" / "ok.py").write_text("pass\n", encoding="utf-8")
    (root / "node_modules" / "pkg" / "a.js").parent.mkdir(parents=True, exist_ok=True)
    (root / "node_modules" / "pkg" / "a.js").write_text("console.log(1)\n", encoding="utf-8")

    _git(root, "add", "src/ok.py")
    _git(root, "commit", "-m", "add ok")

    ignores = build_ignore_set()
    results = scan_repo(root, ignores)
    rels = {c.rel_path for c in results}

    assert "node_modules/pkg/a.js" not in rels
    assert "src/ok.py" in rels


def _test_scanner_submodule_skipped(root: Path) -> None:
    super_root = root / "super"
    sub_root = root / "sub"
    super_root.mkdir(); sub_root.mkdir()
    _init_git_repo(super_root); _init_git_repo(sub_root)

    (sub_root / "sub.txt").write_text("hi\n", encoding="utf-8")
    _git(sub_root, "add", "sub.txt"); _git(sub_root, "commit", "-m", "sub init")

    _git(super_root, "-c", "protocol.file.allow=always", "submodule", "add", str(sub_root), "vendor/sub")
    _git(super_root, "commit", "-m", "add submodule")

    ignores = build_ignore_set()
    results = scan_repo(super_root, ignores)
    rels = {c.rel_path for c in results}
    assert not any(p.startswith("vendor/sub/") for p in rels)


def _test_scanner_not_a_git_repo(root: Path) -> None:
    root.mkdir()
    try:
        scan_repo(root, build_ignore_set())
        assert False, "Expected ScannerError"
    except ScannerError as e:
        assert "Not a git repository" in str(e)


def run_test(base_url: str) -> None:
    _ = base_url
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # basic
        repo1 = tmp / "repo1"
        repo1.mkdir()
        _test_scanner_basic(repo1)
        # untracked + .gitignore
        repo2 = tmp / "repo2"
        repo2.mkdir()
        _test_scanner_untracked_and_gitignore(repo2)
        # submodule
        _test_scanner_submodule_skipped(tmp)
        # not a git repo
        _test_scanner_not_a_git_repo(tmp / "nogit")
