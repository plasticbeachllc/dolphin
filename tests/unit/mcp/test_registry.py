"""Tests for the frozen 0.3.0 MCP discovery contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kb.mcp.contracts import RepoAddInput, SearchInput
from kb.mcp.registry import PUBLIC_MCP_TOOL_NAMES, TOOL_REGISTRY, registry_digest, require_frozen_public_registry


def test_public_registry_is_exact_and_digest_is_stable() -> None:
    assert tuple(spec.name for spec in TOOL_REGISTRY) == PUBLIC_MCP_TOOL_NAMES
    require_frozen_public_registry()
    assert registry_digest() == registry_digest()


def test_repo_forget_annotations_are_explicit_and_conservative() -> None:
    repo_forget = next(spec for spec in TOOL_REGISTRY if spec.name == "repo_forget")

    assert repo_forget.read_only is False
    assert repo_forget.destructive is True
    assert repo_forget.idempotent is True
    assert repo_forget.open_world is False


def test_every_public_schema_is_closed_and_has_an_object_root() -> None:
    for spec in TOOL_REGISTRY:
        schema = spec.input_schema()
        assert schema["type"] == "object"
        assert "anyOf" not in schema
        assert "oneOf" not in schema
        _assert_closed_objects(schema)


def test_search_schema_uses_a_nested_union() -> None:
    schema = next(spec for spec in TOOL_REGISTRY if spec.name == "search").input_schema()
    request = schema["properties"]["request"]

    assert "anyOf" in request
    assert schema["required"] == ["request"]


def test_search_query_requires_explicit_nulls_and_empty_filters() -> None:
    request = {
        "kind": "query",
        "query": "find authentication",
        "workspace_ids": None,
        "paths": [],
        "exclude_paths": [],
        "languages": [],
        "max_results": None,
        "max_context_tokens": None,
    }

    parsed = SearchInput.model_validate({"request": request})
    assert parsed.request.kind == "query"

    missing_budget = dict(request)
    del missing_budget["max_results"]
    with pytest.raises(ValidationError):
        SearchInput.model_validate({"request": missing_budget})


def test_search_rejects_mixed_query_and_continuation_fields() -> None:
    with pytest.raises(ValidationError):
        SearchInput.model_validate(
            {
                "request": {
                    "kind": "query",
                    "query": "find authentication",
                    "workspace_ids": None,
                    "paths": [],
                    "exclude_paths": [],
                    "languages": [],
                    "max_results": None,
                    "max_context_tokens": None,
                    "cursor": "dolphin-search-v1_example",
                }
            }
        )


def test_repo_add_rejects_relative_paths() -> None:
    with pytest.raises(ValidationError, match="path must be absolute"):
        RepoAddInput.model_validate({"path": "."})


def _assert_closed_objects(node: object) -> None:
    if isinstance(node, list):
        for item in node:
            _assert_closed_objects(item)
        return
    if not isinstance(node, dict):
        return
    if node.get("type") == "object" or "properties" in node:
        assert node["additionalProperties"] is False
        assert set(node["required"]) == set(node.get("properties", {}))
    for value in node.values():
        _assert_closed_objects(value)
