"""Tests for embedding provider retry logic."""

import pytest

from kb.embeddings.provider import EmbeddingProvider, embed_texts_with_retry, set_default_provider
from kb.ingest.error_logging import with_retry


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

    # Swap default provider using the new context-aware API
    flaky = FlakyProvider()
    set_default_provider(flaky)

    vecs = embed_texts_with_retry("small", ["a", "b"])
    assert len(vecs) == 2
    assert flaky.calls == 3


def test_embed_texts_with_retry_exhausts_attempts(monkeypatch):
    class AlwaysFailProvider(EmbeddingProvider):
        @with_retry(max_attempts=2, delays=(0.01,))
        def embed_texts(self, model, texts):  # type: ignore[override]
            raise RuntimeError("hard failure")

    set_default_provider(AlwaysFailProvider())

    with pytest.raises(RuntimeError):
        embed_texts_with_retry("small", ["a"])
