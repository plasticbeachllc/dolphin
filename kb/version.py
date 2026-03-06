"""Centralized package version lookup."""

from __future__ import annotations


def get_version(fallback: str = "dev") -> str:
    """Return the installed pb-dolphin package version, or *fallback* if unavailable."""
    try:
        from importlib.metadata import version

        return version("pb-dolphin")
    except Exception:
        return fallback
