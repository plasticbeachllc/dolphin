from __future__ import annotations

from pb_kb.hashing import canonicalize_text, hash_text
from pb_kb.ignores import DEFAULT_IGNORE_PATTERNS, build_ignore_set
from tests.kb_utils import FIXTURE_REPO_ROOT


def run_test() -> None:
    """Verify ignore patterns and hashing stability for the KB pipeline."""

    # Ignore patterns include defaults and custom additions without duplication.
    ignores = build_ignore_set({"*.log", "coverage"})
    assert ".env" in ignores
    assert "*.log" in ignores
    assert len(ignores) >= len(DEFAULT_IGNORE_PATTERNS), "Ignore set should not shrink"

    # Canonicalization trims trailing whitespace but keeps newline semantics.
    raw_text = "alpha  \n beta\t\n"
    canonical = canonicalize_text(raw_text)
    assert canonical == "alpha\n beta\n"

    # Hashing is stable across whitespace-only differences and newline formats.
    base_text = "alpha\n beta\n"
    windows_text = base_text.replace("\n", "\r\n")
    assert hash_text(base_text) == hash_text(raw_text)
    assert hash_text(base_text) == hash_text(windows_text)

    # Fixture file hash is deterministic regardless of newline normalization.
    doc_path = FIXTURE_REPO_ROOT / "docs" / "overview.md"
    original = doc_path.read_text(encoding="utf-8")
    mutated = original.replace("\n", "\r\n")
    assert hash_text(original) == hash_text(mutated)
