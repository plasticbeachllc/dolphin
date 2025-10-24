from __future__ import annotations

from pathlib import Path
from typing import Iterable


def scan_repo(root: Path, ignores: Iterable[str]) -> list[Path]:
    """Placeholder scanner that returns an empty candidate list for now."""
    _ = (root, tuple(ignores))
    return []
