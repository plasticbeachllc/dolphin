"""Unit tests for text hashing and canonicalization."""

from kb.hashing import canonicalize_text, hash_text, verify_hash


class TestCanonicalizeText:
    """Test text normalization and canonicalization."""

    def test_empty_input_normalizes_to_newline(self):
        """Empty input should normalize to a single newline."""
        assert canonicalize_text("") == "\n"

    def test_mixed_newlines_and_trailing_whitespace(self):
        """Mixed newlines, trailing whitespace, and surrounding blanks collapse correctly."""
        messy = "\r\n  hello world   \r\n\r\n"
        assert canonicalize_text(messy) == "  hello world\n"

    def test_preserves_indentation_removes_blank_lines(self):
        """Leading/trailing blank lines are removed but indentation is preserved."""
        indented = "\n\n    def foo():  \r\n        return 42 \r\n\n"
        expected = "    def foo():\n        return 42\n"
        assert canonicalize_text(indented) == expected

    def test_single_trailing_newline_enforcement(self):
        """Ensure single trailing newline is enforced."""
        # Multiple trailing newlines
        assert canonicalize_text("text\n\n") == "text\n"
        # No trailing newline
        assert canonicalize_text("text") == "text\n"
        # Single trailing newline (unchanged)
        assert canonicalize_text("text\n") == "text\n"


class TestHashText:
    """Test SHA256 hashing stability and correctness."""

    def test_hash_determinism(self):
        """Hash determinism across newline formats and trailing spaces."""
        sample = "print('hi')\r\n"
        with_spaces = "print('hi')   \n"
        h1 = hash_text(sample)
        h2 = hash_text(with_spaces)
        assert h1 == h2

    def test_hash_format(self):
        """Test hash format (64-char hex lowercase)."""
        sample = "test content"
        h = hash_text(sample)
        assert len(h) == 64
        # Should be valid hex
        int(h, 16)
        # Should be lowercase
        assert h == h.lower()

    def test_different_inputs_produce_different_hashes(self):
        """Test that different inputs produce different hashes."""
        h1 = hash_text("content one")
        h2 = hash_text("content two")
        assert h1 != h2


class TestVerifyHash:
    """Test hash verification functionality."""

    def test_verify_hash_case_insensitive(self):
        """verify_hash should be case-insensitive on expected hash input."""
        text = "print('hi')"
        h = hash_text(text)
        assert verify_hash(text, h.upper())

    def test_verify_hash_correct(self):
        """Test that verify_hash returns True for matching text and hash."""
        text = "test content"
        h = hash_text(text)
        assert verify_hash(text, h)

    def test_verify_hash_incorrect(self):
        """Test that verify_hash returns False for mismatched text and hash."""
        text = "test content"
        h = hash_text("different content")
        assert not verify_hash(text, h)
