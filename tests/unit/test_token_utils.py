"""Unit tests for token utilities and windowing functions."""

from kb.chunkers.token_utils import window_text_by_tokens, count_tokens, get_tokenizer


class TestTokenUtilities:
    """Test token counting and text windowing functionality."""

    def test_window_text_by_tokens_simple(self):
        """Test basic token windowing with small target size."""
        text = """def a():
    print('hello')

# trailing
"""
        # Create windows with small target so we get multiple windows
        windows = window_text_by_tokens(text, model="small", target=4, overlap=1)

        # Windows should be list of (text, start, end)
        assert isinstance(windows, list)
        assert all(isinstance(w, tuple) and len(w) == 3 for w in windows)

        for sub, s_char, e_char in windows:
            assert text[s_char:e_char] == sub
            assert count_tokens(sub) >= 0

    def test_window_text_by_tokens_empty(self):
        """Test token windowing with empty text."""
        windows = window_text_by_tokens("", model="small", target=10, overlap=2)
        assert windows == []

    def test_window_text_by_tokens_single_window(self):
        """Test token windowing with text that fits in one window."""
        text = "Short text"
        windows = window_text_by_tokens(text, model="small", target=100, overlap=0)
        assert len(windows) == 1
        sub, start, end = windows[0]
        assert sub == text
        assert start == 0
        assert end == len(text)

    def test_window_text_by_tokens_with_overlap(self):
        """Test token windowing with overlap between windows."""
        text = (
            "This is a longer text that should be split into multiple windows with overlap."
            * 5
        )
        windows = window_text_by_tokens(text, model="small", target=20, overlap=5)

        assert len(windows) > 1

        # Check that windows have overlap
        for i in range(len(windows) - 1):
            _, _, end1 = windows[i]
            _, start2, _ = windows[i + 1]
            # There should be overlap (start2 < end1)
            assert start2 < end1

    def test_count_tokens_accuracy(self):
        """Test token counting accuracy for various text inputs."""
        # Simple text
        assert count_tokens("hello world") > 0

        # Code
        code = "def function():\n    return True"
        assert count_tokens(code) > 0

        # Empty string
        assert count_tokens("") == 0

        # Whitespace
        assert count_tokens("   \n\t  ") > 0

    def test_count_tokens_model_variants(self):
        """Test token counting with different model variants."""
        text = "This is a test sentence."

        # Test with different models by getting the appropriate tokenizer
        for model in ["small", "large"]:
            tokenizer = get_tokenizer(model)
            count = count_tokens(text, tokenizer=tokenizer)
            assert count > 0
            # Should be the same regardless of model since both use cl100k_base
            # But we just verify it doesn't crash

    def test_window_text_preserves_content(self):
        """Test that windowing preserves the original content when reassembled."""
        text = """Line 1
Line 2
Line 3
Line 4
Line 5
Line 6
Line 7
Line 8
Line 9
Line 10"""

        windows = window_text_by_tokens(text, model="small", target=10, overlap=2)

        # Reassemble the text from windows
        reassembled = ""
        for i, (sub, start, end) in enumerate(windows):
            # First window starts from beginning
            if i == 0:
                reassembled += text[start:end]
            else:
                # Subsequent windows: take from the overlap boundary
                _, prev_start, prev_end = windows[i - 1]
                overlap_start = prev_end - (end - start) // 2  # Approximate overlap
                reassembled += text[overlap_start:end]

        # The reassembled text should contain all the original content
        # (may not be exact due to overlap handling, but should have all lines)
        for line in text.split("\n"):
            assert line in reassembled

    def test_token_count_consistency(self):
        """Test that token counts are consistent across multiple calls."""
        text = "Consistent token counting test"
        count1 = count_tokens(text)
        count2 = count_tokens(text)
        assert count1 == count2

    def test_window_boundary_conditions(self):
        """Test windowing with edge cases and boundary conditions."""
        # Very small target
        text = "Short"
        windows = window_text_by_tokens(text, model="small", target=1, overlap=0)
        assert len(windows) >= 1

        # Zero overlap
        text = "This is a test"
        windows = window_text_by_tokens(text, model="small", target=5, overlap=0)
        for i in range(len(windows) - 1):
            _, _, end1 = windows[i]
            _, start2, _ = windows[i + 1]
            # With zero overlap, windows should be adjacent
            assert start2 == end1

    def test_unicode_handling(self):
        """Test token counting and windowing with Unicode text."""
        unicode_text = "Hello 世界 🌍 Emoji test 🚀"

        # Should not crash
        count = count_tokens(unicode_text)
        assert count > 0

        windows = window_text_by_tokens(
            unicode_text, model="small", target=10, overlap=2
        )
        assert len(windows) >= 1

        # Verify content preservation
        for sub, start, end in windows:
            assert sub == unicode_text[start:end]
