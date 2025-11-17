# Dolphin Provider Architecture Plan

**Version:** 0.1  
**Date:** 2025-11-16  
**Owner:** Agent Core / VSCode Extension  
**Status:** Draft – Ready for Implementation

## Phase 1 (Agent Core) Alignment

The first implementation milestone focused on getting the Agent Core to boot with
both Anthropic and OpenAI models, mirroring the original Phase 1 charter for the
provider initiative. The following deliverables are covered by the current code
base:

| Deliverable                                       | Status | Evidence & Notes                                                                                                                                                                                                                                                  |
| ------------------------------------------------- | :----: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Shared chat provider abstraction (`ChatProvider`) |   ✅   | `agent-core/src/execution/chat-provider.ts` defines the shared surface and is consumed by the orchestrator + workflows in `agent-core/src/main.ts`, ensuring editor/architect flows bind against the same interface.                                              |
| Anthropic + OpenAI client wrappers                |   ✅   | `agent-core/src/execution/anthropic-provider.ts` wraps `ClaudeClient` + auth manager, while `agent-core/src/execution/openai-provider.ts` together with `agent-core/src/llm/openai-client.ts` implement the OpenAI Responses adapter with streaming/tool support. |
| Tool execution engine with provider adapters      |   ✅   | `agent-core/src/llm/tool-executor.ts` now backs both `anthropic-tool-executor.ts` and `openai-tool-executor.ts`, giving each provider consistent tool call orchestration and diff-generation hooks.                                                               |
| Provider selection knobs                          |   ✅   | `agent-core/src/utils/provider-settings.ts` + `agent-core/src/execution/provider-factory.ts` honor `~/.dolphin/config` and the `DOLPHIN_*`/`OPENAI_*` env vars, enabling default model overrides and OpenAI-compatible API endpoint injection.                    |
| MCP workflow integration                          |   ✅   | Both providers are wired through the shared `MCPClient` + tool loop (`agent-core/src/mcp/mcp-client.ts`), so usage accounting and tool telemetry reach the orchestrator in the same format.                                                                       |

**Default models:** Phase 1 now ships with `claude-sonnet-4-5-20250929` for the Anthropic path. When the OpenAI provider is selected, the editor/coding workflow defaults to `gpt-5.1-codex` while the architect workflow defaults to `gpt-5.1`, keeping runtime behavior aligned with the plan's "Claude 4.5" / "GPT 5.1" targeting without extra configuration.

### Remaining Gaps vs. Original Plan

The broader provider roadmap in `docs/PROVIDER.md` still includes several items
that are **not** part of the Phase 1 Agent Core drop:

- Canonical `provider_config.toml` manifest + JSON Schema generation (still
  tracked, but the runtime currently consumes `~/.dolphin/config`).
- CLI `providers check` validation command.
- GUI workflow for collecting a custom OpenAI-compatible endpoint.
- Dynamic pricing feed and cost estimators.
- MCP Bridge / VS Code wiring (Agent Core only so far).

Those gaps are now explicitly noted here to avoid ambiguity between the plan and
the repository state. Subsequent phases should re-use the abstractions landed in
Phase 1 to flesh out the remaining milestones.

### Phase 2 Readiness Check

Phase 1 exit criteria are satisfied: both Anthropic and OpenAI providers run
through the shared chat abstraction, the provider factory switches between them
based on config/env, and the tool execution and MCP plumbing are commonized.
The latest targeted tests (see **Testing** in this change) confirm the
OpenAI/Anthropic factory + provider paths remain green. With no additional
Phase 1 blockers identified, the codebase is ready for Phase 2 planning and
implementation to begin.

### Phase 2 (Agent Core) Implementation Status

Phase 2 runtime deliverables now live in the repository, so the OpenAI path
ships alongside Anthropic. Targeted OpenAI tool-executor unit tests remain a
follow-up item:

| Deliverable                       | Status | Evidence & Notes                                                                                                                                                                                                                                                                                                         |
| --------------------------------- | :----: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `OpenAIClient` streaming wrapper  |   ✅   | `agent-core/src/llm/openai-client.ts` owns the Responses streaming integration, chunks deltas via `onTextChunk`, and captures token usage so providers receive structured totals.                                                                                                                                        |
| `OpenAIToolExecutor` adapter      |   ✅   | `agent-core/src/llm/openai-tool-executor.ts` bridges MCP tools into OpenAI's function schema, dispatches deltas as `content_delta` events, and reuses the shared `ToolExecutorEngine` loop.                                                                                                                              |
| `OpenAIProvider` + factory wiring |   ✅   | `agent-core/src/execution/openai-provider.ts` injects the executor/client pair, resolves auth/base-url sources, and exposes provider metadata, while `agent-core/src/execution/provider-factory.ts` now promotes OpenAI when requested or when only OpenAI credentials are present.                                      |
| Unit coverage                     |   ⚠️   | `agent-core/tests/unit/llm/openai-client.test.ts`, `agent-core/tests/unit/execution/openai-provider.test.ts`, and `agent-core/tests/unit/execution/provider-factory.test.ts` cover the client/provider/factory paths. A dedicated `OpenAIToolExecutor` suite is still pending.                                           |
| Integration coverage              |   ✅   | `agent-core/tests/integration/auth/openai-auth.test.ts` verifies env/settings precedence + `ensureAuthenticated`, and `agent-core/tests/integration/editor/openai-editor-workflow.test.ts` drives the Editor workflow end-to-end against a mocked OpenAI client to ensure streaming + persistence behaviors stay intact. |

---

## 1. Vision & Goals

Dolphin’s core chat experience should support multiple LLM providers and models in a unified way while remaining:

- **Flexible:** Users can choose between Anthropic (Claude) and OpenAI (GPT‑4.1 family) for chat without changing their workflow.
- **Extensible:** Adding a new provider (e.g., additional OpenAI models, future Anthropic models) should require minimal wiring.
- **Safe & Observable:** Provider usage is explicit, authenticated, and surfaced clearly to users, with good logging and auth status reporting.
- **Well‑Tested:** Provider selection, auth flows, and tool execution paths are covered by comprehensive tests that clean up after themselves.

This plan focuses on **core chat and tool‑enabled workflows** (Editor & Architect) in **Agent Core + VSCode extension**, not on the KB embedding pipeline (which already uses OpenAI via the Python backend).

---

## 2. High‑Level Specification

### 2.1 Supported Providers & Models

- **Anthropic**
  - `claude-sonnet-4-5` (Sonnet 4.5)
  - `claude-haiku-4-5` (Haiku 4.5)
- **OpenAI**
  - `gpt-5.1`
  - `gpt-5.1-codex`
  - `gpt-5.1-codex-mini`

Notes:

- Model naming in code will be centralized behind configuration so front‑end and agent-core stay in sync.
- Provider selection is controlled by the **VSCode front‑end**, not auto‑detection.

### 2.2 Provider Selection & Configuration

**Source of truth:** VSCode settings + secrets.

- VSCode settings (example keys):
  - `dolphin.llm.provider`: `"anthropic"` | `"openai"`
  - `dolphin.llm.model.anthropic`: `"claude-sonnet-4-5"` / `"claude-haiku-4-5"`
  - `dolphin.llm.model.openai`: `"gpt-5.1"` / `"gpt-5.1-codex"` / `"gpt-5.1-codex-mini"`
- Secrets:
  - `dolphin.anthropicApiKey`
  - `dolphin.openaiApiKey`
- Extension passes effective configuration to Agent Core via:
  - Environment variables (e.g., `DOLPHIN_LLM_PROVIDER`, `DOLPHIN_LLM_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) and/or
  - An initial JSON‑RPC configuration request (optional future enhancement).

### 2.3 Core Architectural Changes

1. Introduce a **provider-neutral chat interface** in agent-core:
   - Workflows now depend on `ChatProvider` (`agent-core/src/execution/chat-provider.ts`).
2. Implement provider-specific classes:
   - `AnthropicProvider` continues to wrap the Claude client + executor stack.
   - `OpenAIProvider` injects the Phase 2 OpenAI client + executor pair.
3. Add a **factory** in Agent Core that:
   - Loads persisted provider preferences via `provider-settings.ts`.
   - Detects which credentials are present and returns the matching `ChatProvider` instance.
4. Update VSCode extension (Phase 3+ scope):
   - Settings UI for provider & model selection on the Settings page.
   - Commands to manage both Anthropic and OpenAI keys.
   - Auth Status UI updated to display provider-aware state.

### 2.4 OpenAI Integration Details

- Use the OpenAI Chat Completions API with tools (via the **Context7 MCP server** for authoritative OpenAI docs references during development).
- Map MCP tools (already used for Claude) into OpenAI’s tools schema:
  - `name`, `description`, `parameters` (JSON Schema).
- Implement a loop similar to `ClaudeToolExecutor`:
  - Call OpenAI with tools → receive `tool_calls` → execute via MCP → feed results back into the conversation until completion or max rounds.

---

## 3. Agent Core Spec

### 3.1 Provider-Neutral Interface

**File:** `agent-core/src/execution/chat-provider.ts`

```ts
export interface AuthStatus {
  authenticated: boolean;
  mode: "subscription" | "api_key" | "none" | string;
  source?: string;
  warning?: string;
  error?: string;
}

export interface ExecuteParams {
  message: string;
  conversationHistory?: Array<{ role: "user" | "assistant"; content: string }>;
  onEvent?: (event: AgentEvent) => void;
}

export interface ExecuteResult {
  messages: ToolExecutorMessage[];
  stopReason?: string;
  toolRounds: number;
  usage: UsageStats;
}

export interface ChatProvider {
  initialize(): Promise<void>;
  execute(params: ExecuteParams): Promise<ExecuteResult>;
  abort(): void;
  detectAuthStatus(): Promise<AuthStatus>;
  ensureAuthenticated(): Promise<void>;
  getUsage(): UsageStats;
  getProviderMetadata(): { provider: string; model: string };
}
```

`EditorWorkflow` and `ArchitectWorkflow` each keep a `ChatProvider` reference and no longer
reference Anthropic-specific classes directly. Provider metadata, auth status, and usage
metrics now flow through this shared contract, which is what Phase 2 builds upon.

### 3.2 Anthropic Provider (Claude)

**Files:**

- `agent-core/src/execution/anthropic-provider.ts`
- `agent-core/src/llm/anthropic-tool-executor.ts`
- `agent-core/src/llm/claude-client.ts`

`AnthropicProvider` now implements the shared `ChatProvider` interface. It wires the existing
Claude client + tool executor stack into the new abstraction while keeping the AuthManager
logic that checks both CLI OAuth tokens and `ANTHROPIC_API_KEY`. Notable behaviors:

- Defaults to `claude-sonnet-4-5-20250929` while allowing overrides through provider settings.
- Streams events through the shared `AnthropicToolExecutor`, creating a per-request executor
  when a custom `onEvent` callback is provided.
- `detectAuthStatus()` delegates to `AuthManager`, so subscription vs API-key flows are still
  surfaced to the orchestrator and UI.
- Usage is returned directly from the executor, so workflow telemetry remains unchanged.

Phase 1 completed this refactor, giving Phase 2 a consistent surface to plug in the new
OpenAI implementation.

### 3.3 OpenAI Client & Tool Executor

**Files:**

- `agent-core/src/llm/openai-client.ts`
- `agent-core/src/llm/openai-tool-executor.ts`
- `agent-core/src/execution/openai-provider.ts`

Phase 2 introduced an OpenAI pathway that mirrors the Anthropic architecture:

- `OpenAIClient` is a thin wrapper around the official `openai` SDK Responses API.
  - Accepts model/temperature/base URL overrides via config or env vars.
  - Streams deltas through `onTextChunk` callbacks so workflows receive incremental events.
  - Returns structured usage totals (`input_tokens`, `output_tokens`).
- `OpenAIToolExecutor` subclasses `ToolExecutorEngine`, translating MCP tools to OpenAI
  function definitions and emitting tool call/result messages that match the Responses schema.
- `OpenAIProvider` implements `ChatProvider` by composing the client + executor pair. It
  resolves API keys/base URLs from provider settings or env vars, exposes auth metadata, and
  maps stored conversation history into OpenAI content blocks.

Together these components satisfy the Phase 2 charter: OpenAI chats (Editor + Architect) use
streaming, tool loops, and MCP telemetry identical to Anthropic while relying on the shared
provider abstractions.

### 3.4 Provider Factory

**File:** `agent-core/src/execution/provider-factory.ts`

`createChatProvider` now centralizes provider selection. It loads
`provider-settings.json`, checks explicit preferences, and then falls back to whichever
credential is available. Key excerpt:

```ts
export async function createChatProvider(options: ProviderFactoryOptions): Promise<ChatProvider> {
  const settings = options.settings ?? loadProviderSettings();
  const preference = settings.provider ?? "auto";
  const authManager = options.authManager ?? new AuthManager();
  const openAIModel = settings.model ?? options.defaultOpenAIModel;

  if (preference === "anthropic") {
    return new AnthropicProvider({ ... });
  }

  if (preference === "openai") {
    ensureOpenAIKey(settings);
    return new OpenAIProvider({ ... });
  }

  const anthropicStatus = await authManager.detectAuthStatus();
  if (anthropicStatus.authenticated) {
    return new AnthropicProvider({ ... });
  }

  const hasOpenAIKey =
    settings.openAIApiKey || process.env.DOLPHIN_OPENAI_API_KEY || process.env.OPENAI_API_KEY;
  if (hasOpenAIKey) {
    return new OpenAIProvider({ ... });
  }

  throw new Error(
    "No chat provider credentials found. Authenticate with Claude CLI / ANTHROPIC_API_KEY or set OPENAI_API_KEY."
  );
}
```

This auto-detection path is why the extension work can roll out incrementally—the CLI can
launch Agent Core without new settings and still obtain a provider as long as one set of
credentials exists. Phase 2 exercised this logic heavily via the new tests listed below.

### 3.5 Agent Core Wiring

**File:** `agent-core/src/main.ts`

Pseudocode changes:

```ts
// 1) Create MCP client as today
this.mcpClient = new MCPClient();

// 2) Use factory instead of new ClaudeProvider()
const { llmProvider, providerName } = createLLMProvider({
  mcpClient: this.mcpClient,
});
this.llmProvider = llmProvider;

// 3) Initialize provider and log
await this.llmProvider.initialize();
const authStatus = await this.llmProvider.getAuthStatus();
console.error(`[Agent Core V2] LLM provider: ${providerName}`);
console.error(`[Agent Core V2] LLM auth mode: ${authStatus.mode}`);

if (authStatus.mode === "none") {
  throw new Error(
    "LLM provider is not authenticated. Configure keys or CLI auth in the VSCode settings."
  );
}

// 4) Pass provider into workflows
const editorWorkflow = new EditorWorkflow({
  llmProvider: this.llmProvider,
  // ...
});
const architectWorkflow = new ArchitectWorkflow({
  llmProvider: this.llmProvider,
  // ...
});
```

Workflows replace `claudeProvider` with `llmProvider` and call `execute` identically.

### 3.6 Prompt Neutralization

**File:** `agent-core/src/prompts/prompt-builder.ts`

- Replace hard‑coded “You are Claude…” with a provider‑neutral identity:

> “You are Dolphin, an AI coding assistant helping with code research and implementation.”

- Keep the rest of the structure unchanged.

---

## 4. VSCode Extension Spec

### 4.1 Settings & Secrets

**Files:**

- `vscode-extension/src/extension.ts`
- `vscode-extension/webview/src/routes/settings/+page.svelte`
- `vscode-extension/webview/src/lib/components/AuthStatus.svelte`

**Settings (package.json, not shown here):**

- `dolphin.llm.provider`: `"anthropic"` | `"openai"`
- `dolphin.llm.model.anthropic`: `"claude-sonnet-4-5"` / `"claude-haiku-4-5"`
- `dolphin.llm.model.openai`: `"gpt-5.1"` / `"gpt-5.1-codex"` / `"gpt-5.1-codex-mini"`

**Secrets:**

- Store Anthropic key under `dolphin.anthropicApiKey`.
- Store OpenAI key under `dolphin.openaiApiKey`.

**extension.ts pseudocode:**

```ts
// On activate:
const providerSetting = vscode.workspace
  .getConfiguration("dolphin.llm")
  .get<"anthropic" | "openai">("provider", "anthropic");

const anthropicModel = vscode.workspace
  .getConfiguration("dolphin.llm")
  .get<string>("model.anthropic", "claude-sonnet-4-5");

const openaiModel = vscode.workspace
  .getConfiguration("dolphin.llm")
  .get<string>("model.openai", "gpt-5.1");

const anthropicKey = await context.secrets.get("dolphin.anthropicApiKey");
const openaiKey = await context.secrets.get("dolphin.openaiApiKey");

await agentBridge.start(agentCorePath, extensionPath, {
  anthropicApiKey: providerSetting === "anthropic" ? anthropicKey : undefined,
  openaiApiKey: providerSetting === "openai" ? openaiKey : undefined,
  kbApiKey: process.env.DOLPHIN_API_KEY,
});
```

_(AgentBridge.start now accepts an auth object instead of a single API key.)_

### 4.2 Settings Page (UI)

**File:** `vscode-extension/webview/src/routes/settings/+page.svelte`

Changes (pseudocode only):

- Add provider selector (radio or select):

```svelte
<select bind:value={provider}>
  <option value="anthropic">Anthropic (Claude)</option>
  <option value="openai">OpenAI (GPT‑5.1)</option>
</select>
```

- Show provider‑specific model choice:

```svelte
{#if provider === 'anthropic'}
  <!-- Anthropic model input -->
{:else}
  <!-- OpenAI model input -->
{/if}
```

- Show two password inputs or a provider‑aware single input:

```svelte
{#if provider === 'anthropic'}
  <Input type="password" placeholder="Anthropic API key..." />
{:else}
  <Input type="password" placeholder="OpenAI API key..." />
{/if}
```

Saving will post a message back to the extension to update secrets/settings.

### 4.3 Auth Status Component

**File:** `vscode-extension/webview/src/lib/components/AuthStatus.svelte`

- Extend `AuthStatusData`:

```ts
interface AuthStatusData {
  provider: "anthropic" | "openai";
  mode: "subscription" | "api_key" | "none" | "auto";
  cliInstalled: boolean;
  cliAuthenticated: boolean;
  apiKeySet: boolean;
  willUseSubscription: boolean;
}
```

- Change labels/logic:
  - If `provider === 'anthropic'`:
    - “Using Claude Subscription”, “Using Claude API Key”, etc.
  - If `provider === 'openai'`:
    - “Using OpenAI API Key”, no CLI hints.

The extension already requests `get_auth_status` from Agent Core; only shape/labels change.

### 4.4 Webview Rendering & Streaming of LLM Blocks

**Goal:** Render responses in a rich, provider‑agnostic way while leveraging any formatting the LLM gives us (code blocks, markdown, tool calls/results).

#### 4.4.1 Message Model in the Webview

- Agent Core sends chat messages as an array of `LLMMessage`:
  - `role: "user" | "assistant"`
  - `content: LLMContent` (`LLMBlock | LLMBlock[]`)
- The webview flattens each `LLMMessage.content` into a linear array of `LLMBlock`s for rendering, grouped per message and role.
- Provider differences are hidden behind the `LLMBlock` union; the webview only branches on:
  - `block.type` (`text`, `markdown`, `code`, `tool_call`, `tool_result`, `system_note`)
  - `block.provider` for minor cosmetic tweaks (icons, labels).

#### 4.4.2 Block‑Type Rendering

- **Text / Markdown (`LLMTextBlock` with `type: "text" | "markdown"`):**
  - Use the existing markdown renderer in the webview to display:
    - Paragraphs, headings, lists.
    - Inline code and fenced code blocks.
  - For fenced code blocks detected in markdown:
    - Convert them into `CodeBlock` UI with language label and copy‑to‑clipboard.
  - Ensure any HTML is sanitized before insertion.

- **Code (`LLMCodeBlock`):**
  - Render using the webview’s existing code block component:
    - Syntax highlight based on `language`.
    - Show language badge and copy button.
    - Optionally support an inline “Apply” action when paired with tool diffs (future).

- **Tool Call (`LLMToolCallBlock`):**
  - Render as a compact “Tool Call” card:
    - Header: tool name, provider icon.
    - Body: pretty‑printed `arguments` (JSON) in a monospaced block.
    - Status pill: “Running…” until a matching `tool_result` arrives.
  - Cards should be visually distinct but lightweight to avoid overwhelming the main chat.

- **Tool Result (`LLMToolResultBlock`):**
  - Render as a “Tool Result” card aligned with the previous tool call:
    - Header: tool name, matching call id.
    - Body:
      - If `isError`, show error styling and error message extracted from `result`.
      - Otherwise, show summarized result plus a “View raw” toggle for complex payloads.

- **System Note (`LLMBaseBlock` with `type: "system_note"`):**
  - Render as subtle, low‑contrast inline notes (e.g., “switched provider”, “truncated output”).

- **Raw Provider Payload (`rawProviderPayload`):**
  - Not rendered by default.
  - Expose via an optional “Developer Mode” / “Show raw LLM data” toggle that:
    - Shows a collapsible JSON inspector for debugging.
    - Is clearly marked as provider‑specific and non‑stable.

#### 4.4.3 Streaming & Incremental Updates

- Agent Core continues to emit streaming `AgentEvent`s (e.g., `content_delta`, `tool_call_started`, `tool_call_completed`) during `execute`.
- Webview handling:
  - Maintain an in‑memory representation of the current assistant message as an array of `LLMBlock`s.
  - For text/markdown:
    - Append new `LLMTextBlock` segments as they arrive.
    - Coalesce adjacent text blocks for efficient rendering where possible.
  - For tool calls:
    - On `tool_call_started`, insert a provisional `LLMToolCallBlock` with minimal arguments.
    - On `tool_call_completed`, either:
      - Insert a new `LLMToolResultBlock` card, or
      - Update an existing one if streaming yields partial results.
- The UI should ensure smooth scrolling and minimal layout jumps while blocks are appended.

#### 4.4.4 Persistence Considerations

- When conversations are persisted (TOML, JSON, etc.):
  - Persist only the normalized `LLMBlock` representation (text/markdown/code/tool_call/tool_result).
  - Strip `rawProviderPayload` by default to keep storage stable and provider‑agnostic.
  - On restore, the webview rehydrates messages from `LLMBlock`s only; provider‑specific details can be reattached in memory if needed for debugging.

---

## 5. Testing Strategy

All tests must clean up after themselves (temp dirs, env vars, secrets, test settings).

### 5.1 Agent Core Unit Tests

- **New suites (Phase 2):**
  - `agent-core/tests/unit/llm/openai-client.test.ts`
  - `agent-core/tests/unit/execution/openai-provider.test.ts`
  - `agent-core/tests/unit/execution/provider-factory.test.ts`
- **Outstanding gap:** add targeted `openai-tool-executor` unit coverage. The current
  `tool-executor.test.ts` exercises the shared engine but not the OpenAI adapter.

### 5.2 Agent Core Integration Tests

- Suites landed for Phase 2:
  - `agent-core/tests/integration/auth/openai-auth.test.ts`
  - `agent-core/tests/integration/editor/openai-editor-workflow.test.ts`
- Scenarios:
  - With `DOLPHIN_LLM_PROVIDER=openai` and `OPENAI_API_KEY` set:
    - Editor workflow runs a simple task using a mocked OpenAI client and verifies streaming.
  - With `DOLPHIN_LLM_PROVIDER=anthropic`:
    - Existing Claude integration tests remain passing, exercising regression coverage for auto-detection.

### 5.3 VSCode Extension Tests

- Update `AgentBridge` integration tests to:
  - Accept an `env` object and ensure it passes through to the spawned process.
  - Verify that provider + model env vars are set as expected.
- Add tests for settings & AuthStatus UI (where existing patterns allow).

### 5.4 End‑to‑End Smoke Tests

- Manual / scripted:
  - Start extension with provider `anthropic`, model Sonnet 4.5 → send a chat message, observe results.
  - Switch provider to `openai`, model `gpt-5.1-codex` → send a chat message, verify behavior and logs.

---

## 6. Step‑by‑Step Implementation Plan

### Phase 1 – Abstractions & Wiring (Agent Core)

1. Add `ChatProvider`, `AuthStatus`, `ExecuteParams`, `ExecuteResult` in `agent-core/src/execution/chat-provider.ts`.
2. Refactor existing `ClaudeProvider` into the shared abstraction by implementing `ChatProvider`.
3. Update `EditorWorkflow` and `ArchitectWorkflow` to depend on `ChatProvider` instead of `ClaudeProvider`.
4. Implement `createChatProvider` factory (now `agent-core/src/execution/provider-factory.ts`) and call it from `agent-core/src/main.ts`.
5. Update `get_auth_status` handling to rely on `ChatProvider.detectAuthStatus()` and surface the provider name.
6. Neutralize prompts in `PromptBuilder` to remove “You are Claude” wording.
7. Run `bun test` for agent-core and fix any breakages.

### Phase 2 – OpenAI Provider (Agent Core)

| #   | Deliverable                                            | Status | Evidence / Notes                                                                                                                                                                |
| --- | ------------------------------------------------------ | :----: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 8   | Implement `OpenAIClient` with streaming + auth helpers |   ✅   | `agent-core/src/llm/openai-client.ts` now wraps the Responses API, handles env overrides, and streams deltas via `onTextChunk`.                                                 |
| 9   | Build `OpenAIToolExecutor` with MCP + streaming events |   ✅   | `agent-core/src/llm/openai-tool-executor.ts` subclasses `ToolExecutorEngine`, translates MCP tools into OpenAI functions, and emits `content_delta` events.                     |
| 10  | Provide a ChatProvider implementation for OpenAI       |   ✅   | `agent-core/src/execution/openai-provider.ts` composes the client + executor, resolves auth metadata, and exposes provider metadata.                                            |
| 11  | Extend provider factory to support OpenAI selection    |   ✅   | `agent-core/src/execution/provider-factory.ts` now promotes OpenAI when explicitly requested or when only OpenAI credentials exist.                                             |
| 12  | Add unit coverage for the new components               |   ⚠️   | `openai-client`, `openai-provider`, and `provider-factory` unit tests exist. Dedicated `OpenAIToolExecutor` tests are still outstanding (only the shared engine is covered).    |
| 13  | Add integration tests for OpenAI auth + workflows      |   ✅   | `agent-core/tests/integration/auth/openai-auth.test.ts` and `agent-core/tests/integration/editor/openai-editor-workflow.test.ts` cover auth precedence + streaming editor runs. |

### Phase 3 – VSCode Extension Integration

| #   | Deliverable                                                     | Status | Evidence / Notes                                                                                                                                                                                                                                              |
| --- | --------------------------------------------------------------- | :----: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 14  | AgentBridge accepts structured auth/env payload and merges envs |   ✅   | `vscode-extension/src/agent/bridge.ts` now exports `mergeAgentEnvironment`, documents the precedence order, and spawns Agent Core with Anthropic/OpenAI/Dolphin keys sourced from the VS Code host. Tests cover the merge contract in `agent-bridge.test.ts`. |
| 15  | Extension activation builds provider/model payload & secrets    |   ✅   | `vscode-extension/src/extension.ts` reads `dolphin.llm.*` settings, migrates the legacy secret, and passes provider/model defaults plus both API keys to AgentBridge.                                                                                         |
| 16  | Secret-management commands for Anthropic/OpenAI                 |   ✅   | New commands `dolphin.setClaudeApiKey` and `dolphin.setOpenAIApiKey` prompt, validate, and persist secrets via VS Code `SecretStorage`, with the legacy command delegating to the Claude handler.                                                             |
| 17  | Auth status plumbing emits `{ provider, authenticated, ... }`   |   ✅   | Agent Core responds to `get_auth_status` with provider-specific payloads, `DolphinViewProvider` forwards them, and the Svelte `AuthStatus` component renders provider-aware cards with new bun tests covering the helper logic.                               |

14. Update `AgentBridge.start` to accept an auth/options object instead of a single API key:
    - Populate spawn env with whatever keys are provided (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DOLPHIN_API_KEY`).
    - **Env precedence contract:** Extension payload values always win, followed by settings-derived defaults in `~/.dolphin/config`, then any inherited OS env vars. `AgentBridge.start` MUST merge partial payloads, only overwriting the keys explicitly provided by the VSCode host so that CLI users who already exported `ANTHROPIC_API_KEY` keep working if the extension omits that provider.
    - Document the merge order inline so follow-up work in Phase 4 can rely on the same behavior.
15. In `extension.ts`:
    - Read `dolphin.llm.provider` and model settings.
    - Load both Anthropic and OpenAI API keys from secrets.
    - Build auth payload with `DOLPHIN_LLM_PROVIDER`, `DOLPHIN_LLM_MODEL`, and provider-specific keys.
    - **Model payload semantics:** send a single `DOLPHIN_LLM_MODEL` that corresponds to the active provider (`dolphin.llm.model.anthropic` or `dolphin.llm.model.openai`). If the configured model is missing or invalid, fall back to the defaults established in Phase 1 (`claude-sonnet-4-5-20250929` for Anthropic, `gpt-5.1-codex` for OpenAI) and log a warning so the UI can show a toast. Do **not** send additional provider-specific model env vars until we add multi-provider hot swapping.
    - Pass the payload into `agentBridge.start` so Agent Core spawns with the right credentials.
16. Update or add commands:
    - `dolphin.setClaudeApiKey` → stores `dolphin.anthropicApiKey`.
    - `dolphin.setOpenAIApiKey` → stores `dolphin.openaiApiKey`.
    - Both commands prompt with `showInputBox`, validate non-empty strings, and persist secrets exclusively through VSCode `SecretStorage`. If legacy storage existed (none today), migration would happen once at activation by copying any existing global state into the new secret keys before deletion. Each command should surface success/error notifications via `window.showInformationMessage` / `showErrorMessage` to aid troubleshooting.
17. Update Auth Status plumbing:
    - Ensure the `auth_status` payload from Agent Core includes `provider`.
    - Extend the JSON-RPC message that Agent Core emits so every `auth_status` event contains `{ provider, authenticated, mode, error, warning }`, and thread that field through the extension host to the Svelte webview message bus (`postMessage`). The webview `AuthStatus` component renders provider-aware labels & hints using the new field, and tests must assert both the extension host and UI layer handle the augmented schema.

### Phase 4 – Settings UI & UX Polish

#### Phase 4 Readiness Checklist (2025-01-17)

- ✅ **Message contracts consolidated** – `vscode-extension/src/shared/messages.ts` now declares the canonical extension ⇄ webview payloads (including the upcoming `settings.save`, `settings.saved`, `settings.error`, `setSecret`, and `secretStatus` events) so both `provider.ts` and `webview/src/lib/api/vscode.ts` share a single source of truth.
- ✅ **Provider/model definitions centralized** – `vscode-extension/src/config/provider-options.ts` exports the provider list, defaults, and model enums, and a dedicated Mocha test (`src/test/suite/unit/config/provider-options.test.ts`) asserts the VS Code `package.json` contributions stay in sync with §2.1.
- ✅ **Secret command bridging verified** – `DolphinViewProvider` now handles the `setSecret` message by invoking the existing `dolphin.setClaudeApiKey` / `dolphin.setOpenAIApiKey` commands and replying with `secretStatus` results; integration tests cover both success and failure cases.
- ✅ **Restart plumbing hardened** – `AgentBridge` exposes an `async stop()` plus an awaited `shutdown()` so future `settings.save` handlers can serialize provider restarts without races, and every caller/tests now await teardown.
- ✅ **Test plan captured** – Webview Bun specs will cover the settings route’s dropdown rendering + dirty-state logic, while extension-host Mocha suites (building on the new provider option + secret tests) will exercise `settings.save` validation, telemetry hooks, and the agent restart path.

18. **Settings surface (webview-owned) + provider selector behavior**
    - The **Svelte settings webview** (`vscode-extension/webview/src/routes/settings/+page.svelte`) remains the single UX for provider/model selection. It owns the dropdowns and pushes changes to the real VS Code settings service through the extension host so the `package.json` `contributes.configuration` entries (`dolphin.llm.provider`, `dolphin.llm.model.*`) stay authoritative.
    - The provider dropdown stays simple: two options (`Anthropic (Claude 4.5)` / `OpenAI (GPT‑5.1 family)`) rendered from a hard-coded enum shared with the extension (`vscode-extension/src/config/provider-options.ts`). The webview, not VS Code’s stock settings UI, controls selected state to keep layout consistent with the existing custom settings page.
    - On load, the webview asks the extension for the latest settings + `auth_status` snapshot. Each option shows an inline availability pill (✅ Ready / ⚠️ Key missing) computed by the extension by checking whether `dolphin.{anthropic|openai}ApiKey` exists. A refresh icon beside the pill re-sends the `get_auth_status` request so users can re-check prerequisites without closing the panel.

19. **Model selection + API key capture**
    - Render **two independent dropdowns**, one for Anthropic models and one for OpenAI models, so users can preconfigure both paths before switching providers. Values map to the hard-coded list already enumerated in §2.1; descriptions live in a shared map (`provider-options.ts`) so both extension and UI stay in sync until we add remote discovery.
    - For API keys, keep the existing VS Code secret commands and expose a lightweight “Set API Key” button per provider in the webview. Clicking invokes `vscode.postMessage({ type: "setSecret", provider })`, the extension calls `commands.executeCommand('dolphin.setClaudeApiKey' | 'dolphin.setOpenAIApiKey')`, and upon success the extension responds with `{ type: "secretStatus", provider, ok: true }`. The webview performs only minimal preflight validation (non-empty input length check when we later inline prompts) and otherwise defers to the command validators so the code path stays standard practice. Keys are never echoed in the UI.

20. **Save/apply + optimistic UI rules**
    - The Save button emits `{ type: "settings.save", payload: { provider, models } }`. `DolphinViewProvider` updates the real VS Code settings via `workspace.getConfiguration('dolphin').update(...)`, writes both provider and model keys, and replies with `{ type: "settings.saved", payload }` only after all writes resolve.
    - The webview **waits for this confirmation** before updating its “Current value” badges and before dismissing any dirty-state indicators. While the save is in-flight, the button shows a spinner and becomes disabled to prevent duplicate requests.
    - Extension-side validation keeps the schema simple: reject saves when the active provider has no secret stored (respond with `{ type: "settings.error", code: 'missingSecret' }` so the webview can show inline warnings). All other validation (e.g., invalid enum) is covered by the dropdown options themselves.

21. **Agent Core restart & responsiveness**
    - The extension is the source of truth for detecting changes. After persisting settings, `extension.ts` compares the previous `{ provider, activeModel }` tuple to the new one. If either field changes, call `agentBridge.stop()` followed by `agentBridge.start(newEnv)` once the stop promise resolves. This keeps the restart logic centralized and avoids multi-restart storms when users tweak several controls before pressing Save.
    - Because settings are applied in batches, there is no webview-side restart logic beyond awaiting the saved event. While Agent Core restarts, the webview shows the same spinner state and the Auth Status component continues to display the last-known status until a fresh `auth_status` event arrives.

22. **Error copy, inline warnings, and telemetry**
    - Missing-key scenarios surface as a yellow warning banner directly beneath the provider dropdown that fired the `missingSecret` code. The Auth Status panel mirrors this message verbatim ("OpenAI key missing — click Set API Key to continue"), keeping messaging simple per the UX guidance.
    - Other save failures show a toast plus inline text, but no complex remediation flow is required.
    - Send lightweight telemetry through the existing OpenTelemetry hooks (`observability/src/telemetry.ts`): emit events for `provider_changed`, `model_changed`, and `settings_error` with `{ provider, model, source: 'settings-webview' }`. No new backend plumbing is required; these flow into the centralized observability stack when enabled.

23. **Integration with prerequisites view**
    - The Auth Status card gains a “Refresh status” text button that reuses the same message as the inline availability pill. This ensures users always have a manual way to verify that key commands or external changes succeeded without waiting for polling.
    - The settings page also keeps the existing "Test Connection" entry point (if present) so the prerequisites workflow remains cohesive with other panels.

### Phase 5 – Testing, Cleanup, and Docs

21. Ensure all new tests clean up env vars, temp files, and secret mocks:
    - Pattern from `agent-core/tests/integration/auth/claude-auth.test.ts`.
22. Run:
    - `bun test` in `agent-core`.
    - VSCode extension tests (`npm test` / existing commands).
    - `bun test` in `vscode-extension/webview`.

    **Latest local status (container build, 2025-01-16):**
    - ✅ `cd agent-core && bun test`
    - ✅ `cd vscode-extension/webview && bun test`
    - ❌ `cd vscode-extension && npm test` (fails because the VS Code Electron runner requires the system library `libatk-1.0.so.0`, which is not installed in the container image)

23. Update docs:
    - `docs/ARCHITECTURE.md` – mention multi‑provider LLMs (Anthropic + OpenAI) for Agent Core.
    - `agent-core/README.md` – add examples for configuring Anthropic vs OpenAI.
    - `vscode-extension/README.md` – document new settings and commands.
24. Final manual verification:
    - Anthropic provider flows (Sonnet / Haiku).
    - OpenAI provider flows (5.1 / 5.1 Codex / 5.1 Codex Mini).

---

## 7. Risks & Mitigations

- **Risk:** Divergent behavior between providers (tool calling quirks, error formats).
  - **Mitigation:** Normalize error handling and tool input/output mappings in executors; add cross‑provider tests for representative flows.
- **Risk:** API key misconfiguration across layers (env vs VSCode secrets).
  - **Mitigation:** Auth Status component must clearly indicate which provider is active and whether a key is present; log configuration at Agent Core startup.
- **Risk:** OpenAI SDK or API shape changes.
  - **Mitigation:** Keep `OpenAIClient` as the single integration point; use the Context7 MCP server to consult OpenAI docs during development and keep usage patterns current.

---

## 8. Acceptance Criteria

- Users can select **Anthropic** or **OpenAI** as the LLM provider from the VSCode Settings page.
- Agent Core uses the selected provider for:
  - Editor workflow.
  - Architect workflow.
  - Tool‑enabled chat (MCP).
- Auth Status panel correctly reflects:
  - Active provider.
  - Presence/absence of keys.
  - Subscription vs API key where applicable.
- Tests:
  - New unit & integration tests for providers pass.
  - Existing Agent Core and extension tests remain green.
- Documentation updated to describe multi‑provider support and configuration.
