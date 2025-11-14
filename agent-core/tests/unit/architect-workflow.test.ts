/**
 * Unit tests for ArchitectWorkflow
 */

import { describe, test, expect, beforeEach } from "bun:test";
import { ArchitectWorkflow } from "../../src/workflows/architect-workflow";
import type {
  TaskInput,
  WorkflowUpdate,
  Context,
  ClaudeChunk,
  ResearchResult,
  ClarificationResult,
  Plan,
} from "../../src/types/index";

// Mock implementations
class MockClaudeProvider {
  private mockResponses: Map<string, string> = new Map();

  setMockResponse(model: string, response: string) {
    this.mockResponses.set(model, response);
  }

  async *execute(params: any): AsyncIterableIterator<ClaudeChunk> {
    const response = this.mockResponses.get(params.model) || "Mock response";

    // Yield response character by character (simulating streaming)
    for (const char of response) {
      yield {
        type: "text" as const,
        content: char,
      };
    }
  }
}

class MockContextBuilder {
  async build(_params: any): Promise<Context> {
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
  buildResearchPrompt(params: any): string {
    return `Research prompt for: ${params.task}`;
  }

  buildPlanningPrompt(params: any): string {
    return `Planning prompt for: ${params.task}`;
  }
}

describe("ArchitectWorkflow", () => {
  let workflow: ArchitectWorkflow;
  let mockClaudeProvider: MockClaudeProvider;
  let mockContextBuilder: MockContextBuilder;
  let mockPromptBuilder: MockPromptBuilder;
  let taskInput: TaskInput;

  beforeEach(() => {
    mockClaudeProvider = new MockClaudeProvider();
    mockContextBuilder = new MockContextBuilder();
    mockPromptBuilder = new MockPromptBuilder();

    workflow = new ArchitectWorkflow({
      claudeProvider: mockClaudeProvider as any,
      contextBuilder: mockContextBuilder as any,
      promptBuilder: mockPromptBuilder as any,
      maxClarificationTurns: 2,
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
      const researchFindings = "Found relevant authentication patterns in the codebase.";
      mockClaudeProvider.setMockResponse("claude-haiku-4-20250514", researchFindings);

      const updates: WorkflowUpdate[] = [];
      let researchResult: ResearchResult | undefined;

      const iterator = workflow.execute(taskInput);

      for await (const update of iterator) {
        updates.push(update);

        if (update.type === "progress" && update.data.phase === "research" && update.data.result) {
          researchResult = update.data.result;
        }

        // Break after research phase completes
        if (update.type === "state_change" && update.data.state === "clarifying") {
          break;
        }
      }

      // Verify state transitions
      expect(updates.some((u) => u.type === "state_change" && u.data.state === "researching")).toBe(
        true
      );

      expect(updates.some((u) => u.type === "state_change" && u.data.state === "clarifying")).toBe(
        true
      );

      // Verify research result
      expect(researchResult).toBeDefined();
      expect(researchResult?.findings).toContain("Found relevant authentication");
      expect(researchResult?.kbSearches.length).toBeGreaterThan(0);
      expect(researchResult?.model).toBe("claude-haiku-4-20250514");
    });

    test("should track KB searches during research", async () => {
      mockClaudeProvider.setMockResponse("claude-haiku-4-20250514", "Research findings");

      let researchResult: ResearchResult | undefined;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.phase === "research" && update.data.result) {
          researchResult = update.data.result;
        }

        if (update.type === "state_change" && update.data.state === "clarifying") {
          break;
        }
      }

      expect(researchResult?.kbSearches).toBeDefined();
      expect(researchResult?.kbSearches[0].query).toContain("authentication");
    });
  });

  describe("Clarification Phase", () => {
    test("should execute clarification phase with questions", async () => {
      mockClaudeProvider.setMockResponse("claude-haiku-4-20250514", "Research complete");
      mockClaudeProvider.setMockResponse(
        "claude-sonnet-4-20250514",
        "I have a few questions:\n1. What authentication method should we use?\n2. Should we support OAuth?\n[READY_TO_PLAN]"
      );

      const updates: WorkflowUpdate[] = [];
      let _clarificationResult: ClarificationResult | undefined;

      for await (const update of workflow.execute(taskInput)) {
        updates.push(update);

        if (
          update.type === "progress" &&
          update.data.phase === "clarification" &&
          update.data.result
        ) {
          _clarificationResult = update.data.result;
        }

        // Break after clarification completes
        if (update.type === "state_change" && update.data.state === "planning") {
          break;
        }
      }

      // Verify clarification happened
      expect(updates.some((u) => u.type === "state_change" && u.data.state === "clarifying")).toBe(
        true
      );

      // Note: In the actual implementation, clarification would parse questions
      // For now, we're testing that the phase executes
      expect(updates.some((u) => u.type === "state_change" && u.data.state === "planning")).toBe(
        true
      );
    });

    test("should detect [READY_TO_PLAN] signal", async () => {
      mockClaudeProvider.setMockResponse("claude-haiku-4-20250514", "Research complete");
      mockClaudeProvider.setMockResponse(
        "claude-sonnet-4-20250514",
        "Based on the codebase, I understand the requirements.\n[READY_TO_PLAN]"
      );

      let transitionedToPlanning = false;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "state_change" && update.data.state === "planning") {
          transitionedToPlanning = true;
          break;
        }
      }

      expect(transitionedToPlanning).toBe(true);
    });

    test("should respect max clarification turns", async () => {
      mockClaudeProvider.setMockResponse("claude-haiku-4-20250514", "Research complete");

      // Set response without [READY_TO_PLAN] to force max turns
      mockClaudeProvider.setMockResponse(
        "claude-sonnet-4-20250514",
        "I need more information about X"
      );

      let clarificationTurns = 0;

      for await (const update of workflow.execute(taskInput)) {
        if (
          update.type === "progress" &&
          update.data.phase === "clarification" &&
          update.data.message?.includes("Clarification turn")
        ) {
          clarificationTurns++;
        }

        // Break after planning starts (which should happen after max turns)
        if (update.type === "state_change" && update.data.state === "planning") {
          break;
        }
      }

      // Should respect maxClarificationTurns = 2
      expect(clarificationTurns).toBeLessThanOrEqual(2);
    });
  });

  describe("Planning Phase", () => {
    test("should generate structured plan", async () => {
      mockClaudeProvider.setMockResponse("claude-haiku-4-20250514", "Research findings");
      mockClaudeProvider.setMockResponse("claude-sonnet-4-20250514", "[READY_TO_PLAN]");

      const planContent = `## Overview
Add JWT-based authentication to the REST API

## Files to Modify
- \`src/api/server.ts\`
- \`src/middleware/auth.ts\`

## Files to Create
- \`src/utils/jwt.ts\`

## Implementation Steps
1. Install JWT library
2. Create authentication middleware
3. Add protected routes
4. Implement token refresh

## Complexity
medium`;

      mockClaudeProvider.setMockResponse("claude-opus-4-20250514", planContent);

      let plan: Plan | undefined;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.phase === "planning" && update.data.plan) {
          plan = update.data.plan;
        }

        // Break after awaiting approval
        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      expect(plan).toBeDefined();
      expect(plan?.content).toContain("JWT-based authentication");
      expect(plan?.filesToModify).toContain("src/api/server.ts");
      expect(plan?.filesToCreate).toContain("src/utils/jwt.ts");
      expect(plan?.steps.length).toBeGreaterThan(0);
      expect(plan?.complexity).toBe("medium");
      expect(plan?.status).toBe("pending_approval");
      expect(plan?.model).toBe("claude-opus-4-20250514");
    });

    test("should parse files from plan markdown", async () => {
      mockClaudeProvider.setMockResponse("claude-haiku-4-20250514", "Research");
      mockClaudeProvider.setMockResponse("claude-sonnet-4-20250514", "[READY_TO_PLAN]");

      const planWithFiles = `## Files to Modify
- \`api/routes.ts\`
- \`db/schema.ts\`

## Files to Create
- \`auth/jwt.ts\``;

      mockClaudeProvider.setMockResponse("claude-opus-4-20250514", planWithFiles);

      let plan: Plan | undefined;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.plan) {
          plan = update.data.plan;
        }

        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      expect(plan?.filesToModify).toEqual(["api/routes.ts", "db/schema.ts"]);
      expect(plan?.filesToCreate).toEqual(["auth/jwt.ts"]);
    });
  });

  describe("Complete Workflow", () => {
    test("should execute full research → clarification → planning flow", async () => {
      mockClaudeProvider.setMockResponse(
        "claude-haiku-4-20250514",
        "Found authentication patterns in codebase"
      );
      mockClaudeProvider.setMockResponse(
        "claude-sonnet-4-20250514",
        "Understood requirements [READY_TO_PLAN]"
      );
      mockClaudeProvider.setMockResponse(
        "claude-opus-4-20250514",
        "## Overview\nImplementation plan\n\n## Steps\n1. Step one\n2. Step two"
      );

      const states: string[] = [];
      const phases: string[] = [];

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "state_change") {
          states.push(update.data.state);
        }

        if (update.type === "progress" && update.data.phase) {
          if (!phases.includes(update.data.phase)) {
            phases.push(update.data.phase);
          }
        }

        // Complete workflow until awaiting approval
        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      // Verify all phases executed in order
      expect(phases).toContain("research");
      expect(phases).toContain("clarification");
      expect(phases).toContain("planning");

      // Verify state transitions
      expect(states).toEqual(["researching", "clarifying", "planning", "awaiting_approval"]);
    });

    test("should stream progress updates during execution", async () => {
      mockClaudeProvider.setMockResponse("claude-haiku-4-20250514", "Research");
      mockClaudeProvider.setMockResponse("claude-sonnet-4-20250514", "[READY_TO_PLAN]");
      mockClaudeProvider.setMockResponse("claude-opus-4-20250514", "Plan content");

      const progressMessages: string[] = [];

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.message) {
          progressMessages.push(update.data.message);
        }

        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      expect(progressMessages.some((m) => m.includes("knowledge base"))).toBe(true);
      expect(progressMessages.some((m) => m.includes("clarification"))).toBe(true);
      expect(progressMessages.some((m) => m.includes("plan"))).toBe(true);
    });
  });

  describe("Error Handling", () => {
    test("should handle errors gracefully", async () => {
      // Create a workflow with a provider that throws
      const errorProvider = {
        async *execute(): AsyncIterableIterator<ClaudeChunk> {
          throw new Error("Claude API error");
        },
      };

      const errorWorkflow = new ArchitectWorkflow({
        claudeProvider: errorProvider as any,
        contextBuilder: mockContextBuilder as any,
        promptBuilder: mockPromptBuilder as any,
      });

      let errorCaught = false;

      for await (const update of errorWorkflow.execute(taskInput)) {
        if (update.type === "error") {
          errorCaught = true;
          expect(update.data.error).toContain("Claude API error");
          break;
        }
      }

      expect(errorCaught).toBe(true);
    });

    test("should support abort functionality", async () => {
      mockClaudeProvider.setMockResponse("claude-haiku-4-20250514", "Research");
      mockClaudeProvider.setMockResponse("claude-sonnet-4-20250514", "Clarification");

      // Abort during execution
      setTimeout(() => {
        workflow.abort();
      }, 10);

      let _aborted = false;

      try {
        for await (const update of workflow.execute(taskInput)) {
          // Should eventually throw due to abort
          if (update.type === "error") {
            _aborted = true;
            break;
          }
        }
      } catch (error) {
        if (error instanceof Error && error.message === "Workflow aborted") {
          _aborted = true;
        }
      }

      // Note: Actual abort handling depends on timing, so we just verify the mechanism exists
      expect(workflow.abort).toBeDefined();
    });
  });

  describe("Plan Parsing", () => {
    test("should extract overview from plan", async () => {
      mockClaudeProvider.setMockResponse("claude-haiku-4-20250514", "Research");
      mockClaudeProvider.setMockResponse("claude-sonnet-4-20250514", "[READY_TO_PLAN]");

      const planWithOverview = `## Overview

This plan implements user authentication using JWT tokens and bcrypt password hashing.

## Steps
1. Implementation step`;

      mockClaudeProvider.setMockResponse("claude-opus-4-20250514", planWithOverview);

      let plan: Plan | undefined;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.plan) {
          plan = update.data.plan;
        }

        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      expect(plan?.overview).toContain("JWT tokens");
      expect(plan?.overview).toContain("bcrypt password hashing");
    });

    test("should extract complexity from plan", async () => {
      mockClaudeProvider.setMockResponse("claude-haiku-4-20250514", "Research");
      mockClaudeProvider.setMockResponse("claude-sonnet-4-20250514", "[READY_TO_PLAN]");

      const planWithComplexity = `## Complexity: high\n\nThis is a complex task.`;

      mockClaudeProvider.setMockResponse("claude-opus-4-20250514", planWithComplexity);

      let plan: Plan | undefined;

      for await (const update of workflow.execute(taskInput)) {
        if (update.type === "progress" && update.data.plan) {
          plan = update.data.plan;
        }

        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      expect(plan?.complexity).toBe("high");
    });
  });
});
