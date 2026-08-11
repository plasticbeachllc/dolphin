"""Strict task-level search scope shared by metadata, keyword, and vector reads."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kb.lifecycle_limits import ENTITY_ID_MAX_LENGTH

SEARCH_SCOPE_FORMAT = "dolphin-search-scope-v1"
MAX_SEARCH_PATH_PATTERNS = 64
MAX_SEARCH_PATH_PATTERN_LENGTH = 512
MAX_SEARCH_LANGUAGES = 7
MAX_SEARCH_SCOPE_WORKSPACES = 32

SearchLanguage = Literal["python", "javascript", "typescript", "svelte", "sql", "markdown", "rust"]
SearchFilterShape = Literal["none", "path", "language", "both"]

_SCOPE_DOMAIN = b"dolphin:search-scope:v1\x00"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_PUBLIC_LANGUAGES = frozenset({"python", "javascript", "typescript", "svelte", "sql", "markdown", "rust"})
_LANGUAGE_ALIASES = {
    "py": "python",
    "js": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "md": "markdown",
    "rs": "rust",
}
_INDEXED_LANGUAGE_FAMILIES = {
    "python": ("python",),
    "javascript": ("javascript", "javascriptreact"),
    "typescript": ("typescript", "typescriptreact"),
    "svelte": ("svelte",),
    "sql": ("sql",),
    "markdown": ("markdown",),
    "rust": ("rust",),
}
_REGEX_META = frozenset(".()+|^$[]{}\\")


class SearchScopeError(RuntimeError):
    """Task-level scope is invalid or cannot be resolved safely."""


class SearchScopeUnavailable(SearchScopeError):
    """Published scope metadata or reader authority is unavailable."""


class SearchScopeTimeout(SearchScopeUnavailable):
    """Exact filtered-scope resolution exceeded its bounded deadline."""


class _ScopeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SearchScope(_ScopeModel):
    """Canonical repo-relative filters with identical local and Lance semantics."""

    paths: tuple[str, ...] = Field(max_length=MAX_SEARCH_PATH_PATTERNS)
    exclude_paths: tuple[str, ...] = Field(max_length=MAX_SEARCH_PATH_PATTERNS)
    languages: tuple[SearchLanguage, ...] = Field(max_length=MAX_SEARCH_LANGUAGES)

    @field_validator("paths", "exclude_paths")
    @classmethod
    def paths_are_canonical(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("search path patterns must be unique and canonically ordered")
        for value in values:
            _validate_path_pattern(value)
        return values

    @field_validator("languages")
    @classmethod
    def languages_are_canonical(cls, values: tuple[SearchLanguage, ...]) -> tuple[SearchLanguage, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("search languages must be unique and canonically ordered")
        return values

    @classmethod
    def from_inputs(
        cls,
        *,
        paths: Sequence[str],
        exclude_paths: Sequence[str],
        languages: Sequence[str],
    ) -> SearchScope:
        """Normalize bounded public inputs without accepting string-as-sequence mistakes."""

        return cls(
            paths=_normalize_patterns(paths, "include"),
            exclude_paths=_normalize_patterns(exclude_paths, "exclude"),
            languages=_normalize_languages(languages),
        )

    @property
    def digest(self) -> str:
        digest = hashlib.sha256()
        digest.update(_SCOPE_DOMAIN)
        for value in (SEARCH_SCOPE_FORMAT, *self.paths, "", *self.exclude_paths, "", *self.languages):
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
        return digest.hexdigest()

    @property
    def filter_shape(self) -> SearchFilterShape:
        has_path = bool(self.paths or self.exclude_paths)
        if has_path and self.languages:
            return "both"
        if has_path:
            return "path"
        if self.languages:
            return "language"
        return "none"

    def matches(self, relative_path: str, language: str) -> bool:
        """Apply exact scope semantics to one canonical indexed membership."""

        if self.paths and not any(re.fullmatch(_glob_regex(pattern), relative_path) for pattern in self.paths):
            return False
        if self.exclude_paths and any(
            re.fullmatch(_glob_regex(pattern), relative_path) for pattern in self.exclude_paths
        ):
            return False
        return not self.languages or language in self.indexed_languages

    @property
    def indexed_languages(self) -> tuple[str, ...]:
        return tuple(sorted({stored for language in self.languages for stored in _INDEXED_LANGUAGE_FAMILIES[language]}))

    def lance_predicate(self) -> str | None:
        """Compile a bounded prefilter using only validated literals and RE2-compatible regex."""

        clauses: list[str] = []
        if self.paths:
            includes = " OR ".join(
                f"regexp_like(relative_path, '{_sql_literal(_glob_regex(pattern))}')" for pattern in self.paths
            )
            clauses.append(f"({includes})")
        if self.exclude_paths:
            excludes = " OR ".join(
                f"regexp_like(relative_path, '{_sql_literal(_glob_regex(pattern))}')" for pattern in self.exclude_paths
            )
            clauses.append(f"NOT ({excludes})")
        if self.languages:
            languages = ", ".join(f"'{_sql_literal(language)}'" for language in self.indexed_languages)
            clauses.append(f"language IN ({languages})")
        return " AND ".join(clauses) or None


class WorkspaceScopeCount(_ScopeModel):
    workspace_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    generation_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    searchable_chunks: int = Field(ge=0)


class ResolvedSearchScope(_ScopeModel):
    """Exact filtered published counts proven under one admitted coverage set."""

    scope_digest: str = Field(pattern=_SHA256_PATTERN)
    filter_shape: SearchFilterShape
    workspace_counts: tuple[WorkspaceScopeCount, ...] = Field(
        min_length=1,
        max_length=MAX_SEARCH_SCOPE_WORKSPACES,
    )
    searchable_chunks: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_are_unique_canonical_and_totaled(self) -> ResolvedSearchScope:
        identities = tuple((item.workspace_id, item.generation_id) for item in self.workspace_counts)
        if identities != tuple(sorted(identities)) or len(set(identities)) != len(identities):
            raise ValueError("resolved workspace scope counts must be unique and canonically ordered")
        if self.searchable_chunks != sum(item.searchable_chunks for item in self.workspace_counts):
            raise ValueError("resolved searchable chunk total is inconsistent")
        return self


def _normalize_patterns(values: Sequence[str], label: str) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise SearchScopeError(f"Dolphin {label} path filters must be a sequence")
    if len(values) > MAX_SEARCH_PATH_PATTERNS:
        raise SearchScopeError(f"Dolphin {label} path filter set is too large")
    normalized = tuple(values)
    if any(not isinstance(value, str) for value in normalized):
        raise SearchScopeError(f"Dolphin {label} path filters are invalid")
    for value in normalized:
        _validate_path_pattern(value)
    return tuple(sorted(set(normalized)))


def _normalize_languages(values: Sequence[str]) -> tuple[SearchLanguage, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise SearchScopeError("Dolphin language filters must be a sequence")
    if len(values) > MAX_SEARCH_LANGUAGES:
        raise SearchScopeError("Dolphin language filter set is too large")
    supplied = tuple(values)
    normalized: set[str] = set()
    for value in supplied:
        if not isinstance(value, str) or not value or value != value.strip() or "\x00" in value:
            raise SearchScopeError("Dolphin language filter is invalid")
        language = _LANGUAGE_ALIASES.get(value.casefold(), value.casefold())
        if language not in _PUBLIC_LANGUAGES:
            raise SearchScopeError(f"Dolphin does not support the requested language filter: {value}")
        normalized.add(language)
    return tuple(sorted(normalized))  # type: ignore[return-value]


def _validate_path_pattern(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_SEARCH_PATH_PATTERN_LENGTH
        or len(value.encode("utf-8")) > MAX_SEARCH_PATH_PATTERN_LENGTH
        or "\x00" in value
        or "\\" in value
        or value.startswith("/")
        or value.endswith("/")
        or "//" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise SearchScopeError("Dolphin search path pattern must be canonical and repo-relative")


def _glob_regex(pattern: str) -> str:
    output = ["^"]
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 1
                if index + 1 < len(pattern) and pattern[index + 1] == "/":
                    output.append("(?:(?:.|\\n)*/)?")
                    index += 1
                else:
                    output.append("(?:.|\\n)*")
            else:
                output.append("[^/]*")
        elif character == "?":
            output.append("[^/]")
        else:
            output.append(f"\\{character}" if character in _REGEX_META else character)
        index += 1
    output.append("$")
    return "".join(output)


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")
