from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import KBConfig
from ..store import LanceDBStore, SQLiteMetadataStore


@dataclass
class IngestionPipeline:
    """Coordinates scanning, chunking, and persistence (stub implementation)."""

    config: KBConfig
    lancedb: LanceDBStore
    metadata: SQLiteMetadataStore

    def run(self, repo_name: str, repo_path: Path, *, dry_run: bool = False) -> None:
        """Execute the ingestion pipeline (stub)."""
        _ = (repo_name, repo_path, dry_run)
