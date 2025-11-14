#!/usr/bin/env python3
"""Diagnostic to check chunk distribution by repo and test search."""

import sqlite3
import sys
from pathlib import Path

# Find the KB store
store_path = Path.home() / ".dolphin" / "knowledge_store"
metadata_db = store_path / "metadata.db"

print("=" * 80)
print("SEARCH BY REPO DIAGNOSTIC")
print("=" * 80)

if not metadata_db.exists():
    print(f"❌ Database not found: {metadata_db}")
    sys.exit(1)

conn = sqlite3.connect(metadata_db)
cursor = conn.cursor()

# Check FTS5 distribution by repo
print("\n📊 FTS5 CHUNKS BY REPO:")
cursor.execute(
    """
    SELECT repo, COUNT(*) as count
    FROM chunks_fts
    GROUP BY repo
    ORDER BY count DESC
"""
)
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} chunks")

# Check chunk_content distribution by repo
print("\n📊 CHUNK_CONTENT BY REPO:")
cursor.execute(
    """
    SELECT r.name, COUNT(cc.id) as count
    FROM chunk_content cc
    JOIN repos r ON cc.repo_id = r.id
    GROUP BY r.name
    ORDER BY count DESC
"""
)
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} chunks")

# Test BM25 search for each repo
print("\n🔎 TESTING BM25 SEARCH BY REPO:")
print("  Query: 'validation'")
repos = ["dolphin", "blue-whale"]
for repo in repos:
    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM chunks_fts
        WHERE chunks_fts MATCH ? AND repo = ?
    """,
        ("validation", repo),
    )
    count = cursor.fetchone()[0]
    print(f"  {repo}: {count} results")

    if count > 0:
        # Show sample
        cursor.execute(
            """
            SELECT path, substr(content, 1, 80) as preview
            FROM chunks_fts
            WHERE chunks_fts MATCH ? AND repo = ?
            LIMIT 1
        """,
            ("validation", repo),
        )
        row = cursor.fetchone()
        if row:
            print(f"    Sample: {row[0]}")
            print(f"    Preview: {row[1]}...")

# Check files by repo
print("\n📁 FILES BY REPO:")
cursor.execute(
    """
    SELECT r.name, COUNT(f.id) as count
    FROM files f
    JOIN repos r ON f.repo_id = r.id
    GROUP BY r.name
    ORDER BY count DESC
"""
)
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} files")

conn.close()

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
