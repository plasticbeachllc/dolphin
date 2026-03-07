"""Centralized package version lookup."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version


def get_version(fallback: str = "dev") -> str:
    """Return the installed pb-dolphin package version, or *fallback* if unavailable."""
    try:
        return _pkg_version("pb-dolphin")
    except PackageNotFoundError:
        return fallback
