# Dolphin Agent Core

Agent orchestrator with adaptive planning.

## Development

```bash
# Install dependencies
bun install

# Run
bun run dev

# Test
bun test
```

## Structure

- `src/main.ts` - Entry point
- `src/planner/` - Adaptive planner (architect/editor modes)
- `src/executor/` - Plan executor
- `src/llm/` - Claude API client
- `src/mcp/` - MCP client
- `src/storage/` - TOML persistence