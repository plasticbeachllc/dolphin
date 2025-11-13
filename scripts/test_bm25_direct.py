#!/usr/bin/env python3
"""Test BM25 search directly to see why it returns 0 results."""

import sqlite3
from pathlib import Path

store_path = Path.home() / ".dolphin" / "knowledge_store"
metadata_db = store_path / "metadata.db"

conn = sqlite3.connect(metadata_db)
cur = conn.cursor()

# Test different queries
test_queries = [
    "UI interface validation suite",
    "validation",
    "interface",
    "UI"
]

print("Testing BM25 queries against blue-whale repo:\n")

for query in test_queries:
    print(f"Query: '{query}'")

    # Test without repo filter
    cur.execute("""
        SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?
    """, (query,))
    count_all = cur.fetchone()[0]
    print(f"  Without repo filter: {count_all} results")

    # Test with repo filter
    cur.execute("""
        SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ? AND repo = ?
    """, (query, "blue-whale"))
    count_repo = cur.fetchone()[0]
    print(f"  With repo=blue-whale: {count_repo} results")

    # Show sample if found
    if count_repo > 0:
        cur.execute("""
            SELECT content_id, repo, path, -bm25(chunks_fts) as score
            FROM chunks_fts
            WHERE chunks_fts MATCH ? AND repo = ?
            ORDER BY rank
            LIMIT 1
        """, (query, "blue-whale"))
        row = cur.fetchone()
        if row:
            print(f"  Sample: {row[2]} (score: {row[3]:.4f})")
    print()

# Check what repos are in FTS5
print("Repos in FTS5:")
cur.execute("SELECT DISTINCT repo FROM chunks_fts")
for row in cur.fetchall():
    print(f"  - {row[0]}")

conn.close()
