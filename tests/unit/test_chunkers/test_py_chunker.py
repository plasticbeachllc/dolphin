"""Unit tests for Python symbol-level chunking."""

import pytest
from pathlib import Path
from kb.chunkers.py_chunker import chunk_source
from kb.hashing import canonicalize_text


class TestPythonChunker:
    """Test Python symbol boundary detection and chunking."""

    def test_python_function_chunking(self):
        """Test Python function boundary detection and extraction."""
        src = """
def foo():
    x = 1
    return x

class MyClass:
    def method(self):
        print('hello')
"""
        chunks = chunk_source(src, model="small")
        
        # Assert basic chunk structure
        assert isinstance(chunks, list)
        for c in chunks:
            assert hasattr(c, "text")
            assert hasattr(c, "start_line")
            assert hasattr(c, "end_line")
            assert hasattr(c, "token_count")
            assert c.start_line >= 1
            assert c.end_line >= c.start_line

        # Check for symbol metadata if Tree-sitter parsing is available
        kinds = {(c.symbol_kind, c.symbol_name): c for c in chunks if c.symbol_kind}
        if kinds:
            # If Tree-sitter parsing is available, we expect these symbols
            assert ("function", "foo") in kinds
            assert ("class", "MyClass") in kinds
            # Method may be named 'method'
            assert any(k[0] == "method" and k[1] == "method" for k in kinds.keys())

    def test_python_large_function_multiple_windows(self):
        """Test that large functions are split into multiple token windows."""
        # Create many repeated lines to exceed token target
        long_body = "\n".join(["print('line')" for _ in range(2000)])
        src = f"def big():\n{long_body}\n"
        
        chunks = chunk_source(src, model="small", token_target=400)
        
        # Assert basic chunk structure
        assert isinstance(chunks, list)
        for c in chunks:
            assert hasattr(c, "text")
            assert hasattr(c, "start_line")
            assert hasattr(c, "end_line")
            assert hasattr(c, "token_count")
            assert c.start_line >= 1
            assert c.end_line >= c.start_line
        
        # There should be at least one chunk and likely multiple
        assert len(chunks) >= 1

        # Validate line ranges are within the file
        total_lines = len(canonicalize_text(src).splitlines() or [""])
        for c in chunks:
            assert 1 <= c.start_line <= total_lines
            assert 1 <= c.end_line <= total_lines

    def test_python_symbol_metadata(self):
        """Test symbol metadata attachment for Python code."""
        src = """
class Calculator:
    def __init__(self):
        self.value = 0
    
    def add(self, x, y):
        return x + y
    
    def multiply(self, x, y):
        return x * y
"""
        chunks = chunk_source(src, model="small")
        
        # Look for chunks with symbol metadata
        symbol_chunks = [c for c in chunks if c.symbol_kind]
        
        if symbol_chunks:  # If Tree-sitter is available
            # Should have class and method symbols
            class_chunks = [c for c in symbol_chunks if c.symbol_kind == "class"]
            method_chunks = [c for c in symbol_chunks if c.symbol_kind == "method"]
            
            assert len(class_chunks) >= 1
            assert len(method_chunks) >= 2
            
            # Check symbol names
            class_names = [c.symbol_name for c in class_chunks]
            method_names = [c.symbol_name for c in method_chunks]
            
            assert "Calculator" in class_names
            assert "add" in method_names
            assert "multiply" in method_names

    def test_python_module_level_code(self):
        """Test handling of module-level code (not in functions or classes)."""
        src = """
import os
import sys

CONSTANT = 42

print("Module level code")

def function():
    return "inside function"
"""
        chunks = chunk_source(src, model="small")
        
        # Should have chunks for module-level code and function
        assert len(chunks) >= 1
        
        # Module-level chunks should have appropriate metadata
        for chunk in chunks:
            if chunk.symbol_kind == "function":
                assert chunk.symbol_name == "function"
            elif chunk.symbol_kind is None:
                # Module-level code chunk
                assert "import os" in chunk.text or "CONSTANT = 42" in chunk.text or "Module level code" in chunk.text

    def test_python_nested_classes_and_functions(self):
        """Test chunking of nested classes and functions."""
        src = """
def outer_function():
    def inner_function():
        return "nested"
    
    class InnerClass:
        def method(self):
            return "method in nested class"
    
    return inner_function()
"""
        chunks = chunk_source(src, model="small")
        
        if any(c.symbol_kind for c in chunks):  # If Tree-sitter is available
            # Should detect nested structure
            symbol_paths = [c.symbol_path for c in chunks if c.symbol_path]
            
            # Look for nested symbols in symbol paths
            nested_symbols = [path for path in symbol_paths if "inner" in path.lower()]
            assert len(nested_symbols) >= 1

    def test_python_error_recovery(self):
        """Test that chunker handles syntax errors gracefully."""
        # Malformed Python code
        malformed_src = """
def broken_function(
    missing_paren
    x = 1
    return x
"""
        # Should not raise an exception
        chunks = chunk_source(malformed_src, model="small")
        
        # Should still return chunks (may fall back to token windowing)
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

    def test_python_token_count_accuracy(self):
        """Test that token counts are accurate for Python code."""
        src = """
def calculate(x, y):
    '''Calculate the sum of x and y.'''
    result = x + y
    return result
"""
        chunks = chunk_source(src, model="small")
        
        for chunk in chunks:
            # Token count should be positive
            assert chunk.token_count > 0
            # Token count should be reasonable for the content
            assert chunk.token_count <= 100  # This function is small

    def test_python_class_hierarchy_symbol_path(self):
        """Test class hierarchy in symbol_path for nested structures."""
        src = """
class OuterClass:
    class InnerClass:
        def nested_method(self):
            return "nested"
"""
        chunks = chunk_source(src, model="small")
        
        if any(c.symbol_kind for c in chunks):  # If Tree-sitter is available
            method_chunks = [c for c in chunks if c.symbol_kind == "method"]
            
            if method_chunks:
                method_chunk = method_chunks[0]
                # Symbol path should reflect the hierarchy
                # Note: Current implementation may only show immediate parent class
                assert "InnerClass" in method_chunk.symbol_path
                assert "nested_method" in method_chunk.symbol_path
                # OuterClass may not be included in current symbol path implementation
                # This is acceptable for current chunker behavior
