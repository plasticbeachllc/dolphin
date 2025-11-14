#!/usr/bin/env python3
"""
Debug the indexing pipeline to understand why repositories aren't being indexed.
This script traces through the complete indexing process to find where it fails.
"""

import sqlite3
from pathlib import Path


def check_repository_status():
    """Check what repositories exist and their indexing status."""

    print("🔍 Repository Status Check")
    print("=" * 40)

    store_root = Path.home() / ".dolphin" / "knowledge_store"
    metadata_db = store_root / "metadata.db"

    if not metadata_db.exists():
        print(f"❌ Database doesn't exist at {metadata_db}")
        return

    try:
        conn = sqlite3.connect(metadata_db)
        cursor = conn.cursor()

        # Check repos table
        print("📋 Repositories:")
        cursor.execute("""
            SELECT name, root_path, default_embed_model, 
                   datetime(updated_at) as updated_at
            FROM repos ORDER BY name
        """)
        repos = cursor.fetchall()

        if repos:
            for repo in repos:
                print(f"  ✅ {repo[0]}: {repo[1]} (embed: {repo[2]}, updated: {repo[3]})")
        else:
            print("  ❌ No repositories found")

        # Check sessions table
        print("\n📊 Indexing Sessions:")
        cursor.execute("""
            SELECT s.id, r.name, s.status, s.embed_model, 
                   s.files_indexed, s.chunks_indexed, s.vectors_written,
                   datetime(s.created_at) as created_at,
                   datetime(s.ended_at) as ended_at,
                   s.notes
            FROM sessions s 
            JOIN repos r ON s.repo_id = r.id 
            ORDER BY s.id DESC LIMIT 10
        """)
        sessions = cursor.fetchall()

        if sessions:
            for session in sessions:
                print(f"  📝 Session {session[0]}: {session[1]} ({session[2]})")
                print(f"     Model: {session[3]}, Files: {session[4]}, Chunks: {session[5]}, Vectors: {session[6]}")
                print(f"     Created: {session[7]}, Ended: {session[8]}")
                if session[9]:
                    print(f"     Notes: {session[9]}")
                print()
        else:
            print("  ❌ No sessions found")

        # Check files table
        print("📁 File Catalog:")
        cursor.execute("""
            SELECT COUNT(*) as total_files,
                   COUNT(DISTINCT repo_id) as repos_with_files,
                   SUM(CASE WHEN is_binary = 1 THEN 1 ELSE 0 END) as binary_files,
                   SUM(CASE WHEN is_binary = 0 THEN 1 ELSE 0 END) as text_files
            FROM files
        """)
        file_stats = cursor.fetchone()

        if file_stats[0] > 0:
            print(f"  ✅ Total files: {file_stats[0]}")
            print(f"     Repositories with files: {file_stats[1]}")
            print(f"     Binary files: {file_stats[2]}")
            print(f"     Text files: {file_stats[3]}")

            # Sample some files
            cursor.execute("""
                SELECT f.path, r.name as repo_name, f.language, f.size_bytes, f.is_binary
                FROM files f JOIN repos r ON f.repo_id = r.id
                ORDER BY f.path LIMIT 10
            """)
            sample_files = cursor.fetchall()
            print("  📄 Sample files:")
            for file in sample_files:
                print(f"     {file[1]}:{file[0]} ({file[2]}, {file[4]}binary, {file[3]} bytes)")
        else:
            print("  ❌ No files catalogued")

        # Check chunk_content table
        print("\n🧩 Chunk Content:")
        cursor.execute("SELECT COUNT(*) FROM chunk_content")
        chunk_count = cursor.fetchone()[0]
        print(f"  Total chunks: {chunk_count}")

        if chunk_count > 0:
            # Sample some chunks
            cursor.execute("""
                SELECT cc.id, r.name, cc.path, length(cc.content) as content_length
                FROM chunk_content cc
                JOIN repos r ON cc.repo_id = r.id
                LIMIT 5
            """)
            sample_chunks = cursor.fetchall()
            print("  📋 Sample chunks:")
            for chunk in sample_chunks:
                print(f"     {chunk[1]}:{chunk[2]} ({chunk[3]} chars) -> {chunk[0]}")
        else:
            print("  ❌ No chunks found - indexing pipeline may have failed")

        # Check chunk_locations table
        print("\n📍 Chunk Locations:")
        cursor.execute("SELECT COUNT(*) FROM chunk_locations")
        location_count = cursor.fetchone()[0]
        print(f"  Total locations: {location_count}")

        if location_count > 0:
            cursor.execute("""
                SELECT COUNT(DISTINCT content_id) as unique_chunks,
                       COUNT(DISTINCT file_id) as files_with_chunks
                FROM chunk_locations
            """)
            loc_stats = cursor.fetchone()
            print(f"  Unique chunks: {loc_stats[0]}, Files with chunks: {loc_stats[1]}")

        conn.close()

    except Exception as e:
        print(f"❌ Error checking database: {e}")
        import traceback

        traceback.print_exc()


def check_lancedb_tables():
    """Check what vector data exists in LanceDB."""

    print("\n🔍 LanceDB Vector Storage Check")
    print("=" * 40)

    store_root = Path.home() / ".dolphin" / "knowledge_store"

    try:
        import lancedb

        db = lancedb.connect(store_root.as_posix())

        table_names = db.table_names()
        print(f"LanceDB tables: {table_names}")

        for table_name in table_names:
            try:
                table = db.open_table(table_name)
                count = len(table)
                print(f"  📊 {table_name}: {count} vectors")

                if count > 0:
                    # Sample some records
                    sample = table.head(3)
                    print("     Sample:")
                    for i, record in enumerate(sample):
                        print(f"       {i + 1}. {record['id']} ({record['repo']}, {record['path']})")
                else:
                    print("     ⚠️  Empty table")

            except Exception as e:
                print(f"  ❌ Error reading {table_name}: {e}")

    except ImportError:
        print("❌ LanceDB not installed")
    except Exception as e:
        print(f"❌ Error connecting to LanceDB: {e}")


def check_error_logs():
    """Check for error logs from the indexing process."""

    print("\n🔍 Error Log Analysis")
    print("=" * 30)

    store_root = Path.home() / ".dolphin" / "knowledge_store"
    error_log = store_root / "error_log.json"

    if error_log.exists():
        print(f"📋 Error log found: {error_log}")
        try:
            import json

            with open(error_log) as f:
                errors = json.load(f)

            if errors:
                print(f"Found {len(errors)} errors:")
                for error in errors[-10:]:  # Last 10 errors
                    print(f"  ❌ {error.get('timestamp', 'unknown')}: {error.get('path', 'unknown')}")
                    print(f"     {error.get('error', 'Unknown error')}")
            else:
                print("✅ No errors in log")

        except Exception as e:
            print(f"❌ Error reading error log: {e}")
    else:
        print("✅ No error log found")


def check_embedding_configuration():
    """Check if there are embedding-related configuration issues."""

    print("\n🔍 Embedding Configuration Check")
    print("=" * 40)

    # Check environment variables
    import os

    openai_key = os.getenv("OPENAI_API_KEY")
    print(f"OpenAI API Key: {'✅ Set' if openai_key else '❌ Not set'}")

    # Check config
    try:
        from kb.config import load_config

        config = load_config()
        print(f"Embedding provider: {config.embedding_provider}")
        print(f"Default embed model: {config.default_embed_model}")
        print(f"Batch size: {config.embedding_batch_size}")
        print(f"API key env var: {config.openai_api_key_env}")

        # Check if provider is configured properly
        if config.embedding_provider == "openai" and not openai_key:
            print("⚠️  OpenAI provider selected but API key not set")
        elif config.embedding_provider == "stub":
            print("ℹ️  Using stub embeddings - will not create real vectors")

    except Exception as e:
        print(f"❌ Error loading config: {e}")


def simulate_indexing_step():
    """Simulate what should happen during indexing."""

    print("\n🔍 Indexing Process Simulation")
    print("=" * 40)

    store_root = Path.home() / ".dolphin" / "knowledge_store"

    try:
        from kb.store.sqlite_meta import SQLiteMetadataStore

        sql_store = SQLiteMetadataStore(store_root / "metadata.db")

        # Check if we can create a test session
        repo_info = sql_store.get_repo_by_name("dolphin")  # Use existing repo
        if repo_info:
            print(f"Creating test session for repo {repo_info['id']}...")
            session_id = sql_store.begin_session(
                repo_id=repo_info["id"],
                commit_sha="test123",
                branch="main",
                embed_model="small",
            )
            print(f"✅ Test session created: {session_id}")

            # Clean up
            sql_store.set_session_status(session_id, "aborted", "Test session")
            print("✅ Test session cleaned up")
        else:
            print("⚠️  No existing repositories found for testing")

    except Exception as e:
        print(f"❌ Error in session simulation: {e}")


def main():
    """Run all debugging checks."""

    print("Indexing Pipeline Debug Tool")
    print("=" * 50)

    check_repository_status()
    check_lancedb_tables()
    check_error_logs()
    check_embedding_configuration()
    simulate_indexing_step()

    print("\n💡 Debug Summary:")
    print("If you see 0 chunks but repositories exist:")
    print("1. Check if sessions completed successfully")
    print("2. Verify embedding API credentials are set")
    print("3. Look at error logs for failures")
    print("4. Ensure text files are being found and processed")
    print("5. Check if vector embedding generation is working")


if __name__ == "__main__":
    main()
