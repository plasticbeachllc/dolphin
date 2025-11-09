# Dolphin Agent Core

Agent orchestrator with adaptive planning and Claude AI integration.

## Overview

The Agent Core is the brain of the Dolphin VSCode extension. It manages:

- **Task Planning**: Analyzes user requests and plans execution strategies
- **Claude Integration**: Unified interface for both Claude CLI (subscription) and API modes
- **Knowledge Bank**: Searches indexed codebases for relevant context
- **Event System**: Emits events for UI updates and progress tracking

## Architecture

```
┌─────────────────────────────────────────┐
│         VSCode Extension                │
│  ┌─────────────────────────────────┐    │
│  │      AgentBridge (JSON-RPC)     │    │
│  └──────────────┬──────────────────┘    │
└─────────────────┼───────────────────────┘
                  │ stdio
                  ▼
┌─────────────────────────────────────────┐
│         Agent Core (Bun)                │
│  ┌──────────────┐  ┌─────────────────┐  │
│  │   Planner    │  │  ClaudeClient   │  │
│  │  (Tasks)     │◄─┤ (CLI/API modes) │  │
│  └──────┬───────┘  └─────────────────┘  │
│         │                                │
│         ▼                                │
│  ┌─────────────────┐                    │
│  │   KBManager     │                    │
│  │ (Search/Fetch)  │                    │
│  └────────┬────────┘                    │
└───────────┼─────────────────────────────┘
            │ HTTP
            ▼
    ┌───────────────┐
    │  KB REST API  │
    │ (localhost:8000)│
    └───────────────┘
```

## Components

### Planner (`src/planner/`)

- **BasicPlanner**: Executes user tasks by querying Knowledge Bank and generating responses via Claude
- **Future**: Adaptive planner with architect/editor modes

### Claude Client (`src/llm/`)

- **ClaudeClient**: Unified interface for Claude interactions
  - Auto-detects authentication mode (CLI subscription vs API key)
  - Supports streaming (API) and batch (CLI) responses
  - Handles errors and retries

- **ClaudeCLIDetector**: Detects Claude CLI installation and authentication status
- **ClaudeCLIProcess**: Manages Claude CLI subprocess execution

### Knowledge Bank Manager (`src/kb/`)

- **KBManager**: Interfaces with Dolphin KB REST API
  - Health checks
  - Search queries
  - Chunk/file fetching
  - Future: Auto-start KB server on extension activation

### MCP Client (`src/mcp/`)

- **MCPClient**: Communicates with MCP servers (planned future integration)

### Storage (`src/storage/`)

- **TOML persistence**: Task and configuration storage

## Development

### Setup

```bash
# Install dependencies
bun install

# Run in development
bun run dev

# Run tests
bun test

# Build
bun run build
```

### Project Structure

```
agent-core/
├── src/
│   ├── main.ts                    # Entry point, agent orchestration
│   ├── planner/
│   │   └── basic-planner.ts      # Task planning with Claude
│   ├── llm/
│   │   ├── claude-client.ts      # Unified Claude interface
│   │   ├── claude-cli/
│   │   │   ├── detector.ts       # CLI detection
│   │   │   └── process.ts        # CLI subprocess management
│   │   └── README.md             # LLM integration docs
│   ├── kb/
│   │   └── manager.ts            # KB lifecycle management
│   ├── mcp/
│   │   └── client.ts             # MCP protocol support
│   └── storage/
│       └── toml.ts               # TOML persistence
├── tests/
│   └── *.test.ts                 # Unit tests
└── package.json
```

## Features

### Dual Authentication Support

**Claude CLI (Recommended for Development)**:
- Uses your Claude Pro/Max/Team subscription
- No API costs
- Batch response mode

**API Key (Production)**:
- Direct Anthropic API access
- Streaming responses
- Requires `ANTHROPIC_API_KEY` environment variable

### Knowledge Bank Integration

The agent automatically searches your indexed codebase when processing user queries:

1. User asks: "How does authentication work?"
2. Agent searches KB for "authentication"
3. KB returns top-ranked code snippets
4. Agent sends snippets + query to Claude
5. Claude generates response with code context

### Event System

Agent emits events for UI synchronization:

- `agent_ready`: Agent initialization complete
- `task_started`: New task execution begins
- `tool_call_started`: KB search or tool use initiated
- `tool_call_finished`: Tool completed with results
- `task_completed`: Task finished (success/error)
- `message_chunk`: Streaming response chunk (API mode only)

## Testing

```bash
# Run all tests
bun test

# Run specific test file
bun test src/llm/claude-client.test.ts

# Watch mode
bun test --watch
```

Current test coverage: **3/3 tests passing** (requires authentication setup)

## Integration with VSCode Extension

The Agent Core runs as a subprocess spawned by the VSCode extension:

1. Extension activates → spawns `bun run src/main.ts`
2. Agent initializes → emits `agent_ready` event
3. Extension ready → user can send messages
4. User sends message → extension forwards via JSON-RPC
5. Agent processes → emits events for UI updates
6. Task completes → extension displays results

See [vscode-extension README](../vscode-extension/README.md) for extension details.

## Configuration

No configuration files needed. Agent auto-detects:

- Claude CLI installation and auth status
- Anthropic API key from environment
- KB server endpoint (default: http://localhost:8000)

## Troubleshooting

### "No authentication configured"

**Solution**: Set up Claude CLI or API key:

```bash
# Option A: Claude CLI
npm install -g @anthropic-ai/claude-code
claude

# Option B: API Key
export ANTHROPIC_API_KEY=sk-ant-...
```

### "KB server not running"

**Solution**: Start the KB server:

```bash
# In dolphin directory
uv run dolphin serve
```

Future: KB server will auto-start with the extension.

### Tests failing

**Cause**: Tests require authentication to be configured.

**Solution**: Set up auth as above, then rerun tests.

## Contributing

1. Make changes to `src/`
2. Add tests in `tests/`
3. Run `bun test` to verify
4. Run `bun run build` to check compilation
5. Test integration with VSCode extension (F5 in extension dev host)

## License

MIT - see [LICENSE](../LICENSE.md) for details

## Links

- [Main Project README](../README.md)
- [Architecture Documentation](../docs/ARCHITECTURE.md)
- [Testing Guide](../docs/TESTING-GUIDE.md)
- [VSCode Extension](../vscode-extension/README.md)
