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
import { ContextBuilder } from "../../../src/context/context-builder";
import { PromptBuilder } from "../../../src/prompts/prompt-builder";
import type { TaskInput, TaskSession } from "../../../src/types/index";
import { mkdtemp, rm } from "fs/promises";
import { tmpdir } from "os";
import { join } from "path";

// Comprehensive mock Claude provider
class E2EMockClaudeProvider {
  private scenario: string;

  constructor(scenario: string = "happy_path") {
    this.scenario = scenario;
  }

  async *execute(params: unknown) {
    const { model } = params;

    let response = "";

    if (this.scenario === "happy_path") {
      if (model === "claude-haiku-4-20250514") {
        response = `# Research Findings

## Codebase Architecture
The application uses a standard Express.js architecture with the following key components:

- **Authentication**: JWT-based auth with refresh tokens (src/auth/)
- **API Routes**: RESTful endpoints in src/routes/
- **Middleware**: Request validation and error handling (src/middleware/)
- **Database**: PostgreSQL with Prisma ORM (src/db/)

## Current Auth Implementation
- JWT tokens stored in httpOnly cookies
- Password hashing with bcrypt
- No rate limiting currently implemented
- Basic session management

## Relevant Files
- src/auth/jwt.ts - Token generation and validation
- src/middleware/auth.ts - Authentication middleware
- src/routes/auth.ts - Auth endpoints (login, register, refresh)
- src/models/user.ts - User model and validation`;
      } else if (model === "claude-sonnet-4-20250514") {
        response = `I've reviewed the research findings and have a good understanding of the current authentication system.

I have a few clarifying questions to ensure the implementation meets your needs:

1. **Rate Limiting**: Should we implement rate limiting on all auth endpoints or just login/register?
2. **Token Expiry**: What should be the expiry time for access tokens and refresh tokens?
3. **Multi-Factor Auth**: Is 2FA required in this phase, or should we design for future extension?

Based on typical security best practices, I recommend:
- Rate limiting on all auth endpoints (especially login)
- Short-lived access tokens (15 minutes) with longer refresh tokens (7 days)
- Architecture that supports 2FA addition later

If you're comfortable with these defaults, I'm [READY_TO_PLAN]`;
      } else if (model === "claude-opus-4-20250514") {
        response = `## Overview

Enhance the authentication system with rate limiting, improved token management, and security hardening. The implementation will extend the existing JWT-based auth system while maintaining backward compatibility.

## Goals
1. Prevent brute force attacks via rate limiting
2. Implement token rotation for enhanced security
3. Add comprehensive audit logging
4. Improve error handling and security responses

## Files to Modify

- \`src/middleware/auth.ts\` - Add rate limiting middleware
- \`src/auth/jwt.ts\` - Implement token rotation logic
- \`src/routes/auth.ts\` - Update endpoints with new security features
- \`src/models/user.ts\` - Add failed login tracking
- \`src/db/schema.prisma\` - Add audit log table

## Files to Create

- \`src/middleware/rate-limit.ts\` - Rate limiting implementation
- \`src/auth/token-rotation.ts\` - Refresh token rotation logic
- \`src/utils/audit-logger.ts\` - Security event logging
- \`src/tests/auth-security.test.ts\` - Security-focused tests

## Implementation Steps

1. **Add Rate Limiting Middleware**
   - Install express-rate-limit package
   - Create rate-limit.ts with configurable limits
   - Apply to auth endpoints: 5 attempts per 15 minutes for login
   - Apply to auth endpoints: 3 attempts per hour for register

2. **Implement Token Rotation**
   - Modify jwt.ts to support token families
   - Add rotation logic in token-rotation.ts
   - Update refresh endpoint to rotate tokens on use
   - Invalidate all tokens in family if reuse detected

3. **Add Audit Logging**
   - Create audit log database table in schema.prisma
   - Implement audit-logger.ts utility
   - Log all auth events: login, logout, token refresh, failed attempts
   - Include IP address, user agent, timestamp

4. **Update Failed Login Tracking**
   - Add failed_login_count and locked_until fields to User model
   - Implement account lockout after 5 failed attempts
   - Add 30-minute lockout period
   - Send email notification on account lock

5. **Security Response Handling**
   - Standardize error responses to prevent user enumeration
   - Return generic "Invalid credentials" for both email and password errors
   - Add timing attack prevention with constant-time comparisons
   - Implement secure password reset flow

6. **Testing**
   - Write comprehensive security tests
   - Test rate limiting enforcement
   - Test token rotation and invalidation
   - Test account lockout functionality
   - Perform security audit

## Database Schema Changes

\`\`\`prisma
model User {
  id                String   @id @default(uuid())
  email             String   @unique
  password_hash     String
  failed_login_count Int     @default(0)
  locked_until      DateTime?
  created_at        DateTime @default(now())
  updated_at        DateTime @updatedAt
}

model AuditLog {
  id         String   @id @default(uuid())
  user_id    String?
  event_type String   // 'login', 'logout', 'token_refresh', 'failed_login'
  ip_address String
  user_agent String
  success    Boolean
  metadata   Json?
  timestamp  DateTime @default(now())
}

model TokenFamily {
  id            String   @id @default(uuid())
  user_id       String
  family_id     String   @unique
  revoked       Boolean  @default(false)
  created_at    DateTime @default(now())
}
\`\`\`

## Security Considerations

1. **Rate Limiting**: Use Redis for distributed rate limiting in production
2. **Token Storage**: Refresh tokens stored in httpOnly, secure cookies
3. **Token Rotation**: Detect and prevent token reuse attacks
4. **Audit Logs**: Store indefinitely for security analysis
5. **Account Lockout**: Email notification and manual unlock process

## Estimated Effort

**Complexity**: medium
**Time Estimate**: 2-3 days
**Testing Time**: 1 day

## Rollback Plan

If issues arise:
1. Disable rate limiting via feature flag
2. Revert to single-token system (no rotation)
3. Keep audit logging (low risk)

## Success Metrics

- Zero successful brute force attacks in testing
- All security tests passing
- Audit logs capturing all auth events
- Token rotation preventing reuse attacks
- Response times under 100ms for auth endpoints`;
      }
    } else if (this.scenario === "needs_multiple_clarifications") {
      if (model === "claude-haiku-4-20250514") {
        response = "Basic research findings about authentication system.";
      } else if (model === "claude-sonnet-4-20250514") {
        // First clarification turn
        response = `I need to understand a few things:

1. What specific security vulnerability are we addressing?
2. What is the current authentication method?`;
      }
    } else if (this.scenario === "max_turns_reached") {
      if (model === "claude-haiku-4-20250514") {
        response = "Research complete";
      } else if (model === "claude-sonnet-4-20250514") {
        // Never sends [READY_TO_PLAN], forcing max turns
        response = "I have some more questions about the implementation...";
      } else if (model === "claude-opus-4-20250514") {
        response = "## Plan\nImplementation details based on available information.";
      }
    }

    for (const char of response) {
      yield {
        type: "text" as const,
        content: char,
      };
    }
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
    const contextBuilder = new ContextBuilder({
      workspaceRoot: tempDir,
      kbUrl: "http://localhost:7777",
    });
    const promptBuilder = new PromptBuilder();

    const architectWorkflow = new ArchitectWorkflow({
      claudeProvider: claudeProvider as unknown,
      contextBuilder: contextBuilder as unknown,
      promptBuilder,
      maxClarificationTurns: 2,
    });

    const editorWorkflow = new EditorWorkflow({
      claudeProvider: claudeProvider as unknown,
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
