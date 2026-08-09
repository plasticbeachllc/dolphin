"""Composition root for MCP-facing Dolphin application services."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from kb.mcp.contracts import StatusInput
from kb.services.status import StatusService


def default_mcp_handlers() -> dict[str, Callable[[BaseModel], BaseModel]]:
    """Return the currently available 0.3.0 application-service handlers."""
    status = StatusService()

    def handle_status(input_model: BaseModel) -> BaseModel:
        if not isinstance(input_model, StatusInput):
            raise TypeError("status must receive StatusInput")
        return status(input_model)

    return {"status": handle_status}
