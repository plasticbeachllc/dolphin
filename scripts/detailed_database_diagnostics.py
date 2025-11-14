#!/usr/bin/env python3
"""
Detailed diagnostics to understand database state and vector search performance.
"""

from pathlib import Path


def check_all_database_locations():
    """Check multiple possible database locations."""

    print("🔍 Comprehensive Database Diagnostics")
    print("=" * 50)

    # Check multiple potential locations
    potential_paths = [
        Path.home() / ".dolphin" / "knowledge_store",
        Path("/Users/tdc/.dolphin/knowledge_store"),
        Path("/Users/tdc/worktable/dolphin/.dolphin/knowledge_store"),
        Path("./.dolphin/knowledge_store"),
    ]

    for path in potential_paths:
        print(f"\n📁 Checking: {path}")
        if path.exists():
            print("   ✅ Directory exists")

            # Check metadata.db
            meta_db = path / "metadata.db"
            if meta_db.exists():
                print("   ✅ metadata.db exists")
            else:
                print("   ❌ metadata.db not found")

            # Check for LanceDB data
            lancedb_dir = path / "_lancedb"
            if lancedb_dir.exists():
                print("   ✅ LanceDB directory exists")
                # Check for tables
                table_files = list(lancedb_dir.glob("**/*.lance"))
                print(f"   📊 Found {len(table_files)} LanceDB table files:")
                for table in table_files:
                    size_mb = table.stat().st_size / (1024 * 1024)
                    print(f"      - {table.name}: {size_mb:.1f}MB")
            else:
                print("   ❌ LanceDB directory not found")
        else:
            print("   ❌ Directory doesn't exist")


def check_lancedb_tables_directly():
    """Check LanceDB tables directly to see if they have data."""

    store_root = Path.home() / ".dolphin" / "knowledge_store"
    lancedb_dir = store_root / "_lancedb"

    if not lancedb_dir.exists():
        print(f"\n❌ LanceDB directory not found at {lancedb_dir}")
        return

    print("\n🔍 Direct LanceDB Table Analysis")
    print("=" * 40)

    # Try to connect to LanceDB directly
    try:
        import lancedb

        db_path = store_root.as_posix()
        print(f"Connecting to LanceDB at: {db_path}")

        db = lancedb.connect(db_path)

        # Get table names
        table_names = db.table_names()
        print(f"Found {len(table_names)} tables: {table_names}")

        for table_name in table_names:
            try:
                table = db.open_table(table_name)
                count = len(table)
                print(f"\n📊 Table '{table_name}':")
                print(f"   Records: {count}")

                if count > 0:
                    # Sample some records
                    sample = table.head(3)
                    print("   Sample records:")
                    for i, record in enumerate(sample):
                        print(f"     {i + 1}. {record}")
                else:
                    print("   ⚠️  Table is empty")

            except Exception as e:
                print(f"   ❌ Error opening table '{table_name}': {e}")

    except ImportError:
        print("❌ LanceDB not installed")
    except Exception as e:
        print(f"❌ Error connecting to LanceDB: {e}")


def test_vector_search_detailed():
    """Test vector search with detailed logging."""

    print("\n🔍 Detailed Vector Search Test")
    print("=" * 40)

    store_root = Path.home() / ".dolphin" / "knowledge_store"

    try:
        from kb.embeddings.provider import create_provider
        from kb.store.lancedb_store import LanceDBStore

        print(f"Testing with store root: {store_root}")

        # Create lance store
        lance_store = LanceDBStore(store_root)
        lance_store.initialize_collections()  # Ensure collections exist

        # Create embedding provider
        provider = create_provider("stub")  # Use stub for testing

        # Generate test query vector (1536 dimensions for small model)
        import numpy as np

        test_vector = np.random.rand(1536).tolist()

        print(f"Test vector dimension: {len(test_vector)}")

        # Test search with timing
        import time

        start = time.time()
        results = lance_store.query(test_vector, model="small", top_k=5)
        elapsed = (time.time() - start) * 1000

        print("\nSearch results:")
        print(f"  Time: {elapsed:.1f}ms")
        print(f"  Results count: {len(results)}")

        if results:
            print(f"  Sample result: {results[0]}")
        else:
            print("  ⚠️  No results found")
            print("  This could mean:")
            print("    - Tables are empty")
            print("    - Vector dimensions don't match")
            print("    - Query vector is too different from indexed vectors")

    except Exception as e:
        print(f"❌ Error in vector search test: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Run all diagnostics."""

    check_all_database_locations()
    check_lancedb_tables_directly()
    test_vector_search_detailed()

    print("\n💡 Summary:")
    print("If you have indexed repositories but see empty results:")
    print("1. Check that the repository indexing completed successfully")
    print("2. Verify the LanceDB tables contain vector data")
    print("3. Ensure vector dimensions match between indexing and search")


if __name__ == "__main__":
    main()
