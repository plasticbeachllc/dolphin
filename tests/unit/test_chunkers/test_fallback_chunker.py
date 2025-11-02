"""Unit tests for fallback chunker with token windowing."""

import pytest
from kb.chunkers.fallback_chunker import chunk_text
from kb.chunkers.token_utils import count_tokens, get_tokenizer


class TestFallbackChunker:
    """Test generic token-based chunking for fallback scenarios."""

    def test_empty_text_returns_empty_list(self):
        """Empty text should return empty list."""
        chunks = chunk_text("")
        assert chunks == []

    def test_single_short_chunk(self):
        """Short text should return a single chunk."""
        text = "This is a short text file.\nWith just two lines."
        chunks = chunk_text(text, token_target=100)
        
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].start_line == 1
        assert chunks[0].end_line == 2
        assert chunks[0].token_count > 0
        assert chunks[0].symbol_kind is None
        assert chunks[0].symbol_name is None
        assert chunks[0].symbol_path is None

    def test_multi_chunk_with_overlap(self):
        """Long text should be split into overlapping chunks."""
        # Create a text with enough tokens to require multiple chunks
        lines = [f"Line {i}: This is some content that will be tokenized." for i in range(50)]
        text = "\n".join(lines)
        
        chunks = chunk_text(text, token_target=100, overlap_pct=0.10)
        
        # Should have multiple chunks
        assert len(chunks) > 1
        
        # All chunks should have proper metadata
        for chunk in chunks:
            assert chunk.text
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line
            assert chunk.token_count > 0
            assert chunk.symbol_kind is None
            assert chunk.symbol_name is None
            assert chunk.symbol_path is None
        
        # Chunks should be ordered by line number
        for i in range(len(chunks) - 1):
            assert chunks[i].start_line <= chunks[i + 1].start_line

    def test_line_number_accuracy(self):
        """Line numbers should accurately map to source text."""
        # Create numbered lines for easy verification
        lines = [f"Line {i}" for i in range(1, 21)]
        text = "\n".join(lines)
        
        chunks = chunk_text(text, token_target=50, overlap_pct=0.0)
        
        # Verify that line numbers are in valid ranges
        for chunk in chunks:
            # Start line should be valid
            assert 1 <= chunk.start_line <= 20
            # End line should be >= start line and valid
            assert chunk.start_line <= chunk.end_line <= 20
            
            # The chunk text should appear somewhere in the original text
            assert chunk.text in text or text.startswith(chunk.text) or text.endswith(chunk.text)
            
            # Count actual newlines in chunk and verify it's consistent with line range
            newline_count = chunk.text.count("\n")
            # Line range should be at least as large as newline count
            # (may be larger if chunk ends mid-line)
            assert (chunk.end_line - chunk.start_line) >= newline_count

    def test_trim_leading_trailing_newlines(self):
        """Chunks should have leading/trailing newlines trimmed."""
        text = "\n\n\nSome content here\n\n\nMore content\n\n\n"
        chunks = chunk_text(text, token_target=50)
        
        for chunk in chunks:
            # Should not start or end with newline
            assert not chunk.text.startswith("\n")
            assert not chunk.text.endswith("\n")

    def test_overlap_creates_redundancy(self):
        """Overlapping chunks should share some content."""
        lines = [f"Line {i}: Content for testing overlap functionality." for i in range(30)]
        text = "\n".join(lines)
        
        # Get chunks with overlap
        chunks_with_overlap = chunk_text(text, token_target=80, overlap_pct=0.20)
        
        # Get chunks without overlap
        chunks_no_overlap = chunk_text(text, token_target=80, overlap_pct=0.0)
        
        # With overlap should have more chunks (or same number but with shared content)
        if len(chunks_with_overlap) > 1:
            # Check that consecutive chunks have some overlap
            for i in range(len(chunks_with_overlap) - 1):
                chunk1 = chunks_with_overlap[i]
                chunk2 = chunks_with_overlap[i + 1]
                
                # Second chunk should start before first chunk ends
                assert chunk2.start_line <= chunk1.end_line

    def test_token_count_accuracy(self):
        """Token counts should match actual tokenized content."""
        text = "This is a test document with multiple sentences. " * 20
        chunks = chunk_text(text, token_target=100)
        
        tok = get_tokenizer()
        
        for chunk in chunks:
            # Recount tokens to verify
            actual_count = count_tokens(chunk.text, tok)
            assert chunk.token_count == actual_count

    def test_preserves_indentation(self):
        """Should preserve indentation within chunks."""
        text = """def example():
    if True:
        print("indented")
        for i in range(10):
            print(i)"""
        
        chunks = chunk_text(text, token_target=100)
        
        assert len(chunks) == 1
        # Should preserve the indentation
        assert "    if True:" in chunks[0].text
        assert "        print" in chunks[0].text

    def test_various_file_types(self):
        """Should handle different file content types."""
        # JSON-like content
        json_text = """{\n  "key": "value",\n  "array": [1, 2, 3]\n}"""
        chunks = chunk_text(json_text, token_target=50)
        assert len(chunks) >= 1
        
        # YAML-like content
        yaml_text = """key: value\narray:\n  - item1\n  - item2"""
        chunks = chunk_text(yaml_text, token_target=50)
        assert len(chunks) >= 1
        
        # Plain text
        plain_text = "Just some plain text content here."
        chunks = chunk_text(plain_text, token_target=50)
        assert len(chunks) == 1

    def test_target_token_size(self):
        """Test that chunks approximate the target token size."""
        # Create text that should generate multiple chunks
        lines = [f"This is line {i} with enough content to create tokens." for i in range(100)]
        text = "\n".join(lines)
        
        target_tokens = 50
        chunks = chunk_text(text, token_target=target_tokens, overlap_pct=0.0)
        
        # Most chunks should be close to target size
        for chunk in chunks:
            # Allow some flexibility due to line boundaries
            assert chunk.token_count <= target_tokens * 1.2

    def test_overlap_calculation(self):
        """Test overlap percentage calculation."""
        text = "\n".join([f"Line {i}" for i in range(100)])
        
        overlap_pct = 0.25
        chunks = chunk_text(text, token_target=30, overlap_pct=overlap_pct)
        
        if len(chunks) > 1:
            for i in range(len(chunks) - 1):
                chunk1 = chunks[i]
                chunk2 = chunks[i + 1]
                
                # Calculate overlap in lines
                overlap_lines = chunk1.end_line - chunk2.start_line + 1
                chunk1_lines = chunk1.end_line - chunk1.start_line + 1
                
                # Approximate overlap percentage
                actual_overlap = overlap_lines / chunk1_lines
                
                # Should be roughly the target overlap
                assert abs(actual_overlap - overlap_pct) < 0.15  # Allow some tolerance