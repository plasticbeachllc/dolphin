# Dolphin v2 Agent Core

**Status:** ✅ Phase 1 Complete
**Version:** 0.1.0 (Foundation)
**Architecture:** Research-backed Orchestration System

---

## Overview

The Dolphin v2 Agent Core is a complete replacement of the v1 Agent Core with a research-backed orchestration system. It implements a **Research → Plan → Code → Validate** workflow with a provider-neutral LLM layer (Anthropic Claude + OpenAI GPT family) and deep Knowledge Bank semantic search.

Based on the comprehensive [Dolphin v2 Orchestration Project Plan](../docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md).

---

## Phase 1 Status: ✅ Complete

**Delivered:** All core components for Foundation phase (Weeks 1-3)

### Components

- ✅ [`Orchestrator`](src/orchestrator/orchestrator.ts) - State machine & workflow coordination (458 lines)
- ✅ [`StateStore`](src/state/state-store.ts) - TOML persistence & versioning (459 lines)
- ✅ [`JSON-RPC`](src/utils/json-rpc.ts) - Extension communication (291 lines)
- ✅ [`AnthropicProvider`](src/execution/anthropic-provider.ts) / [`OpenAIProvider`](src/execution/openai-provider.ts) - Multi-provider chat interface
- ✅ [`EditorWorkflow`](src/workflows/editor-workflow.ts) - Fast-path execution (260 lines)
- ✅ [`ContextBuilder`](src/context/context-builder.ts) - KB integration (320 lines)
- ✅ [`PromptBuilder`](src/prompts/prompt-builder.ts) - Phase-specific prompts (207 lines)

**Total:** ~3,500 lines of production code + 1,600+ lines of tests (110+ test cases)

See: [Phase 1 Validation Report](docs/PHASE-1-VALIDATION.md)

---

## Architecture

### Workflow State Machine

```
idle → researching → planning → awaiting_approval → executing → complete
                                       ↓
                                  plan_revision
                                       ↓
                                   cancelled
```

### Multi-Model Configuration

```typescript
const MODEL_CONFIG = {
  anthropic: {
    default: "claude-sonnet-4-5-20250929",
    research: "claude-haiku-4-5",
  },
  openai: {
    default: "gpt-5.1-codex",
    architect: "gpt-5.1",
  },
};
```

### Communication Flow

```
VSCode Extension (Svelte 5)
         ↕ JSON-RPC (stdio)
   Orchestrator (State Machine)
         ↕
   Workflow Implementations
         ↕
   ChatProvider (Anthropic/OpenAI)
         ↕
 Anthropic CLI/API or OpenAI Responses API
```

---

## Installation

```bash
# Install dependencies
bun install

# Run tests
bun test

# Run integration test suite
bun run tests/run-integration-tests.ts
```

---

## Quick Start

### Editor Mode (Fast-Path)

```typescript
import { Orchestrator } from "./src/orchestrator/orchestrator";
import { EditorWorkflow } from "./src/workflows/editor-workflow";
import { createChatProvider } from "./src/execution/provider-factory";
import { ContextBuilder } from "./src/context/context-builder";
import { PromptBuilder } from "./src/prompts/prompt-builder";
import { StateStore } from "./src/state/state-store";
import { MCPClient } from "./src/mcp/mcp-client";

// Setup provider + MCP bridge
const mcpClient = new MCPClient();
await mcpClient.start("mcp-bridge/src/index.ts");

const chatProvider = await createChatProvider({
  workspaceRoot: "/path/to/workspace",
  mcpClient,
  settings: {
    provider: process.env.DOLPHIN_PROVIDER ?? "anthropic",
    model: process.env.DOLPHIN_MODEL,
    openAIApiKey: process.env.OPENAI_API_KEY,
  },
});

const stateStore = new StateStore({
  storagePath: ".dolphin",
});

const contextBuilder = new ContextBuilder({
  workspaceRoot: "/path/to/workspace",
  kbUrl: "http://localhost:7777",
});

const promptBuilder = new PromptBuilder();

const editorWorkflow = new EditorWorkflow({
  chatProvider,
  contextBuilder,
  promptBuilder,
  stateStore,
  workspaceRoot: "/path/to/workspace",
});

const orchestrator = new Orchestrator({
  workspaceRoot: "/path/to/workspace",
  stateStore,
  editorWorkflow,
  architectWorkflow: editorWorkflow, // supply dedicated architect workflow when configured
});

// Start task
const session = await orchestrator.startTask({
  mode: "editor",
  message: "Add error handling to the API",
  context: { files: ["api.ts"] },
});

// Subscribe to updates
for await (const update of orchestrator.subscribeToUpdates(session.id)) {
  console.log(update);

  if (update.type === "state_change" && update.data.state === "complete") {
    break;
  }
}
```

### Authentication Helpers

`AnthropicProvider` ships with a lightweight `AuthManager` that understands both
Claude CLI OAuth logins and the `ANTHROPIC_API_KEY` environment variable.
`OpenAIProvider` reports its own auth status by checking `OPENAI_API_KEY` or a
custom `DOLPHIN_OPENAI_API_KEY` override, so UI surfaces can show whether the
provider is ready before users swap workflows.

```typescript
import { AnthropicProvider, AuthManager } from "./src/execution/anthropic-provider";
import { OpenAIProvider } from "./src/execution/openai-provider";

const anthropic = new AnthropicProvider({ workspaceRoot: "/repo" });
await anthropic.ensureAuthenticated();

const authManager = new AuthManager();
console.log(await authManager.detectAuthStatus());

const openai = new OpenAIProvider({
  workspaceRoot: "/repo",
  mcpClient,
  apiKey: process.env.DOLPHIN_OPENAI_API_KEY,
});
console.log(await openai.detectAuthStatus());
```

### Provider selection & OpenAI-compatible endpoints

The Agent Core consumes a shared provider abstraction (see
[`docs/PROVIDER_PLAN.md`](../docs/PROVIDER_PLAN.md)) and can talk to either the
Anthropic CLI/API stack or any OpenAI-compatible Responses endpoint.

#### Environment variables

```bash
# Force OpenAI provider and override per-workflow defaults
export DOLPHIN_LLM_PROVIDER=openai
export DOLPHIN_LLM_MODEL_OPENAI=gpt-5.1-codex

# Keep Anthropic as default provider but opt into Haiku
export DOLPHIN_LLM_MODEL_ANTHROPIC=claude-haiku-4-5

# Route through a custom OpenAI-compatible gateway
export DOLPHIN_OPENAI_BASE_URL=https://my-proxy/v1
export DOLPHIN_OPENAI_API_KEY=sk-proxy
```

#### `~/.dolphin/config` excerpt

```toml
[llm]
provider = "openai"

[llm.model]
anthropic = "claude-sonnet-4-5-20250929"
openai = "gpt-5.1-codex"

[llm.openai]
api_key = "sk-proxy"
base_url = "https://my-proxy/v1"
```

When `llm.openai.api_key` (or `DOLPHIN_OPENAI_API_KEY`) is present, the OpenAI
provider will route traffic through the specified base URL without requiring
`OPENAI_API_KEY`, enabling custom gateways while keeping Anthropic as
the default fallback when present.

If you do not provide `DOLPHIN_MODEL` (or a config `model`), the editor workflow
defaults to `gpt-5.1-codex` for coding tasks, while the architect workflow uses
`gpt-5.1` for planning runs whenever the OpenAI provider is active.

---

## Testing

### Unit Tests (34+ tests)

```bash
bun test tests/unit/orchestrator.test.ts
bun test tests/unit/state-store.test.ts
bun test tests/unit/json-rpc.test.ts
```

### Integration Tests (60+ tests)

```bash
bun test tests/integration/editor-workflow.test.ts
bun test tests/integration/orchestrator-e2e.test.ts
bun test tests/integration/kb-integration.test.ts
bun test tests/integration/claude-auth.test.ts
```

### Run All Tests

```bash
bun run tests/run-integration-tests.ts
```

---

## Project Structure

```
agent-core-v2/
├── src/
│   ├── orchestrator/
│   │   └── orchestrator.ts          # State machine & coordination
│   ├── workflows/
│   │   └── editor-workflow.ts       # Fast-path execution
│   ├── execution/
│   │   ├── anthropic-provider.ts   # Anthropic ChatProvider implementation
│   │   ├── openai-provider.ts      # OpenAI ChatProvider implementation
│   │   └── provider-factory.ts     # Provider selection helper
│   ├── context/
│   │   └── context-builder.ts       # KB integration
│   ├── prompts/
│   │   └── prompt-builder.ts        # Phase-specific prompts
│   ├── state/
│   │   └── state-store.ts           # TOML persistence
│   ├── utils/
│   │   └── json-rpc.ts              # Extension communication
│   ├── storage/
│   │   └── toml-writer.ts           # TOML utilities
│   └── types/
│       └── index.ts                 # TypeScript types
├── tests/
│   ├── unit/                        # Unit tests (34+ tests)
│   ├── integration/                 # Integration tests (60+ tests)
│   └── run-integration-tests.ts     # Test runner
└── docs/
    └── PHASE-1-VALIDATION.md        # Validation report
```

---

## Key Features

### ✅ Editor Workflow

- Fast-path execution for simple tasks
- Lightweight context (8000 tokens max)
- Sonnet 4.5 with normal thinking mode
- Single-step execution

### ✅ State Management

- Event-driven architecture
- TOML persistence for human readability
- Plan versioning with revision history
- Atomic writes with backup support

### ✅ Knowledge Bank Integration

- Semantic search via HTTP API
- Context assembly with token tracking
- Intelligent truncation with priority system
- Graceful degradation when KB unavailable

### ✅ Multi-Model Support

- Model selection per workflow phase
- Provider factory with Anthropic/OpenAI routing
- CLI subprocess management
- OpenAI Responses streaming client + tool executor
- Streaming response parsing
- Process lifecycle control

### ✅ Authentication

- OAuth detection (`.claude/settings.json`)
- API key detection (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DOLPHIN_OPENAI_API_KEY`)
- Priority handling (OAuth > API key)
- Warning system for pay-as-you-go

---

## Phase 2 Roadmap (Weeks 4-6)

### Week 4: Research & Planning Phases

- [ ] Implement ArchitectWorkflow with research phase
- [ ] KB search prompting with Haiku
- [ ] Research summary generation
- [ ] Planning phase with Opus
- [ ] Plan.md generation and parsing

### Week 5: User Approval Flow

- [ ] Approval state management
- [ ] Plan revision logic
- [ ] VSCode UI integration
- [ ] Plan display components
- [ ] Progress indicators

### Week 6: Implementation & Validation

- [ ] Implementation phase with Sonnet
- [ ] Step-by-step execution
- [ ] Error handling and recovery
- [ ] End-to-end testing
- [ ] Performance optimization

---

## Success Criteria

### Phase 1 (Complete) ✅

- [x] Editor Mode works end-to-end
- [x] Provider factory selects Anthropic/OpenAI reliably
- [x] KB search integration functional
- [x] State persists in TOML correctly
- [x] 100+ tests passing
- [x] Authentication detection works

### Phase 2 (In Progress)

- [ ] Architect Mode completes complex tasks end-to-end
- [ ] Plan approval flow works smoothly
- [ ] Plan revision works correctly
- [ ] Multi-model orchestration functional
- [ ] UI shows all workflow phases
- [ ] 200+ tests passing

---

## Contributing

### Development Workflow

1. Create feature branch
2. Implement with tests
3. Run test suite: `bun run tests/run-integration-tests.ts`
4. Ensure all tests pass
5. Submit PR with validation report

### Code Standards

- TypeScript strict mode
- Comprehensive error handling
- Event-driven architecture
- Test coverage for all features
- Clear documentation

---

## Resources

- [Project Plan](../docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md) - Comprehensive 2,831-line specification
- [Phase 1 Validation](docs/PHASE-1-VALIDATION.md) - Complete validation report
- [Implementation Guide](../docs/orchestration/DOLPHIN-V2-IMPLEMENTATION-GUIDE.md) - Step-by-step guide
- [Executive Summary](../docs/orchestration/DOLPHIN-V2-EXECUTIVE-SUMMARY.md) - High-level overview

---

## License

MIT

---

**Phase 1 Status:** ✅ Complete
**Next Milestone:** Phase 2 Week 4 - ArchitectWorkflow
**Documentation:** docs/PHASE-1-VALIDATION.md
