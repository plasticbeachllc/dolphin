from __future__ import annotations

from pb_kb.hashing import canonicalize_text, hash_text, verify_hash


def run_test() -> None:
    # Empty input should normalize to a single newline
    assert canonicalize_text("") == "\n"

    # Mixed newlines, trailing whitespace, and surrounding blanks collapse correctly
    messy = "\r\n  hello world   \r\n\r\n"
    assert canonicalize_text(messy) == "  hello world\n"

    # Leading/trailing blank lines are removed but indentation is preserved
    indented = "\n\n    def foo():  \r\n        return 42 \r\n\n"
    expected = "    def foo():\n        return 42\n"
    assert canonicalize_text(indented) == expected

    # Hash determinism across newline formats and trailing spaces
    sample = "print('hi')\r\n"
    with_spaces = "print('hi')   \n"
    h1 = hash_text(sample)
    h2 = hash_text(with_spaces)
    assert h1 == h2
    assert len(h1) == 64
    int(h1, 16)  # raises ValueError if not valid hex

    # verify_hash should be case-insensitive on expected hash input
    assert verify_hash("print('hi')", h1.upper())

    print("hashing tests passed")
