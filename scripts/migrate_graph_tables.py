#!/usr/bin/env python3
"""Migrate database to add code graph tables."""

import sys
from pathlib import Path

# Add kb to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kb.store.sqlite_meta import SQLiteMetadataStore


def migrate_graph_tables():
    """Create graph tables in the metadata database."""

    # Find the metadata database
    dolphin_dir = Path.home() / ".dolphin"
    db_path = dolphin_dir / "metadata.db"

    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        print("   Please run 'kb index' on at least one repository first.")
        return False

    print(f"📊 Migrating database: {db_path}")
    print()

    try:
        # Initialize store (this will trigger migration)
        store = SQLiteMetadataStore(db_path)
        store._ensure_schema()  # type: ignore[attr-defined]

        print("✅ Graph tables created successfully!")
        print()

        # Verify tables exist
        with store._connect() as conn:
            cursor = conn.cursor()

            # Check for graph tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'code_%'")
            tables = cursor.fetchall()

            print("Graph tables created:")
            for table in tables:
                table_name = table[0]
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"  ✓ {table_name} (rows: {count})")

        print()
        print("🎉 Migration complete!")
        print()
        print("Next steps:")
        print("  1. Reindex your repositories to extract graph data:")
        print("     kb index --full-reindex dolphin")
        print()
        print("  2. Test graph-enriched search:")
        print("     Use the search_knowledge MCP tool")

        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = migrate_graph_tables()
    sys.exit(0 if success else 1)
