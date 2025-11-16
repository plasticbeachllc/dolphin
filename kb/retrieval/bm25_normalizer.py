"""Normalization strategies for BM25 scores."""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import Protocol

from .bm25_stats import BM25Statistics


class ScoreNormalizer(Protocol):
    name: str

    def normalize(self, score: float) -> float:
        ...


@dataclass(slots=True)
class SigmoidNormalizer:
    divisor: float = 10.0
    name: str = "sigmoid"

    def normalize(self, score: float) -> float:
        scaled = score / max(self.divisor, 1e-6)
        return 1.0 / (1.0 + math.exp(-scaled))


@dataclass(slots=True)
class MinMaxNormalizer:
    stats: BM25Statistics
    epsilon: float = 1e-6
    name: str = "min_max"

    def normalize(self, score: float) -> float:
        span = max(self.stats.max_score - self.stats.min_score, self.epsilon)
        normalized = (score - self.stats.min_score) / span
        return max(0.0, min(1.0, normalized))


@dataclass(slots=True)
class QuantileNormalizer:
    stats: BM25Statistics
    name: str = "quantile"
    _scores: list[float] = field(init=False, default_factory=list)
    _values: list[float] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        anchors = [
            (self.stats.min_score, 0.0),
            (self.stats.p05, 0.05),
            (self.stats.p25, 0.25),
            (self.stats.median, 0.5),
            (self.stats.p75, 0.75),
            (self.stats.p95, 0.95),
            (self.stats.p99, 0.99),
            (self.stats.max_score, 1.0),
        ]
        deduped: list[tuple[float, float]] = []
        for score, value in anchors:
            if not deduped or score > deduped[-1][0]:
                deduped.append((score, value))
        self._scores = [s for s, _ in deduped]
        self._values = [v for _, v in deduped]

    def normalize(self, score: float) -> float:
        if score <= self._scores[0]:
            return 0.0
        if score >= self._scores[-1]:
            return 1.0
        idx = bisect.bisect_right(self._scores, score)
        hi_score = self._scores[idx]
        lo_score = self._scores[idx - 1]
        hi_val = self._values[idx]
        lo_val = self._values[idx - 1]
        if hi_score == lo_score:
            return lo_val
        ratio = (score - lo_score) / (hi_score - lo_score)
        return lo_val + ratio * (hi_val - lo_val)

