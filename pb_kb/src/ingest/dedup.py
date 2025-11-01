from __future__ import annotations

import logging
from typing import List, Tuple, Set

from ..chunkers.types import Chunk
from ..store.sqlite_meta import SQLiteMetadataStore
from ..hashing import hash_text

__all__ = ["ChunkDeduplicator"]

_log = logging.getLogger(__name__)


class ChunkDeduplicator:
    """Manages chunk deduplication via content hashing.

    Uses text-hash-only deduplication (ignores locations) to decide which
    chunks require embedding. This is robust to chunks moving within a file.

    On any error fetching existing hashes or computing a hash, we log a
    warning and treat the affected chunks as changed (safe fallback).
    """

    def __init__(self, store: SQLiteMetadataStore):
        self.store = store

    def get_existing_hashes_set(self, repo_id: int, file_id: int, embed_model: str) -> Set[str]:
        """Return the set of existing text hashes for a file+model.

        On failure to query the store, returns an empty set (conservative).
        """
        try:
            return self.store.get_existing_content_hashes_for_file(repo_id, file_id, embed_model)
        except Exception as e:
            _log.warning(
                "Failed to fetch existing hashes for repo_id=%s file_id=%s model=%s; treating all as changed: %s",
                repo_id,
                file_id,
                embed_model,
                e,
            )
            return set()

    def filter_unchanged_chunks(
        self, chunks: List[Chunk], repo_id: int, file_id: int, embed_model: str
    ) -> Tuple[List[Chunk], List[Chunk]]:
        """Separate changed from unchanged chunks using text-hash dedup.

        - Unchanged: chunk.text_hash exists in the file's existing hash set
        - Changed: chunk.text_hash not present, or hash computation failed
        """
        existing_hashes = self.get_existing_hashes_set(repo_id, file_id, embed_model)

        changed: List[Chunk] = []
        unchanged: List[Chunk] = []

        for ch in chunks:
            # Ensure the chunk has a text_hash; compute if missing
            if getattr(ch, "text_hash", None) is None:
                try:
                    ch.text_hash = hash_text(ch.text)
                except Exception as e:
                    _log.warning("Failed to compute hash for chunk %s-%s: %s", ch.start_line, ch.end_line, e)
                    changed.append(ch)
                    continue

            if ch.text_hash in existing_hashes:
                unchanged.append(ch)
            else:
                changed.append(ch)

        return changed, unchanged
