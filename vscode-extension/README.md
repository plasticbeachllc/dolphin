# Dolphin VSCode Extension

AI coding assistant with semantic code search, powered by Claude and Dolphin Knowledge Bank.

## Overview

The Dolphin VSCode Extension brings AI-powered code assistance directly into your editor with intelligent context from your codebase.

### Key Features

- **AI Chat Interface**: Natural language conversations with Claude or OpenAI models
- **Semantic Code Search**: Automatically searches your indexed codebase for relevant context
- **Dual Authentication**:
  - Claude CLI (subscription mode - no API costs)
  - Anthropic or OpenAI API keys (direct API access)
- **Real-time Streaming**: See AI responses as they're generated
- **Tool Call Visualization**: Monitor Knowledge Bank searches and tool executions
- **Beautiful UI**: Modern Svelte-based interface with shadcn/ui components

## Architecture

```
┌─────────────────────────────────────────┐
│       VSCode Extension Host             │
│  ┌───────────────────────────────────┐  │
│  │   Extension (TypeScript)          │  │
│  │  ┌────────────┐  ┌─────────────┐  │  │
│  │  │AgentBridge │  │ Webview     │  │  │
│  │  │ (JSON-RPC) │◄─┤ Provider    │  │  │
│  │  └─────┬──────┘  └─────────────┘  │  │
│  └────────┼──────────────────────────┘  │
└───────────┼─────────────────────────────┘
            │ stdio
            ▼
    ┌───────────────┐
    │  Agent Core   │
    │    (Bun)      │
    └───────┬───────┘
            │
            ▼
    ┌───────────────┐
    │ Knowledge Bank│
    │   REST API    │
    └───────────────┘
```

### Components

**Extension** (`src/extension.ts`)

- VSCode extension entry point
- Manages webview lifecycle
- Spawns Agent Core subprocess

**AgentBridge** (`src/agent/bridge.ts`)

- JSON-RPC communication with Agent Core
- Request/response handling
- Event stream management

**Webview** (`webview/`)

- SvelteKit-based UI
- Chat interface with message history
- Tool call visualization
- Settings and auth status panels
- Component gallery for testing

**Agent Core** (`../agent-core/`)

- Separate Bun-based process
- Handles Claude AI interactions
- Manages Knowledge Bank queries
- See [agent-core README](../agent-core/README.md)

## Development Setup

### Prerequisites

- **Node.js** ≥ 18
- **Bun** ≥ 1.0 (for Agent Core and webview)
- **VSCode** ≥ 1.85
- **Python** ≥ 3.12 (for Knowledge Bank)

### Installation

```bash
# 1. Install extension dependencies
npm install

# 2. Install webview dependencies
cd webview
bun install
cd ..

# 3. Install Agent Core dependencies
cd ../agent-core
bun install
cd ../vscode-extension

# 4. Compile TypeScript
npm run compile
```

### Build Webview

The webview UI must be built before running the extension:

```bash
cd webview
bun run build
cd ..
```

For development with hot reload:

```bash
cd webview
bun run dev
```

### Running the Extension

1. Open `vscode-extension` folder in VSCode
2. Press **F5** to launch Extension Development Host
3. A new VSCode window will open with the extension loaded
4. Click the Dolphin icon in the sidebar to open the extension

## Configuration

### Authentication Setup

**Option A: Claude CLI (Recommended for Development)**

No API costs, uses your Claude Pro/Max/Team subscription:

```bash
npm install -g @anthropic-ai/claude-code
claude
# Select: "1. Claude account with subscription"
```

**Option B: Anthropic or OpenAI API Keys**

For production or if you prefer direct API access run the commands below from VS Code:

- `Dolphin: Set Claude API Key` (`dolphin.setClaudeApiKey`)
- `Dolphin: Set OpenAI API Key` (`dolphin.setOpenAIApiKey`)

Both commands store secrets in VS Code SecretStorage; the legacy `Dolphin: Set API Key` command now delegates to the Claude handler for compatibility. Environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) are still honored if you prefer exporting them manually.

### Provider & Model Selection

The extension now drives Agent Core’s provider settings through VS Code configuration:

- `dolphin.llm.provider` – `anthropic` (default) or `openai`
- `dolphin.llm.model.anthropic` – Claude Sonnet/Haiku variants
- `dolphin.llm.model.openai` – GPT‑5.1 family models

Set these options via VS Code Settings (search for “Dolphin LLM”) or your `settings.json`. Invalid models automatically fall back to the defaults from the provider plan and emit a warning toast.

### Knowledge Bank Setup

**Development Mode** (manual startup required):

```bash
# In dolphin root directory
export DOLPHIN_API_KEY=kb-local-secret
uv run dolphin serve
```

The KB server runs on `http://127.0.0.1:7777` by default. If you are running the
Knowledge Bank elsewhere (containers, remote host, etc.) override the endpoint
with the VS Code setting **`dolphin.kb.apiBaseUrl`** so the extension and its
tests can talk to the correct server without environment variables.

### KB API Authentication

All `/v1/**` Knowledge Bank endpoints require the `X-API-Key` header to match the
`DOLPHIN_API_KEY` environment variable that the Python service was launched
with. When you start the KB manually set `DOLPHIN_API_KEY` (see above). Inside
VS Code run the **Dolphin: Set KB API Key** command (`dolphin.kb.setApiKey`) to
store the same value in SecretStorage so the extension, auto-sync, and KB panel
can authenticate automatically.

**Production Mode** (planned): KB server will auto-start with the extension.

See [KB Lifecycle Management Plan](../docs/KB-LIFECYCLE-MANAGEMENT.md) for details.

## Project Structure

```
vscode-extension/
├── src/
│   ├── extension.ts              # Extension entry point
│   ├── agent/
│   │   └── bridge.ts            # Agent Core communication
│   ├── views/
│   │   └── webview-provider.ts  # Webview management
│   └── test/                    # Extension tests
├── webview/                     # Svelte UI
│   ├── src/
│   │   ├── routes/
│   │   │   ├── +page.svelte    # Main chat interface
│   │   │   ├── settings/       # Settings page
│   │   │   └── gallery/        # Component gallery
│   │   ├── lib/
│   │   │   ├── components/     # Reusable components
│   │   │   └── stores/         # Svelte stores
│   │   └── app.html            # HTML template
│   ├── static/                  # Static assets
│   └── package.json
├── package.json                 # Extension manifest
└── tsconfig.json               # TypeScript config
```

## Features in Detail

### Chat Interface

- **Message History**: Persistent chat history across sessions
- **Markdown Rendering**: Rich text display with code highlighting
- **Auto-scroll**: Automatically follows conversation
- **Tool Call Cards**: Visual feedback for KB searches and tool executions

### Settings Panel

- **Authentication Status**: Real-time display of auth mode (CLI/API/none)
- **Refresh Button**: Manually refresh auth status
- **Setup Instructions**: Contextual help for authentication setup

### Component Gallery

Developer tool for testing UI components:

- Message components (user/assistant/system)
- Tool call states (running/success/error)
- Diff viewer
- Plan timeline
- Error alerts
- Confirmation dialogs

Access at: Settings → Gallery tab

## Testing

### Manual Testing

See [TESTING-GUIDE.md](../docs/TESTING-GUIDE.md) for complete testing instructions.

**Quick Test:**

1. Launch extension (F5)
2. Open Dolphin sidebar
3. Send: "Hello! Can you tell me about the Dolphin project?"
4. Verify:
   - KB search executes
   - Response streams/appears
   - Task completes successfully

### Extension Tests

```bash
# Run the full VS Code test suite headlessly
npm test

# Filter by label (unit, integration, e2e)
npm test -- --label unit
npm test -- --label integration
npm test -- --label e2e

# Compile and watch
npm run watch
```

The `.vscode-test.mjs` config pins a VS Code build and launches Electron with
headless-friendly flags, so no additional environment variables or xvfb setup is
required in CI.

### Integration Testing

Full end-to-end testing requires:

1. KB server running (`uv run dolphin serve`)
2. Authentication configured (CLI or API key)
3. Extension launched in debug mode (F5)

## Building for Distribution

### Create VSIX Package

```bash
# Install vsce if not already installed
npm install -g @vscode/vsce

# Build webview
cd webview && bun run build && cd ..

# Compile extension
npm run compile

# Package extension
vsce package
```

This creates `dolphin-{version}.vsix` which can be installed in VSCode:

```bash
code --install-extension dolphin-{version}.vsix
```

### Publishing to Marketplace

**Planned for Week 6**

1. Implement KB auto-start (KB lifecycle management)
2. Complete production testing
3. Create publisher account
4. Publish with `vsce publish`

See [Implementation Status](../docs/IMPLEMENTATION-STATUS.md) for roadmap.

## Troubleshooting

### "No authentication configured"

**Cause**: Neither Claude CLI nor API key is set up.

**Solution**: Follow authentication setup instructions above.

### "KB server not running"

**Cause**: Knowledge Bank REST API is not accessible.

**Solution**:

```bash
# Check if KB is running
curl http://127.0.0.1:7777/health

# If not, start it
uv run dolphin serve
```

### Webview not loading

**Cause**: Webview build is missing or outdated.

**Solution**:

```bash
cd webview
bun run build
cd ..
# Restart extension (F5)
```

### Extension activation fails

**Cause**: Agent Core failed to start.

**Solution**:

1. Check Output panel: View → Output → Dolphin
2. Verify Agent Core dependencies: `cd ../agent-core && bun install`
3. Test Agent Core directly: `cd ../agent-core && bun run dev`

### Messages not sending

**Cause**: AgentBridge not connected or KB unavailable.

**Solution**:

1. Check if KB is running (see above)
2. Restart extension
3. Check extension logs in Output panel

## Development Workflow

### Typical Development Session

```bash
# Terminal 1: Watch TypeScript compilation
npm run watch

# Terminal 2: Watch webview build (optional, for UI changes)
cd webview && bun run dev

# Terminal 3: KB server
cd .. && uv run dolphin serve

# VSCode: Press F5 to launch Extension Development Host
```

### Making Changes

**Extension Code** (`src/`):

1. Edit TypeScript files
2. Changes auto-compile if `npm run watch` is running
3. Reload extension: Cmd+R / Ctrl+R in Extension Development Host

**Webview UI** (`webview/`):

1. Edit Svelte components
2. Run `bun run build` to rebuild
3. Reload extension to see changes

**Agent Core** (`../agent-core/`):

1. Edit TypeScript files
2. Restart extension to pick up changes
3. See [agent-core README](../agent-core/README.md)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Run `npm run compile` to verify
6. Submit a pull request

## Roadmap

### Current (Week 1)

- ✅ Basic chat interface
- ✅ Claude CLI integration
- ✅ KB search integration
- ✅ Auth status UI

### Near-term (Week 2-6)

- ⏳ KB auto-start (lifecycle management)
- ⏳ Extension packaging
- ⏳ Production hardening
- ⏳ Marketplace publication

### Future

- Multi-file editing
- Diff preview and apply
- Code generation
- Test generation
- Refactoring tools

## License

MIT - see [LICENSE](../LICENSE.md) for details

## Links

- [Main Project README](../README.md)
- [Agent Core](../agent-core/README.md)
- [Architecture Documentation](../docs/ARCHITECTURE.md)
- [Testing Guide](../docs/TESTING-GUIDE.md)
- [Implementation Status](../docs/IMPLEMENTATION-STATUS.md)
- [KB Lifecycle Plan](../docs/KB-LIFECYCLE-MANAGEMENT.md)

---

**Need Help?** Open an issue at https://github.com/plasticbeachllc/dolphin/issues
