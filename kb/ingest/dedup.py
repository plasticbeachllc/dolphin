from __future__ import annotations

import logging

from ..chunkers.types import Chunk
from ..hashing import hash_text
from ..store.sqlite_meta import SQLiteMetadataStore

__all__ = ["ChunkDeduplicator"]

_log = logging.getLogger(__name__)


class ChunkDeduplicator:
    """Manages chunk deduplication via content hashing.

    Uses text-hash-only deduplication (ignores locations) to decide which
    chunks require embedding. This is robust to chunks moving within a file.

    On any error computing a chunk hash, we log a warning and treat the
    affected chunk as changed (safe fallback for that individual chunk).
    On any error *fetching* existing hashes, we propagate the exception so
    the caller (the ingestion pipeline) can decide whether to skip the file
    or abort, rather than silently re-embedding every chunk.
    """

    def __init__(self, store: SQLiteMetadataStore):
        self.store = store

    def get_existing_hashes_set(self, repo_id: int, file_id: int, embed_model: str) -> set[str]:
        """Return the set of existing text hashes for a file+model.

        Raises:
            Exception: Propagates any store error so the caller can skip the
                file and increment its error counter rather than re-embedding
                every chunk (which can cause duplicate vectors).
        """
        return self.store.get_existing_content_hashes_for_file(repo_id, file_id, embed_model)

    def filter_unchanged_chunks(
        self, chunks: list[Chunk], repo_id: int, file_id: int, embed_model: str
    ) -> tuple[list[Chunk], list[Chunk]]:
        """Separate changed from unchanged chunks using text-hash dedup.

        - Unchanged: chunk.text_hash exists in the file's existing hash set
        - Changed: chunk.text_hash not present, or hash computation failed
        """
        existing_hashes = self.get_existing_hashes_set(repo_id, file_id, embed_model)

        changed: list[Chunk] = []
        unchanged: list[Chunk] = []

        for ch in chunks:
            # Ensure the chunk has a text_hash; compute if missing
            if getattr(ch, "text_hash", None) is None:
                try:
                    ch.text_hash = hash_text(ch.text)
                except Exception as e:
                    _log.warning(
                        "Failed to compute hash for chunk %s-%s: %s",
                        ch.start_line,
                        ch.end_line,
                        e,
                    )
                    changed.append(ch)
                    continue

            if ch.text_hash in existing_hashes:
                unchanged.append(ch)
            else:
                changed.append(ch)

        return changed, unchanged
