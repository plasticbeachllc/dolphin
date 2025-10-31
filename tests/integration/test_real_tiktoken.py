"""Integration tests that validate real tiktoken behavior.

These tests use real tiktoken to ensure production behavior matches expectations.
They verify:
1. Token counts match OpenAI's tokenizer
2. Chunk boundaries are correct
3. Text windowing produces expected results

Tiktoken is required for all tests (enforced by setup_tiktoken fixture).
"""

import pytest
from pb_kb.chunkers.token_utils import (
    count_tokens,
    window_text_by_tokens,
    window_token_ranges,
    get_tokenizer,
)


class TestRealTiktokenBehavior:
    """Tests that validate real tiktoken produces expected results."""

    def test_token_count_known_values(self):
        """Verify token counts match known values from OpenAI's tokenizer.

        These values were pre-calculated using OpenAI's tiktoken with cl100k_base.
        If this test fails with real tiktoken, the expected values may need updating.
        """
        test_cases = [
            # (text, expected_token_count_with_cl100k_base)
            ("hello world", 2),  # "hello" + " world"
            ("The quick brown fox", 4),  # "The" + " quick" + " brown" + " fox"
            ("print('hello')", 5),  # "print" + "(" + "'" + "hello" + "')"
            ("def example():\n    pass", 7),  # Typical Python function
        ]

        for text, expected_count in test_cases:
            actual_count = count_tokens(text)
            # With real tiktoken, counts should match exactly
            # With mock tiktoken, counts will differ (more tokens due to 3-char chunks)
            assert actual_count == expected_count, (
                f"Token count mismatch for '{text}': "
                f"expected {expected_count}, got {actual_count}. "
                f"This suggests mock tiktoken is being used instead of real tiktoken."
            )

    def test_window_text_boundaries_real_tiktoken(self):
        """Verify text windowing produces correct boundaries with real tiktoken."""
        text = "The quick brown fox jumps over the lazy dog"


        # With real tiktoken and target=5, overlap=2
        windows = window_text_by_tokens(text, model="small", target=5, overlap=2)

        # Should have multiple windows with overlap
        assert len(windows) > 1, "Expected multiple windows with target=5"

        # Verify windows are tuples of (text, start, end)
        for window_text, start, end in windows:
            assert isinstance(window_text, str)
            assert isinstance(start, int)
            assert isinstance(end, int)
            assert start >= 0
            assert end <= len(text)
            assert start < end
            # Verify the slice matches
            assert text[start:end] == window_text

        # Verify overlap behavior
        if len(windows) >= 2:
            # Second window should start before first window ends (overlap)
            _, start1, end1 = windows[0]
            _, start2, end2 = windows[1]
            assert start2 < end1, "Windows should overlap"

    def test_chunking_consistency_real_tiktoken(self):
        """Verify chunking is deterministic with real tiktoken."""
        text = """
def example_function():
    for i in range(10):
        print(i)
    return True
"""


        # Get chunks twice
        chunks1 = window_text_by_tokens(text, target=20, overlap=5)
        chunks2 = window_text_by_tokens(text, target=20, overlap=5)

        # Should be identical
        assert len(chunks1) == len(chunks2)
        for (text1, s1, e1), (text2, s2, e2) in zip(chunks1, chunks2):
            assert text1 == text2
            assert s1 == s2
            assert e1 == e2

    def test_tiktoken_decode_reversibility(self):
        """Verify tiktoken encode/decode roundtrip works correctly."""
        test_texts = [
            "Simple English text",
            "Code: def foo():\n    return 42",
            "Mixed 中文 and English",
            "Symbols: @#$%^&*()",
        ]


        tokenizer = get_tokenizer("small")

        for text in test_texts:
            tokens = tokenizer.encode(text)
            decoded = tokenizer.decode(tokens)
            assert decoded == text, (
                f"Encode/decode roundtrip failed for: {text!r}\n"
                f"Got: {decoded!r}"
            )


class TestTiktokenAvailabilityHandling:
    """Tests that verify graceful handling when tiktoken is not available."""

    def test_mock_tiktoken_still_works(self, mock_tiktoken):
        """Verify mock tiktoken works as fallback."""
        # Explicitly use mock tiktoken fixture
        text = "hello world"
        tokens = mock_tiktoken.encode(text)
        decoded = mock_tiktoken.decode(tokens)

        # Mock should be reversible
        assert decoded == text

        # Mock uses 3-char chunks, so ~11 chars / 3 = ~4 tokens
        assert len(tokens) >= 3  # At least a few tokens

    def test_token_utils_work_without_real_tiktoken(self, mock_tiktoken):
        """Verify token utils work with mock tiktoken."""
        text = "def example():\n    pass"

        # These should work with mock tiktoken (just different values)
        count = count_tokens(text)
        assert count > 0

        windows = window_text_by_tokens(text, target=10, overlap=2)
        assert len(windows) > 0

        # Verify basic structure
        for window_text, start, end in windows:
            assert isinstance(window_text, str)
            assert text[start:end] == window_text
