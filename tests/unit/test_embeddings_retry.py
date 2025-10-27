"""Tests for embedding provider retry logic."""

import time
import types
import pytest

from pb_kb.embeddings.provider import EmbeddingProvider, embed_texts_with_retry, _default_provider
from pb_kb.ingest.error_logging import with_retry


def test_embed_texts_with_retry_success_after_retries(monkeypatch):
    class FlakyProvider(EmbeddingProvider):
        def __init__(self):
            super().__init__()
            self.calls = 0

        @staticmethod
        def _zeroes(dim, n):
            return [[0.0] * dim for _ in range(n)]

        @with_retry(max_attempts=3, delays=(0.01, 0.01))
        def embed_texts(self, model, texts):  # type: ignore[override]
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("temporary failure")
            return self._zeroes(self.model_dimensions[model], len(texts))

    # Swap default provider
    flaky = FlakyProvider()
    monkeypatch.setattr("pb_kb.embeddings.provider._default_provider", flaky, raising=False)

    vecs = embed_texts_with_retry("small", ["a", "b"])
    assert len(vecs) == 2
    assert flaky.calls == 3


def test_embed_texts_with_retry_exhausts_attempts(monkeypatch):
    class AlwaysFailProvider(EmbeddingProvider):
        @with_retry(max_attempts=2, delays=(0.01,))
        def embed_texts(self, model, texts):  # type: ignore[override]
            raise RuntimeError("hard failure")

    monkeypatch.setattr("pb_kb.embeddings.provider._default_provider", AlwaysFailProvider(), raising=False)

    with pytest.raises(RuntimeError):
        embed_texts_with_retry("small", ["a"])