#!/usr/bin/env python3
"""Quick test to reproduce the 0 chunks issue."""

import logging
import sys
from pathlib import Path

# Set up logging to see DEBUG output
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)

# Add kb to path
sys.path.insert(0, str(Path(__file__).parent))

from kb.store.sqlite_meta import SQLiteMetadataStore
from kb.chunkers.registry import (
    detect_language_from_extension,
    chunk_file as chunk_file_with_config,
)
from kb.chunkers.repo_config import load_repo_chunking_config
from kb.hashing import hash_text
from kb.ingest._helpers import build_desired_map
from kb.ingest.dedup import ChunkDeduplicator

# Use actual KB store
store_path = Path.home() / ".dolphin" / "knowledge_store"
metadata_db = store_path / "metadata.db"

print("=" * 80)
print("REINDEX DEBUG TEST")
print("=" * 80)

sql_store = SQLiteMetadataStore(metadata_db)
sql_store.initialize()

# Get dolphin repo
repo = sql_store.get_repo_by_name("dolphin")
if not repo:
    print("❌ dolphin repo not found")
    sys.exit(1)

print(f"\nRepo object: {repo}")

repo_id = repo["id"]
root = Path(repo["root_path"])
embed_model = repo["default_embed_model"]

print(f"Root: {root}")
print(f"Model: {embed_model}")

# Test with a single file
test_file = "kb/api/app.py"
file_path = root / test_file

print(f"\n📄 Testing file: {test_file}")

# Upsert file
file_id = sql_store.upsert_file(
    repo_id=repo_id,
    path=test_file,
    ext=file_path.suffix,
    language=None,
    is_binary=False,
    size_bytes=file_path.stat().st_size,
)
print(f"  File ID: {file_id}")

# Chunk the file
language = detect_language_from_extension(file_path) or "text"
text = file_path.read_text(encoding="utf-8", errors="ignore")
repo_config = load_repo_chunking_config(root)

chunks = chunk_file_with_config(
    abs_path=file_path,
    rel_path=test_file,
    language=language,
    text=text,
    repo_config=repo_config,
)
print(f"  Extracted {len(chunks)} chunks")

# Compute text_hash for each chunk
for chunk in chunks:
    chunk.text_hash = hash_text(chunk.text)

# Build desired map
desired = build_desired_map(chunks)
print(f"  Desired map: {len(desired)} unique hashes")

# Check deduplication
chunk_deduplicator = ChunkDeduplicator(sql_store)
changed_chunks, unchanged_chunks = chunk_deduplicator.filter_unchanged_chunks(
    chunks, repo_id, file_id, embed_model
)
new_hashes = {c.text_hash for c in changed_chunks}
print(f"  Changed: {len(changed_chunks)}, Unchanged: {len(unchanged_chunks)}")
print(f"  New hashes: {len(new_hashes)}")

# Try ensure_content_rows_for_file
mapping = sql_store.ensure_content_rows_for_file(
    repo_id, file_id, embed_model, list(desired.keys())
)
print(f"  Mapping size: {len(mapping)}")

# Check what's in chunk_content now
import sqlite3

with sql_store._connect() as conn:
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM chunk_content WHERE repo_id = ? AND file_id = ?",
        (repo_id, file_id),
    )
    count = cur.fetchone()[0]
    print(f"  chunk_content rows for this file: {count}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
