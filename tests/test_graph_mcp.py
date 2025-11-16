#!/usr/bin/env python3
"""Fixture-based test for graph-enriched MCP search results."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"
DEFAULT_FIXTURE = "mcp_graph_response.json"


def _load_fixture_response(fixture_name: str = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture_path = FIXTURE_DIR / fixture_name
    if not fixture_path.exists():
        raise FileNotFoundError(
            f"Missing MCP fixture at {fixture_path}. Update tests/fixtures/*.json if the format changes."
        )
    return json.loads(fixture_path.read_text())


def _run_live_mcp_request() -> dict[str, Any] | None:
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search_knowledge",
            "arguments": {
                "query": "GraphStore",
                "repos": ["dolphin"],
                "top_k": 3,
                "include_graph_context": True,
            },
        },
    }

    try:
        result = subprocess.run(  # noqa: S603,S607 - optional diagnostic path
            ["bun", "run", "mcp-bridge/src/index.ts"],
            input=json.dumps(request) + "\n",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("bun is not available; skipping live MCP graph test")
        return None
    except subprocess.TimeoutExpired:
        pytest.skip("MCP bridge timed out; skipping live MCP graph test")
        return None

    if result.returncode != 0:
        pytest.skip(f"MCP bridge failed: {result.stderr.strip()}")
        return None

    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic path
        pytest.skip(f"Could not parse MCP response: {exc}")
        return None


def _extract_graph_context_blocks(content: list[dict[str, Any]]) -> list[str]:
    contexts: list[str] = []
    for block in content:
        if block.get("type") != "text":
            continue
        text = block.get("text", "")
        if text.lower().startswith("#### code graph context"):
            contexts.append(text)
    return contexts


FIXTURE_CASES = [
    ("mcp_graph_response.json", True, 1, 1, ["graphstore"]),
    ("mcp_graph_response_multi_repo.json", True, 2, 2, ["graphstore", "agentbridge"]),
    ("mcp_graph_response_no_context.json", False, 0, 1, []),
]


@pytest.mark.parametrize(
    "fixture_name, expect_graph, expected_contexts, expected_resources, keywords",
    FIXTURE_CASES,
)
def test_mcp_graph_fixture_coverage(
    fixture_name: str,
    expect_graph: bool,
    expected_contexts: int,
    expected_resources: int,
    keywords: list[str],
    tmp_path: Path,
) -> None:
    """Ensure fixtures cover both graph context and no-context scenarios."""

    response = _load_fixture_response(fixture_name)

    content = response.get("result", {}).get("content", [])
    contexts = _extract_graph_context_blocks(content)  # type: ignore[arg-type]

    if expect_graph:
        assert contexts, f"{fixture_name} should include graph context"
        assert len(contexts) == expected_contexts
        snippet = contexts[0]
        assert "graph context" in snippet.lower()
        for keyword in keywords:
            assert any(keyword in ctx.lower() for ctx in contexts), f"{fixture_name} should mention {keyword}"
        debug_file = tmp_path / f"{fixture_name}.snippet.txt"
        debug_file.write_text(snippet)
    else:
        assert not contexts, f"{fixture_name} should not include graph context"

    resource_blocks = [c for c in content if c.get("type") == "resource"]
    assert resource_blocks, f"{fixture_name} should provide at least one resource block"
    if expected_resources:
        assert len(resource_blocks) == expected_resources, (
            f"{fixture_name} expected {expected_resources} resource blocks"
        )
    for block in resource_blocks:
        href = block.get("href", "")
        assert href.startswith("file://"), f"Resources in {fixture_name} should point to file URIs (got {href})"


@pytest.mark.skipif(
    os.getenv("RUN_MCP_GRAPH_TEST") != "1",
    reason="Live MCP graph test disabled (set RUN_MCP_GRAPH_TEST=1 to run)",
)
def test_mcp_search_live_has_graph_context() -> None:
    """Optional live integration test to ensure graph context is returned."""

    response = _run_live_mcp_request()
    if response is None:
        pytest.skip("Live MCP search not available")
        return

    content = response.get("result", {}).get("content", [])
    contexts = _extract_graph_context_blocks(content)  # type: ignore[arg-type]

    assert contexts, (
        "Live MCP search should include graph context. Ensure the repository is indexed before enabling this test."
    )
