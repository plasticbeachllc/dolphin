"""Unit tests for SQLite connection pool."""

import tempfile
import threading
import time
from pathlib import Path

import pytest

from kb.store.connection_pool import SQLiteConnectionPool, close_connection_pool, get_connection_pool


class TestSQLiteConnectionPool:
    """Unit tests for SQLiteConnectionPool class."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        yield db_path

        # Cleanup
        try:
            Path(db_path).unlink()
        except Exception:
            pass

    def test_pool_initialization(self, temp_db):
        """Test pool initialization."""
        pool = SQLiteConnectionPool(
            database=temp_db,
            pool_size=5,
            max_overflow=3,
        )

        assert pool.pool_size == 5
        assert pool.max_overflow == 3
        stats = pool.stats()
        assert stats["pool_size"] == 5
        assert stats["created_connections"] >= 5

        pool.close_all()

    def test_acquire_and_release(self, temp_db):
        """Test basic acquire and release operations."""
        pool = SQLiteConnectionPool(database=temp_db, pool_size=2)

        # Acquire connection
        conn1 = pool.acquire()
        assert conn1 is not None

        # Should be able to execute queries
        cursor = conn1.execute("SELECT 1")
        result = cursor.fetchone()
        assert result is not None

        # Release connection
        pool.release(conn1)

        # Should be able to acquire again
        conn2 = pool.acquire()
        assert conn2 is not None

        pool.release(conn2)
        pool.close_all()

    def test_context_manager(self, temp_db):
        """Test connection context manager."""
        pool = SQLiteConnectionPool(database=temp_db, pool_size=2)

        # Use context manager
        with pool.connection() as conn:
            cursor = conn.execute("SELECT 1")
            result = cursor.fetchone()
            assert result is not None

        # Connection should be automatically released

        # Should be able to acquire again
        with pool.connection() as conn:
            assert conn is not None

        pool.close_all()

    def test_connection_reuse(self, temp_db):
        """Test that connections are reused."""
        pool = SQLiteConnectionPool(database=temp_db, pool_size=2)

        # Acquire and release multiple times
        for _ in range(10):
            conn = pool.acquire()
            pool.release(conn)

        stats = pool.stats()

        # Should have high reuse rate
        assert stats["reused_connections"] >= 8
        assert stats["reuse_rate"] > 80.0

        pool.close_all()

    def test_overflow_connections(self, temp_db):
        """Test overflow connection creation."""
        pool = SQLiteConnectionPool(
            database=temp_db,
            pool_size=2,
            max_overflow=2,
        )

        # Acquire all pooled connections
        conn1 = pool.acquire()
        conn2 = pool.acquire()

        # Should create overflow connection
        conn3 = pool.acquire()
        assert conn3 is not None

        stats = pool.stats()
        assert stats["current_overflow"] >= 1

        # Release all
        pool.release(conn1)
        pool.release(conn2)
        pool.release(conn3)

        # Overflow should be back to 0
        stats = pool.stats()
        assert stats["current_overflow"] == 0

        pool.close_all()

    def test_timeout_error(self, temp_db):
        """Test timeout when pool is exhausted."""
        pool = SQLiteConnectionPool(
            database=temp_db,
            pool_size=1,
            max_overflow=0,
            timeout=0.5,  # Short timeout
        )

        # Acquire the only connection
        conn1 = pool.acquire()

        # Try to acquire another - should timeout
        with pytest.raises(TimeoutError):
            pool.acquire()

        pool.release(conn1)
        pool.close_all()

    def test_connection_validation(self, temp_db):
        """Test connection health validation."""
        pool = SQLiteConnectionPool(database=temp_db, pool_size=2)

        conn = pool.acquire()

        # Connection should be valid
        assert pool._validate_connection(conn)

        # Close the connection to make it invalid
        conn.close()

        # Should detect invalid connection
        assert not pool._validate_connection(conn)

        pool.close_all()

    def test_wal_mode_enabled(self, temp_db):
        """Test that WAL mode is enabled."""
        pool = SQLiteConnectionPool(
            database=temp_db,
            pool_size=1,
            enable_wal=True,
        )

        with pool.connection() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode.upper() == "WAL"

        pool.close_all()

    def test_thread_safety(self, temp_db):
        """Test thread-safe connection usage."""
        pool = SQLiteConnectionPool(database=temp_db, pool_size=5)

        errors = []

        def worker():
            try:
                for _ in range(10):
                    with pool.connection() as conn:
                        conn.execute("SELECT 1")
                        time.sleep(0.01)  # Simulate work
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [threading.Thread(target=worker) for _ in range(5)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0

        pool.close_all()

    def test_rollback_on_release(self, temp_db):
        """Test that uncommitted transactions are rolled back."""
        pool = SQLiteConnectionPool(database=temp_db, pool_size=2)

        # Create a table
        with pool.connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER)")
            conn.commit()

        # Start transaction but don't commit
        conn = pool.acquire()
        conn.execute("INSERT INTO test VALUES (1)")
        # Don't commit - just release
        pool.release(conn)

        # Check that insert was rolled back
        with pool.connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 0  # Should be rolled back

        pool.close_all()

    def test_stats_tracking(self, temp_db):
        """Test statistics tracking."""
        pool = SQLiteConnectionPool(database=temp_db, pool_size=2)

        # Perform some operations
        for _ in range(5):
            conn = pool.acquire()
            pool.release(conn)

        stats = pool.stats()

        assert stats["pool_size"] == 2
        assert stats["created_connections"] >= 2
        assert stats["reused_connections"] >= 3
        assert stats["available_connections"] >= 0
        assert "reuse_rate" in stats

        pool.close_all()

    def test_close_all(self, temp_db):
        """Test closing all connections."""
        pool = SQLiteConnectionPool(database=temp_db, pool_size=3)

        # Acquire and release
        conn = pool.acquire()
        pool.release(conn)

        # Close all
        pool.close_all()

        stats = pool.stats()
        assert stats["available_connections"] == 0


class TestGlobalPoolHelpers:
    """Unit tests for global pool helper functions."""

    def test_get_connection_pool(self):
        """Test getting global pool instance."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Get pool instance
            pool1 = get_connection_pool(db_path, pool_size=5)
            pool2 = get_connection_pool(db_path, pool_size=5)

            # Should return same instance
            assert pool1 is pool2

            # Close pool
            close_connection_pool()

        finally:
            # Cleanup
            try:
                Path(db_path).unlink()
            except Exception:
                pass

    def test_close_connection_pool(self):
        """Test closing global pool."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            pool = get_connection_pool(db_path, pool_size=2)

            with pool.connection() as conn:
                conn.execute("SELECT 1")

            # Close pool
            close_connection_pool()

            # Getting pool again should create new instance
            pool2 = get_connection_pool(db_path, pool_size=2)
            assert pool2 is not None

            close_connection_pool()

        finally:
            try:
                Path(db_path).unlink()
            except Exception:
                pass

    def test_connection_pools_are_per_database(self):
        """Different database paths should receive isolated pool instances."""

        with (
            tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f1,
            tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f2,
        ):
            db_path_1 = f1.name
            db_path_2 = f2.name

        try:
            pool1 = get_connection_pool(db_path_1, pool_size=2)
            pool2 = get_connection_pool(db_path_2, pool_size=2)

            assert pool1 is not pool2

            close_connection_pool()
        finally:
            for db_path in (db_path_1, db_path_2):
                try:
                    Path(db_path).unlink()
                except Exception:
                    pass

    def test_close_specific_pool(self):
        """Closing a specific pool should not impact other databases."""

        with (
            tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f1,
            tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f2,
        ):
            db_path_1 = f1.name
            db_path_2 = f2.name

        try:
            pool1 = get_connection_pool(db_path_1, pool_size=2)
            pool2 = get_connection_pool(db_path_2, pool_size=2)

            close_connection_pool(db_path_1)

            # Pool for db_path_2 should remain usable
            with pool2.connection() as conn:
                conn.execute("SELECT 1")

            # Requesting db_path_1 again should yield a new instance
            pool1_recreated = get_connection_pool(db_path_1, pool_size=2)
            assert pool1_recreated is not pool1

            close_connection_pool()
        finally:
            for db_path in (db_path_1, db_path_2):
                try:
                    Path(db_path).unlink()
                except Exception:
                    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
