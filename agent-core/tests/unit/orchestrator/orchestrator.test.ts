/**
 * Unit tests for Orchestrator
 */

import { describe, it, expect, beforeEach, mock } from "bun:test";
import { Orchestrator } from "../../../src/orchestrator/orchestrator";
import type { TaskInput } from "../../../src/types/index";

describe("Orchestrator", () => {
  let orchestrator: Orchestrator;
  let mockStateStore: unknown;
  let mockEditorWorkflow: unknown;
  let mockArchitectWorkflow: unknown;

  beforeEach(() => {
    // Create mock state store
    mockStateStore = {
      saveSession: mock(async () => {}),
      loadSession: mock(async () => null),
      savePlan: mock(async () => {}),
      loadPlan: mock(async () => null),
    };

    // Create mock workflows
    mockEditorWorkflow = {
      execute: mock(async function* () {
        yield {
          type: "state_change",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: { state: "executing" },
        };
        yield {
          type: "chunk",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: { content: "Hello" },
        };
        yield {
          type: "state_change",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: { state: "complete" },
        };
      }),
    };

    mockArchitectWorkflow = {
      execute: mock(async function* () {
        yield {
          type: "state_change",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: { state: "researching" },
        };
        yield {
          type: "state_change",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: { state: "planning" },
        };
        yield {
          type: "progress",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: {
            phase: "planning",
            plan: {
              version: 1,
              status: "pending_approval",
              createdAt: new Date().toISOString(),
              model: "claude-opus-4-20250514",
              tokensUsed: 1000,
              estimatedCost: 0.3,
              content: "# Plan\n\nTest plan",
              filesToModify: ["file1.ts"],
              filesToCreate: [],
              steps: ["Step 1"],
              complexity: "medium",
              estimatedTokens: 5000,
            },
          },
        };
        yield {
          type: "state_change",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: { state: "awaiting_approval" },
        };
      }),
    };

    orchestrator = new Orchestrator({
      workspaceRoot: "/test/workspace",
      stateStore: mockStateStore,
      editorWorkflow: mockEditorWorkflow,
      architectWorkflow: mockArchitectWorkflow,
    });
  });

  describe("startTask", () => {
    it("should create a new session with editor mode", async () => {
      const input: TaskInput = {
        mode: "editor",
        message: "Test task",
        context: { files: ["test.ts"] },
      };

      const session = await orchestrator.startTask(input);

      expect(session.id).toMatch(/^sess_\d+_[a-f0-9]{6}$/);
      expect(session.mode).toBe("editor");
      expect(session.state).toBe("idle");
      expect(mockStateStore.saveSession).toHaveBeenCalled();
    });

    it("should create a new session with architect mode", async () => {
      const input: TaskInput = {
        mode: "architect",
        message: "Test task",
        context: { files: [] },
      };

      const session = await orchestrator.startTask(input);

      expect(session.mode).toBe("architect");
      expect(mockStateStore.saveSession).toHaveBeenCalled();
    });

    it("should generate unique session IDs", async () => {
      const input: TaskInput = {
        mode: "editor",
        message: "Test task",
        context: {},
      };

      const session1 = await orchestrator.startTask(input);
      const session2 = await orchestrator.startTask(input);

      expect(session1.id).not.toBe(session2.id);
    });
  });

  describe("approveTask", () => {
    it("should approve a pending plan", async () => {
      const input: TaskInput = {
        mode: "architect",
        message: "Test task",
        context: {},
      };

      const session = await orchestrator.startTask(input);

      // Wait a bit for workflow to reach awaiting_approval
      await new Promise((resolve) => setTimeout(resolve, 100));

      await orchestrator.approveTask(session.id);

      const updatedSession = await orchestrator.getSession(session.id);
      expect(updatedSession?.plan?.status).toBe("approved");
    });

    it("should throw error if session not found", async () => {
      expect(async () => {
        await orchestrator.approveTask("nonexistent");
      }).toThrow("Session not found");
    });
  });

  describe("rejectTask", () => {
    it("should reject a pending plan with feedback", async () => {
      const input: TaskInput = {
        mode: "architect",
        message: "Test task",
        context: {},
      };

      const session = await orchestrator.startTask(input);

      // Wait for workflow to reach awaiting_approval
      await new Promise((resolve) => setTimeout(resolve, 100));

      await orchestrator.rejectTask(session.id, "Not good enough");

      const updatedSession = await orchestrator.getSession(session.id);
      expect(updatedSession?.plan?.status).toBe("rejected");
      expect(updatedSession?.state).toBe("cancelled");
    });
  });

  describe("cancelTask", () => {
    it("should cancel an active task", async () => {
      const input: TaskInput = {
        mode: "editor",
        message: "Test task",
        context: {},
      };

      const session = await orchestrator.startTask(input);
      await orchestrator.cancelTask(session.id);

      const updatedSession = await orchestrator.getSession(session.id);
      expect(updatedSession?.state).toBe("cancelled");
    });
  });

  describe("getCurrentPhase", () => {
    it("should map researching state to research phase", async () => {
      const input: TaskInput = {
        mode: "architect",
        message: "Test task",
        context: {},
      };

      const session = await orchestrator.startTask(input);

      // Wait for workflow to start
      await new Promise((resolve) => setTimeout(resolve, 50));

      const phase = await orchestrator.getCurrentPhase(session.id);
      expect(["research", "planning"]).toContain(phase);
    });
  });

  describe("subscribeToUpdates", () => {
    it("should stream workflow updates", async () => {
      const input: TaskInput = {
        mode: "editor",
        message: "Test task",
        context: {},
      };

      const session = await orchestrator.startTask(input);
      const updates: unknown[] = [];

      // Subscribe to updates
      const subscription = orchestrator.subscribeToUpdates(session.id);

      for await (const update of subscription) {
        updates.push(update);
        if (update.type === "state_change" && update.data.state === "complete") {
          break;
        }
      }

      expect(updates.length).toBeGreaterThan(0);
      expect(updates.some((u) => u.type === "state_change")).toBe(true);
    });
  });
});
