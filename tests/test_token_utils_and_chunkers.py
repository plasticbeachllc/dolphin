from __future__ import annotations

import textwrap

from pb_kb.chunkers.token_utils import window_text_by_tokens, count_tokens
from pb_kb.chunkers.ts_chunker import chunk_source as ts_chunk_source
from pb_kb.chunkers.md_chunker import chunk_markdown
from pb_kb.hashing import canonicalize_text


def _test_window_text_by_tokens_simple():
    text = """def a():\n    print('hello')\n\n# trailing\n"""
    # create windows with small target so we get multiple windows
    windows = window_text_by_tokens(text, model="small", target=4, overlap=1)
    # windows should be list of (text, start, end)
    assert isinstance(windows, list)
    assert all(isinstance(w, tuple) and len(w) == 3 for w in windows)
    for sub, s_char, e_char in windows:
        assert text[s_char:e_char] == sub
        assert count_tokens(sub) >= 0


def _test_ts_chunker_basic():
    src = textwrap.dedent("""
    export default class Foo {
      bar() {
        return 1
      }
    }

    const baz = () => {
      return 2
    }

    function qux() {
      return 3
    }
    """)
    chunks = ts_chunk_source(src, lang="typescript", model="small", token_target=50)
    assert isinstance(chunks, list)
    # Require Tree-sitter symbols; fallback (symbol_kind=None) must not occur
    kinds = {(c.symbol_kind, c.symbol_name, c.symbol_path) for c in chunks if c.symbol_kind}
    assert kinds, "Expected symbol-aware chunks; Tree-sitter fallback should not be used"
    # at least one method and one function must be present
    assert any(k[0] == "method" for k in kinds), "Expected at least one method symbol"
    assert any(k[0] == "function" for k in kinds), "Expected at least one function symbol"
    # validate that start/end lines are within file
    total_lines = len(canonicalize_text(src).splitlines() or [""])
    for c in chunks:
        assert 1 <= c.start_line <= total_lines
        assert 1 <= c.end_line <= total_lines


def _test_md_chunker_basic():
    md = textwrap.dedent("""
    # Title

    Some intro text.

    ## Section 1

    Content line 1
    Content line 2

    ## Section 2

    More content
    """)
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


def run_test() -> None:
    _test_window_text_by_tokens_simple()
    _test_ts_chunker_basic()
    _test_md_chunker_basic()
