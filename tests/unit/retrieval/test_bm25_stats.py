from pathlib import Path

import pytest

from kb.retrieval.bm25_stats import BM25Statistics, BM25StatisticsCollector


def build_stats(sample_size: int = 200) -> BM25Statistics:
    return BM25Statistics(
        min_score=0.0,
        max_score=40.0,
        mean=10.0,
        median=8.0,
        std=3.0,
        p05=1.0,
        p25=5.0,
        p75=12.0,
        p95=20.0,
        p99=30.0,
        sample_size=sample_size,
    )


def test_statistics_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "bm25_stats.json"
    stats = build_stats()
    stats.save(path)

    loaded = BM25Statistics.load(path)

    assert loaded == stats


def test_collector_requires_minimum_samples(tmp_path: Path) -> None:
    collector = BM25StatisticsCollector(min_samples=3)
    collector.extend([1.0, 2.0])

    assert collector.compute() is None

    collector.record(3.0)
    stats = collector.compute()

    assert stats is not None
    assert stats.sample_size == 3
    assert stats.max_score == pytest.approx(3.0)


def test_collector_flushes_to_disk(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    collector = BM25StatisticsCollector(min_samples=2)
    collector.extend([4.0, 8.0])

    written = collector.flush_to(path)

    assert written == path
    assert path.exists()
