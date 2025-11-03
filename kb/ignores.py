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
    ".continue",
    ".continue/**",
    ".continue-config",
    ".continue-config/**",
    ".kilocode-config",
    ".kilocode-config/**",
)


def build_ignore_set(extra: Iterable[str] | None = None, exceptions: Iterable[str] | None = None) -> set[str]:
    """Return the default ignore patterns merged with any extras, excluding exceptions."""
    patterns = set(DEFAULT_IGNORE_PATTERNS)
    if extra:
        patterns.update(extra)
    
    # Start with expanded patterns
    expanded: set[str] = set()
    for pattern in patterns:
        expanded.add(pattern)
        if "/" not in pattern and not pattern.startswith("**"):
            expanded.add(f"**/{pattern}")
    
    # Remove exception patterns from the final set (exceptions should NOT be ignored)
    if exceptions:
        for exception in exceptions:
            expanded.discard(exception)
            # Also remove the expanded version if it was created
            if "/" not in exception and not exception.startswith("**"):
                expanded.discard(f"**/{exception}")
    
    return expanded


def load_repo_ignores(repo_root: Path) -> tuple[set[str], set[str]]:
    """Load repo-level ignore patterns from .dolphin/config.toml if present.

    Looks for patterns in:
    - `ignore = [..]` (top-level array)
    - `ignore_patterns = [..]` (top-level array)
    - `[ignore] patterns = [..]` (section with patterns key)
    - `ignore_exceptions = [..]` or `[ignore] exceptions = [..]`
    - `[indexing] ignore_patterns = [..]`
    - `[indexing] ignore_exceptions = [..]`
    
    Returns:
        Tuple of (ignore_patterns, exception_patterns)
    """
    repo_root = repo_root.expanduser().resolve()
    cfg = repo_root / ".dolphin" / "config.toml"
    if not cfg.exists():
        return set(), set()
    try:
        with cfg.open("rb") as fh:
            data = tomllib.load(fh) or {}
        patterns: list[str] = []
        exceptions: list[str] = []
        
        # Check top-level arrays first
        if isinstance(data.get("ignore"), list):
            patterns.extend([str(x) for x in data.get("ignore", [])])
        if isinstance(data.get("ignore_patterns"), list):
            patterns.extend([str(x) for x in data.get("ignore_patterns", [])])
        if isinstance(data.get("ignore_exceptions"), list):
            exceptions.extend([str(x) for x in data.get("ignore_exceptions", [])])
            
        # Check for [ignore] section (only if it's a dict, not an array)
        ignore_section = data.get("ignore")
        if isinstance(ignore_section, dict):
            if isinstance(ignore_section.get("patterns"), list):
                patterns.extend([str(x) for x in ignore_section.get("patterns", [])])
            if isinstance(ignore_section.get("exceptions"), list):
                exceptions.extend([str(x) for x in ignore_section.get("exceptions", [])])
            
        # Check indexing section
        indexing = data.get("indexing") or {}
        if isinstance(indexing.get("ignore_patterns"), list):
            patterns.extend([str(x) for x in indexing.get("ignore_patterns", [])])
        if isinstance(indexing.get("ignore_exceptions"), list):
            exceptions.extend([str(x) for x in indexing.get("ignore_exceptions", [])])
            
        # If no patterns were loaded, fall back to empty (let caller decide)
        # but don't use defaults - this is repo-level configuration
        expanded_patterns: set[str] = set()
        for pattern in patterns:
            expanded_patterns.add(pattern)
            if "/" not in pattern and not pattern.startswith("**"):
                expanded_patterns.add(f"**/{pattern}")
                
        # Expand exceptions
        expanded_exceptions: set[str] = set()
        for exception in exceptions:
            expanded_exceptions.add(exception)
            if "/" not in exception and not exception.startswith("**"):
                expanded_exceptions.add(f"**/{exception}")
            
        return expanded_patterns, expanded_exceptions
    except Exception:
        # On parse issues, fail closed (no additional repo ignores)
        _log.warning("Failed to load repo ignore configuration from %s", cfg, exc_info=True)
        return set(), set()
