/**
 * Unit tests for ArchitectWorkflow
 */

import { describe, test, expect, beforeEach } from "bun:test";
import { ArchitectWorkflow } from "../../../src/workflows/architect-workflow";
import type {
  ChatProvider,
  ExecuteParams,
  ExecuteResult,
  AuthStatus,
} from "../../../src/execution/chat-provider";
import type { ContextBuilder } from "../../../src/context/context-builder";
import type { PromptBuilder } from "../../../src/prompts/prompt-builder";
import type { StateStore } from "../../../src/state/state-store";
import type { PlanStore } from "../../../src/storage/plan-store";
import type {
  TaskInput,
  WorkflowUpdate,
  Context,
  ResearchResult,
  ClarificationResult,
} from "../../../src/types/index";
import type { UsageStats, ToolExecutorMessage } from "../../../src/llm/tool-executor";

class MockChatProvider implements ChatProvider {
  private responses: Array<{ text: string; usage: UsageStats }> = [];
  private totalUsage: UsageStats = {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
  };

  enqueueResponse(text: string, usage?: UsageStats) {
    this.responses.push({ text, usage: usage ?? this.defaultUsage() });
  }

  async initialize(): Promise<void> {
    // no-op
  }

  async execute(params: ExecuteParams): Promise<ExecuteResult> {
    const response = this.responses.shift() ?? {
      text: "default response",
      usage: this.defaultUsage(),
    };

    if (params.onEvent) {
      for (const char of response.text) {
        params.onEvent({ type: "content_delta", delta: char });
      }
    }

    this.totalUsage.inputTokens += response.usage.inputTokens;
    this.totalUsage.outputTokens += response.usage.outputTokens;
    this.totalUsage.cacheReadTokens += response.usage.cacheReadTokens;
    this.totalUsage.cacheWriteTokens += response.usage.cacheWriteTokens;

    const conversationHistory = params.conversationHistory ?? [];
    const messages: ToolExecutorMessage[] = [
      ...conversationHistory,
      { role: "user", content: params.message },
      { role: "assistant", content: response.text },
    ];

    return {
      messages,
      stopReason: "end_turn",
      toolRounds: 0,
      usage: response.usage,
    };
  }

  abort(): void {
    // no-op
  }

  async detectAuthStatus(): Promise<AuthStatus> {
    return { authenticated: true, mode: "mock" };
  }

  async ensureAuthenticated(): Promise<void> {
    // no-op
  }

  getUsage(): UsageStats {
    return { ...this.totalUsage };
  }

  getProviderMetadata() {
    return { provider: "mock", model: "mock-model" };
  }

  private defaultUsage(): UsageStats {
    return { inputTokens: 10, outputTokens: 5, cacheReadTokens: 0, cacheWriteTokens: 0 };
  }
}

class MockContextBuilder {
  async build(_params: unknown): Promise<Context> {
    return {
      kbResults: [
        {
          file: "src/test.ts",
          startLine: 1,
          endLine: 10,
          content: "mock code content",
          language: "typescript",
          score: 0.9,
          chunkId: "chunk_123",
        },
      ],
      files: [],
      repoMap: null,
      totalTokens: 500,
      truncated: false,
    };
  }
}

class MockPromptBuilder {
  buildResearchPrompt(params: { task: string }): string {
    return `Research prompt for: ${params.task}`;
  }

  buildPlanningPrompt(params: { task: string }): string {
    return `Planning prompt for: ${params.task}`;
  }
}

function createPlanResponse(): string {
  return `Here is the plan:
\n\n\`\`\`toml
plan_version = 1
overview = """High level"""
complexity = "medium"
estimated_tokens = 100
files_to_modify = []
files_to_create = []

[[steps]]
id = 1
description = "Do something"
files = ["src/index.ts"]
estimated_tokens = 50
\`\`\``;
}

describe("ArchitectWorkflow", () => {
  let workflow: ArchitectWorkflow;
  let mockProvider: MockChatProvider;
  let mockContextBuilder: MockContextBuilder;
  let mockPromptBuilder: MockPromptBuilder;
  let taskInput: TaskInput;

  beforeEach(() => {
    mockProvider = new MockChatProvider();
    mockContextBuilder = new MockContextBuilder();
    mockPromptBuilder = new MockPromptBuilder();

    workflow = new ArchitectWorkflow({
      chatProvider: mockProvider as unknown as ChatProvider,
      contextBuilder: mockContextBuilder as unknown as ContextBuilder,
      promptBuilder: mockPromptBuilder as unknown as PromptBuilder,
      maxClarificationTurns: 2,
      stateStore: {} as unknown as StateStore,
      planStore: {} as unknown as PlanStore,
      workspaceRoot: "/tmp",
    });

    taskInput = {
      mode: "architect" as const,
      message: "Add user authentication to the API",
      context: {
        files: [],
        folders: [],
      },
    };
  });

  describe("Research Phase", () => {
    test("should execute research phase successfully", async () => {
      const researchUsage: UsageStats = {
        inputTokens: 11,
        outputTokens: 7,
        cacheReadTokens: 2,
        cacheWriteTokens: 0,
      };
      mockProvider.enqueueResponse("Found relevant authentication patterns.", researchUsage);
      mockProvider.enqueueResponse("I have a few questions? [READY_TO_PLAN]");
      mockProvider.enqueueResponse(createPlanResponse());

      const updates: WorkflowUpdate[] = [];
      let researchResult: ResearchResult | undefined;

      for await (const update of workflow.execute(taskInput)) {
        updates.push(update);
        if (update.type === "progress" && update.data.phase === "research" && update.data.result) {
          researchResult = update.data.result as ResearchResult;
        }
      }

      expect(updates.some((u) => u.type === "state_change" && u.data.state === "researching")).toBe(
        true
      );
      expect(updates.some((u) => u.type === "state_change" && u.data.state === "clarifying")).toBe(
        true
      );

      expect(researchResult).toBeDefined();
      expect(researchResult?.findings).toContain("authentication patterns");
      expect(researchResult?.model).toBe("mock-model");
      expect(researchResult?.tokensUsed).toBe(20);
    });
  });

  describe("Clarification Phase", () => {
    test("should execute clarification phase with questions", async () => {
      mockProvider.enqueueResponse("Research complete.");
      mockProvider.enqueueResponse(
        "I have a few questions:\n1. What auth method?\n2. Should we support OAuth?\n[READY_TO_PLAN]"
      );
      mockProvider.enqueueResponse(createPlanResponse());

      const updates: WorkflowUpdate[] = [];
      let clarificationResult: ClarificationResult | undefined;

      for await (const update of workflow.execute(taskInput)) {
        updates.push(update);
        if (
          update.type === "progress" &&
          update.data.phase === "clarification" &&
          update.data.result
        ) {
          clarificationResult = update.data.result as ClarificationResult;
        }
      }

      expect(updates.some((u) => u.type === "state_change" && u.data.state === "clarifying")).toBe(
        true
      );
      expect(updates.some((u) => u.type === "state_change" && u.data.state === "planning")).toBe(
        true
      );
      expect(clarificationResult).toBeDefined();
      expect(clarificationResult?.conversationTurns).toBeGreaterThan(0);
      expect(clarificationResult?.readyForPlanning).toBe(true);
      expect(clarificationResult?.model).toBe("mock-model");
      expect(clarificationResult?.tokensUsed).toBeGreaterThan(0);
    });
  });
});
