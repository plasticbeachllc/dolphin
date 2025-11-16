"""Benchmark coverage for the SQLite connection pool."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pytest import MonkeyPatch

from kb.store.connection_pool import SQLiteConnectionPool


def _initialize_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS demo (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO demo (value) VALUES ('seed')")
    conn.commit()
    conn.close()


def _run_in_threads(worker: Callable[[], None], count: int, concurrency: int) -> None:
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker) for _ in range(count)]
        for future in futures:
            future.result()


def test_connection_pool_outperforms_raw_connections(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    db_path = tmp_path / "pool_perf.db"
    _initialize_db(str(db_path))

    original_connect = sqlite3.connect

    def delayed_connect(*args, **kwargs):
        time.sleep(0.002)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", delayed_connect)

    def pooled_worker(pool: SQLiteConnectionPool) -> None:
        with pool.connection() as conn:
            conn.execute("SELECT COUNT(*) FROM demo").fetchone()

    def direct_worker() -> None:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("SELECT COUNT(*) FROM demo").fetchone()

    def run_with_pool() -> float:
        pool = SQLiteConnectionPool(str(db_path), pool_size=4, max_overflow=2, timeout=5.0)
        start = time.perf_counter()

        def worker() -> None:
            pooled_worker(pool)

        _run_in_threads(worker, count=60, concurrency=8)
        duration = time.perf_counter() - start
        pool.close_all()
        return duration

    def run_without_pool() -> float:
        start = time.perf_counter()
        _run_in_threads(direct_worker, count=60, concurrency=8)
        return time.perf_counter() - start

    pooled_duration = run_with_pool()
    direct_duration = run_without_pool()

    improvement = direct_duration / pooled_duration
    assert improvement > 3.0, f"Expected >3x improvement, observed {improvement:.2f}x"
