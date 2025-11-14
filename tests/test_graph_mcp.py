#!/usr/bin/env python3
"""Test script for graph-enriched MCP search."""

import json
import subprocess
import sys


def test_mcp_search():
    """Test the search_knowledge MCP tool with graph context."""

    # Test query
    test_request = {
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

    print("🔍 Testing MCP search_knowledge tool with graph context...")
    print(f"Query: {test_request['params']['arguments']['query']}")
    print(f"Repo: {test_request['params']['arguments']['repos']}")
    print()

    try:
        # Call the MCP bridge
        result = subprocess.run(
            ["bun", "run", "mcp-bridge/src/index.ts"],
            input=json.dumps(test_request) + "\n",
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            print("❌ MCP server error:")
            print(result.stderr)
            return False

        # Parse response
        response = json.loads(result.stdout.strip())

        if "error" in response:
            print(f"❌ MCP error: {response['error']}")
            return False

        # Extract results
        content = response.get("result", {}).get("content", [])

        print("✅ Search completed successfully!")
        print(f"📊 Results: {len([c for c in content if c.get('type') == 'resource'])} hits")
        print()

        # Check for graph context in prompt-ready text
        for block in content:
            if block.get("type") == "text" and "Code Graph Context" in block.get("text", ""):
                print("✅ Graph context found in results!")
                print()
                # Print a snippet
                text = block["text"]
                lines = text.split("\n")
                context_start = next(
                    (i for i, line in enumerate(lines) if "Code Graph Context" in line),
                    None,
                )
                if context_start is not None:
                    context_snippet = "\n".join(lines[context_start : context_start + 20])
                    print("Sample graph context:")
                    print("-" * 60)
                    print(context_snippet)
                    print("-" * 60)
                return True

        print("⚠️  No graph context found in results")
        print("   This is expected if:")
        print("   - Repository hasn't been reindexed yet")
        print("   - No code entities overlap with search results")
        print()
        return False

    except subprocess.TimeoutExpired:
        print("❌ MCP server timeout")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse MCP response: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    success = test_mcp_search()
    sys.exit(0 if success else 1)
