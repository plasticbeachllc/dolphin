"""Unit tests for Phase 1 Database Initialization Improvements.

This test module validates the implementation of the remediation plan's Phase 1:
- Enhanced Initialization with Validation
- Safe FTS5 Table Creation
- Thread-safe initialization
- Comprehensive validation mechanisms
"""

import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
from contextlib import closing
import pytest

from kb.store.sqlite_meta import SQLiteMetadataStore


class TestEnhancedInitialization:
    """Test enhanced initialization with proper validation and error handling."""

    def test_initialize_with_missing_tables(self, tmp_path):
        """Test initialization handles missing tables gracefully."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        
        # Initialize should work normally
        store.initialize()
        
        # Verify all expected tables exist
        with store._connect() as conn:
            with closing(conn.cursor()) as cur:
                expected_tables = ["repos", "sessions", "files", "chunk_content", "chunk_locations", "chunks_fts"]
                for table in expected_tables:
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                    assert cur.fetchone() is not None, f"Table {table} should exist"

    def test_initialize_concurrent_access(self, tmp_path):
        """Test initialization is thread-safe."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        results = []
        errors = []
        
        def initialize_store():
            try:
                store.initialize()
                results.append("success")
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads trying to initialize simultaneously
        threads = []
        for i in range(5):
            thread = threading.Thread(target=initialize_store)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have exactly one success and no errors
        assert len(errors) == 0, f"Should not have errors: {errors}"
        assert len(results) == 5, "All threads should complete successfully"
        
        # Verify store is properly initialized
        assert store._initialized is True

    def test_initialize_foreign_key_validation(self, tmp_path):
        """Test foreign key constraint validation."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        
        # Initialize should work and enable foreign keys
        store.initialize()
        
        with store._connect() as conn:
            with closing(conn.cursor()) as cur:
                # Check that foreign keys are enabled
                cur.execute("PRAGMA foreign_keys")
                result = cur.fetchone()
                assert result[0] == 1, "Foreign keys should be enabled"
                
                # Check foreign key check returns no violations
                cur.execute("PRAGMA foreign_key_check")
                violations = cur.fetchall()
                assert len(violations) == 0, f"Foreign key violations: {violations}"

    def test_initialize_idempotent(self, tmp_path):
        """Test that multiple initialize() calls are idempotent."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        
        # First initialization
        store.initialize()
        first_state = store._initialized
        
        # Second initialization should be no-op
        store.initialize()
        second_state = store._initialized
        
        assert first_state == second_state == True
        
        # Should not create duplicate tables
        with store._connect() as conn:
            with closing(conn.cursor()) as cur:
                cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                table_count_first = cur.fetchone()[0]
            
            # Third initialization
            store.initialize()
            with closing(conn.cursor()) as cur:
                cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                table_count_second = cur.fetchone()[0]
            
            assert table_count_first == table_count_second


class TestSafeFTS5Creation:
    """Test safe FTS5 table creation with version and feature detection."""

    def test_fts5_creation_with_supported_version(self, tmp_path):
        """Test FTS5 creation with supported SQLite version."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        # Verify FTS5 table exists and has correct structure
        with store._connect() as conn:
            with closing(conn.cursor()) as cur:
                # Check table exists
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'")
                assert cur.fetchone() is not None
                
                # Check table schema
                cur.execute("PRAGMA table_info(chunks_fts)")
                columns = {row[1]: row[2] for row in cur.fetchall()}
                
                expected_columns = {
                    'content_id', 'repo', 'path', 'content', 
                    'symbol_name', 'symbol_path'
                }
                assert all(col in columns for col in expected_columns)

    def test_fts5_creation_already_exists(self, tmp_path):
        """Test FTS5 creation when table already exists."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        
        # Initialize twice
        store.initialize()
        store.initialize()  # Should not fail
        
        # Verify table is still intact
        with store._connect() as conn:
            with closing(conn.cursor()) as cur:
                cur.execute("SELECT COUNT(*) FROM chunks_fts")
                result = cur.fetchone()
                assert result[0] == 0  # Should be empty


class TestTableSchemaValidation:
    """Test table schema validation and integrity checking."""

    def test_validate_table_schema_success(self, tmp_path):
        """Test successful table schema validation."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        # Validate all expected tables
        with store._connect() as conn:
            with closing(conn.cursor()) as cur:
                for table in ["repos", "sessions", "files", "chunk_content", "chunk_locations"]:
                    # Should not raise any exceptions
                    store._validate_table_schema(cur, table)

    def test_validate_table_schema_missing_table(self, tmp_path):
        """Test schema validation with missing table."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        with store._connect() as conn:
            with closing(conn.cursor()) as cur:
                # This should raise RuntimeError for missing table
                with pytest.raises(RuntimeError, match="exists but has no columns"):
                    store._validate_table_schema(cur, "nonexistent_table")

    def test_validate_table_schema_missing_columns(self, tmp_path):
        """Test schema validation with missing columns."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        with store._connect() as conn:
            with closing(conn.cursor()) as cur:
                # Create a malformed repos table with missing columns - drop if exists first
                cur.execute("DROP TABLE IF EXISTS repos")
                cur.execute("CREATE TABLE repos (id INTEGER)")
                
                # This should raise RuntimeError for missing columns for known tables
                with pytest.raises(RuntimeError, match="missing required columns"):
                    store._validate_table_schema(cur, "repos")


class TestDatabaseIntegrityValidation:
    """Test comprehensive database integrity validation."""

    def test_validate_database_integrity_success(self, tmp_path):
        """Test successful database integrity validation."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        
        # Initialize database first - this is required for integrity checks
        store.initialize()
        
        # Should not raise any exceptions
        store._validate_database_integrity()

    def test_validate_database_integrity_with_data(self, tmp_path):
        """Test database integrity validation with actual data."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        # Add some test data
        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        
        repo = store.get_repo_by_name("test-repo")
        repo_id = int(repo["id"])
        
        file_id = store.upsert_file(
            repo_id, path="src/a.py", ext=".py", language="python", 
            is_binary=False, size_bytes=123
        )
        
        # Should still pass integrity check with valid data
        store._validate_database_integrity()

    def test_database_integrity_check(self, tmp_path):
        """Test PRAGMA integrity_check execution."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        with store._connect() as conn:
            with closing(conn.cursor()) as cur:
                cur.execute("PRAGMA integrity_check")
                result = cur.fetchone()
                assert result[0] == "ok", f"Database integrity check failed: {result}"

    def test_orphaned_record_detection(self, tmp_path):
        """Test detection of orphaned records."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        # Manually create an orphaned record to test detection
        with store._connect() as conn:
            with closing(conn.cursor()) as cur:
                # Temporarily disable foreign keys to insert orphaned data
                cur.execute("PRAGMA foreign_keys = OFF")
                # Insert orphaned chunk_location (referencing non-existent content)
                cur.execute("""
                    INSERT INTO chunk_locations (id, content_id, start_line, end_line)
                    VALUES ('orphan1', 'nonexistent_content', 1, 10)
                """)
                # Re-enable foreign keys
                cur.execute("PRAGMA foreign_keys = ON")
                conn.commit()
        
        # Should log warning but not fail
        store._validate_database_integrity()


class TestInitializationEdgeCases:
    """Test initialization edge cases and error conditions."""

    def test_initialization_with_invalid_engine(self, tmp_path):
        """Test initialization with engine creation issues."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        
        # Mock engine creation to fail
        with patch.object(store, '_engine', side_effect=Exception("Engine creation failed")):
            with pytest.raises(Exception, match="Engine creation failed"):
                store.initialize()

    def test_initialization_rollback_on_failure(self, tmp_path):
        """Test that initialization properly rolls back on failure."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        
        # Mock table creation to fail after creating some tables
        with patch('sqlmodel.SQLModel.metadata.create_all', side_effect=Exception("Table creation failed")):
            with pytest.raises(Exception, match="Table creation failed"):
                store.initialize()
            
            # Store should not be marked as initialized
            assert store._initialized is False
            assert store._initializing is False

    def test_double_initialization_with_initializing_flag(self, tmp_path):
        """Test double-check pattern with _initializing flag."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        
        # This is implicitly tested by the concurrent access test
        # but we can test the logic directly
        store._initializing = False
        store.initialize()
        assert store._initializing is False


class TestPhase1Integration:
    """Integration tests to verify Phase 1 works end-to-end."""

    def test_full_initialization_workflow(self, tmp_path):
        """Test complete initialization workflow with all validations."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        
        # Initialize should work seamlessly
        store.initialize()
        
        # Verify all components are working
        assert store._initialized is True
        
        # Test repository operations work
        repo_path = Path("/test/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        assert repo is not None
        assert repo["id"] > 0
        
        # Test FTS5 operations work
        store.index_chunk_for_fts(
            content_id="test1",
            repo="test-repo",
            path="test.py",
            text_hash="hash_test1",
            content="test content",
            symbol_name="test",
            symbol_path="test"
        )
        
        results = store.bm25_search("test")
        assert len(results) > 0
        assert results[0]["chunk_id"] == "test1"

    def test_initialization_persistence(self, tmp_path):
        """Test that initialization state persists across store instances."""
        # First store initializes the database
        store1 = SQLiteMetadataStore(tmp_path / "test.db")
        store1.initialize()
        repo_path = Path("/test/repo")
        store1.record_repo("test-repo", repo_path)
        
        # Second store should see initialized state
        store2 = SQLiteMetadataStore(tmp_path / "test.db")
        store2.initialize()
        
        # Should immediately recognize initialized state
        assert store2._initialized is True
        
        # Should be able to access data
        repo = store2.get_repo_by_name("test-repo")
        assert repo is not None
        assert repo["id"] > 0

    def test_concurrent_initialization_different_stores(self, tmp_path):
        """Test concurrent initialization of different store instances."""
        store1 = SQLiteMetadataStore(tmp_path / "test1.db")
        store2 = SQLiteMetadataStore(tmp_path / "test2.db")
        
        results = []
        errors = []
        
        def init_store(store, name):
            try:
                store.initialize()
                results.append(name)
            except Exception as e:
                errors.append((name, e))
        
        # Initialize both stores concurrently
        thread1 = threading.Thread(target=init_store, args=(store1, "store1"))
        thread2 = threading.Thread(target=init_store, args=(store2, "store2"))
        
        thread1.start()
        thread2.start()
        
        thread1.join()
        thread2.join()
        
        # Both should succeed
        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 2
        assert "store1" in results and "store2" in results