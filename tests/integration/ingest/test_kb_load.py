"""Integration tests for KB loading with hashing and ignore patterns."""

from __future__ import annotations

from kb.hashing import canonicalize_text, hash_text
from kb.ignores import DEFAULT_IGNORE_PATTERNS, build_ignore_set
from tests.kb_utils import FIXTURE_REPO_ROOT


def test_ignore_patterns():
    """Test ignore patterns include defaults and custom additions without duplication."""
    ignores = build_ignore_set({"*.log", "coverage"})
    assert ".env" in ignores
    assert "*.log" in ignores
    assert len(ignores) >= len(DEFAULT_IGNORE_PATTERNS), "Ignore set should not shrink"


def test_text_canonicalization():
    """Test canonicalization trims trailing whitespace but keeps newline semantics."""
    raw_text = "alpha  \n beta\t\n"
    canonical = canonicalize_text(raw_text)
    assert canonical == "alpha\n beta\n"


def test_hash_stability():
    """Test hashing is stable across whitespace-only differences and newline formats."""
    base_text = "alpha\n beta\n"
    raw_text = "alpha  \n beta\t\n"
    windows_text = base_text.replace("\n", "\r\n")
    assert hash_text(base_text) == hash_text(raw_text)
    assert hash_text(base_text) == hash_text(windows_text)


def test_fixture_file_hash_determinism():
    """Test fixture file hash is deterministic regardless of newline normalization."""
    doc_path = FIXTURE_REPO_ROOT / "docs" / "overview.md"
    original = doc_path.read_text(encoding="utf-8")
    mutated = original.replace("\n", "\r\n")
    assert hash_text(original) == hash_text(mutated)
