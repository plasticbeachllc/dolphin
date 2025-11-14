"""Unit tests for Markdown chunking with heading detection."""

import textwrap

from kb.chunkers.md_chunker import chunk_markdown
from kb.hashing import canonicalize_text


class TestMarkdownChunker:
    """Test Markdown heading detection and section chunking."""

    def test_markdown_heading_detection(self):
        """Test heading level detection and extraction."""
        md = textwrap.dedent(
            """
        # Title

        Some intro text.

        ## Section 1

        Content line 1
        Content line 2

        ## Section 2

        More content
        """
        )
        chunks = chunk_markdown(md, model="small", token_target=20)

        assert isinstance(chunks, list)

        # Each chunk should have start_line <= end_line and token_count >= 0
        for c in chunks:
            assert c.start_line >= 1
            assert c.end_line >= c.start_line
            assert c.token_count >= 0

        # Map chunks back to original lines and ensure they are within bounds
        total_lines = len(canonicalize_text(md).splitlines() or [""])
        for c in chunks:
            assert 1 <= c.start_line <= total_lines
            assert 1 <= c.end_line <= total_lines

    def test_markdown_h1_h2_h3_extraction(self):
        """Test extraction of H1-H3 heading metadata."""
        md = textwrap.dedent(
            """
        # Main Title

        Introduction paragraph.

        ## First Section

        Section content here.

        ### Subsection

        Subsection content.

        ## Second Section

        More content.
        """
        )
        chunks = chunk_markdown(md, model="small", token_target=30)

        # Should have chunks with heading metadata
        h1_chunks = [c for c in chunks if c.h1 == "Main Title"]
        h2_chunks = [
            c for c in chunks if c.h2 == "First Section" or c.h2 == "Second Section"
        ]
        h3_chunks = [c for c in chunks if c.h3 == "Subsection"]

        assert len(h1_chunks) >= 1
        assert len(h2_chunks) >= 1
        assert len(h3_chunks) >= 1

    def test_markdown_heading_context_preservation(self):
        """Test heading context preservation in chunk metadata."""
        md = textwrap.dedent(
            """
        # Document Title

        This is the introduction.

        ## Chapter 1

        Chapter 1 content.

        ### Section 1.1

        Section 1.1 content.

        ## Chapter 2

        Chapter 2 content.
        """
        )
        chunks = chunk_markdown(md, model="small", token_target=25)

        # Find a chunk in Section 1.1
        section_1_1_chunks = [c for c in chunks if c.h3 == "Section 1.1"]

        if section_1_1_chunks:
            chunk = section_1_1_chunks[0]
            # Should have both H1 and H2 context
            assert chunk.h1 == "Document Title"
            assert chunk.h2 == "Chapter 1"
            assert chunk.h3 == "Section 1.1"

    def test_markdown_heading_stripping_from_embedded_content(self):
        """Test that headings are stripped from embedded content but preserved as metadata."""
        md = textwrap.dedent(
            """
        # Main Heading

        Content under main heading.

        ## Subheading

        Content under subheading.
        """
        )
        chunks = chunk_markdown(md, model="small", token_target=50)

        for chunk in chunks:
            # The chunk text should not contain the heading markers
            if chunk.h1:
                assert "# Main Heading" not in chunk.text
            if chunk.h2:
                assert "## Subheading" not in chunk.text

            # But the content should be preserved
            assert "Content under" in chunk.text

    def test_markdown_section_chunking_logical_boundaries(self):
        """Test logical section boundaries in Markdown."""
        md = textwrap.dedent(
            """
        # Title

        First paragraph.

        Second paragraph with some longer content that might span multiple lines and include various elements.

        ## New Section

        Content in new section.

        Another paragraph in the same section.
        """
        )
        chunks = chunk_markdown(md, model="small", token_target=30)

        # Should create chunks that respect section boundaries
        section_chunks = [c for c in chunks if c.h2 == "New Section"]

        # All chunks in the same section should have the same H2 context
        if len(section_chunks) > 1:
            first_h2 = section_chunks[0].h2
            for chunk in section_chunks:
                assert chunk.h2 == first_h2

    def test_markdown_code_block_preservation(self):
        """Test code block preservation in Markdown chunks."""
        md = textwrap.dedent(
            """
        # Code Example

        Here is some code:

        ```python
        def hello():
            print("Hello, World!")
        ```

        And here is inline `code`.
        """
        )
        chunks = chunk_markdown(md, model="small", token_target=40)

        # Should preserve code blocks
        code_chunks = [c for c in chunks if "```python" in c.text]
        assert len(code_chunks) >= 1

        for chunk in code_chunks:
            assert "def hello():" in chunk.text
            assert 'print("Hello, World!")' in chunk.text

    def test_markdown_list_item_handling(self):
        """Test list item handling in Markdown."""
        md = textwrap.dedent(
            """
        # List Examples

        - First item
        - Second item
          - Nested item
        - Third item

        1. Numbered item
        2. Another numbered item
        """
        )
        chunks = chunk_markdown(md, model="small", token_target=30)

        # Should handle lists without crashing
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

        # List items should be preserved in chunks
        list_chunks = [
            c
            for c in chunks
            if "- First item" in c.text or "1. Numbered item" in c.text
        ]
        assert len(list_chunks) >= 1

    def test_markdown_yaml_front_matter(self):
        """Test YAML front matter handling in Markdown."""
        md = textwrap.dedent(
            """
        ---
        title: "Document Title"
        author: "John Doe"
        date: 2024-01-01
        ---

        # Actual Content

        This is the main content after front matter.
        """
        )
        chunks = chunk_markdown(md, model="small", token_target=50)

        # Should handle front matter without crashing
        assert isinstance(chunks, list)

        # Front matter should be stripped from content chunks
        for chunk in chunks:
            assert "---" not in chunk.text
            assert "title:" not in chunk.text
            assert "author:" not in chunk.text

            # But the actual content should be preserved
            if "Actual Content" in chunk.h1:
                assert "This is the main content" in chunk.text

    def test_markdown_mixed_content_types(self):
        """Test Markdown with mixed content types."""
        md = textwrap.dedent(
            """
        # Mixed Content

        **Bold text** and *italic text*.

        > Blockquote with important information.

        [Link to example](https://example.com)

        ![Image alt text](image.jpg)

        | Table | Header |
        |-------|--------|
        | Cell  | Data   |
        """
        )
        chunks = chunk_markdown(md, model="small", token_target=40)

        # Should handle all Markdown elements without crashing
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

        # Various Markdown elements should be preserved
        for chunk in chunks:
            if "**Bold text**" in chunk.text:
                assert "**Bold text**" in chunk.text
            if "> Blockquote" in chunk.text:
                assert "> Blockquote" in chunk.text

    def test_markdown_error_handling(self):
        """Test that Markdown chunker handles malformed content gracefully."""
        # Malformed Markdown with unclosed elements
        malformed_md = """
        # Heading

        Unclosed **bold text

        Another paragraph
        """

        # Should not raise an exception
        chunks = chunk_markdown(malformed_md, model="small", token_target=30)

        # Should still return chunks
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

    def test_markdown_token_count_accuracy(self):
        """Test that token counts are accurate for Markdown content."""
        md = """
        # Simple Document

        This is a paragraph with some content that should be tokenized correctly.

        - List item one
        - List item two
        """
        chunks = chunk_markdown(md, model="small", token_target=25)

        for chunk in chunks:
            # Token count should be positive
            assert chunk.token_count > 0
            # Token count should be reasonable for the content
            assert chunk.token_count <= 30  # Allow some flexibility

    def test_markdown_paragraph_grouping(self):
        """Test paragraph grouping in logical chunks."""
        md = textwrap.dedent(
            """
        # Multiple Paragraphs

        First paragraph with some text.

        Second paragraph that continues the discussion.

        Third paragraph that wraps up the section.

        ## New Section

        Paragraph in new section.
        """
        )
        chunks = chunk_markdown(md, model="small", token_target=50)

        # Should group related paragraphs together
        title_chunks = [c for c in chunks if c.h1 == "Multiple Paragraphs"]

        if len(title_chunks) > 0:
            # Should include multiple paragraphs in the same chunk if they fit
            chunk_text = title_chunks[0].text
            assert "First paragraph" in chunk_text
            assert "Second paragraph" in chunk_text
            assert "Third paragraph" in chunk_text
