import { describe, it, expect, beforeEach, afterEach, mock } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { EditorWorkflow } from "../../../src/workflows/editor-workflow";
import { ContextBuilder } from "../../../src/context/context-builder";
import { PromptBuilder } from "../../../src/prompts/prompt-builder";
import type { WorkflowUpdate, TaskInput } from "../../../src/types/index";
import { OpenAIProvider } from "../../../src/execution/openai-provider";
import type { MCPClient } from "../../../src/mcp/mcp-client";
import type { OpenAIClient, OpenAIResponse } from "../../../src/llm/openai-client";

describe("Editor workflow with OpenAI provider", () => {
  let workspaceRoot: string;
  let workflow: EditorWorkflow;
  let contextBuilder: ContextBuilder;
  let promptBuilder: PromptBuilder;
  let mockStateStore: {
    saveSession: ReturnType<typeof mock>;
    loadSession: ReturnType<typeof mock>;
  };
  let originalFetch: typeof fetch;

  const response: OpenAIResponse = {
    id: "resp-openai",
    model: "gpt-5.1-codex",
    status: "completed",
    output: [
      {
        type: "message",
        role: "assistant",
        content: [
          { type: "text", text: "I updated the requested file." },
          { type: "text", text: "Changes look good." },
        ],
      },
    ],
    usage: { input_tokens: 42, output_tokens: 21 },
    stop_reason: "end_turn",
  };

  const mockOpenAIClient: OpenAIClient = {
    streamResponse: async (options) => {
      options.onTextChunk?.("I updated the requested file. ");
      options.onTextChunk?.("Changes look good.");
      return response;
    },
  } as OpenAIClient;

  const mockMcpClient: MCPClient = {
    listTools: async () => [],
    callTool: async () => ({}),
  } as unknown as MCPClient;

  beforeEach(() => {
    workspaceRoot = mkdtempSync(join(tmpdir(), "dolphin-openai-"));
    writeFileSync(join(workspaceRoot, "index.ts"), "export const value = 42;\n");

    mockStateStore = {
      saveSession: mock(async () => {}),
      loadSession: mock(async () => null),
    };

    contextBuilder = new ContextBuilder({ workspaceRoot, kbUrl: "http://localhost:7777" });
    promptBuilder = new PromptBuilder();

    originalFetch = global.fetch;
    global.fetch = mock(async () => ({
      ok: true,
      json: async () => [],
    })) as unknown as typeof fetch;

    const provider = new OpenAIProvider({
      workspaceRoot,
      apiKey: "sk-test",
      openAIClient: mockOpenAIClient,
      mcpClient: mockMcpClient,
      model: "gpt-5.1-codex",
      maxToolRounds: 2,
    });

    workflow = new EditorWorkflow({
      chatProvider: provider,
      contextBuilder,
      promptBuilder,
      stateStore: mockStateStore,
      workspaceRoot,
    });
  });

  afterEach(() => {
    global.fetch = originalFetch;
    rmSync(workspaceRoot, { recursive: true, force: true });
  });

  it("streams updates from OpenAI provider", async () => {
    const input: TaskInput = {
      mode: "editor",
      message: "Review index.ts and describe improvements",
      context: { files: ["index.ts"] },
    };

    const updates: WorkflowUpdate[] = [];
    for await (const update of workflow.execute(input)) {
      updates.push(update);
    }

    const startUpdate = updates.find(
      (u) => u.type === "state_change" && u.data.state === "executing"
    );
    const completionUpdate = updates.find(
      (u) => u.type === "state_change" && u.data.state === "complete"
    );
    const toolSummaryUpdate = updates.find(
      (u) =>
        u.type === "progress" &&
        u.data.phase === "complete" &&
        u.data.message?.includes("tool rounds")
    );

    expect(startUpdate).toBeDefined();
    expect(completionUpdate).toBeDefined();
    expect(toolSummaryUpdate).toBeDefined();
    expect(mockStateStore.saveSession).toHaveBeenCalled();
  });
});
