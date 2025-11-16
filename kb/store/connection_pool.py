"""SQLite connection pooling for improved performance.

This module provides connection pooling for SQLite to reduce
connection overhead and improve concurrent access performance.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any

logger = logging.getLogger(__name__)


class SQLiteConnectionPool:
    """Thread-safe SQLite connection pool.

    This pool maintains a set of reusable SQLite connections to
    avoid the overhead of creating new connections for each query.

    Features:
    - Thread-safe connection management
    - Configurable pool size
    - Connection health checks
    - Automatic WAL mode enablement
    - Connection timeout handling
    """

    def __init__(
        self,
        database: str,
        pool_size: int = 10,
        max_overflow: int = 5,
        timeout: float = 30.0,
        enable_wal: bool = True,
    ):
        """Initialize connection pool.

        Args:
            database: Path to SQLite database file
            pool_size: Number of connections to maintain
            max_overflow: Additional connections allowed beyond pool_size
            timeout: Connection acquisition timeout (seconds)
            enable_wal: Enable WAL mode for better concurrency
        """
        self.database = database
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.timeout = timeout
        self.enable_wal = enable_wal

        self._pool: Queue = Queue(maxsize=pool_size)
        self._overflow_count = 0
        self._overflow_lock = threading.Lock()

        # Statistics
        self._created_connections = 0
        self._reused_connections = 0
        self._overflow_connections = 0

        # Initialize pool with connections
        self._initialize_pool()

    def _initialize_pool(self) -> None:
        """Initialize the connection pool."""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            self._pool.put(conn)
            self._created_connections += 1

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with optimal settings.

        Returns:
            Configured SQLite connection
        """
        conn = sqlite3.connect(
            self.database,
            check_same_thread=False,
            timeout=self.timeout,
        )

        conn.execute("PRAGMA foreign_keys=ON")
        # Enable WAL mode for better concurrency
        if self.enable_wal:
            conn.execute("PRAGMA journal_mode=WAL")

        # Optimization pragmas
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA mmap_size=30000000000")  # 30GB
        conn.execute("PRAGMA page_size=4096")

        # Set row factory for dict-like access
        conn.row_factory = sqlite3.Row

        return conn

    def _validate_connection(self, conn: sqlite3.Connection) -> bool:
        """Validate that a connection is still usable.

        Args:
            conn: Connection to validate

        Returns:
            True if connection is valid
        """
        try:
            conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    @contextmanager
    def connection(self):
        """Get a connection from the pool (context manager).

        Usage:
            with pool.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ...")

        Yields:
            SQLite connection
        """
        conn = self.acquire()
        try:
            yield conn
        finally:
            self.release(conn)

    def acquire(self) -> sqlite3.Connection:
        """Acquire a connection from the pool.

        Returns:
            SQLite connection

        Raises:
            TimeoutError: If connection cannot be acquired within timeout
        """
        # Try to get from pool
        try:
            conn = self._pool.get(timeout=self.timeout)

            # Validate connection
            if self._validate_connection(conn):
                self._reused_connections += 1
                return conn
            else:
                # Connection is stale, create new one
                logger.warning("Stale connection detected, creating new one")
                conn = self._create_connection()
                self._created_connections += 1
                return conn

        except Empty:
            # Pool is empty, try to create overflow connection
            with self._overflow_lock:
                if self._overflow_count < self.max_overflow:
                    self._overflow_count += 1
                    self._overflow_connections += 1
                    conn = self._create_connection()
                    self._created_connections += 1
                    logger.info(f"Created overflow connection ({self._overflow_count}/{self.max_overflow})")
                    return conn
                else:
                    raise TimeoutError(
                        f"Could not acquire connection within {self.timeout}s. "
                        f"Pool size: {self.pool_size}, "
                        f"Overflow: {self._overflow_count}/{self.max_overflow}"
                    )

    def release(self, conn: sqlite3.Connection) -> None:
        """Release a connection back to the pool.

        Args:
            conn: Connection to release
        """
        # Rollback any uncommitted transaction
        try:
            conn.rollback()
        except sqlite3.Error:
            pass

        # Try to return to pool
        try:
            self._pool.put_nowait(conn)
        except Full:
            # Pool is full, this must be an overflow connection
            with self._overflow_lock:
                self._overflow_count = max(0, self._overflow_count - 1)
            conn.close()

    def close_all(self) -> None:
        """Close all connections in the pool."""
        # Close all pooled connections
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Empty:
                break

    def stats(self) -> dict[str, Any]:
        """Get connection pool statistics.

        Returns:
            Dictionary with pool stats
        """
        return {
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "current_overflow": self._overflow_count,
            "available_connections": self._pool.qsize(),
            "created_connections": self._created_connections,
            "reused_connections": self._reused_connections,
            "overflow_connections": self._overflow_connections,
            "reuse_rate": (self._reused_connections / max(1, self._created_connections) * 100),
        }

    def __del__(self):
        """Cleanup on deletion."""
        self.close_all()


# Global pool registry keyed by resolved database path
_connection_pools: dict[str, SQLiteConnectionPool] = {}
_pool_registry_lock = threading.Lock()


def get_connection_pool(
    database: str | os.PathLike[str],
    *,
    pool_size: int = 10,
    max_overflow: int = 5,
    timeout: float = 30.0,
    enable_wal: bool = True,
) -> SQLiteConnectionPool:
    """Get or create a connection pool for the given database."""

    resolved = str(Path(database).resolve())

    with _pool_registry_lock:
        pool = _connection_pools.get(resolved)
        if pool is None:
            pool = SQLiteConnectionPool(
                database=resolved,
                pool_size=pool_size,
                max_overflow=max_overflow,
                timeout=timeout,
                enable_wal=enable_wal,
            )
            _connection_pools[resolved] = pool

        return pool


def close_connection_pool(database: str | os.PathLike[str] | None = None) -> None:
    """Close one or all registered connection pools."""

    if database is None:
        with _pool_registry_lock:
            pools = list(_connection_pools.values())
            _connection_pools.clear()
    else:
        resolved = str(Path(database).resolve())
        with _pool_registry_lock:
            pool = _connection_pools.pop(resolved, None)
            pools = [pool] if pool else []

    for pool in pools:
        if pool:
            pool.close_all()
