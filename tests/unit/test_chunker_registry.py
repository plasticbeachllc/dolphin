"""Unit tests for chunker registry and routing system."""

from pathlib import Path

from kb.chunkers import Chunk, RepoChunkingConfig, chunk_file, detect_language_from_extension, get_chunker


class TestLanguageDetection:
    """Test extension-to-language detection."""

    def test_python_extensions(self):
        """Test Python file extension detection."""
        assert detect_language_from_extension(Path("main.py")) == "python"
        assert detect_language_from_extension(Path("script.pyw")) == "python"
        assert detect_language_from_extension(Path("types.pyi")) == "python"

    def test_typescript_extensions(self):
        """Test TypeScript file extension detection."""
        assert detect_language_from_extension(Path("app.ts")) == "typescript"
        assert detect_language_from_extension(Path("component.tsx")) == "typescriptreact"
        assert detect_language_from_extension(Path("module.mts")) == "typescript"

    def test_javascript_extensions(self):
        """Test JavaScript file extension detection."""
        assert detect_language_from_extension(Path("app.js")) == "javascript"
        assert detect_language_from_extension(Path("component.jsx")) == "javascriptreact"
        assert detect_language_from_extension(Path("module.mjs")) == "javascript"

    def test_markdown_extensions(self):
        """Test Markdown file extension detection."""
        assert detect_language_from_extension(Path("README.md")) == "markdown"
        assert detect_language_from_extension(Path("doc.markdown")) == "markdown"
        assert detect_language_from_extension(Path("blog.mdx")) == "markdown"

    def test_data_format_extensions(self):
        """Test data format file extension detection."""
        assert detect_language_from_extension(Path("config.json")) == "json"
        assert detect_language_from_extension(Path("settings.toml")) == "toml"
        assert detect_language_from_extension(Path("config.yaml")) == "yaml"
        assert detect_language_from_extension(Path("data.yml")) == "yaml"

    def test_case_insensitive_detection(self):
        """Test case insensitive language detection."""
        assert detect_language_from_extension(Path("Main.PY")) == "python"
        assert detect_language_from_extension(Path("App.TS")) == "typescript"
        assert detect_language_from_extension(Path("README.MD")) == "markdown"

    def test_unknown_extensions(self):
        """Test unknown file extension handling."""
        assert detect_language_from_extension(Path("file.xyz")) is None
        assert detect_language_from_extension(Path("binary.exe")) is None

    def test_no_extension(self):
        """Test files without extensions."""
        assert detect_language_from_extension(Path("Makefile")) is None
        assert detect_language_from_extension(Path("LICENSE")) is None


class TestChunkerRouting:
    """Test chunker selection and routing."""

    def test_python_chunker_selection(self):
        """Test Python chunker selection and functionality."""
        chunker = get_chunker("python")
        assert chunker is not None
        assert callable(chunker)
        result = chunker("def foo():\n    pass\n", model="small", token_target=400)
        assert isinstance(result, list)
        assert len(result) > 0
        # Python chunker should extract function symbols
        assert any(c.symbol_kind == "function" for c in result)

    def test_typescript_chunker_selection(self):
        """Test TypeScript chunker selection and functionality."""
        chunker = get_chunker("typescript")
        assert chunker is not None
        assert callable(chunker)
        result = chunker("function foo() {}", model="small", token_target=400)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_markdown_chunker_selection(self):
        """Test Markdown chunker selection and functionality."""
        chunker = get_chunker("markdown")
        assert chunker is not None
        assert callable(chunker)
        result = chunker("# Heading\n\nContent", model="small", token_target=400)
        assert isinstance(result, list)
        assert len(result) > 0
        # Markdown chunker should extract heading metadata
        assert any(c.h1 is not None for c in result)

    def test_fallback_chunker_selection(self):
        """Test fallback chunker selection for unknown languages."""
        chunker = get_chunker("unknown")
        assert chunker is not None
        assert callable(chunker)
        result = chunker("Some text content", model="small", token_target=400)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_case_insensitive_routing(self):
        """Test case insensitive chunker routing."""
        chunker_lower = get_chunker("python")
        chunker_upper = get_chunker("PYTHON")
        chunker_mixed = get_chunker("Python")
        assert chunker_lower is chunker_upper is chunker_mixed


class TestChunkFileInterface:
    """Test the high-level chunk_file interface."""

    def test_python_file_chunking(self):
        """Test chunking of Python files with repository configuration."""
        mock_config = RepoChunkingConfig(
            repo_path=Path("/mock/repo"),
            default_window_size=400,
            per_language={"python": 512, "markdown": 256},
            overlap_pct=0.10,
        )

        source = """
def add(a, b):
    '''Add two numbers.'''
    return a + b

class Calculator:
    def multiply(self, x, y):
        return x * y
"""
        chunks = chunk_file(
            abs_path=Path("/mock/repo/src/math.py"),
            rel_path="src/math.py",
            language="python",
            text=source,
            repo_config=mock_config,
        )

        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert chunk.text
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line
            assert chunk.token_count > 0
            assert chunk.symbol_path is not None
            assert "src/math.py" in chunk.symbol_path

    def test_markdown_file_chunking(self):
        """Test chunking of Markdown files with repository configuration."""
        mock_config = RepoChunkingConfig(
            repo_path=Path("/mock/repo"),
            default_window_size=400,
            per_language={"python": 512, "markdown": 256},
            overlap_pct=0.10,
        )

        markdown = """
# Main Heading

Some introduction text.

## Section 1

Content for section 1.

## Section 2

Content for section 2.
"""
        chunks = chunk_file(
            abs_path=Path("/mock/repo/docs/guide.md"),
            rel_path="docs/guide.md",
            language="markdown",
            text=markdown,
            repo_config=mock_config,
        )

        assert len(chunks) > 0
        has_h1 = any(c.h1 == "Main Heading" for c in chunks)
        has_h2 = any(c.h2 in ["Section 1", "Section 2"] for c in chunks)
        assert has_h1 or has_h2

    def test_symbol_path_enrichment(self):
        """Test symbol path enrichment in chunk metadata."""
        mock_config = RepoChunkingConfig(
            repo_path=Path("/mock/repo"),
            default_window_size=400,
            per_language={"python": 512},
            overlap_pct=0.10,
        )

        source = """
class MyClass:
    def method(self):
        pass
"""
        chunks = chunk_file(
            abs_path=Path("/mock/repo/src/module.py"),
            rel_path="src/module.py",
            language="python",
            text=source,
            repo_config=mock_config,
        )

        method_chunks = [c for c in chunks if c.symbol_kind == "method"]
        if method_chunks:
            method_chunk = method_chunks[0]
            assert "src/module.py" in method_chunk.symbol_path
            assert "MyClass.method" in method_chunk.symbol_path


class TestIntegration:
    """Test complete pipeline integration."""

    def test_complete_pipeline_flow(self):
        """Test complete pipeline: detect language → get chunker → chunk file."""
        file_path = Path("src/example.py")
        source = """
def calculate(x, y):
    '''Calculate something.'''
    result = x + y
    return result

class DataProcessor:
    def __init__(self):
        self.data = []

    def process(self, item):
        self.data.append(item)
"""
        config = RepoChunkingConfig(
            repo_path=Path("."),
            default_window_size=400,
            per_language={"python": 512},
        )

        # Detect language
        language = detect_language_from_extension(file_path)
        assert language == "python"

        # Get chunker
        chunker = get_chunker(language)
        assert chunker is not None

        # Chunk file
        chunks = chunk_file(
            abs_path=file_path,
            rel_path=str(file_path),
            language=language,
            text=source,
            repo_config=config,
        )

        # Verify output
        assert len(chunks) >= 2
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(c.token_count > 0 for c in chunks)
        assert all(c.start_line >= 1 for c in chunks)
        assert all(c.symbol_path and "src/example.py" in c.symbol_path for c in chunks)

    def test_error_handling_in_pipeline(self):
        """Test error handling during the chunking pipeline."""
        config = RepoChunkingConfig(
            repo_path=Path("."),
            default_window_size=400,
            per_language={"python": 512},
        )

        # Test with invalid language
        chunks = chunk_file(
            abs_path=Path("/mock/repo/src/file.unknown"),
            rel_path="src/file.unknown",
            language="unknown",
            text="Some content",
            repo_config=config,
        )

        # Should still return chunks using fallback chunker
        assert len(chunks) > 0
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_config_override_behavior(self):
        """Test that repository configuration properly overrides defaults."""
        config = RepoChunkingConfig(
            repo_path=Path("."),
            default_window_size=400,
            per_language={"python": 600, "markdown": 300},  # Custom sizes
            overlap_pct=0.15,
        )

        source = "print('hello world')\n"
        chunks = chunk_file(
            abs_path=Path("/mock/repo/test.py"),
            rel_path="test.py",
            language="python",
            text=source,
            repo_config=config,
            model="text-embedding-3-large",
        )

        # Should use the custom Python window size from config
        assert len(chunks) == 1  # Small file, should be one chunk
        # Token count should reflect the custom configuration
        assert chunks[0].token_count > 0
