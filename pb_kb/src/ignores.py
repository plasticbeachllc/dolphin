from __future__ import annotations

import logging
from typing import Iterable
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found]

_log = logging.getLogger(__name__)

DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    ".secrets",
    "**/.env",
    "**/.env.*",
    "**/.secrets",
    "node_modules",
    "node_modules/**",
    ".npm",
    ".pnpm-store",
    ".yarn",
    ".yarn/cache",
    "dist",
    "dist/**",
    "build",
    "build/**",
    "coverage",
    "coverage/**",
    ".cache",
    ".cache/**",
    "target",
    "target/**",
    "vendor",
    "vendor/**",
    ".svelte-kit",
    ".svelte-kit/**",
    ".vercel",
    ".vercel/**",
    ".vite",
    ".vite/**",
    ".next",
    ".next/**",
    ".venv",
    ".venv/**",
    ".mypy_cache",
    ".mypy_cache/**",
    ".pytest_cache",
    ".pytest_cache/**",
    ".DS_Store",
    "**/.DS_Store",
)


def build_ignore_set(extra: Iterable[str] | None = None) -> set[str]:
    """Return the default ignore patterns merged with any extras."""
    patterns = set(DEFAULT_IGNORE_PATTERNS)
    if extra:
        patterns.update(extra)
    expanded: set[str] = set()
    for pattern in patterns:
        expanded.add(pattern)
        if "/" not in pattern and not pattern.startswith("**"):
            expanded.add(f"**/{pattern}")
    return expanded


def load_repo_ignores(repo_root: Path) -> set[str]:
    """Load repo-level ignore patterns from .dolphin/config.toml if present.

    Looks for either a top-level `ignore_patterns = [..]` array or an
    `[indexing] ignore_patterns = [..]` table within the file.
    """
    repo_root = repo_root.expanduser().resolve()
    cfg = repo_root / ".dolphin" / "config.toml"
    if not cfg.exists():
        return set()
    try:
        with cfg.open("rb") as fh:
            data = tomllib.load(fh) or {}
        patterns: list[str] = []
        
        # Look for ignore_patterns in top-level or indexing section
        if isinstance(data.get("ignore_patterns"), list):
            patterns.extend([str(x) for x in data.get("ignore_patterns", [])])
            
        indexing = data.get("indexing") or {}
        if isinstance(indexing.get("ignore_patterns"), list):
            patterns.extend([str(x) for x in indexing.get("ignore_patterns", [])])
            
        return build_ignore_set(patterns)
    except Exception:
        # On parse issues, fail closed (no additional repo ignores)
        _log.warning("Failed to load repo ignore configuration from %s", cfg, exc_info=True)
        return set()
