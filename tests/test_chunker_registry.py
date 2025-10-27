"""Tests for the chunker registry and routing system."""

from __future__ import annotations

from pathlib import Path

from pb_kb.chunkers import (
    Chunk,
    RepoChunkingConfig,
    chunk_file,
    detect_language_from_extension,
    get_chunker,
)


def test_language_detection():
    """Test extension-to-language detection."""
    
    # Python extensions
    assert detect_language_from_extension(Path("main.py")) == "python"
    assert detect_language_from_extension(Path("script.pyw")) == "python"
    assert detect_language_from_extension(Path("types.pyi")) == "python"
    
    # TypeScript extensions
    assert detect_language_from_extension(Path("app.ts")) == "typescript"
    assert detect_language_from_extension(Path("component.tsx")) == "typescriptreact"
    assert detect_language_from_extension(Path("module.mts")) == "typescript"
    
    # JavaScript extensions
    assert detect_language_from_extension(Path("app.js")) == "javascript"
    assert detect_language_from_extension(Path("component.jsx")) == "javascriptreact"
    assert detect_language_from_extension(Path("module.mjs")) == "javascript"
    
    # Markdown extensions
    assert detect_language_from_extension(Path("README.md")) == "markdown"
    assert detect_language_from_extension(Path("doc.markdown")) == "markdown"
    assert detect_language_from_extension(Path("blog.mdx")) == "markdown"
    
    # Data format extensions
    assert detect_language_from_extension(Path("config.json")) == "json"
    assert detect_language_from_extension(Path("settings.toml")) == "toml"
    assert detect_language_from_extension(Path("config.yaml")) == "yaml"
    assert detect_language_from_extension(Path("data.yml")) == "yaml"
    
    # Case insensitive
    assert detect_language_from_extension(Path("Main.PY")) == "python"
    assert detect_language_from_extension(Path("App.TS")) == "typescript"
    assert detect_language_from_extension(Path("README.MD")) == "markdown"
    
    # Unknown extensions
    assert detect_language_from_extension(Path("file.xyz")) is None
    assert detect_language_from_extension(Path("binary.exe")) is None
    
    # No extension
    assert detect_language_from_extension(Path("Makefile")) is None
    assert detect_language_from_extension(Path("LICENSE")) is None
    
    print("✓ Language detection tests passed")


def test_chunker_routing():
    """Test chunker selection and routing."""
    
    # Python chunker selection
    chunker = get_chunker("python")
    assert chunker is not None
    assert callable(chunker)
    result = chunker("def foo():\n    pass\n", model="small", token_target=400)
    assert isinstance(result, list)
    assert len(result) > 0
    # Python chunker should extract function symbols
    assert any(c.symbol_kind == "function" for c in result)
    
    # TypeScript chunker selection
    chunker = get_chunker("typescript")
    assert chunker is not None
    assert callable(chunker)
    result = chunker("function foo() {}", model="small", token_target=400)
    assert isinstance(result, list)
    assert len(result) > 0
    
    # Markdown chunker selection
    chunker = get_chunker("markdown")
    assert chunker is not None
    assert callable(chunker)
    result = chunker("# Heading\n\nContent", model="small", token_target=400)
    assert isinstance(result, list)
    assert len(result) > 0
    # Markdown chunker should extract heading metadata
    assert any(c.h1 is not None for c in result)
    
    # Fallback chunker selection
    chunker = get_chunker("unknown")
    assert chunker is not None
    assert callable(chunker)
    result = chunker("Some text content", model="small", token_target=400)
    assert isinstance(result, list)
    assert len(result) > 0
    
    # Case insensitive routing
    chunker_lower = get_chunker("python")
    chunker_upper = get_chunker("PYTHON")
    chunker_mixed = get_chunker("Python")
    assert chunker_lower is chunker_upper is chunker_mixed
    
    print("✓ Chunker routing tests passed")


def test_chunk_file():
    """Test the high-level chunk_file interface."""
    
    mock_config = RepoChunkingConfig(
        repo_path=Path("/mock/repo"),
        default_window_size=400,
        per_language={"python": 512, "markdown": 256},
        embedding_model="text-embedding-3-small",
        overlap_pct=0.10,
    )
    
    # Python file chunking
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
    
    # Markdown file chunking
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
    
    # Symbol path enrichment
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
    
    print("✓ chunk_file tests passed")


def test_integration():
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
    
    print("✓ Integration test passed")


def run_test():
    """Run all tests for manual execution."""
    test_language_detection()
    test_chunker_routing()
    test_chunk_file()
    test_integration()
    print("\n✅ All chunker registry tests passed!")


if __name__ == "__main__":
    run_test()
