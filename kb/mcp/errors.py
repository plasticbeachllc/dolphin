"""Bounded, structured errors returned by the Python MCP adapter."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolError(BaseModel):
    """A safe error envelope that agents can act on without parsing prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ToolFailure(Exception):
    """Internal control flow for returning a :class:`ToolError` over MCP."""

    def __init__(self, error: ToolError) -> None:
        super().__init__(error.code)
        self.error = error


def invalid_arguments(message: str) -> ToolError:
    """Return the common strict-schema validation failure shape."""
    return ToolError(code="INVALID_ARGUMENTS", message=message, retryable=False)


def runtime_not_ready(tool_name: str) -> ToolError:
    """Return an explicit non-retryable capability gap while services are wired in."""
    return ToolError(
        code="RUNTIME_NOT_READY",
        message=f"Dolphin's {tool_name} service is not initialized yet.",
        retryable=False,
    )


def cursor_invalid() -> ToolError:
    return ToolError(
        code="CURSOR_INVALID",
        message="The repository-list cursor is invalid; restart repo_list with cursor set to null.",
        retryable=False,
        details={"next_action": {"tool": "repo_list", "arguments": {"cursor": None}}},
    )


def cursor_expired() -> ToolError:
    return ToolError(
        code="CURSOR_EXPIRED",
        message="The repository list changed; restart repo_list with cursor set to null.",
        retryable=False,
        details={"next_action": {"tool": "repo_list", "arguments": {"cursor": None}}},
    )


def operation_missing() -> ToolError:
    return ToolError(
        code="OPERATION_MISSING",
        message="The Dolphin operation is unavailable or its status has expired.",
        retryable=False,
    )


def storage_unavailable() -> ToolError:
    return ToolError(
        code="STORAGE_UNAVAILABLE",
        message="Dolphin's private metadata storage is unavailable.",
        retryable=True,
    )
