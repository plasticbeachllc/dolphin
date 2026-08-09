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
