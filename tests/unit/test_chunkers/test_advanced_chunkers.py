"""Advanced tests for chunkers: python, markdown, and fallback behavior."""

from kb.chunkers.fallback_chunker import chunk_text as chunk_fallback
from kb.chunkers.md_chunker import chunk_markdown
from kb.chunkers.py_chunker import chunk_source as chunk_python
from kb.chunkers.token_utils import get_tokenizer


def test_python_chunker_symbol_extraction_with_fallback(monkeypatch):
    src_ok = """
class A:
    def m(self):
        return 1

def f():
    return 2
""".strip()

    chunks = chunk_python(src_ok, model="small", token_target=128, overlap_pct=0.1)
    # Expect at least function/method/class chunks
    assert any(c.symbol_kind == "class" for c in chunks)
    assert any(c.symbol_kind in ("function", "method") for c in chunks)

    # Now simulate tree-sitter failure to trigger fallback
    def boom(*args, **kwargs):
        raise RuntimeError("parser boom")

    from kb.chunkers import py_chunker as pyc

    monkeypatch.setattr(pyc, "_get_python_parser", boom)

    chunks_fb = chunk_python(src_ok, model="small", token_target=64, overlap_pct=0.1)
    # Fallback emits chunks with no symbol metadata
    assert all(c.symbol_kind is None for c in chunks_fb)
    assert sum(c.token_count for c in chunks_fb) > 0


def test_markdown_chunker_headings():
    md = """
# Title

## Section

Some text.

### Subsection

More text.
""".strip()

    chunks = chunk_markdown(md, model="small", token_target=64, overlap_pct=0.1)
    # Ensure headings are captured somewhere across chunks
    assert any(c.h1 == "Title" for c in chunks)
    assert any(c.h2 == "Section" for c in chunks)
    assert any(c.h3 == "Subsection" for c in chunks)


def test_fallback_chunker_windowing_edges():
    get_tokenizer("small")
    text = ("line\n" * 300).strip()
    chunks = chunk_fallback(text, model="small", token_target=50, overlap_pct=0.2)
    # Should produce multiple overlapping windows
    assert len(chunks) > 1
    # Token counts should be non-zero
    assert all(c.token_count > 0 for c in chunks)
    # Line ranges should be increasing
    assert all(chunks[i].start_line <= chunks[i].end_line for i in range(len(chunks)))
