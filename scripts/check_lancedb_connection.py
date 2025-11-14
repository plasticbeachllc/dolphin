#!/usr/bin/env python3
"""
Check LanceDB connection and diagnose why tables appear empty.
"""

from pathlib import Path


def check_lancedb_connection():
    """Check LanceDB connection and data."""

    print("🔍 LanceDB Connection Diagnosis")
    print("=" * 40)

    store_root = Path.home() / ".dolphin" / "knowledge_store"
    lancedb_dir = store_root / "lancedb"

    print(f"Store root: {store_root}")
    print(f"LanceDB dir: {lancedb_dir}")

    # Check what directories exist
    if lancedb_dir.exists():
        print("\n📁 LanceDB directory contents:")
        for item in lancedb_dir.iterdir():
            if item.is_dir():
                print(f"  📁 {item.name}/")
                # Check if this is a table directory
                table_dir = item
                if table_dir.name.endswith(".lance"):
                    # Count actual vector files
                    data_dir = table_dir / "data"
                    if data_dir.exists():
                        vector_files = list(data_dir.glob("*.lance"))
                        print(f"    📊 {len(vector_files)} vector files")
                        if len(vector_files) > 0:
                            print(f"    📄 Sample: {vector_files[0].name}")
            else:
                print(f"  📄 {item.name}")
    else:
        print("❌ LanceDB directory doesn't exist")
        return

    # Try to connect and check tables
    try:
        import lancedb

        print("\n🔌 Testing LanceDB connection...")

        # Connect to LanceDB
        db = lancedb.connect(lancedb_dir.as_posix())
        table_names = db.table_names()
        print("✅ Connected successfully")
        print(f"📋 Table names: {table_names}")

        # Check each table
        for table_name in table_names:
            try:
                table = db.open_table(table_name)
                count = len(table)
                print(f"  📊 {table_name}: {count} records")

                if count > 0:
                    sample = table.head(3)
                    print("     Sample record:")
                    print(f"     {sample}")

            except Exception as e:
                print(f"  ❌ Error reading {table_name}: {e}")

    except ImportError:
        print("❌ LanceDB not installed")
    except Exception as e:
        print(f"❌ LanceDB connection error: {e}")
        import traceback

        traceback.print_exc()


def check_vector_file_structure():
    """Check the actual vector file structure."""

    print("\n🔍 Vector File Structure Analysis")
    print("=" * 40)

    store_root = Path.home() / ".dolphin" / "knowledge_store"
    lancedb_dir = store_root / "lancedb"

    # Check chunks_large.lance specifically
    chunks_large_dir = lancedb_dir / "chunks_large.lance"
    if chunks_large_dir.exists():
        print("✅ chunks_large.lance exists")

        # Check data directory
        data_dir = chunks_large_dir / "data"
        if data_dir.exists():
            vector_files = list(data_dir.glob("*.lance"))
            print(f"📊 {len(vector_files)} vector files in data directory")

            if vector_files:
                # Check file sizes
                total_size = sum(f.stat().st_size for f in vector_files)
                print(f"📏 Total size: {total_size:,} bytes ({total_size / 1024 / 1024:.1f} MB)")

                # Sample a few files
                print("📄 Sample files:")
                for f in vector_files[:5]:
                    size = f.stat().st_size
                    print(f"  {f.name}: {size:,} bytes")

                # Check if these are actually LanceDB table files
                # This would indicate the table structure is different
                print("🔍 File structure suggests LanceDB v2 format")
                print("   This might explain why connection shows empty tables")
        else:
            print("❌ data directory doesn't exist")
    else:
        print("❌ chunks_large.lance doesn't exist")


def main():
    """Run all diagnostics."""

    check_lancedb_connection()
    check_vector_file_structure()

    print("\n💡 Analysis:")
    print("If vector files exist but LanceDB reports empty tables:")
    print("1. Check LanceDB version compatibility")
    print("2. Verify table initialization worked correctly")
    print("3. Look for path configuration mismatches")
    print("4. Consider that files might be in wrong format/location")


if __name__ == "__main__":
    main()
