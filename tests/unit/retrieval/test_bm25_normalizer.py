import pytest

from kb.retrieval.bm25_normalizer import MinMaxNormalizer, QuantileNormalizer, SigmoidNormalizer
from kb.retrieval.bm25_stats import BM25Statistics


def sample_stats() -> BM25Statistics:
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
        sample_size=200,
    )


def test_sigmoid_normalizer_is_monotonic() -> None:
    normalizer = SigmoidNormalizer(divisor=5.0)
    assert normalizer.normalize(-10) < normalizer.normalize(0) < normalizer.normalize(10)


def test_min_max_normalizer_clamps() -> None:
    stats = sample_stats()
    normalizer = MinMaxNormalizer(stats)

    assert normalizer.normalize(-10) == 0.0
    assert normalizer.normalize(50) == 1.0
    assert normalizer.normalize(20.0) == pytest.approx(0.5, rel=1e-3)


def test_quantile_normalizer_interpolates() -> None:
    stats = sample_stats()
    normalizer = QuantileNormalizer(stats)

    # Between p25 (5 -> 0.25) and median (8 -> 0.5)
    assert normalizer.normalize(6.5) == pytest.approx(0.375, rel=1e-3)
    assert normalizer.normalize(-5) == 0.0
    assert normalizer.normalize(80) == 1.0
