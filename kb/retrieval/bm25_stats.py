"""Helpers for collecting and persisting BM25 score statistics."""

from __future__ import annotations

import json
import logging
import math
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_BM25_STATS_FILENAME = "bm25_stats.json"
MIN_SAMPLE_SIZE = 100


@dataclass(slots=True)
class BM25Statistics:
    """Summary statistics describing the BM25 score distribution."""

    min_score: float
    max_score: float
    mean: float
    median: float
    std: float
    p05: float
    p25: float
    p75: float
    p95: float
    p99: float
    sample_size: int

    def to_dict(self) -> dict[str, float | int]:
        payload = asdict(self)
        payload["percentiles"] = {
            "p05": self.p05,
            "p25": self.p25,
            "p75": self.p75,
            "p95": self.p95,
            "p99": self.p99,
        }
        for key in ("p05", "p25", "p75", "p95", "p99"):
            payload.pop(key, None)
        return payload

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        logger.info(
            "BM25 statistics saved",
            extra={
                "path": str(path),
                "sample_size": self.sample_size,
                "min_score": self.min_score,
                "max_score": self.max_score,
            },
        )

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> BM25Statistics:
        def _coerce_float(value: object, default: float = 0.0) -> float:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    return default
            return default

        def _coerce_int(value: object, default: int = 0) -> int:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    return default
            return default

        percentiles_payload = payload.get("percentiles")
        percentiles: dict[str, object]
        if isinstance(percentiles_payload, dict):
            percentiles = cast(dict[str, object], percentiles_payload)
        else:
            percentiles = {}
        return cls(
            min_score=_coerce_float(payload.get("min_score", 0.0)),
            max_score=_coerce_float(payload.get("max_score", 0.0)),
            mean=_coerce_float(payload.get("mean", 0.0)),
            median=_coerce_float(payload.get("median", 0.0)),
            std=_coerce_float(payload.get("std", 0.0)),
            p05=_coerce_float(percentiles.get("p05", payload.get("p05", 0.0))),
            p25=_coerce_float(percentiles.get("p25", payload.get("p25", 0.0))),
            p75=_coerce_float(percentiles.get("p75", payload.get("p75", 0.0))),
            p95=_coerce_float(percentiles.get("p95", payload.get("p95", 0.0))),
            p99=_coerce_float(percentiles.get("p99", payload.get("p99", 0.0))),
            sample_size=_coerce_int(payload.get("sample_size", 0)),
        )

    @classmethod
    def load(cls, path: Path) -> BM25Statistics:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


class BM25StatisticsCollector:
    """Thread-safe sampler for BM25 scores recorded during runtime."""

    def __init__(self, *, max_samples: int = 100_000, min_samples: int = MIN_SAMPLE_SIZE) -> None:
        self._scores: list[float] = []
        self._max_samples = max_samples
        self._min_samples = min_samples
        self._lock = threading.Lock()

    def record(self, score: float) -> None:
        if not math.isfinite(score):
            return
        with self._lock:
            if len(self._scores) >= self._max_samples:
                return
            self._scores.append(float(score))

    def extend(self, scores: Iterable[float]) -> None:
        for score in scores:
            self.record(score)

    def sample_size(self) -> int:
        with self._lock:
            return len(self._scores)

    def has_enough_samples(self) -> bool:
        return self.sample_size() >= self._min_samples

    def compute(self) -> BM25Statistics | None:
        with self._lock:
            if len(self._scores) < self._min_samples:
                return None
            scores = np.asarray(self._scores, dtype=float)

        return BM25Statistics(
            min_score=float(np.min(scores)),
            max_score=float(np.max(scores)),
            mean=float(np.mean(scores)),
            median=float(np.median(scores)),
            std=float(np.std(scores)),
            p05=float(np.percentile(scores, 5)),
            p25=float(np.percentile(scores, 25)),
            p75=float(np.percentile(scores, 75)),
            p95=float(np.percentile(scores, 95)),
            p99=float(np.percentile(scores, 99)),
            sample_size=len(scores),
        )

    def flush_to(self, path: Path) -> Path | None:
        stats = self.compute()
        if not stats:
            logger.info(
                "BM25 statistics skipped", extra={"reason": "insufficient_samples", "sample_size": self.sample_size()}
            )
            return None
        stats.save(path)
        return path
