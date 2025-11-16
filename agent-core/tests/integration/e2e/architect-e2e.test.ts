/**
 * End-to-End tests for ArchitectWorkflow
 *
 * These tests verify the complete research → clarification → planning flow
 * with real-world scenarios and edge cases.
 */

import { describe, test, expect, beforeEach, afterAll } from "bun:test";
import { Orchestrator } from "../../../src/orchestrator/orchestrator";
import { ArchitectWorkflow } from "../../../src/workflows/architect-workflow";
import { EditorWorkflow } from "../../../src/workflows/editor-workflow";
import { StateStore } from "../../../src/state/state-store";
import { PromptBuilder } from "../../../src/prompts/prompt-builder";
import type {
  TaskInput,
  TaskSession,
  Context,
  ContextBuildParams,
  FileContent,
  KBResult,
} from "../../../src/types/index";
import { mkdtemp, rm } from "fs/promises";
import { tmpdir } from "os";
import { join } from "path";
import type {
  ChatProvider,
  ExecuteParams,
  ExecuteResult,
  AuthStatus,
} from "../../../src/execution/chat-provider";
import type { UsageStats, ToolExecutorMessage } from "../../../src/llm/tool-executor";

// Comprehensive mock provider
class E2EMockClaudeProvider implements ChatProvider {
  private scenario: string;
  private totalUsage: UsageStats = {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
  };

  constructor(scenario: string = "happy_path") {
    this.scenario = scenario;
  }

  async initialize(): Promise<void> {}

  async execute(params: ExecuteParams): Promise<ExecuteResult> {
    const prompt = params.message ?? "";
    const response = this.buildResponse(prompt);
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

  private buildResponse(prompt: string): string {
    const normalized = prompt.toLowerCase();

    if (
      normalized.includes("helping with code research") ||
      normalized.includes("begin your research now")
    ) {
      return this.researchResponse();
    }

    if (
      normalized.includes("plan must be provided as a toml code block") ||
      normalized.includes("creating implementation plan") ||
      normalized.includes("begin creating the plan now")
    ) {
      return this.planResponse();
    }

    if (prompt.includes("You are Claude, an expert coding assistant")) {
      return "Here is the requested change with explanations.";
    }

    if (normalized.includes("clarification phase")) {
      return this.clarificationResponse();
    }

    return "Acknowledged.";
  }

  private researchResponse(): string {
    if (this.scenario === "needs_multiple_clarifications") {
      return "Basic research findings about authentication system.";
    }

    if (this.scenario === "max_turns_reached") {
      return "Research complete";
    }

    return `# Research Findings

## Codebase Architecture
The application uses a standard Express.js architecture with the following key components:

- Authentication: JWT-based auth with refresh tokens (src/auth/)
- API Routes: RESTful endpoints in src/routes/
- Middleware: Request validation and error handling (src/middleware/)
- Database: PostgreSQL with Prisma ORM (src/db/)

## Current Auth Implementation
- JWT tokens stored in httpOnly cookies
- Password hashing with bcrypt
- No rate limiting currently implemented
- Basic session management

## Relevant Files
- src/auth/jwt.ts
- src/middleware/auth.ts
- src/routes/auth.ts
- src/models/user.ts`;
  }

  private clarificationResponse(): string {
    if (this.scenario === "needs_multiple_clarifications") {
      return `I need to understand a few things:

1. What specific security vulnerability are we addressing?
2. What is the current authentication method?`;
    }

    if (this.scenario === "max_turns_reached") {
      return "I have some more questions about the implementation...";
    }

    return `I've reviewed the research findings and have a good understanding of the current authentication system.

I have a few clarifying questions to ensure the implementation meets your needs:

1. Rate Limiting: Should we implement rate limiting on all auth endpoints or just login/register?
2. Token Expiry: What should be the expiry time for access tokens and refresh tokens?
3. Multi-Factor Auth: Is 2FA required now or later?

If you're comfortable with these defaults, I'm [READY_TO_PLAN]`;
  }

  private planResponse(): string {
    if (this.scenario === "max_turns_reached") {
      return "## Plan\nImplementation details based on available information.";
    }

    return `## Overview
Enhance the authentication system with rate limiting, token rotation, and audit logging.

${"```toml"}
plan_version = 1
overview = """
Secure auth flows with layered protections, telemetry, and auditability.
"""
complexity = "medium"
estimated_tokens = 2000

files_to_modify = [
  "src/middleware/auth.ts",
  "src/auth/jwt.ts",
  "src/routes/auth.ts",
  "src/models/user.ts",
  "src/db/schema.prisma"
]

files_to_create = [
  "src/middleware/rate-limit.ts",
  "src/auth/token-rotation.ts",
  "src/utils/audit-logger.ts",
  "src/tests/auth-security.test.ts"
]

[[steps]]
id = 1
description = "Add configurable rate limiting middleware and attach to all auth routes"
files = ["src/middleware/auth.ts", "src/middleware/rate-limit.ts", "src/routes/auth.ts"]
estimated_tokens = 500

[[steps]]
id = 2
description = "Implement refresh token rotation with JWT helpers and persistence"
files = ["src/auth/jwt.ts", "src/auth/token-rotation.ts", "src/models/user.ts"]
estimated_tokens = 600

[[steps]]
id = 3
description = "Create audit logging utilities and schema tables"
files = ["src/utils/audit-logger.ts", "src/db/schema.prisma"]
estimated_tokens = 450

[[steps]]
id = 4
description = "Backfill security regression tests for auth flows"
files = ["src/tests/auth-security.test.ts"]
estimated_tokens = 300
${"```"}

## Steps
1. Add rate limiting middleware
2. Implement token rotation
3. Add audit logging
4. Update security-focused tests`;
  }

  private defaultUsage(): UsageStats {
    return { inputTokens: 20, outputTokens: 15, cacheReadTokens: 0, cacheWriteTokens: 0 };
  }

  private incrementUsage(usage: UsageStats) {
    this.totalUsage.inputTokens += usage.inputTokens;
    this.totalUsage.outputTokens += usage.outputTokens;
    this.totalUsage.cacheReadTokens += usage.cacheReadTokens;
    this.totalUsage.cacheWriteTokens += usage.cacheWriteTokens;
  }
}
// Deterministic context builder to avoid real KB/file IO during tests
class TestContextBuilder {
  async build(params: ContextBuildParams): Promise<Context> {
    const files: FileContent[] = (params.files ?? []).map((path) => ({
      path,
      content: this.stubFileContent(path),
      language: this.detectLanguage(path),
      tokens: 120,
    }));

    const kbResults: KBResult[] =
      params.searchQuery && params.searchQuery.length > 0
        ? [
            {
              file: "src/auth/jwt.ts",
              startLine: 10,
              endLine: 40,
              content: `Stub KB context for "${params.searchQuery}"`,
              language: "typescript",
              score: 0.95,
              chunkId: "kb_stub_chunk",
            },
          ]
        : [];

    const totalTokens = files.reduce((sum, file) => sum + file.tokens, 0) + kbResults.length * 200;

    return {
      kbResults,
      files,
      repoMap: null,
      totalTokens,
      truncated: totalTokens > params.maxTokens,
    };
  }

  private stubFileContent(path: string): string {
    return `// Stub content for ${path}\nexport const placeholder = true;`;
  }

  private detectLanguage(path: string): string {
    const ext = path.split(".").pop()?.toLowerCase();
    const languageMap: Record<string, string> = {
      ts: "typescript",
      tsx: "typescript",
      js: "javascript",
      jsx: "javascript",
      py: "python",
    };

    return languageMap[ext ?? ""] || "text";
  }
}

describe("ArchitectWorkflow E2E", () => {
  let tempDir: string;
  let stateStore: StateStore;
  let orchestrator: Orchestrator;
  const tempDirs: string[] = [];

  beforeEach(async () => {
    // Create temporary directory for state storage
    tempDir = await mkdtemp(join(tmpdir(), "dolphin-test-"));
    tempDirs.push(tempDir);

    stateStore = new StateStore({
      storagePath: join(tempDir, ".dolphin"),
    });
  });

  const createOrchestrator = (scenario: string = "happy_path") => {
    const claudeProvider = new E2EMockClaudeProvider(scenario);
    const contextBuilder = new TestContextBuilder();
    const promptBuilder = new PromptBuilder();

    const architectWorkflow = new ArchitectWorkflow({
      chatProvider: claudeProvider as unknown as ChatProvider,
      contextBuilder: contextBuilder as unknown,
      promptBuilder,
      maxClarificationTurns: 2,
    });

    const editorWorkflow = new EditorWorkflow({
      chatProvider: claudeProvider as unknown as ChatProvider,
      contextBuilder: contextBuilder as unknown,
      promptBuilder,
    });

    return new Orchestrator({
      workspaceRoot: tempDir,
      stateStore,
      editorWorkflow,
      architectWorkflow,
    });
  };

  describe("Happy Path Flow", () => {
    test("should complete full workflow from research to plan approval", async () => {
      orchestrator = createOrchestrator("happy_path");

      const taskInput: TaskInput = {
        mode: "architect",
        message: "Enhance authentication system with rate limiting and token rotation",
        context: {
          files: ["src/auth/jwt.ts", "src/middleware/auth.ts"],
        },
      };

      const session = await orchestrator.startTask(taskInput);
      expect(session.id).toBeDefined();
      expect(session.mode).toBe("architect");
      expect(session.state).toBe("idle");

      const phases: string[] = [];
      const states: string[] = [];
      let finalSession: TaskSession | null = null;

      // Subscribe to updates
      for await (const update of orchestrator.subscribeToUpdates(session.id)) {
        if (update.type === "state_change") {
          states.push(update.data.state);
          console.error(`State: ${update.data.state}`);
        }

        if (update.type === "progress") {
          if (update.data.phase && !phases.includes(update.data.phase)) {
            phases.push(update.data.phase);
            console.error(`Phase: ${update.data.phase}`);
          }
        }

        // Stop at awaiting_approval
        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      // Verify complete flow
      expect(states).toContain("researching");
      expect(states).toContain("clarifying");
      expect(states).toContain("planning");
      expect(states).toContain("awaiting_approval");

      expect(phases).toContain("research");
      expect(phases).toContain("clarification");
      expect(phases).toContain("planning");

      // Check final session state
      finalSession = await orchestrator.getSession(session.id);
      expect(finalSession?.state).toBe("awaiting_approval");
      expect(finalSession?.research).toBeDefined();
      expect(finalSession?.clarification).toBeDefined();
      expect(finalSession?.plan).toBeDefined();

      // Verify plan content
      const plan = finalSession?.plan;
      expect(plan?.status).toBe("pending_approval");
      expect(plan?.filesToModify?.length).toBeGreaterThan(0);
      expect(plan?.filesToCreate?.length).toBeGreaterThan(0);
      expect(plan?.steps?.length).toBeGreaterThan(0);
      expect(plan?.complexity).toBe("medium");
      expect(plan?.content).toContain("rate limiting");
      expect(plan?.content).toContain("token rotation");
    });

    test("should persist session state through workflow", async () => {
      orchestrator = createOrchestrator("happy_path");

      const taskInput: TaskInput = {
        mode: "architect",
        message: "Add 2FA authentication",
        context: {},
      };

      const session = await orchestrator.startTask(taskInput);

      // Collect updates until planning completes
      for await (const update of orchestrator.subscribeToUpdates(session.id)) {
        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      // Load session from storage
      const loadedSession = await stateStore.loadSession(session.id);
      expect(loadedSession).toBeDefined();
      expect(loadedSession?.research).toBeDefined();
      expect(loadedSession?.clarification).toBeDefined();
      expect(loadedSession?.plan).toBeDefined();

      // Verify TOML serialization worked
      expect(loadedSession?.research?.findings).toBeTruthy();
      expect(loadedSession?.clarification?.conversationTurns).toBeGreaterThan(0);
      expect(loadedSession?.plan?.content).toBeTruthy();
    });
  });

  describe("Clarification Scenarios", () => {
    test("should handle immediate [READY_TO_PLAN] signal", async () => {
      orchestrator = createOrchestrator("happy_path");

      const taskInput: TaskInput = {
        mode: "architect",
        message: "Simple authentication fix",
        context: {},
      };

      const session = await orchestrator.startTask(taskInput);
      let clarificationTurns = 0;

      for await (const update of orchestrator.subscribeToUpdates(session.id)) {
        if (
          update.type === "progress" &&
          update.data.phase === "clarification" &&
          update.data.message?.includes("turn")
        ) {
          clarificationTurns++;
        }

        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      // Should complete quickly with minimal clarification
      expect(clarificationTurns).toBeLessThanOrEqual(1);
    });

    test("should enforce max clarification turns", async () => {
      orchestrator = createOrchestrator("max_turns_reached");

      const taskInput: TaskInput = {
        mode: "architect",
        message: "Complex multi-system integration",
        context: {},
      };

      const session = await orchestrator.startTask(taskInput);
      let clarificationTurns = 0;
      let reachedPlanning = false;

      for await (const update of orchestrator.subscribeToUpdates(session.id)) {
        if (
          update.type === "progress" &&
          update.data.phase === "clarification" &&
          update.data.message?.includes("turn")
        ) {
          clarificationTurns++;
        }

        if (update.type === "state_change" && update.data.state === "planning") {
          reachedPlanning = true;
        }

        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      // Should respect max turns and proceed to planning
      expect(clarificationTurns).toBeLessThanOrEqual(2);
      expect(reachedPlanning).toBe(true);
    });
  });

  describe("Plan Management", () => {
    test("should approve plan and transition to complete", async () => {
      orchestrator = createOrchestrator("happy_path");

      const taskInput: TaskInput = {
        mode: "architect",
        message: "Add authentication",
        context: {},
      };

      const session = await orchestrator.startTask(taskInput);

      // Wait for awaiting_approval
      for await (const update of orchestrator.subscribeToUpdates(session.id)) {
        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      // Approve the plan
      await orchestrator.approveTask(session.id);

      const approvedSession = await orchestrator.getSession(session.id);
      expect(approvedSession?.plan?.status).toBe("approved");
      expect(approvedSession?.plan?.approvedAt).toBeDefined();
    });

    test("should reject plan and transition to cancelled", async () => {
      orchestrator = createOrchestrator("happy_path");

      const taskInput: TaskInput = {
        mode: "architect",
        message: "Add feature",
        context: {},
      };

      const session = await orchestrator.startTask(taskInput);

      // Wait for awaiting_approval
      for await (const update of orchestrator.subscribeToUpdates(session.id)) {
        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      // Reject the plan
      await orchestrator.rejectTask(session.id, "Plan needs more detail");

      const rejectedSession = await orchestrator.getSession(session.id);
      expect(rejectedSession?.state).toBe("cancelled");
      expect(rejectedSession?.plan?.status).toBe("rejected");
    });

    test("should request plan revision", async () => {
      orchestrator = createOrchestrator("happy_path");

      const taskInput: TaskInput = {
        mode: "architect",
        message: "Add feature",
        context: {},
      };

      const session = await orchestrator.startTask(taskInput);

      // Wait for awaiting_approval
      for await (const update of orchestrator.subscribeToUpdates(session.id)) {
        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      // Request revision
      await orchestrator.revisePlan(session.id, "Please add more detail about error handling");

      const revisedSession = await orchestrator.getSession(session.id);
      expect(revisedSession?.state).toBe("plan_revision");
      expect(revisedSession?.plan?.revisions?.length).toBeGreaterThan(0);
    });
  });

  describe("State Persistence", () => {
    test("should save complete workflow state to TOML", async () => {
      orchestrator = createOrchestrator("happy_path");

      const taskInput: TaskInput = {
        mode: "architect",
        message: "Implement feature",
        context: { files: ["src/app.ts"] },
      };

      const session = await orchestrator.startTask(taskInput);

      // Complete workflow
      for await (const update of orchestrator.subscribeToUpdates(session.id)) {
        if (update.type === "state_change" && update.data.state === "awaiting_approval") {
          break;
        }
      }

      // Reload from disk
      const reloaded = await stateStore.loadSession(session.id);

      expect(reloaded).toBeDefined();
      expect(reloaded?.id).toBe(session.id);
      expect(reloaded?.mode).toBe("architect");
      expect(reloaded?.input.message).toBe(taskInput.message);
      expect(reloaded?.research?.findings).toBeTruthy();
      expect(reloaded?.clarification?.conversationTurns).toBeGreaterThan(0);
      expect(reloaded?.plan?.content).toBeTruthy();
    });
  });

  // Cleanup
  afterAll(async () => {
    for (const dir of tempDirs) {
      try {
        await rm(dir, { recursive: true, force: true });
      } catch (error) {
        // Ignore cleanup errors
      }
    }
  });
});
