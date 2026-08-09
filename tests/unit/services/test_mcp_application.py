"""Tests for the production MCP lifecycle composition root."""

from kb.services.mcp_application import default_mcp_handlers


def test_default_handlers_expose_only_completed_read_services() -> None:
    assert set(default_mcp_handlers()) == {"status", "repo_list", "operation_status"}
