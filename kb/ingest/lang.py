from __future__ import annotations

from pathlib import Path

# Coarse language tags used by chunkers and storage
# Keep names stable: python | typescript | typescriptreact | javascript | javascriptreact | markdown | json | yaml | toml | shell | just | svelte | text

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".mts": "typescript",
    ".cts": "typescript",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".cjs": "javascript",
    ".mjs": "javascript",
    ".md": "markdown",
    ".markdown": "markdown",
    ".mdx": "markdown",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".just": "just",
    ".svelte": "svelte",
    ".txt": "text",
}

_SPECIAL_FILENAMES: dict[str, str] = {
    "Justfile": "just",
    "README": "text",
    "LICENSE": "text",
    "Makefile": "text",
    "Dockerfile": "text",
}


def classify_language(path: Path) -> tuple[str | None, str]:
    """Return (ext, language) for a given file path.

    - ext is lowercased dot-extension or None if no extension.
    - language is a coarse tag suitable for downstream chunkers.
    """
    name = path.name
    if name in _SPECIAL_FILENAMES:
        return None, _SPECIAL_FILENAMES[name]

    ext = path.suffix.lower() or None
    if ext and ext in _EXT_TO_LANG:
        return ext, _EXT_TO_LANG[ext]
    return ext, "text"
