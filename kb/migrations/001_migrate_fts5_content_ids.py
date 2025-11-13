"""Migration 001: Migrate FTS5 content IDs to deterministic format

This migration handles the schema change where FTS5 content_ids are now
generated deterministically from (repo_id, file_id, text_hash) instead of
including embed_model, which caused duplication.

Migration Steps:
1. Read all existing FTS5 entries
2. Regenerate content IDs using new deterministic function
3. Drop and recreate FTS5 table with new schema
4. Re-insert entries with new content IDs (deduplicating as needed)
"""

import sqlite3
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def generate_fts_content_id(repo_id: int, file_id: int, text_hash: str) -> str:
    """Generate deterministic FTS5 content_id independent of embed_model.

    This ensures that the same text content (identified by repo_id, file_id, text_hash)
    always gets the same FTS5 content_id, regardless of which embedding model(s)
    are used to index it.

    Args:
        repo_id: Repository ID
        file_id: File ID
        text_hash: SHA-256 hash of chunk text content

    Returns:
        Deterministic content_id for FTS5 table (32-character hex string)
    """
    composite = f"{repo_id}:{file_id}:{text_hash}"
    return hashlib.sha256(composite.encode()).hexdigest()[:32]


def get_repo_and_file_ids(
    conn: sqlite3.Connection, repo_name: str, file_path: str
) -> Tuple[int | None, int | None]:
    """Get repo_id and file_id from names/paths.

    Args:
        conn: Database connection
        repo_name: Repository name
        file_path: File path relative to repo root

    Returns:
        Tuple of (repo_id, file_id) or (None, None) if not found
    """
    cursor = conn.cursor()

    # Get repo_id
    cursor.execute("SELECT id FROM repos WHERE name = ?", (repo_name,))
    repo_row = cursor.fetchone()
    if not repo_row:
        return None, None
    repo_id = repo_row[0]

    # Get file_id
    cursor.execute(
        "SELECT id FROM files WHERE repo_id = ? AND path = ?", (repo_id, file_path)
    )
    file_row = cursor.fetchone()
    if not file_row:
        return repo_id, None

    return repo_id, file_row[0]


def migrate_fts5_content_ids(db_path: Path) -> Dict[str, int]:
    """Migrate existing FTS5 content IDs to new deterministic format.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        Dictionary with migration statistics
    """
    stats = {
        "entries_read": 0,
        "entries_migrated": 0,
        "duplicates_merged": 0,
        "errors": 0,
    }

    logger.info("[FTS5 Migration 001] Starting migration of FTS5 content IDs...")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Step 1: Check if FTS5 table exists and has data
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
        )
        if not cursor.fetchone():
            logger.info(
                "[FTS5 Migration 001] No chunks_fts table found, skipping migration"
            )
            return stats

        # Read all existing FTS5 entries
        cursor.execute(
            """
            SELECT content_id, repo, path, text_hash, content, symbol_name, symbol_path
            FROM chunks_fts
        """
        )
        old_entries = cursor.fetchall()
        stats["entries_read"] = len(old_entries)

        if stats["entries_read"] == 0:
            logger.info("[FTS5 Migration 001] No entries to migrate")
            return stats

        logger.info(
            f"[FTS5 Migration 001] Read {stats['entries_read']} entries from chunks_fts"
        )

        # Step 2: Transform entries to new format
        new_entries: Dict[str, Dict] = {}  # Use dict to deduplicate by new content_id

        for entry in old_entries:
            repo_name = entry["repo"]
            file_path = entry["path"]
            text_hash = entry["text_hash"]

            # Get repo_id and file_id
            repo_id, file_id = get_repo_and_file_ids(conn, repo_name, file_path)

            if repo_id is None or file_id is None:
                logger.warning(
                    f"[FTS5 Migration 001] Skipping entry: "
                    f"repo={repo_name}, path={file_path} (not found in metadata)"
                )
                stats["errors"] += 1
                continue

            # Generate new deterministic content_id
            new_content_id = generate_fts_content_id(repo_id, file_id, text_hash)

            # Check for duplicates (same content indexed with different embed_models)
            if new_content_id in new_entries:
                stats["duplicates_merged"] += 1
                logger.debug(
                    f"[FTS5 Migration 001] Duplicate found: "
                    f"{new_content_id} (keeping first occurrence)"
                )
                continue

            # Store entry with new content_id
            new_entries[new_content_id] = {
                "content_id": new_content_id,
                "repo": repo_name,
                "path": file_path,
                "text_hash": text_hash,
                "content": entry["content"],
                "symbol_name": entry["symbol_name"],
                "symbol_path": entry["symbol_path"],
            }

        logger.info(
            f"[FTS5 Migration 001] Transformed {len(new_entries)} unique entries "
            f"(merged {stats['duplicates_merged']} duplicates)"
        )

        # Step 3: Drop and recreate FTS5 table with new schema
        logger.info("[FTS5 Migration 001] Dropping old chunks_fts table...")
        cursor.execute("DROP TABLE chunks_fts")

        logger.info("[FTS5 Migration 001] Creating new chunks_fts table...")
        cursor.execute(
            """
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                content_id UNINDEXED,
                repo UNINDEXED,
                path UNINDEXED,
                text_hash UNINDEXED,
                content,
                symbol_name,
                symbol_path,
                tokenize='porter unicode61'
            )
        """
        )

        # Step 4: Insert entries with new content_ids
        logger.info("[FTS5 Migration 001] Inserting entries with new content IDs...")
        for entry in new_entries.values():
            cursor.execute(
                """
                INSERT INTO chunks_fts (content_id, repo, path, text_hash, content, symbol_name, symbol_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry["content_id"],
                    entry["repo"],
                    entry["path"],
                    entry["text_hash"],
                    entry["content"],
                    entry["symbol_name"],
                    entry["symbol_path"],
                ),
            )
            stats["entries_migrated"] += 1

        conn.commit()

        logger.info(
            f"[FTS5 Migration 001] ✅ Migration complete! "
            f"Migrated {stats['entries_migrated']} entries, "
            f"merged {stats['duplicates_merged']} duplicates, "
            f"{stats['errors']} errors"
        )

    except Exception as e:
        conn.rollback()
        logger.error(f"[FTS5 Migration 001] ❌ Migration failed: {e}", exc_info=True)
        raise
    finally:
        conn.close()

    return stats


def check_migration_needed(db_path: Path) -> bool:
    """Check if FTS5 migration is needed.

    Returns True if the old schema is detected (no text_hash column or old content_id format).
    """
    try:
        conn = sqlite3.Connection(str(db_path))
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
        )
        if not cursor.fetchone():
            return False  # No table, no migration needed

        # Try to select text_hash column
        try:
            cursor.execute("SELECT text_hash FROM chunks_fts LIMIT 0")
            # Column exists, migration already done
            return False
        except sqlite3.OperationalError as e:
            if "text_hash" in str(e).lower():
                # Old schema detected
                return True
            raise

    except Exception as e:
        logger.warning(f"[FTS5 Migration 001] Could not check migration status: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    """Run migration standalone for testing."""
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python 001_migrate_fts5_content_ids.py <db_path>")
        sys.exit(1)

    db_path = Path(sys.argv[1])

    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    if check_migration_needed(db_path):
        print("Migration needed, starting...")
        stats = migrate_fts5_content_ids(db_path)
        print(f"✅ Migration complete: {stats}")
    else:
        print("✅ Migration not needed (already up to date)")
