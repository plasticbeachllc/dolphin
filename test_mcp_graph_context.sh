#!/bin/bash

# Test the MCP server's search_knowledge tool with graph context

echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0"}}}' | \
bun run mcp-bridge/src/index.ts 2>/dev/null | head -1

echo '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "search_knowledge", "arguments": {"query": "pipeline index method", "top_k": 2, "include_graph_context": true}}}' | \
bun run mcp-bridge/src/index.ts 2>/dev/null | \
python3 -c "
import sys, json

for line in sys.stdin:
    try:
        msg = json.loads(line)
        if msg.get('id') == 2 and 'result' in msg:
            result = msg['result']
            content = result.get('content', [])
            
            if content and isinstance(content, list):
                for item in content:
                    if item.get('type') == 'text':
                        text = item.get('text', '')
                        
                        # Check for graph context markers
                        has_graph = '## Code Graph Context' in text
                        has_nodes = 'Entities in this code' in text
                        has_edges = 'Relationships:' in text
                        
                        print(f'Graph Context Found: {has_graph}')
                        print(f'Has Nodes Section: {has_nodes}')
                        print(f'Has Edges Section: {has_edges}')
                        
                        if has_graph:
                            print('\nGraph Context Preview:')
                            lines = text.split('\n')
                            for i, line in enumerate(lines):
                                if '## Code Graph Context' in line:
                                    # Print next 20 lines
                                    print('\n'.join(lines[i:min(i+20, len(lines))]))
                                    break
                        else:
                            print('\nNo graph context found in response')
                            print('Response preview (first 500 chars):')
                            print(text[:500])
            break
    except json.JSONDecodeError:
        continue
"