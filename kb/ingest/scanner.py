from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, List

from pathspec import PathSpec

from .lang import classify_language


@dataclass(slots=True)
class FileCandidate:
    repo_root: Path
    rel_path: str  # POSIX
    abs_path: Path
    ext: str | None
    language: str
    size_bytes: int
    is_binary: bool


class ScannerError(RuntimeError):
    pass


def _git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        raise ScannerError(e.output.decode("utf-8", errors="ignore"))


def _list_tracked(root: Path) -> list[str]:
    """List files respecting .gitignore patterns.
    
    Uses git ls-files with:
    - --cached: Include tracked files
    - --others: Include untracked files
    - --exclude-standard: Respect .gitignore, .git/info/exclude, and global excludes
    - -z: NUL-separated output for safe parsing
    
    This ensures we respect .gitignore even for files that were previously committed
    but are now in .gitignore.
    """
    out = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    items = [p for p in out.split(b"\x00") if p]
    return [PurePosixPath(p.decode("utf-8")).as_posix() for p in items]


def _submodule_roots(root: Path) -> list[str]:
    try:
        out = _git(root, "submodule", "status", "--recursive")
    except ScannerError:
        return []
    prefixes: list[str] = []
    for line in out.decode("utf-8", errors="ignore").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            rel = PurePosixPath(parts[1]).as_posix()
            if not rel.endswith("/"):
                rel = f"{rel}/"
            prefixes.append(rel)
    return prefixes


def _build_pathspec(ignores: Iterable[str]) -> PathSpec:
    patterns = list(ignores or [])
    return PathSpec.from_lines("gitwildmatch", patterns)


def _is_binary(path: Path, sniff_bytes: int = 65536) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(sniff_bytes)
        # Fast NUL-byte heuristic
        if b"\x00" in chunk:
            return True
        # UTF-8 decode check
        chunk.decode("utf-8")
        return False
    except Exception:
        return True


def scan_repo(root: Path, ignores: Iterable[str]) -> List[FileCandidate]:
    """Scan a git repo for candidate files with language tagging.

    - Uses `git ls-files` to respect .gitignore implicitly.
    - Applies additional ignore patterns via pathspec.
    - Skips submodules, symlinks, and binary files.
    """
    root = root.expanduser().resolve()
    if not (root / ".git").exists():
        raise ScannerError(f"Not a git repository: {root}")

    rel_paths = _list_tracked(root)
    submods = _submodule_roots(root)
    spec = _build_pathspec(ignores)

    candidates: List[FileCandidate] = []
    for rel in rel_paths:
        # Skip submodules
        if any(rel.startswith(prefix) for prefix in submods):
            continue
        # Skip by pathspec
        if spec.match_file(rel):
            continue
        abs_path = (root / rel).resolve()
        # Skip symlinks
        if abs_path.is_symlink():
            continue
        # Skip non-files
        if not abs_path.is_file():
            continue
        # Binary detection
        is_bin = _is_binary(abs_path)
        if is_bin:
            continue
        # Size
        try:
            size = abs_path.stat().st_size
        except OSError:
            continue
        # Language
        _, language = classify_language(Path(rel))
        ext = Path(rel).suffix.lower() or None
        candidates.append(
            FileCandidate(
                repo_root=root,
                rel_path=rel,
                abs_path=abs_path,
                ext=ext,
                language=language,
                size_bytes=size,
                is_binary=is_bin,
            )
        )

    return candidates
