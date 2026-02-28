"""Helpers for managing the per-user KB API key."""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

KB_API_KEY_FILENAME = "kb_api_key"


def get_kb_key_path() -> Path:
    """Return the canonical path to the KB API key file (~/.dolphin/kb_api_key)."""
    return Path.home() / ".dolphin" / KB_API_KEY_FILENAME


def _env_override() -> str | None:
    """Return API key from environment if set."""
    for name in ("DOLPHIN_API_KEY", "DOLPHIN_KB_API_KEY"):
        value = os.environ.get(name)
        if value:
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def load_kb_api_key() -> str | None:
    """Load KB API key without creating it."""
    env_val = _env_override()
    if env_val:
        return env_val

    path = get_kb_key_path()
    if not path.exists():
        return None

    data = path.read_text(encoding="utf-8").strip()
    return data or None


def get_or_create_kb_api_key() -> str:
    """Load existing KB API key or create a new high-entropy key."""
    env_val = _env_override()
    if env_val:
        return env_val

    path = get_kb_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        data = path.read_text(encoding="utf-8").strip()
        if data:
            return data

    key = secrets.token_hex(32)  # 64 hex characters

    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(key + "\n")
        try:
            os.chmod(path, 0o600)
        except OSError:
            logger.warning(
                "Could not set restrictive permissions on API key file %s; file may be readable by other users",
                path,
            )
        return key
    except FileExistsError:
        # Another process created it – read and return value if possible.
        data = path.read_text(encoding="utf-8").strip()
        return data or key
