"""Legacy helpers to validate the single-pass filtering implementation."""

from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath
from typing import Any

from kb.api.app import SearchRequest
from kb.constants.retrieval_config import RETRIEVAL_PARAMS


def _normalize_path(path_str: str) -> PurePosixPath:
    path_str = path_str.lstrip("./")
    path_str = path_str.lstrip("/")
    return PurePosixPath(path_str)


def legacy_apply_request_filters(
    results: list[dict[str, Any]], request: SearchRequest
) -> list[dict[str, Any]]:
    """Reproduce the historical multi-pass filtering logic."""

    filtered = results

    if request.repos:
        repo_set = set(request.repos)
        filtered = [r for r in filtered if r.get("repo") in repo_set]

    if request.path_prefix:

        def matches_prefix(path_str: str) -> bool:
            path = _normalize_path(path_str)
            for prefix_str in request.path_prefix or []:
                prefix = _normalize_path(prefix_str)
                try:
                    path.relative_to(prefix)
                    return True
                except ValueError:
                    continue
            return False

        filtered = [r for r in filtered if matches_prefix(str(r.get("path", "")))]

    if request.exclude_paths:

        def matches_excluded_path(path_str: str) -> bool:
            path = _normalize_path(path_str)
            for excl_str in request.exclude_paths or []:
                excl = _normalize_path(excl_str)
                try:
                    path.relative_to(excl)
                    return True
                except ValueError:
                    continue
            return False

        filtered = [r for r in filtered if not matches_excluded_path(str(r.get("path", "")))]

    if request.exclude_patterns:

        def matches_excluded_pattern(path_str: str) -> bool:
            path = _normalize_path(path_str)
            for pattern in request.exclude_patterns or []:
                if fnmatch.fnmatch(str(path), pattern) or fnmatch.fnmatch(path.name, pattern):
                    return True
            return False

        filtered = [r for r in filtered if not matches_excluded_pattern(str(r.get("path", "")))]

    return filtered


def legacy_apply_file_type_scoring(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply the legacy config-file scoring penalty."""

    adjusted: list[dict[str, Any]] = []
    for result in results:
        path_obj = result.get("path", "")
        path = str(path_obj) if path_obj else ""
        score_obj = result.get("score", 0.0)
        score = float(score_obj) if isinstance(score_obj, (int, float)) else 0.0
        lower = path.lower()
        is_config = (
            lower.endswith(".toml")
            or lower.endswith(".json")
            or lower.endswith(".yaml")
            or lower.endswith(".yml")
            or "config.toml" in lower
            or "package.json" in lower
            or "tsconfig.json" in lower
        )

        if is_config:
            adjusted.append(
                {
                    **result,
                    "score": score * RETRIEVAL_PARAMS.CONFIG_FILE_SCORE_PENALTY,
                }
            )
        else:
            adjusted.append(result)

    return adjusted


def legacy_filter_and_score(
    results: list[dict[str, Any]], request: SearchRequest
) -> list[dict[str, Any]]:
    """Convenience helper that chains filtering and scoring."""

    return legacy_apply_file_type_scoring(legacy_apply_request_filters(results, request))
