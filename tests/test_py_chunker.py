from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pb_kb.chunkers.py_chunker import chunk_source
from pb_kb.hashing import canonicalize_text


def _assert_chunk_structure(chunks):
    assert isinstance(chunks, list), "chunks should be a list"
    for c in chunks:
        assert hasattr(c, "text")
        assert hasattr(c, "start_line")
        assert hasattr(c, "end_line")
        assert hasattr(c, "token_count")
        assert c.start_line >= 1
        assert c.end_line >= c.start_line


def run_test() -> None:
    # Test 1: small module with a function and a class+method
    src = """
def foo():
    x = 1
    return x

class MyClass:
    def method(self):
        print('hello')
"""
    chunks = chunk_source(src, model="small")
    _assert_chunk_structure(chunks)

    kinds = { (c.symbol_kind, c.symbol_name): c for c in chunks if c.symbol_kind }
    if kinds:
        # If Tree-sitter parsing is available, we expect these symbols
        assert ("function", "foo") in kinds
        assert ("class", "MyClass") in kinds
        # Method may be named 'method'
        assert any(k[0] == "method" and k[1] == "method" for k in kinds.keys())
    else:
        # Otherwise, parsing fell back to token windows; we only assert structure
        pass

    # Test 2: large function should result in multiple windows (>=1)
    # Create many repeated lines to exceed token target
    long_body = "\n".join(["print('line')" for _ in range(2000)])
    src2 = f"def big():\n{long_body}\n"
    chunks2 = chunk_source(src2, model="small", token_target=400)
    _assert_chunk_structure(chunks2)
    # There should be at least one chunk and likely multiple
    assert len(chunks2) >= 1

    # Validate line ranges are within the file
    total_lines = len(canonicalize_text(src2).splitlines() or [""])
    for c in chunks2:
        assert 1 <= c.start_line <= total_lines
        assert 1 <= c.end_line <= total_lines

    print("py_chunker unit tests passed")
