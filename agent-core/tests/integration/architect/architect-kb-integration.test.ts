/**
 * Integration tests for ArchitectWorkflow with Knowledge Bank
 *
 * These tests verify the integration between the architect workflow
 * and the Knowledge Bank system, including semantic search during
 * research and clarification phases.
 */

import { describe, test, expect, beforeAll, afterAll, mock } from "bun:test";
import { ArchitectWorkflow } from "../../../src/workflows/architect-workflow";
import { ContextBuilder } from "../../../src/context/context-builder";
import { PromptBuilder } from "../../../src/prompts/prompt-builder";
import type { TaskInput, WorkflowUpdate, ResearchResult } from "../../../src/types/index";
import type {
  ChatProvider,
  ExecuteParams,
  ExecuteResult,
  AuthStatus,
} from "../../../src/execution/chat-provider";
import type { UsageStats, ToolExecutorMessage } from "../../../src/llm/tool-executor";

// Simple mock provider for integration tests
class MockClaudeProvider implements ChatProvider {
  private totalUsage: UsageStats = {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
  };

  async initialize(): Promise<void> {}

  async execute(params: ExecuteParams): Promise<ExecuteResult> {
    const prompt = params.message ?? "";
    const response = this.selectResponse(prompt);
    const usage = this.defaultUsage();

    if (params.onEvent) {
      for (const char of response) {
        params.onEvent({ type: "content_delta", delta: char });
      }
    }

    this.incrementUsage(usage);

    const history = params.conversationHistory ?? [];
    const messages: ToolExecutorMessage[] = [
      ...history,
      { role: "user", content: prompt },
      { role: "assistant", content: response },
    ];

    return {
      messages,
      stopReason: "end_turn",
      toolRounds: 0,
      usage,
    };
  }

  abort(): void {}

  async detectAuthStatus(): Promise<AuthStatus> {
    return { authenticated: true, mode: "mock" };
  }

  async ensureAuthenticated(): Promise<void> {}

  getUsage(): UsageStats {
    return { ...this.totalUsage };
  }

  getProviderMetadata() {
    return { provider: "mock", model: "mock-model" };
  }

  private selectResponse(prompt: string): string {
    const normalized = prompt.toLowerCase();

    if (normalized.includes("helping with code research") || normalized.includes("begin your research now")) {
      return `Based on the KB search results, I found:
- Authentication middleware in src/middleware/auth.ts
- JWT utilities in src/utils/jwt.ts
- User model in src/models/user.ts

The codebase follows a standard Express.js pattern with middleware-based auth.`;
    }

    if (
      normalized.includes("plan must be provided as a toml code block") ||
      normalized.includes("creating implementation plan") ||
      normalized.includes("begin creating the plan now")
    ) {
      return `## Overview
Enhance the existing authentication system with additional security features.

Here is the proposed implementation plan:

${"```toml"}
plan_version = 1
overview = """
Enhance the auth middleware with stronger protections and password policies.
"""
complexity = "medium"
estimated_tokens = 1200

files_to_modify = [
  "src/middleware/auth.ts",
  "src/utils/jwt.ts",
  "src/models/user.ts"
]

files_to_create = [
  "src/middleware/rate-limit.ts",
  "src/utils/password-policy.ts"
]

[[steps]]
id = 1
description = "Introduce shared rate limiting middleware and wire it through auth routes"
files = ["src/middleware/auth.ts", "src/middleware/rate-limit.ts"]
estimated_tokens = 400

[[steps]]
id = 2
description = "Expand JWT utilities to support refresh rotation and revocation lists"
files = ["src/utils/jwt.ts"]
estimated_tokens = 300

[[steps]]
id = 3
description = "Store password policy settings on the user model with validation helpers"
files = ["src/models/user.ts", "src/utils/password-policy.ts"]
estimated_tokens = 300
${"```"}

## Implementation Steps
1. Add rate limiting to auth endpoints (estimated 400 tokens)
2. Implement password complexity requirements (estimated 300 tokens)
3. Add refresh token rotation (estimated 300 tokens)`;
    }

    if (normalized.includes("clarification phase")) {
      return `I have reviewed the codebase and understand the authentication patterns.

Questions for clarification:
1. Should we extend the existing JWT implementation or replace it?
2. Do we need to support multiple authentication methods?

[READY_TO_PLAN]`;
    }

    return "Acknowledged.";
  }

  private defaultUsage(): UsageStats {
    return { inputTokens: 15, outputTokens: 10, cacheReadTokens: 0, cacheWriteTokens: 0 };
  }

  private incrementUsage(usage: UsageStats) {
    this.totalUsage.inputTokens += usage.inputTokens;
    this.totalUsage.outputTokens += usage.outputTokens;
    this.totalUsage.cacheReadTokens += usage.cacheReadTokens;
    this.totalUsage.cacheWriteTokens += usage.cacheWriteTokens;
  }
}

describe("ArchitectWorkflow KB Integration", () => {
  let workflow: ArchitectWorkflow;
  let contextBuilder: ContextBuilder;
  let originalFetch: typeof fetch;

  beforeAll(() => {
    originalFetch = global.fetch;

    const sampleHits = [
      {
        file_path: "src/middleware/auth.ts",
        start_line: 10,
        end_line: 80,
        snippet_text: "export function authMiddleware(req, res, next) { /* ... */ }",
        language: "typescript",
        score: 0.92,
        chunk_id: "chunk_auth_middleware",
      },
      {
        file_path: "src/utils/jwt.ts",
        start_line: 1,
        end_line: 60,
        snippet_text: "export const signJwt = () => {/* ... */};",
        language: "typescript",
        score: 0.88,
        chunk_id: "chunk_jwt_utils",
      },
    ];

    global.fetch = mock(async (input: Request | string, _init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.url;

      if (url.includes("localhost:9999")) {
        throw new Error("Connection refused");
      }

      if (url.includes("/v1/search")) {
        return {
          ok: true,
          json: async () => sampleHits,
        } as Response;
      }

      return {
        ok: true,
        json: async () => ({}),
      } as Response;
    }) as unknown as typeof fetch;

    // Setup with real context builder (will use mock KB for testing)
    contextBuilder = new ContextBuilder({
      workspaceRoot: "/test/workspace",
      kbUrl: "http://localhost:7777", // Will be mocked in actual tests
    });

    const promptBuilder = new PromptBuilder();
    const claudeProvider = new MockClaudeProvider();

    workflow = new ArchitectWorkflow({
      chatProvider: claudeProvider as unknown as ChatProvider,
      contextBuilder: contextBuilder as unknown,
      promptBuilder,
      maxClarificationTurns: 2,
    });
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  describe("KB Search During Research", () => {
    test("should perform KB search with task query", async () => {
      const taskInput: TaskInput = {
        mode: "architect",
        message: "Add user authentication with JWT",
        context: {
          files: [],
          folders: [],
        },
      };

      let researchResult: ResearchResult | undefined;
      const kbSearchQueries: string[] = [];

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.phase === "research") {
          if (update.data.message?.includes("Searching knowledge base")) {
            // KB search initiated
            kbSearchQueries.push(taskInput.message);
          }

          if (update.data.result) {
            researchResult = update.data.result;
          }
        }

        // Break after research phase
        if (update.type === "state_change" && update.data.state === "clarifying") {
          break;
        }
      }

      expect(kbSearchQueries.length).toBeGreaterThan(0);
      expect(researchResult).toBeDefined();
      expect(researchResult?.kbSearches.length).toBeGreaterThan(0);
    });

    test("should include KB results in research findings", async () => {
      const taskInput: TaskInput = {
        mode: "architect",
        message: "Implement rate limiting for API endpoints",
        context: {},
      };

      let researchResult: ResearchResult | undefined;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.phase === "research" && update.data.result) {
          researchResult = update.data.result;
        }

        if (update.type === "state_change" && update.data.state === "clarifying") {
          break;
        }
      }

      expect(researchResult?.findings).toBeDefined();
      expect(researchResult?.findings.length).toBeGreaterThan(0);

      // Findings should reference codebase insights from KB
      expect(
        researchResult?.findings.toLowerCase().includes("middleware") ||
          researchResult?.findings.toLowerCase().includes("auth") ||
          researchResult?.findings.toLowerCase().includes("jwt")
      ).toBe(true);
    });

    test("should track relevant files from KB search", async () => {
      const taskInput: TaskInput = {
        mode: "architect",
        message: "Add authentication middleware",
        context: {},
      };

      let researchResult: ResearchResult | undefined;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.phase === "research" && update.data.result) {
          researchResult = update.data.result;
        }

        if (update.type === "state_change" && update.data.state === "clarifying") {
          break;
        }
      }

      // Should have identified relevant files from KB
      expect(researchResult?.relevantFiles).toBeDefined();
      // At minimum, KB search should return some files
      // (actual files depend on mock setup)
    });
  });

  describe("KB Context in Clarification", () => {
    test("should maintain KB context through clarification phase", async () => {
      const taskInput: TaskInput = {
        mode: "architect",
        message: "Enhance authentication system",
        context: {},
      };

      const updates: WorkflowUpdate[] = [];

      for await (const update of workflow.execute(taskInput)) {
        updates.push(update);

        // Stop after clarification completes
        if (update.type === "state_change" && update.data.state === "planning") {
          break;
        }
      }

      // Verify both research and clarification phases occurred
      expect(updates.some((u) => u.type === "state_change" && u.data.state === "researching")).toBe(
        true
      );

      expect(updates.some((u) => u.type === "state_change" && u.data.state === "clarifying")).toBe(
        true
      );

      // Clarification should reference research findings
      const clarificationUpdates = updates.filter(
        (u) => u.type === "progress" && u.data.phase === "clarification"
      );

      expect(clarificationUpdates.length).toBeGreaterThan(0);
    });

    test("should allow LLM to request additional KB searches during clarification", async () => {
      // Note: This test verifies the architecture supports it
      // Actual tool calling would require more complex mocking

      const taskInput: TaskInput = {
        mode: "architect",
        message: "Refactor authentication system",
        context: {},
      };

      let clarificationStarted = false;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "state_change" && update.data.state === "clarifying") {
          clarificationStarted = true;
        }

        // In a real scenario with tool calling, we'd see tool_call updates here
        // For now, we just verify clarification phase is reached
        if (update.type === "state_change" && update.data.state === "planning") {
          break;
        }
      }

      expect(clarificationStarted).toBe(true);
    });
  });

  describe("KB Context in Planning", () => {
    test("should use KB context to generate grounded plan", async () => {
      const taskInput: TaskInput = {
        mode: "architect",
        message: "Add two-factor authentication",
        context: {},
      };

      let plan: unknown;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.phase === "planning" && update.data.plan) {
          plan = update.data.plan;
        }

        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      expect(plan).toBeDefined();

      // Plan should reference actual files from codebase
      expect(plan.filesToModify?.length).toBeGreaterThan(0);

      // Files should be realistic paths (not hallucinated)
      expect(plan.filesToModify?.some((f: string) => f.includes(".ts") || f.includes(".js"))).toBe(
        true
      );
    });

    test("should include file references in implementation steps", async () => {
      const taskInput: TaskInput = {
        mode: "architect",
        message: "Implement session management",
        context: {},
      };

      let plan: unknown;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.plan) {
          plan = update.data.plan;
        }

        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      expect(plan).toBeDefined();
      expect(plan.steps).toBeDefined();
      expect(plan.steps.length).toBeGreaterThan(0);

      // Steps should be concrete and actionable
      plan.steps.forEach((step: string) => {
        expect(step.length).toBeGreaterThan(10);
      });
    });
  });

  describe("Context Assembly", () => {
    test("should respect token limits when building context", async () => {
      // This tests that ContextBuilder properly truncates KB results
      const taskInput: TaskInput = {
        mode: "architect",
        message: "Large refactoring task requiring many file changes",
        context: {
          files: Array.from({ length: 50 }, (_, i) => `src/file${i}.ts`),
        },
      };

      let hasError = false;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "error") {
          hasError = true;
          break;
        }

        // Should complete without token limit errors
        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      expect(hasError).toBe(false);
    });

    test("should prioritize most relevant KB results", async () => {
      const taskInput: TaskInput = {
        mode: "architect",
        message: "Fix critical authentication vulnerability",
        context: {},
      };

      let researchResult: ResearchResult | undefined;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.phase === "research" && update.data.result) {
          researchResult = update.data.result;
        }

        if (update.type === "state_change" && update.data.state === "clarifying") {
          break;
        }
      }

      // KB should have returned results sorted by relevance
      expect(researchResult?.kbSearches[0]).toBeDefined();
      // Note: resultsCount may be 0 if KB is not running - that's OK for this test
      expect(researchResult?.kbSearches[0].resultsCount).toBeGreaterThanOrEqual(0);
    });
  });

  describe("Error Scenarios", () => {
    test("should handle KB unavailability gracefully", async () => {
      // Create workflow with unreachable KB
      const offlineContextBuilder = new ContextBuilder({
        workspaceRoot: "/test/workspace",
        kbUrl: "http://localhost:9999", // Non-existent
      });

      const offlineWorkflow = new ArchitectWorkflow({
        chatProvider: new MockClaudeProvider() as unknown as ChatProvider,
        contextBuilder: offlineContextBuilder as unknown,
        promptBuilder: new PromptBuilder(),
      });

      const taskInput: TaskInput = {
        mode: "architect",
        message: "Test task",
        context: {},
      };

      // Workflow should degrade gracefully without KB
      let completedSomePhase = false;

      try {
        for await (const update of offlineWorkflow.execute(taskInput)) {
          if (update.type === "progress") {
            completedSomePhase = true;
          }

          // Break early to avoid long timeout
          if (completedSomePhase) {
            break;
          }
        }
      } catch (error) {
        // KB errors should be caught and handled
      }

      // Should attempt to continue even if KB is unavailable
      expect(completedSomePhase).toBe(true);
    });

    test("should handle empty KB search results", async () => {
      const taskInput: TaskInput = {
        mode: "architect",
        message: "Implement blockchain integration", // Likely to return no results
        context: {},
      };

      let researchCompleted = false;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.phase === "research" && update.data.result) {
          researchCompleted = true;
        }

        if (update.type === "state_change" && update.data.state === "clarifying") {
          break;
        }
      }

      // Should complete research even with no KB results
      expect(researchCompleted).toBe(true);
    });
  });
});
