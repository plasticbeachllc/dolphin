"""Tests for the frozen 0.3.0 MCP discovery contract."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from pydantic import ValidationError

from kb.mcp.contracts import RepoAddInput, SearchInput
from kb.mcp.registry import (
    FROZEN_PUBLIC_REGISTRY_DIGEST,
    PUBLIC_MCP_TOOL_NAMES,
    TOOL_REGISTRY,
    registry_digest,
    require_frozen_public_registry,
)


def test_public_registry_matches_the_committed_frozen_contract() -> None:
    assert tuple(spec.name for spec in TOOL_REGISTRY) == PUBLIC_MCP_TOOL_NAMES
    require_frozen_public_registry()
    assert registry_digest() == FROZEN_PUBLIC_REGISTRY_DIGEST


def test_frozen_registry_rejects_every_discovery_surface_drift() -> None:
    changed_description = (replace(TOOL_REGISTRY[0], description="Different discovery text."), *TOOL_REGISTRY[1:])
    changed_annotation = (replace(TOOL_REGISTRY[0], read_only=False), *TOOL_REGISTRY[1:])
    changed_schema = (replace(TOOL_REGISTRY[0], input_model=RepoAddInput), *TOOL_REGISTRY[1:])

    for changed in (changed_description, changed_annotation, changed_schema):
        with pytest.raises(RuntimeError, match="does not match the frozen"):
            require_frozen_public_registry(changed)


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
    schema_node = cast(dict[str, object], node)
    if schema_node.get("type") == "object" or "properties" in schema_node:
        additional_properties = schema_node.get("additionalProperties")
        required = schema_node.get("required")
        properties = schema_node.get("properties")
        assert additional_properties is False
        assert isinstance(required, list)
        assert isinstance(properties, dict)
        assert set(required) == set(properties)
    for value in schema_node.values():
        _assert_closed_objects(value)
