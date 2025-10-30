from __future__ import annotations

from typing import Iterable

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
