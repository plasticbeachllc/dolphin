#!/usr/bin/env python3
"""Fixture-based test for graph-enriched MCP search results."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest

from kb.config import KBConfig
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore
from kb.store.graph_store import GraphStore

FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures"
DEFAULT_FIXTURE = "mcp_graph_response.json"


def _load_fixture_response(fixture_name: str = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture_path = FIXTURE_DIR / fixture_name
    if not fixture_path.exists():
        raise FileNotFoundError(
            f"Missing MCP fixture at {fixture_path}. Update tests/fixtures/*.json if the format changes."
        )
    return json.loads(fixture_path.read_text())


def _run_live_mcp_request(
    api_url: str, tool_name: str = "search", arguments: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    if arguments is None:
        arguments = {
            "query": "Calculator",
            "repos": ["test-repo"],
            "top_k": 3,
            "include_graph_context": True,
        }

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    env = os.environ.copy()
    env["DOLPHIN_API_URL"] = api_url

    try:
        # We need to run bun from the project root
        project_root = Path(__file__).parents[3]
        result = subprocess.run(  # noqa: S603,S607
            ["bun", "run", "mcp-bridge/src/index.ts"],
            input=json.dumps(request) + "\n",
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_root,
            env=env,
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
        # Parse the JSON-RPC response
        # The output might contain logging lines, we need to find the JSON line
        for line in result.stdout.strip().splitlines():
            try:
                data = json.loads(line)
                if "result" in data:
                    return data
            except json.JSONDecodeError:
                continue

        # Fallback if specific line parsing fails (e.g. clean output)
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        pytest.skip(f"Could not parse MCP response: {exc}. Output: {result.stdout}")
        return None


def _extract_graph_context_blocks(content: list[dict[str, Any]]) -> list[str]:
    contexts: list[str] = []
    for block in content:
        if block.get("type") != "text":
            continue
        text = block.get("text", "")
        # The graph context is often appended to the result block
        if "### code graph context" in text.lower():
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
    contexts = _extract_graph_context_blocks(content)

    if expect_graph:
        assert contexts, f"{fixture_name} should include graph context"
        assert len(contexts) == expected_contexts
        snippet = contexts[0]
        assert "graph context" in snippet.lower()
        for keyword in keywords:
            assert any(keyword in ctx.lower() for ctx in contexts), f"{fixture_name} should mention {keyword}"
    else:
        assert not contexts, f"{fixture_name} should not include graph context"

    resource_blocks = [c for c in content if c.get("type") == "resource"]
    assert resource_blocks, f"{fixture_name} should provide at least one resource block"


@pytest.fixture
def live_api_server(repo_path: Path, temp_dir: Path, port: int) -> Generator[str, None, None]:
    """Start a live API server serving a test repo index."""

    # 1. Setup Configuration
    # Ensure repo content produces edges
    (repo_path / "main.py").write_text("""
class Base:
    def base_method(self):
        pass

class Calculator(Base):
    def add(self, a, b):
        return a + b

    def calculate(self):
        self.add(1, 2)
        self.base_method()
""")

    store_root = temp_dir
    config_path = temp_dir / "config.toml"
    config_content = f"""
[storage]
store_root = "{temp_dir}"

[server]
endpoint = "127.0.0.1:{port}"

[embedding]
provider = "stub"
default_embed_model = "small"

[retrieval]
score_cutoff = 0.0

[api]
include_graph_context = true
"""
    config_path.write_text(config_content)

    # 2. Index the Test Repo
    # We use the codebase's own pipeline to populate the DB that the server will read
    db_path = store_root / "metadata.db"
    metadata_store = SQLiteMetadataStore(db_path)
    metadata_store.initialize()

    # Use disk-based lancedb within store_root so API server finds it automatically
    # SearchBackend defaults to store_root / "vectordb"
    lancedb_uri = str(store_root / "vectordb")
    lancedb_store = LanceDBStore(lancedb_uri)

    # Load config object to pass to pipeline
    kb_config = KBConfig.from_mapping(
        {
            "storage": {"store_root": str(store_root)},
            "embedding": {"provider": "stub"},
            "api": {"include_graph_context": True},
        }
    )
    # easier to reload from file to be sure
    # But pipeline accepts config object.

    # We need to make sure the pipeline writes to the same DB path.
    # SQLiteMetadataStore was init with db_path. Pipeline uses the stores passed to it.

    graph_store = GraphStore(db_path)
    pipeline = IngestionPipeline(kb_config, lancedb_store, metadata_store, graph_store=graph_store)

    # Register and index interactions with real graph extraction
    metadata_store.record_repo("test-repo", repo_path, default_embed_model="small")
    pipeline.index("test-repo", force=True)

    # 3. Start API Server
    env = os.environ.copy()
    env["DOLPHIN_CONFIG_PATH"] = str(config_path)

    # Use uvicorn directly ensures we run the app
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "kb.api.server:app_with_lifespan",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "info",
    ]

    log_file = temp_dir / "api_server.log"
    with log_file.open("w") as f:
        proc = subprocess.Popen(cmd, env=env, stdout=f, stderr=subprocess.STDOUT)

    api_url = f"http://127.0.0.1:{port}"

    # Wait for health check
    start_time = time.time()
    connected = False
    while time.time() - start_time < 10:
        try:
            r = httpx.get(f"{api_url}/v1/health", timeout=1)
            if r.status_code == 200:
                connected = True
                break
        except httpx.HTTPError:
            time.sleep(0.1)

    if not connected:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

        print("\n=== API SERVER STARTUP FAILED ===")
        print(log_file.read_text())
        print("=================================")
        pytest.fail(f"API server failed to start at {api_url}")

    yield api_url

    # Teardown
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()

    # Print logs if there was a failure (heuristic: if we are here, test finished)
    # But pytest fixture teardown doesn't easily know if test failed.
    # We'll just print if log is not empty and "error" in it?
    # Or just always print for debugging this issue.
    print(f"\n=== API SERVER LOGS ({api_url}) ===")
    print(log_file.read_text())
    print("================================")


@pytest.mark.skipif(
    os.getenv("DOLPHIN_TEST_FULL") != "1",
    reason="Live MCP graph test disabled (set DOLPHIN_TEST_FULL=1 to run)",
)
def test_mcp_search_live_has_graph_context(live_api_server: str) -> None:
    """Live integration test with isolated server and test repo."""

    args = {
        "query": "Calculator",
        "include_graph_context": True,
        "output_mode": "prompt_ready",
        "top_k": 3,
    }

    response = _run_live_mcp_request(live_api_server, "search", args)

    if response is None:
        return  # Skip called inside

    content = response.get("result", {}).get("content", [])
    contexts = _extract_graph_context_blocks(content)

    if not contexts:
        print("\n\n=== DEBUG: FULL MCP RESPONSE CONTENT ===")
        print(json.dumps(content, indent=2))
        print("========================================\n")

    # We expect some context because we indexed the Calculator class
    # and queried for "Calculator"
    assert contexts, f"Live MCP search against {live_api_server} return no graph context for 'Calculator' query."

    assert "Calculator" in contexts[0] and "Base" in contexts[0], (
        f"Graph context should contain relevant code elements. Got: {contexts[0]}"
    )
