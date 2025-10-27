from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from ..chunkers.types import Chunk
from ..store.sqlite_meta import SQLiteMetadataStore
from ..hashing import hash_text

__all__ = ["ChunkDeduplicator"]

_log = logging.getLogger(__name__)


class ChunkDeduplicator:
    """Manages chunk deduplication via content hashing.

    Compares current chunk hashes against the metadata store and separates
    changed chunks from unchanged chunks. If any error occurs while fetching
    existing hashes or computing a hash, we log a warning and treat the
    affected chunks as changed (safe fallback).
    """

    def __init__(self, store: SQLiteMetadataStore):
        self.store = store

    def get_existing_hashes(self, repo_id: int, file_id: int) -> Dict[Tuple[int, int], str]:
        """Get existing chunk hashes for a file.

        Returns a mapping of (start_line, end_line) -> text_hash.
        On failure to query the store, returns an empty mapping.
        """
        try:
            rows = self.store.get_chunk_hashes_for_file(repo_id, file_id)
        except Exception as e:  # broad: store implementation may raise sqlite3.Error or custom
            _log.warning(
                "Failed to fetch existing chunk hashes for repo_id=%s file_id=%s; treating all as changed: %s",
                repo_id,
                file_id,
                e,
            )
            return {}

        existing: Dict[Tuple[int, int], str] = {}
        for row in rows or []:
            # Support dict-like rows and sqlite3.Row
            try:
                start = int(row["start_line"]) if "start_line" in row.keys() else int(row[0])  # type: ignore[attr-defined]
                end = int(row["end_line"]) if "end_line" in row.keys() else int(row[1])  # type: ignore[attr-defined]
                th = str(row["text_hash"]) if "text_hash" in row.keys() else str(row[2])  # type: ignore[attr-defined]
            except Exception:
                _log.debug("Skipping unexpected row format when reading chunk hashes: %r", row)
                continue

            existing[(start, end)] = th
        return existing

    def filter_unchanged_chunks(
        self, chunks: List[Chunk], repo_id: int, file_id: int
    ) -> Tuple[List[Chunk], List[Chunk]]:
        """Separate changed from unchanged chunks.

        Unchanged means the (start_line, end_line) pair exists with the same text_hash.
        Any failure to compute or compare hashes logs a warning and treats the chunk as changed.
        """
        existing = self.get_existing_hashes(repo_id, file_id)

        changed: List[Chunk] = []
        unchanged: List[Chunk] = []

        for ch in chunks:
            # Ensure the chunk has a text_hash; compute if missing
            if getattr(ch, "text_hash", None) is None:
                try:
                    ch.text_hash = hash_text(ch.text)
                except Exception as e:
                    _log.warning("Failed to obtain hash for input chunk %s-%s: %s", ch.start_line, ch.end_line, e)
                    changed.append(ch)
                    continue

            key = (ch.start_line, ch.end_line)
            existing_hash = existing.get(key)

            if existing_hash is not None and existing_hash == ch.text_hash:
                unchanged.append(ch)
            else:
                changed.append(ch)

        return changed, unchanged
