"""One canonical source for Dolphin's public MCP tool discovery contract."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from pydantic import BaseModel

from kb.mcp.contracts import (
    OpenRefInput,
    OperationStatusInput,
    RepoAddInput,
    RepoForgetInput,
    RepoListInput,
    RepoSyncInput,
    SearchInput,
    StatusInput,
)

PUBLIC_MCP_TOOL_NAMES: Final[tuple[str, ...]] = (
    "status",
    "repo_list",
    "repo_add",
    "repo_forget",
    "repo_sync",
    "operation_status",
    "search",
    "open_ref",
)

# This hash covers the complete discovery-visible contract: order, names,
# descriptions, annotations, and strict input schemas. Deliberate protocol
# changes must update this pinned value in the same reviewed change.
FROZEN_PUBLIC_REGISTRY_DIGEST: Final = "25955b0697bb5370164936540bc4a68c1b2de98b2ca45b258ffb81d15097e14c"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A transport-neutral public tool definition."""

    name: str
    title: str
    description: str
    input_model: type[BaseModel]
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool

    def input_schema(self) -> dict[str, Any]:
        """Return the strict-compatible schema consumed by every MCP client."""
        return strict_json_schema(self.input_model)


TOOL_REGISTRY: Final[tuple[ToolSpec, ...]] = (
    ToolSpec(
        name="status",
        title="Dolphin status",
        description="Report bounded local readiness and at most the resolved current workspace.",
        input_model=StatusInput,
        read_only=True,
        destructive=False,
        idempotent=True,
        open_world=False,
    ),
    ToolSpec(
        name="repo_list",
        title="List Dolphin workspaces",
        description="Page through actionable registered workspaces without starting work.",
        input_model=RepoListInput,
        read_only=True,
        destructive=False,
        idempotent=True,
        open_world=False,
    ),
    ToolSpec(
        name="repo_add",
        title="Add a Git worktree to Dolphin",
        description=(
            "Explicitly register one local Git worktree. Eligible source content is embedded through OpenAI "
            "when indexing is required. Generate and retain the required cleanup receipt before calling; retry "
            "with the same receipt after a lost response."
        ),
        input_model=RepoAddInput,
        read_only=False,
        destructive=False,
        idempotent=True,
        open_world=True,
    ),
    ToolSpec(
        name="repo_forget",
        title="Forget a Dolphin workspace",
        description=(
            "Release exactly the registration epoch authorized by its repo_add cleanup receipt. "
            "Never deletes source files or Git state."
        ),
        input_model=RepoForgetInput,
        read_only=False,
        destructive=True,
        idempotent=True,
        open_world=False,
    ),
    ToolSpec(
        name="repo_sync",
        title="Synchronize a Dolphin workspace",
        description=(
            "Request safe freshness reconciliation for one workspace. Eligible source content is embedded "
            "through OpenAI only when required."
        ),
        input_model=RepoSyncInput,
        read_only=False,
        destructive=False,
        idempotent=True,
        open_world=True,
    ),
    ToolSpec(
        name="operation_status",
        title="Inspect a Dolphin operation",
        description="Read one immediate, bounded operation snapshot without waiting or changing work.",
        input_model=OperationStatusInput,
        read_only=True,
        destructive=False,
        idempotent=True,
        open_world=False,
    ),
    ToolSpec(
        name="search",
        title="Search indexed code",
        description="Find semantic, lexical, and structural code evidence with bounded task-level output.",
        input_model=SearchInput,
        read_only=True,
        destructive=False,
        idempotent=True,
        open_world=False,
    ),
    ToolSpec(
        name="open_ref",
        title="Open a Dolphin reference",
        description="Read a bounded current-worktree excerpt through a Dolphin-issued search reference.",
        input_model=OpenRefInput,
        read_only=True,
        destructive=False,
        idempotent=True,
        open_world=False,
    ),
)


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Produce the JSON Schema subset accepted by strict MCP/OpenAI tool callers.

    Pydantic already emits the required union shape for ``SearchInput``.  This
    final pass makes every object closed and makes nullable fields explicit
    required values rather than relying on client-specific omission behavior.
    """
    schema = copy.deepcopy(model.model_json_schema())
    _close_schema_objects(schema)
    if schema.get("type") != "object" or "anyOf" in schema or "oneOf" in schema:
        raise RuntimeError("Dolphin public tool schemas require an object root without a root union")
    return schema


def registry_digest(specs: Sequence[ToolSpec] = TOOL_REGISTRY) -> str:
    """Return a stable digest over discovery-visible public tool metadata."""
    payload = [
        {
            "name": spec.name,
            "title": spec.title,
            "description": spec.description,
            "read_only": spec.read_only,
            "destructive": spec.destructive,
            "idempotent": spec.idempotent,
            "open_world": spec.open_world,
            "input_schema": spec.input_schema(),
        }
        for spec in specs
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_frozen_public_registry(
    specs: Sequence[ToolSpec] = TOOL_REGISTRY,
    handlers: Mapping[str, object] | None = None,
) -> None:
    """Reject any registry drift before server discovery is exposed."""
    names = tuple(spec.name for spec in specs)
    if names != PUBLIC_MCP_TOOL_NAMES:
        raise RuntimeError(f"invalid Dolphin 0.3.0 tool registry: {names!r}")
    if len(names) != len(set(names)):
        raise RuntimeError("Dolphin public tool registry contains duplicate names")
    if any(not spec.title or not spec.description for spec in specs):
        raise RuntimeError("Dolphin public tool registry contains incomplete metadata")
    if registry_digest(specs) != FROZEN_PUBLIC_REGISTRY_DIGEST:
        raise RuntimeError("Dolphin public tool registry does not match the frozen 0.3.0 contract")
    if handlers is not None and set(handlers) != set(PUBLIC_MCP_TOOL_NAMES):
        raise RuntimeError("public tool handlers do not match the frozen registry")


def _close_schema_objects(node: object) -> None:
    """Recursively enforce strict-object rules without changing union semantics."""
    if isinstance(node, list):
        for item in node:
            _close_schema_objects(item)
        return
    if not isinstance(node, dict):
        return

    schema_node = cast(dict[str, Any], node)
    properties = schema_node.get("properties")
    if schema_node.get("type") == "object" or isinstance(properties, dict):
        schema_node["additionalProperties"] = False
        schema_node["required"] = list(properties) if isinstance(properties, dict) else []
    for value in schema_node.values():
        _close_schema_objects(value)
