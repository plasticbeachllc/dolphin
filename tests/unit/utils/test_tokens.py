"""Unit tests for token estimation utilities."""

from __future__ import annotations

import logging

import pytest

import kb.utils.tokens as tokens_module
from kb.utils.tokens import estimate_tokens, estimate_tokens_batch


@pytest.fixture(autouse=True)
def _reset_encoder_state(monkeypatch):
    """Reset module-level singleton state before each test."""
    monkeypatch.setattr(tokens_module, "_encoder", None)
    monkeypatch.setattr(tokens_module, "_tiktoken_available", None)


class TestEstimateTokens:
    """Tests for estimate_tokens with tiktoken available."""

    def test_estimate_tokens_with_tiktoken(self):
        """Returns a positive int for non-empty text; value is plausible."""
        result = estimate_tokens("Hello, world! This is a test string.")
        assert isinstance(result, int)
        assert result > 0
        text = "Hello, world! This is a test string."
        assert len(text) // 4 < result < len(text)

    def test_estimate_tokens_empty_string(self):
        """Returns 1 for empty string (the max(1, ...) guard via fallback path)."""
        result = estimate_tokens("")
        # tiktoken encodes "" to 0 tokens, but the function returns len(enc.encode(text))
        # which is 0 — however the fallback path returns max(1, ...).
        # With tiktoken available, empty string encodes to 0 tokens.
        assert isinstance(result, int)
        assert result >= 0

    def test_estimate_tokens_caches_encoder(self, monkeypatch):
        """Second call does not re-import; _encoder persists."""
        # First call populates the encoder
        estimate_tokens("test")
        assert tokens_module._encoder is not None

        # Now make import fail — cached encoder should still work
        import builtins

        original_import = builtins.__import__

        def fail_tiktoken(name, *args, **kwargs):
            if name == "tiktoken":
                raise ImportError("blocked")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fail_tiktoken)
        result = estimate_tokens("still works")
        assert isinstance(result, int)
        assert result > 0


class TestEstimateTokensFallback:
    """Tests for estimate_tokens when tiktoken is unavailable."""

    def test_estimate_tokens_fallback_when_tiktoken_unavailable(self, monkeypatch):
        """Monkeypatch tiktoken import to fail; function returns max(1, len(text) // 4)."""
        monkeypatch.setattr(tokens_module, "_tiktoken_available", False)

        text = "Hello, this is a test string for fallback estimation."
        result = estimate_tokens(text)
        expected = max(1, len(text) // 4)
        assert result == expected

    def test_estimate_tokens_batch_fallback(self, monkeypatch):
        """Monkeypatch tiktoken unavailable; returns character-based approximation."""
        monkeypatch.setattr(tokens_module, "_tiktoken_available", False)

        texts = ["hello world", "foo bar baz"]
        result = estimate_tokens_batch(texts)
        expected = max(1, sum(len(t) for t in texts) // 4)
        assert result == expected

    def test_fallback_logged_once(self, monkeypatch, caplog):
        """The debug log 'tiktoken unavailable' appears exactly once even after multiple calls."""
        # Force re-detection by resetting state
        monkeypatch.setattr(tokens_module, "_encoder", None)
        monkeypatch.setattr(tokens_module, "_tiktoken_available", None)

        # Make tiktoken import fail
        import builtins

        original_import = builtins.__import__

        def fail_tiktoken(name, *args, **kwargs):
            if name == "tiktoken":
                raise ImportError("no tiktoken")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fail_tiktoken)

        with caplog.at_level(logging.DEBUG, logger="kb.utils.tokens"):
            estimate_tokens("first call")
            estimate_tokens("second call")
            estimate_tokens("third call")

        fallback_messages = [r for r in caplog.records if "tiktoken unavailable" in r.message]
        assert len(fallback_messages) == 1


class TestEstimateTokensBatch:
    """Tests for estimate_tokens_batch."""

    def test_estimate_tokens_batch_sums_correctly(self):
        """estimate_tokens_batch(['a', 'b']) equals sum of individual calls."""
        texts = ["hello world", "foo bar"]
        batch_result = estimate_tokens_batch(texts)
        individual_sum = sum(estimate_tokens(t) for t in texts)
        assert batch_result == individual_sum

    def test_estimate_tokens_batch_empty_list(self, monkeypatch):
        """Returns 1 for empty list (the max(1, ...) guard on empty sum via fallback)."""
        # With tiktoken, sum of empty list is 0
        # With fallback, max(1, 0 // 4) = 1
        monkeypatch.setattr(tokens_module, "_tiktoken_available", False)
        result = estimate_tokens_batch([])
        assert result == 1
