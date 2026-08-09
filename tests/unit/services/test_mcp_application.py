"""Tests for the production MCP lifecycle composition root."""

from kb.services.mcp_application import default_mcp_handlers
from kb.services.workspace_resolution import WorkspaceSessionScope


def test_default_handlers_expose_only_completed_read_services() -> None:
    assert set(default_mcp_handlers(session_scope=WorkspaceSessionScope())) == {
        "status",
        "repo_list",
        "operation_status",
    }
