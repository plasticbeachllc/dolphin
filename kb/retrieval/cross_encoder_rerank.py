"""Cross-encoder reranking for search results."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np

_log = logging.getLogger(__name__)

# Try to import sentence_transformers at module level for easier mocking
try:
    from sentence_transformers import CrossEncoder as _CrossEncoder

    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    _CrossEncoder: type | None = None
    _SENTENCE_TRANSFORMERS_AVAILABLE = False


class CrossEncoderReranker:
    """Rerank search results using a cross-encoder model."""

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str | None = None,
        batch_size: int = 32,
    ):
        self.model_name = model_name
        self.batch_size = batch_size
        self.enabled = False
        self.model = None
        self.load_error: str | None = None  # Set when model loading fails

        if model_name == "test-model":
            self.model = self._create_mock_model()
            self.enabled = True
            _log.info("Cross-encoder running in test mode.")
            return

        if not _SENTENCE_TRANSFORMERS_AVAILABLE:
            self.load_error = "dependencies missing — install with: uv pip install pb-dolphin[reranking]"
            _log.error(
                "⚠️  Cross-encoder reranking is enabled in config but dependencies are missing!\n"
                "   Required: torch and sentence-transformers (~2GB install)\n"
                "   Install with: pip install pb-dolphin[reranking]\n"
                "   Or with uv: uv pip install pb-dolphin[reranking]\n"
                "   Reranking will be disabled until dependencies are installed."
            )
            return

        try:
            _log.info(f"Loading cross-encoder model: {model_name}")
            # Only pass device parameter if explicitly set (avoid empty string error)
            # Type narrowing: _CrossEncoder is available when _SENTENCE_TRANSFORMERS_AVAILABLE is True
            if _CrossEncoder is None:
                raise RuntimeError("CrossEncoder is not available")
            if device:
                self.model = _CrossEncoder(model_name, device=device)
            else:
                self.model = _CrossEncoder(model_name)
            self.enabled = True
            _log.info(f"Cross-encoder loaded successfully on {self.model.device}")
        except Exception as e:
            self.load_error = str(e)
            _log.error("Failed to load cross-encoder model: %s. Reranking disabled.", e, exc_info=True)

    def _create_mock_model(self):
        """Creates a mock model object for testing."""

        class MockModel:
            device = "cpu"

            def predict(self, *args, **kwargs):
                num_pairs = len(args[0]) if args else 0
                return [0.5] * num_pairs

        return MockModel()

    def rerank(
        self,
        query: str,
        results: Sequence[dict],
        top_k: int = 5,
        text_field: str = "text",
        score_threshold: float | None = None,
    ) -> list[dict]:
        """Reranks results using the cross-encoder model."""
        if not self.enabled or not self.model:
            _log.warning("Cross-encoder is not available or enabled. Returning original order.")
            return list(results[:top_k])

        if not results:
            return []

        pairs = [[query, r.get(text_field, "")] for r in results]

        try:
            scores = self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)

            if isinstance(scores, np.ndarray):
                scores = scores.tolist()

            for result, score in zip(results, scores):
                result["rerank_score"] = float(score)

            # Filter and sort
            reranked_results = [r for r in results if score_threshold is None or r["rerank_score"] >= score_threshold]
            reranked_results.sort(key=lambda x: x["rerank_score"], reverse=True)

            return reranked_results[:top_k]

        except Exception as e:
            _log.error(f"Reranking failed: {e}. Returning original results.")
            return list(results[:top_k])
