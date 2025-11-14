# Dolphin v2 Agent Core

**Status:** ✅ Phase 1 Complete  
**Version:** 0.1.0 (Foundation)  
**Architecture:** Research-backed Orchestration System

---

## Overview

The Dolphin v2 Agent Core is a complete replacement of the v1 Agent Core with a research-backed orchestration system. It implements a **Research → Plan → Code → Validate** workflow with multi-model Claude integration and deep Knowledge Bank semantic search.

Based on the comprehensive [Dolphin v2 Orchestration Project Plan](../docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md).

---

## Phase 1 Status: ✅ Complete

**Delivered:** All core components for Foundation phase (Weeks 1-3)

### Components

- ✅ [`Orchestrator`](src/orchestrator/orchestrator.ts) - State machine & workflow coordination (458 lines)
- ✅ [`StateStore`](src/state/state-store.ts) - TOML persistence & versioning (459 lines)
- ✅ [`JSON-RPC`](src/utils/json-rpc.ts) - Extension communication (291 lines)
- ✅ [`ClaudeProvider`](src/execution/claude-provider.ts) - Multi-model CLI execution (493 lines)
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
MODEL_CONFIG = {
  research: "claude-haiku-4-20250514", // Fast, cost-effective
  planning: "claude-opus-4-20250514", // Best reasoning
  coding: "claude-sonnet-4-20250514", // Balanced
  editor: "claude-sonnet-4-20250514", // Fast & capable
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
   ClaudeProvider (CLI subprocess)
         ↕
   Claude Code CLI
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
import { ClaudeProvider } from "./src/execution/claude-provider";
import { ContextBuilder } from "./src/context/context-builder";
import { PromptBuilder } from "./src/prompts/prompt-builder";
import { StateStore } from "./src/state/state-store";

// Setup
const claudeProvider = new ClaudeProvider({
  workspaceRoot: "/path/to/workspace",
});

const contextBuilder = new ContextBuilder({
  workspaceRoot: "/path/to/workspace",
  kbUrl: "http://localhost:7777",
});

const promptBuilder = new PromptBuilder();

const editorWorkflow = new EditorWorkflow({
  claudeProvider,
  contextBuilder,
  promptBuilder,
});

const stateStore = new StateStore({
  storagePath: ".dolphin",
});

const orchestrator = new Orchestrator({
  workspaceRoot: "/path/to/workspace",
  stateStore,
  editorWorkflow,
  architectWorkflow: editorWorkflow, // Phase 2
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

`ClaudeProvider` ships with a lightweight `AuthManager` that understands both
Claude CLI OAuth logins and the `ANTHROPIC_API_KEY` environment variable. You
can use it directly, or call the convenience methods on `ClaudeProvider`:

```typescript
import { AuthManager, ClaudeProvider } from "./src/execution/claude-provider";

const provider = new ClaudeProvider({ workspaceRoot: "/path/to/workspace" });
await provider.ensureAuthenticated();

const authManager = new AuthManager();
const status = await authManager.detectAuthStatus();
console.log(status.mode, status.warning);
```

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
│   │   └── claude-provider.ts       # Multi-model CLI spawning
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
- CLI subprocess management
- Streaming response parsing
- Process lifecycle control

### ✅ Authentication

- OAuth detection (`.claude/settings.json`)
- API key detection (`ANTHROPIC_API_KEY`)
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
- [x] Claude CLI subprocess spawning reliable
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
