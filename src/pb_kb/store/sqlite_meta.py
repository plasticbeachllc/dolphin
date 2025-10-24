from __future__ import annotations

from pathlib import Path


class SQLiteMetadataStore:
    """Placeholder metadata store backed by SQLite."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        """Ensure the metadata directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def record_repo(self, name: str, path: Path) -> None:
        """Stub for recording repository metadata."""
        _ = (name, path)

    def summarize(self) -> dict[str, int]:
        """Return empty summary data."""
        return {"repos": 0, "files": 0, "chunks": 0}
