#!/usr/bin/env python3
"""
Test the indexing process to see where vector data goes.
"""

import tempfile
from pathlib import Path

from kb.store.lancedb_store import LanceDBStore
from kb.store.sqlite_meta import SQLiteMetadataStore


def test_indexing_workflow():
    """Test the full indexing workflow to see where data goes."""

    print("🔍 Testing Indexing Workflow")
    print("=" * 40)

    with tempfile.TemporaryDirectory() as temp_dir:
        store_root = Path(temp_dir) / "knowledge_store"
        print(f"Test store root: {store_root}")

        # Initialize both stores
        sql_store = SQLiteMetadataStore(store_root / "metadata.db")
        lance_store = LanceDBStore(store_root)

        print("\n1. Initializing stores...")
        sql_store.initialize()
        lance_store.initialize_collections()

        # Check what gets created
        print("\n2. Checking what was created...")

        if store_root.exists():
            for item in store_root.iterdir():
                if item.is_dir():
                    print(f"   📁 {item.name}/")
                    for subitem in item.iterdir():
                        print(f"      📄 {subitem.name}")
                else:
                    print(f"   📄 {item.name}")

        # Try to add some test vector data manually
        print("\n3. Testing vector data insertion...")

        test_vector = [0.1] * 1536  # Small model dimension
        test_chunk = {
            "id": "test_chunk_1",
            "vector": test_vector,
            "repo": "test_repo",
            "path": "test.py",
            "start_line": 1,
            "end_line": 10,
            "text_hash": "abc123",
            "commit": "abc123",
            "branch": "main",
            "embed_model": "small",
            "language": "python",
            "token_count": 100,
        }

        try:
            lance_store.upsert_chunks("test_repo", [test_chunk], model="small")
            print("   ✅ Vector data inserted successfully")
        except Exception as e:
            print(f"   ❌ Vector insertion failed: {e}")

        # Test search with the inserted data
        print("\n4. Testing search with inserted data...")

        try:
            results = lance_store.query(test_vector, model="small", top_k=5)
            print(f"   Search results: {len(results)} found")
            if results:
                print(f"   Sample: {results[0]}")
        except Exception as e:
            print(f"   ❌ Search failed: {e}")


def check_sqlite_metadata():
    """Check what's in the SQLite metadata store."""

    store_root = Path.home() / ".dolphin" / "knowledge_store"
    print("\n🔍 Checking SQLite Metadata")
    print("=" * 30)

    try:
        sql_store = SQLiteMetadataStore(store_root / "metadata.db")

        # Check table contents
        with sql_store._connect() as conn:
            cursor = conn.cursor()

            # List all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"Tables: {tables}")

            # Check chunk content table
            if "chunk_content" in tables:
                cursor.execute("SELECT COUNT(*) FROM chunk_content")
                chunk_count = cursor.fetchone()[0]
                print(f"Chunk records: {chunk_count}")

                if chunk_count > 0:
                    cursor.execute("SELECT content_id, repo, path FROM chunk_content LIMIT 3")
                    samples = cursor.fetchall()
                    print("Sample chunks:")
                    for sample in samples:
                        print(f"  - {sample}")

            # Check files table
            if "files" in tables:
                cursor.execute("SELECT COUNT(*) FROM files")
                file_count = cursor.fetchone()[0]
                print(f"File records: {file_count}")

            # Check repos table
            if "repos" in tables:
                cursor.execute("SELECT name, root_path FROM repos")
                repos = cursor.fetchall()
                print("Repositories:")
                for repo in repos:
                    print(f"  - {repo[0]}: {repo[1]}")

    except Exception as e:
        print(f"❌ Error checking SQLite: {e}")


def main():
    """Run all tests."""

    test_indexing_workflow()
    check_sqlite_metadata()

    print("\n💡 Analysis:")
    print("If repositories are indexed but vectors are missing:")
    print("1. Check if LanceDB collections are created during indexing")
    print("2. Verify vector embedding generation is working")
    print("3. Ensure upsert_chunks is being called with actual vector data")


if __name__ == "__main__":
    main()
