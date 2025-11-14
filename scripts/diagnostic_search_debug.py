#!/usr/bin/env python3
"""Comprehensive diagnostic script to debug why search returns 0 results."""

import sqlite3
import sys
from pathlib import Path

# Find the KB store
store_path = Path.home() / ".dolphin" / "knowledge_store"
metadata_db = store_path / "metadata.db"
lancedb_dir = store_path / "lancedb"

print("=" * 80)
print("KB SEARCH DIAGNOSTIC SCRIPT")
print("=" * 80)

if not metadata_db.exists():
    print(f"❌ Metadata DB not found at: {metadata_db}")
    sys.exit(1)

conn = sqlite3.connect(metadata_db)
cursor = conn.cursor()

# 1. Check repositories
print("\n📦 REPOSITORIES:")
cursor.execute("SELECT id, name, root_path, default_embed_model FROM repos")
repos = cursor.fetchall()
for repo in repos:
    print(f"  ID: {repo[0]}, Name: {repo[1]}, Model: {repo[3]}")

# 2. Check files count
cursor.execute("SELECT COUNT(*) FROM files")
files_count = cursor.fetchone()[0]
print(f"\n📁 FILES: {files_count} files indexed")

# 3. Check chunk_content
cursor.execute("SELECT COUNT(*), embed_model FROM chunk_content GROUP BY embed_model")
chunks = cursor.fetchall()
print("\n🧩 CHUNK_CONTENT:")
for row in chunks:
    print(f"  {row[1]} model: {row[0]} chunks")

# 4. Check FTS5 table - CRITICAL
print("\n🔍 FTS5 TABLE (chunks_fts):")
try:
    cursor.execute("SELECT COUNT(*) FROM chunks_fts")
    fts_count = cursor.fetchone()[0]
    print(f"  Total entries: {fts_count}")

    if fts_count == 0:
        print("  ❌ FTS5 TABLE IS EMPTY! This is why search returns 0 results!")
    else:
        # Sample some FTS5 entries
        cursor.execute("SELECT content_id, repo, path, text_hash, substr(content, 1, 100) FROM chunks_fts LIMIT 5")
        samples = cursor.fetchall()
        print("  Sample entries:")
        for s in samples:
            print(f"    - content_id: {s[0][:16]}... repo: {s[1]}, file: {s[2]}, text_hash: {s[3][:16]}...")
            print(f"      content preview: {s[4][:80]}...")

        # Check if text_hash column exists
        cursor.execute("PRAGMA table_info(chunks_fts)")
        columns = cursor.fetchall()
        col_names = [c[1] for c in columns]
        print(f"  Columns: {col_names}")

        if "text_hash" not in col_names:
            print("  ⚠️  WARNING: text_hash column missing from FTS5!")

except sqlite3.Error as e:
    print(f"  ❌ Error querying FTS5: {e}")

# 5. Check LanceDB tables
print("\n🎯 LANCEDB TABLES:")
try:
    import lancedb

    db = lancedb.connect(str(lancedb_dir))
    tables = db.table_names()
    print(f"  Available tables: {tables}")

    for table_name in tables:
        try:
            table = db.open_table(table_name)
            count = table.count_rows()
            print(f"  {table_name}: {count} vectors")

            # Sample a few vectors
            if count > 0:
                sample = table.search().limit(3).to_list()
                print(f"    Sample IDs: {[s['id'][:50] for s in sample]}")
        except Exception as e:
            print(f"    Error reading {table_name}: {e}")

except Exception as e:
    print(f"  ❌ Error accessing LanceDB: {e}")

# 6. Test BM25 search directly
print("\n🔎 TESTING BM25 SEARCH DIRECTLY:")
try:
    test_query = "validation"
    cursor.execute(
        """
        SELECT content_id, repo, path, -bm25(chunks_fts) as score
        FROM chunks_fts
        WHERE chunks_fts MATCH ?
        ORDER BY score DESC
        LIMIT 5
    """,
        (test_query,),
    )

    results = cursor.fetchall()
    print(f"  Query: '{test_query}'")
    print(f"  Results: {len(results)}")

    if results:
        for r in results:
            print(f"    - content_id: {r[0][:16]}..., repo: {r[1]}, file: {r[2]}, score: {r[3]:.4f}")
    else:
        print("  ❌ NO RESULTS from BM25 search!")

except sqlite3.Error as e:
    print(f"  ❌ Error running BM25 search: {e}")

# 7. Check sessions
cursor.execute(
    "SELECT id, commit_sha, branch, embed_model, status, chunks_indexed FROM sessions ORDER BY id DESC LIMIT 3"
)
sessions = cursor.fetchall()
print("\n📊 RECENT SESSIONS:")
for s in sessions:
    print(f"  Session {s[0]}: {s[4]}, {s[5]} chunks, model: {s[3]}")

conn.close()

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
