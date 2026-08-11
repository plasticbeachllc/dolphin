"""Tests for strict shared task-level search scope semantics."""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from kb.search_scope import ResolvedSearchScope, SearchScope, SearchScopeError, WorkspaceScopeCount


def test_scope_normalizes_aliases_order_and_digest() -> None:
    first = SearchScope.from_inputs(
        paths=["src/**/*.py", "README?"],
        exclude_paths=["src/generated/**"],
        languages=["TS", "py", "typescript", "rs"],
    )
    second = SearchScope.from_inputs(
        paths=["README?", "src/**/*.py"],
        exclude_paths=["src/generated/**"],
        languages=["python", "ts", "rust"],
    )

    assert first == second
    assert first.languages == ("python", "rust", "typescript")
    assert first.indexed_languages == ("python", "rust", "typescript", "typescriptreact")
    assert first.filter_shape == "both"
    assert first.digest == second.digest


def test_segment_globs_and_exclude_precedence_are_exact() -> None:
    scope = SearchScope.from_inputs(
        paths=["src/**/*.py", "README?"],
        exclude_paths=["src/generated/**"],
        languages=["python"],
    )

    assert scope.matches("src/main.py", "python")
    assert scope.matches("src/pkg/main.py", "python")
    assert scope.matches("src/pkg\nname/main.py", "python")
    assert SearchScope.from_inputs(paths=["src/**"], exclude_paths=[], languages=[]).matches("src", "python")
    assert scope.matches("README1", "python")
    assert not scope.matches("src/pkg/main.py", "typescript")
    assert not scope.matches("src/generated/main.py", "python")
    assert not scope.matches("src/main.py/child", "python")
    assert not scope.matches("other/main.py", "python")


def test_repeated_globstars_use_bounded_non_backtracking_matching() -> None:
    pattern = "/".join(["**", "a"] * 8 + ["needle.py"])
    scope = SearchScope.from_inputs(paths=[pattern], exclude_paths=[], languages=[])
    adversarial_path = "/".join(["a"] * 1_000 + ["not-the-target.py"])

    started_at = time.monotonic()
    assert not scope.matches(adversarial_path, "python")

    assert time.monotonic() - started_at < 1.0


def test_lance_predicate_uses_only_bounded_validated_literals() -> None:
    scope = SearchScope.from_inputs(
        paths=["src/it's-*.py"],
        exclude_paths=["src/generated/**"],
        languages=["js"],
    )

    assert scope.lance_predicate() == (
        "(regexp_like(relative_path, '^src/it''s-[^/]*\\.py$')) "
        "AND NOT (regexp_like(relative_path, '^src/generated(?:/(?:.|\\n)*)?$')) "
        "AND language IN ('javascript', 'javascriptreact')"
    )


@pytest.mark.parametrize(
    "pattern",
    [
        "",
        "/src/**",
        "./src/**",
        "src/../secret",
        "src//main.py",
        "src/",
        "src\\main.py",
        "src/file**.py",
        "src/**/**",
        "/".join(["**"] * 9),
        "bad\x00path",
    ],
)
def test_scope_rejects_noncanonical_or_unsafe_patterns(pattern: str) -> None:
    with pytest.raises(SearchScopeError, match="canonical and repo-relative"):
        SearchScope.from_inputs(paths=[pattern], exclude_paths=[], languages=[])


def test_scope_rejects_string_sequences_and_unknown_languages() -> None:
    with pytest.raises(SearchScopeError, match="must be a sequence"):
        SearchScope.from_inputs(paths="src/**", exclude_paths=[], languages=[])
    with pytest.raises(SearchScopeError, match="does not support"):
        SearchScope.from_inputs(paths=[], exclude_paths=[], languages=["brainfuck"])


def test_resolved_scope_requires_canonical_exact_total() -> None:
    with pytest.raises(ValidationError, match="searchable chunk total is inconsistent"):
        ResolvedSearchScope(
            scope_digest="a" * 64,
            filter_shape="none",
            workspace_counts=(WorkspaceScopeCount(workspace_id="ws_a", generation_id="gen_a", searchable_chunks=2),),
            searchable_chunks=1,
        )
