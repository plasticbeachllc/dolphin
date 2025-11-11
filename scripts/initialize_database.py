#!/usr/bin/env python3
"""
Initialize the SQLite database schema for Dolphin knowledge store.
Run this script to create all necessary tables including FTS5 for hybrid search.
"""

from pathlib import Path
from kb.store.sqlite_meta import SQLiteMetadataStore


def main():
    """Initialize the database schema."""
    
    print("Initializing Dolphin Knowledge Store Database")
    print("=" * 50)
    
    # Set up paths
    store_root = Path.home() / '.dolphin' / 'knowledge_store'
    print(f"Store root: {store_root}")
    
    # Create database store
    sql_store = SQLiteMetadataStore(store_root / "metadata.db")
    
    try:
        # Initialize database (creates all tables including FTS5)
        print("\nCreating database schema...")
        sql_store.initialize()
        print("✅ Database initialized successfully!")
        
        # Verify tables were created
        print("\nVerifying tables...")
        with sql_store._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row[0] for row in cursor.fetchall()]
            
        print(f"✅ Created {len(tables)} tables: {tables}")
        
        # Check if FTS5 table was created
        if 'chunks_fts' in tables:
            print("✅ FTS5 virtual table created for BM25 hybrid search")
        else:
            print("⚠️  FTS5 table not found - hybrid search may not work properly")
            
        print("\n🎉 Database initialization complete!")
        print("\nNext steps:")
        print("1. Index a repository: uv run python -m kb.cli index --repo my-repo /path/to/repo")
        print("2. Test hybrid search: uv run tests/test_hybrid_search_performance.py")
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)