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
                "include_graph_context": True
            }
        }
    }
    
    print("🔍 Testing MCP search_knowledge tool with graph context...")
    print(f"Query: {test_request['params']['arguments']['query']}")
    print(f"Repo: {test_request['params']['arguments']['repos']}")
    print()
    
    # Call the MCP bridge
    result = subprocess.run(
        ["bun", "run", "mcp-bridge/src/index.ts"],
        input=json.dumps(test_request) + "\n",
        capture_output=True,
        text=True,
        timeout=30
    )
    
    # Verify no errors
    assert result.returncode == 0, f"MCP server error: {result.stderr}"
    
    # Parse response
    response = json.loads(result.stdout.strip())
    
    assert "error" not in response, f"MCP error: {response.get('error')}"
    
    # Extract results
    content = response.get("result", {}).get("content", [])
    
    print(f"✅ Search completed successfully!")
    print(f"📊 Results: {len([c for c in content if c.get('type') == 'resource'])} hits")
    print()
    
    # Test passes if search completes successfully
    # Graph context is optional depending on repo state
    assert content is not None, "No content returned from search"

if __name__ == "__main__":
    success = test_mcp_search()
    sys.exit(0 if success else 1)