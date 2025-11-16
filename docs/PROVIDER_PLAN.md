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

| Deliverable                                      | Status | Notes |
| ------------------------------------------------ | :----: | ----- |
| Shared chat provider abstraction (`ChatProvider`) |  ✅   | Implemented in `agent-core/src/execution/chat-provider.ts` and adopted by the orchestrator/editor/architect workflows. |
| Anthropic + OpenAI client wrappers               |  ✅   | `AnthropicProvider` keeps the CLI + API dual-mode AuthManager, while `OpenAIProvider` uses the new OpenAI Responses adapter with streaming/tool support. |
| Tool execution engine with provider adapters     |  ✅   | `ToolExecutorEngine` powers both Anthropic and OpenAI adapters (`anthropic-tool-executor.ts`, `openai-tool-executor.ts`). |
| Provider selection knobs                         |  ✅   | `~/.dolphin/config` + `DOLPHIN_*` env vars select provider/model/temperature; a custom OpenAI-compatible base URL/API key are now supported via `provider.openai` overrides. |
| MCP workflow integration                         |  ✅   | Both providers use the same MCP tool loop and bubble up token usage to orchestrator telemetry. |

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
  - `claude-3.5-sonnet` (Sonnet 4.5)
  - `claude-3.5-haiku` (Haiku 4.5)
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
  - `dolphin.llm.model.anthropic`: `"claude-3.5-sonnet"` / `"claude-3.5-haiku"`
  - `dolphin.llm.model.openai`: `"gpt-5.1"` / `"gpt-5.1-codex"` / `"gpt-5.1-codex-mini"`
- Secrets:
  - `dolphin.anthropicApiKey`
  - `dolphin.openaiApiKey`
- Extension passes effective configuration to Agent Core via:
  - Environment variables (e.g., `DOLPHIN_LLM_PROVIDER`, `DOLPHIN_LLM_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) and/or
  - An initial JSON‑RPC configuration request (optional future enhancement).

### 2.3 Core Architectural Changes

1. Introduce a **provider‑neutral LLM interface** in agent-core:
   - Workflows depend on `ILLMProvider` instead of `ClaudeProvider`.
2. Implement two concrete providers:
   - `ClaudeLLMProvider` – wraps current Claude client and tool executor.
   - `OpenAILLMProvider` – new provider using OpenAI Chat + tools.
3. Add a **factory** in Agent Core that:
   - Reads provider + model from environment.
   - Constructs the appropriate `ILLMProvider` instance.
4. Update VSCode extension:
   - Settings UI for provider & model selection on the Settings page.
   - Commands to manage both Anthropic and OpenAI keys.
   - Auth Status UI updated to display provider‑aware state.

### 2.4 OpenAI Integration Details

- Use the OpenAI Chat Completions API with tools (via the **Context7 MCP server** for authoritative OpenAI docs references during development).
- Map MCP tools (already used for Claude) into OpenAI’s tools schema:
  - `name`, `description`, `parameters` (JSON Schema).
- Implement a loop similar to `ClaudeToolExecutor`:
  - Call OpenAI with tools → receive `tool_calls` → execute via MCP → feed results back into the conversation until completion or max rounds.

---

## 3. Agent Core Spec

### 3.1 Provider‑Neutral Interface

**File:** `agent-core/src/llm/llm-provider.ts`

```ts
export type LLMProviderName = "anthropic" | "openai";

export type LLMBlockType =
  | "text"
  | "code"
  | "tool_call"
  | "tool_result"
  | "system_note"
  | "markdown";

export interface LLMBaseBlock {
  type: LLMBlockType;
  provider: LLMProviderName;
  /**
   * Escape hatch for provider-specific data (Anthropic/OpenAI/etc).
   * May be omitted when persisting to disk to keep formats stable.
   */
  rawProviderPayload?: unknown;
}

export interface LLMTextBlock extends LLMBaseBlock {
  type: "text" | "markdown";
  text: string;
}

export interface LLMCodeBlock extends LLMBaseBlock {
  type: "code";
  language?: string;
  code: string;
}

export interface LLMToolCallBlock extends LLMBaseBlock {
  type: "tool_call";
  toolName: string;
  arguments: Record<string, unknown>;
  callId: string;
}

export interface LLMToolResultBlock extends LLMBaseBlock {
  type: "tool_result";
  toolName: string;
  callId: string;
  result: unknown;
  isError?: boolean;
}

export type LLMBlock =
  | LLMTextBlock
  | LLMCodeBlock
  | LLMToolCallBlock
  | LLMToolResultBlock
  | LLMBaseBlock; // open for future extension

/**
 * Content may be a single block or an ordered array of blocks.
 * Implementations MUST preserve structure from the underlying SDK.
 */
export type LLMContent = LLMBlock | LLMBlock[];

export interface LLMMessage {
  role: "user" | "assistant";
  content: LLMContent;
}

export interface LLMAuthStatus {
  provider: LLMProviderName;
  mode: "subscription" | "api_key" | "none";
  apiKeySet: boolean;
  cliInstalled?: boolean;
  cliAuthenticated?: boolean;
  willUseSubscription?: boolean;
  warning?: string;
  error?: string;
}

export interface LLMExecuteParams {
  message: string;
  // Provider implementations may attach rich content blocks to history entries.
  conversationHistory?: LLMMessage[];
  onEvent?: (event: AgentEvent) => void;
}

export interface LLMExecuteResult {
  // Full conversation messages with provider-specific content preserved.
  messages: LLMMessage[];
  stopReason?: string;
  toolRounds: number;
  usage: {
    inputTokens: number;
    outputTokens: number;
    cacheReadTokens: number;
    cacheWriteTokens: number;
  };
}

export interface ILLMProvider {
  readonly name: LLMProviderName;

  initialize(): Promise<void>;
  execute(params: LLMExecuteParams): Promise<LLMExecuteResult>;
  /**
   * Best-effort, fire-and-forget cancellation.
   * Implementations must be idempotent; some events may still arrive briefly
   * after abort is called while upstream streams are draining.
   */
  abort(): void;
  getAuthStatus(): Promise<LLMAuthStatus>;
  getUsage(): LLMExecuteResult["usage"];
}
```

Existing `ClaudeProvider` will be adapted to implement `ILLMProvider` (as `ClaudeLLMProvider`).

### 3.2 Claude Provider (Anthropic)

**Files:**

- `agent-core/src/execution/claude-provider.ts` → refactor into `ClaudeLLMProvider`.
- `agent-core/src/llm/claude-client.ts` (unchanged external API).
- `agent-core/src/llm/claude-tool-executor.ts` (unchanged external API).

**Key changes (pseudocode):**

```ts
// agent-core/src/execution/claude-llm-provider.ts
export class ClaudeLLMProvider implements ILLMProvider {
  readonly name = "anthropic" as const;
  private executor: ClaudeToolExecutor;
  private claudeClient: ClaudeClient;
  private authManager: AuthManager;

  constructor(config: ClaudeProviderConfig & { model: string }) {
    this.authManager = config.authManager ?? new AuthManager();
    this.claudeClient =
      config.claudeClient ??
      new ClaudeClient({
        model: config.model,           // from front-end/config
        maxTokens: 4096,
        temperature: 1.0,
      });
    this.executor =
      config.toolExecutor ??
      new ClaudeToolExecutor({
        claudeClient: this.claudeClient,
        mcpClient: config.mcpClient,
        maxToolRounds: config.maxToolRounds ?? 10,
        onEvent: config.onEvent ?? defaultOnEvent,
      });
  }

  async initialize(): Promise<void> {
    await this.executor.initialize();
  }

  async execute(params: LLMExecuteParams): Promise<LLMExecuteResult> {
    const executor =
      params.onEvent && params.onEvent !== defaultOnEvent
        ? new ClaudeToolExecutor({ ...this.executorConfig, onEvent: params.onEvent })
        : this.executor;

    const result = await executor.executeWithTools(
      params.message,
      // Pass through rich content blocks from history.
      (params.conversationHistory ?? []).map((m) => ({ role: m.role, content: m.content })),
    );

    return {
      // Preserve rich content blocks from Claude (no flattening).
      messages: result.messages as LLMMessage[],
      stopReason: result.stopReason,
      toolRounds: result.toolRounds,
      usage: executor.getUsage(),
    };
  }

  abort(): void {
    this.executor.abort();
  }

  async getAuthStatus(): Promise<LLMAuthStatus> {
    const status = await this.claudeClient.getAuthStatus();
    return {
      provider: "anthropic",
      mode: status.apiKeySet || status.cliAuthenticated ? "api_key" : "none", // refined mapping
      apiKeySet: status.apiKeySet,
      cliInstalled: status.cliInstalled,
      cliAuthenticated: status.cliAuthenticated,
      willUseSubscription: status.willUseSubscription,
      warning: undefined,
    };
  }

  getUsage(): LLMExecuteResult["usage"] {
    return this.executor.getUsage();
  }
}
```

### 3.3 OpenAI Client & Tool Executor

**Files:**

- `agent-core/src/llm/openai-client.ts`
- `agent-core/src/llm/openai-tool-executor.ts`
- `agent-core/src/execution/openai-llm-provider.ts`

**OpenAIClient pseudocode:**

```ts
// agent-core/src/llm/openai-client.ts
import OpenAI from "openai";

export interface OpenAIConfig {
  apiKey?: string;
  model: string;         // e.g. "gpt-5.1-codex"
  maxTokens: number;
  temperature?: number;
}

export interface OpenAIChatRequest {
  messages: { role: "user" | "assistant" | "system"; content: string }[];
  tools?: OpenAI.ChatCompletionTool[];
}

export interface OpenAIChatResult {
  message: OpenAI.Chat.Completions.ChatCompletionMessage;
  usage: {
    input_tokens: number;
    output_tokens: number;
  };
}

export class OpenAIClient {
  private client: OpenAI;
  private config: OpenAIConfig;

  constructor(config: OpenAIConfig) {
    const apiKey = config.apiKey ?? process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error("OPENAI_API_KEY is required for OpenAI provider");
    }
    this.client = new OpenAI({ apiKey });
    this.config = config;
  }

  async chat(request: OpenAIChatRequest): Promise<OpenAIChatResult> {
    const completion = await this.client.chat.completions.create({
      model: this.config.model,
      messages: request.messages,
      tools: request.tools,
      temperature: this.config.temperature ?? 1.0,
      max_tokens: this.config.maxTokens,
    });

    const message = completion.choices[0]?.message;
    return {
      message,
      usage: {
        input_tokens: completion.usage?.prompt_tokens ?? 0,
        output_tokens: completion.usage?.completion_tokens ?? 0,
      },
    };
  }

  async getAuthStatus(): Promise<LLMAuthStatus> {
    const apiKeySet = !!(this.config.apiKey ?? process.env.OPENAI_API_KEY);
    return {
      provider: "openai",
      mode: apiKeySet ? "api_key" : "none",
      apiKeySet,
    };
  }
}
```

**OpenAIToolExecutor pseudocode:**

```ts
// agent-core/src/llm/openai-tool-executor.ts
export class OpenAIToolExecutor {
  private config: {
    openaiClient: OpenAIClient;
    mcpClient: MCPClient;
    maxToolRounds: number;
    onEvent: (event: AgentEvent) => void;
  };
  private tools: OpenAI.ChatCompletionTool[] = [];
  private abortController: AbortController | null = null;

  constructor(config: OpenAIToolExecutor["config"]) {
    this.config = config;
  }

  async initialize(): Promise<void> {
    const mcpTools = await this.config.mcpClient.listTools();
    this.tools = mapMCPToOpenAITools(mcpTools);
  }

  abort(): void {
    this.abortController?.abort();
  }

  async executeWithTools(
    userMessage: string,
    history: { role: "user" | "assistant"; content: LLMContent }[] = [],
  ): Promise<LLMExecuteResult> {
    this.abortController = new AbortController();

    const messages: OpenAI.ChatCompletionMessageParam[] = [
      // Map existing history into OpenAI’s message format, preserving content
      // structure where possible.
      ...history.map((m) => ({
        role: m.role,
        content: m.content as OpenAI.ChatCompletionContentPart[] | string,
      })),
      { role: "user", content: userMessage },
    ];

    let toolRounds = 0;
    let usageTotals = { inputTokens: 0, outputTokens: 0 };

    while (toolRounds < this.config.maxToolRounds) {
      if (this.abortController.signal.aborted) {
        throw new Error("Generation aborted by user");
      }

      const { message, usage } = await this.config.openaiClient.chat({
        messages,
        tools: this.tools,
      });

      usageTotals.inputTokens += usage.input_tokens;
      usageTotals.outputTokens += usage.output_tokens;

      if (!message.tool_calls || message.tool_calls.length === 0) {
        messages.push({ role: "assistant", content: message.content ?? "" });
        break;
      }

      // Execute tools via MCP
      const toolResults = await this.executeToolCalls(message.tool_calls);
      messages.push({ role: "assistant", content: message.content ?? "" });
      messages.push({ role: "user", content: toolResultsAsJson(toolResults) });
      toolRounds++;
    }

    return {
      messages: messages
        .filter((m) => m.role === "assistant" || m.role === "user")
        .map((m) => ({
          role: m.role as "user" | "assistant",
          // Preserve OpenAI content blocks or strings as-is.
          content: m.content as LLMContent,
        })),
      stopReason: undefined,
      toolRounds,
      usage: {
        inputTokens: usageTotals.inputTokens,
        outputTokens: usageTotals.outputTokens,
        cacheReadTokens: 0,
        cacheWriteTokens: 0,
      },
    };
  }

  private async executeToolCalls(
    toolCalls: OpenAI.Chat.Completions.ChatCompletionMessageToolCall[],
  ): Promise<unknown[]> {
    // Map each OpenAI tool call to MCP call, emit events, return results
  }
}
```

**OpenAI LLM Provider pseudocode:**

```ts
// agent-core/src/execution/openai-llm-provider.ts
export class OpenAILLMProvider implements ILLMProvider {
  readonly name = "openai" as const;
  private client: OpenAIClient;
  private executor: OpenAIToolExecutor;

  constructor(config: { model: string; mcpClient: MCPClient; maxToolRounds?: number }) {
    this.client = new OpenAIClient({
      model: config.model,
      maxTokens: 4096,
    });
    this.executor = new OpenAIToolExecutor({
      openaiClient: this.client,
      mcpClient: config.mcpClient,
      maxToolRounds: config.maxToolRounds ?? 10,
      onEvent: (event) => console.error("[OpenAI] Event:", event.type),
    });
  }

  async initialize(): Promise<void> {
    await this.executor.initialize();
  }

  async execute(params: LLMExecuteParams): Promise<LLMExecuteResult> {
    return await this.executor.executeWithTools(
      params.message,
      params.conversationHistory ?? [],
    );
  }

  abort(): void {
    this.executor.abort();
  }

  async getAuthStatus(): Promise<LLMAuthStatus> {
    return await this.client.getAuthStatus();
  }

  getUsage(): LLMExecuteResult["usage"] {
    // Could aggregate from executor; stub initially.
    return {
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0,
    };
  }
}
```

### 3.4 Provider Factory

**File:** `agent-core/src/llm/provider-factory.ts`

```ts
export interface ProviderFactoryConfig {
  mcpClient: MCPClient;
}

export interface ProviderFactoryResult {
  providerName: LLMProviderName;
  llmProvider: ILLMProvider;
}

export function createLLMProvider(config: ProviderFactoryConfig): ProviderFactoryResult {
  const providerEnv = process.env.DOLPHIN_LLM_PROVIDER as LLMProviderName | undefined;
  const modelEnv = process.env.DOLPHIN_LLM_MODEL;

  if (!providerEnv || !modelEnv) {
    throw new Error(
      "LLM provider is not configured. Set DOLPHIN_LLM_PROVIDER and DOLPHIN_LLM_MODEL via the front end."
    );
  }

  const provider = providerEnv;

  if (provider === "anthropic") {
    return {
      providerName: "anthropic",
      llmProvider: new ClaudeLLMProvider({
        model: modelEnv,
        mcpClient: config.mcpClient,
      }),
    };
  }

  if (provider === "openai") {
    return {
      providerName: "openai",
      llmProvider: new OpenAILLMProvider({
        model: modelEnv,
        mcpClient: config.mcpClient,
      }),
    };
  }

  throw new Error(`Unsupported LLM provider: ${provider}`);
}
```

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
- `dolphin.llm.model.anthropic`: `"claude-3.5-sonnet"` / `"claude-3.5-haiku"`
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
  .get<string>("model.anthropic", "claude-3.5-sonnet");

const openaiModel = vscode.workspace
  .getConfiguration("dolphin.llm")
  .get<string>("model.openai", "gpt-5.1");

const anthropicKey = await context.secrets.get("dolphin.anthropicApiKey");
const openaiKey = await context.secrets.get("dolphin.openaiApiKey");

const env = {
  ...process.env,
  DOLPHIN_LLM_PROVIDER: providerSetting,
  DOLPHIN_LLM_MODEL: providerSetting === "anthropic" ? anthropicModel : openaiModel,
};

// Only expose the key for the active provider.
if (providerSetting === "anthropic" && anthropicKey) {
  env.ANTHROPIC_API_KEY = anthropicKey;
}
if (providerSetting === "openai" && openaiKey) {
  env.OPENAI_API_KEY = openaiKey;
}

await agentBridge.start(agentCorePath, extensionPath, env);
```

*(AgentBridge.start signature will be adjusted to accept an `env` object rather than a single API key.)*

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
  provider: 'anthropic' | 'openai';
  mode: 'subscription' | 'api_key' | 'none' | 'auto';
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

- **New suites:**
  - `agent-core/tests/unit/llm/openai-client.test.ts`
  - `agent-core/tests/unit/llm/openai-tool-executor.test.ts`
  - `agent-core/tests/unit/llm/provider-factory.test.ts`
- Coverage:
  - OpenAIClient:
    - Missing `OPENAI_API_KEY` → throws with clear error.
    - Valid key (mocked) → `chat()` called with correct parameters.
  - OpenAIToolExecutor:
    - Maps MCP tools into OpenAI tools.
    - Handles no tool_calls → returns final assistant message.
    - Handles single/multiple tool_calls with mocked MCP responses.
    - Aborts correctly when `abort()` called.
  - Provider factory:
    - Creates correct provider based on env.
    - Throws on unsupported provider values.

### 5.2 Agent Core Integration Tests

- New suites:
  - `agent-core/tests/integration/llm/openai-auth.test.ts`
  - `agent-core/tests/integration/llm/openai-editor-workflow.test.ts`
- Scenarios:
  - With `DOLPHIN_LLM_PROVIDER=openai` and `OPENAI_API_KEY` set:
    - Editor workflow runs a simple task using mocked OpenAI client.
  - With `DOLPHIN_LLM_PROVIDER=anthropic`:
    - Existing Claude integration tests remain passing.

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

1. Add `ILLMProvider`, `LLMAuthStatus`, `LLMExecuteParams`, `LLMExecuteResult` in `agent-core/src/llm/llm-provider.ts`.
2. Refactor existing `ClaudeProvider` into `ClaudeLLMProvider`:
   - Implement `ILLMProvider`.
   - Adjust tests to reference the new class.
3. Update `EditorWorkflow` and `ArchitectWorkflow` to depend on `ILLMProvider` instead of `ClaudeProvider`.
4. Implement `createLLMProvider` factory and call it from `agent-core/src/main.ts`.
5. Update `get_auth_status` handling to use `ILLMProvider.getAuthStatus()` and include `provider`.
6. Neutralize prompts in `PromptBuilder` to remove “You are Claude” wording.
7. Run `bun test` for agent-core and fix any breakages.

### Phase 2 – OpenAI Provider (Agent Core)

8. Implement `OpenAIClient` with minimal `chat()` + `getAuthStatus()` using OpenAI Node SDK.
9. Implement `OpenAIToolExecutor`:
   - Map MCP tools → OpenAI tools.
   - Implement tool loop (similar to `ClaudeToolExecutor`) **with streaming and incremental `AgentEvent` emission**.
10. Implement `OpenAILLMProvider` that wraps `OpenAIClient` + `OpenAIToolExecutor`.
11. Extend provider factory to support `"openai"`.
12. Add unit tests for `OpenAIClient`, `OpenAIToolExecutor`, and OpenAI provider.
13. Add integration tests for OpenAI auth and editor workflow (with mocked client).

### Phase 3 – VSCode Extension Integration

14. Update `AgentBridge.start` to accept an `env` object instead of a single API key:
    - Adjust spawning logic to use provided env instead of constructing it internally.
15. In `extension.ts`:
    - Read `dolphin.llm.provider` and model settings.
    - Load both Anthropic and OpenAI API keys from secrets.
    - Build env with `DOLPHIN_LLM_PROVIDER`, `DOLPHIN_LLM_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.
    - Pass env into `agentBridge.start`.
16. Update or add commands:
    - `dolphin.setClaudeApiKey` → stores `dolphin.anthropicApiKey`.
    - `dolphin.setOpenAIApiKey` → stores `dolphin.openaiApiKey`.
17. Update Auth Status plumbing:
    - Ensure the `auth_status` payload from Agent Core includes `provider`.
    - Update webview `AuthStatus` component to render provider‑aware labels & hints.

### Phase 4 – Settings UI & UX Polish

18. Update settings page to:
    - Add provider selector.
    - Add provider‑specific model + key inputs.
    - Wire Save button to send config to extension (or rely on VSCode settings UI if used).
19. Ensure error states are friendly:
    - Missing key for selected provider → clear message in Auth Status panel.
20. Validate that switching provider in settings triggers a restart or refresh of Agent Core as needed.

### Phase 5 – Testing, Cleanup, and Docs

21. Ensure all new tests clean up env vars, temp files, and secret mocks:
    - Pattern from `agent-core/tests/integration/auth/claude-auth.test.ts`.
22. Run:
    - `bun test` in `agent-core`.
    - VSCode extension tests (`npm test` / existing commands).
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
