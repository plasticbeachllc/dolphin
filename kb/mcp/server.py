"""Protocol-safe stdio MCP server backed by Dolphin's frozen tool registry."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, ValidationError

from kb.mcp.errors import ToolError, ToolFailure, invalid_arguments, runtime_not_ready
from kb.mcp.registry import TOOL_REGISTRY, ToolSpec, require_frozen_public_registry
from kb.version import get_version

type ToolResult = BaseModel | Mapping[str, Any]
type ToolHandler = Callable[[Any], ToolResult | Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class MCPAdapter:
    """Typed, testable adapter between Dolphin services and MCP callbacks."""

    specs: tuple[ToolSpec, ...]
    handlers: Mapping[str, ToolHandler]

    async def list_tools(self) -> mcp_types.ListToolsResult:
        """Return the frozen discovery list in its canonical order."""
        return mcp_types.ListToolsResult(tools=[_wire_tool(spec) for spec in self.specs])

    async def call_tool(self, params: mcp_types.CallToolRequestParams) -> mcp_types.CallToolResult:
        """Validate one call then delegate it to its registered application service."""
        spec = next((candidate for candidate in self.specs if candidate.name == params.name), None)
        if spec is None:
            return _error_result(ToolError(code="TOOL_UNKNOWN", message="Unknown Dolphin tool.", retryable=False))

        try:
            parsed_input = spec.input_model.model_validate(params.arguments or {})
        except ValidationError as exc:
            return _error_result(invalid_arguments(_validation_message(exc)))

        try:
            handler_result = self.handlers[spec.name](parsed_input)
            result = await handler_result if inspect.isawaitable(handler_result) else handler_result
            if not isinstance(result, BaseModel) and not isinstance(result, Mapping):
                raise TypeError("Dolphin MCP handlers must return a Pydantic model or mapping")
            return _success_result(cast(ToolResult, result))
        except ToolFailure as exc:
            return _error_result(exc.error)
        except Exception:
            return _error_result(
                ToolError(
                    code="INTERNAL_ERROR",
                    message="Dolphin could not complete this request safely.",
                    retryable=True,
                )
            )


def create_server(
    handlers: Mapping[str, ToolHandler] | None = None,
    *,
    specs: Sequence[ToolSpec] = TOOL_REGISTRY,
    version: str | None = None,
) -> Server:
    """Create the fixed Dolphin MCP server without any resources or prompts.

    ``handlers`` is dependency injection for the transport-independent
    application services. Until a service is supplied, a tool deliberately
    returns a bounded readiness result instead of disappearing from discovery.
    """
    adapter = create_adapter(handlers, specs=specs)

    async def list_tools(
        _context: Any,
        _params: mcp_types.PaginatedRequestParams | None,
    ) -> mcp_types.ListToolsResult:
        return await adapter.list_tools()

    async def call_tool(
        _context: Any,
        params: mcp_types.CallToolRequestParams,
    ) -> mcp_types.CallToolResult:
        return await adapter.call_tool(params)

    return Server(
        "dolphin",
        version=version or get_version(),
        title="Dolphin",
        description="Semantic code search and repository knowledge for coding agents.",
        instructions=(
            "Call status first and honor its per-tool availability. When repo_add is available, register the exact "
            "current Git worktree before repository-scoped work. Use operation_status only for an exact operation ID."
        ),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def create_adapter(
    handlers: Mapping[str, ToolHandler] | None = None,
    *,
    specs: Sequence[ToolSpec] = TOOL_REGISTRY,
) -> MCPAdapter:
    """Create a validated service adapter independently of the stdio server."""
    resolved_handlers = _complete_handlers(handlers, specs)
    require_frozen_public_registry(specs, resolved_handlers)
    return MCPAdapter(specs=tuple(specs), handlers=resolved_handlers)


def run_stdio() -> None:
    """Run Dolphin's installed stdio transport with the application composition root."""
    asyncio.run(_serve_stdio())


async def _serve_stdio() -> None:
    """Own exactly one stdio connection for the foreground Dolphin process."""
    from kb.services import WorkspaceSessionScope, default_mcp_handlers

    async with stdio_server() as (read_stream, write_stream):
        # MCP 2026-07-28 has no client-roots request surface. Keep the
        # connection-owned scope here; root snapshots can join this boundary
        # when the transport exposes them again.
        session_scope = WorkspaceSessionScope()
        server = create_server(default_mcp_handlers(session_scope=session_scope))
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="dolphin",
                server_version=get_version(),
                capabilities=server.get_capabilities(notification_options=NotificationOptions()),
            ),
        )


def _complete_handlers(
    handlers: Mapping[str, ToolHandler] | None,
    specs: Sequence[ToolSpec],
) -> dict[str, ToolHandler]:
    supplied = dict(handlers or {})
    unknown = set(supplied) - {spec.name for spec in specs}
    if unknown:
        raise RuntimeError(f"unknown Dolphin MCP handler(s): {sorted(unknown)!r}")
    for spec in specs:
        supplied.setdefault(spec.name, _not_ready_handler(spec.name))
    return supplied


def _not_ready_handler(tool_name: str) -> ToolHandler:
    def handler(_input: BaseModel) -> Mapping[str, Any]:
        raise ToolFailure(runtime_not_ready(tool_name))

    return handler


def _wire_tool(spec: ToolSpec) -> mcp_types.Tool:
    return mcp_types.Tool(
        name=spec.name,
        title=spec.title,
        description=spec.description,
        input_schema=spec.input_schema(),
        annotations=mcp_types.ToolAnnotations(
            read_only_hint=spec.read_only,
            destructive_hint=spec.destructive,
            idempotent_hint=spec.idempotent,
            open_world_hint=spec.open_world,
        ),
    )


def _success_result(result: ToolResult) -> mcp_types.CallToolResult:
    structured = result.model_dump(mode="json") if isinstance(result, BaseModel) else dict(result)
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(text=json.dumps(structured, sort_keys=True, separators=(",", ":")))],
        structured_content=structured,
    )


def _error_result(error: ToolError) -> mcp_types.CallToolResult:
    structured = error.model_dump(mode="json")
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(text=json.dumps(structured, sort_keys=True, separators=(",", ":")))],
        structured_content=structured,
        is_error=True,
    )


def _validation_message(exc: ValidationError) -> str:
    """Reduce Pydantic's detailed internals to a bounded agent-facing signal."""
    locations = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
    fields = ", ".join(locations[:3])
    suffix = "" if len(locations) <= 3 else ", …"
    return f"Arguments do not match Dolphin's strict tool schema: {fields}{suffix}."
