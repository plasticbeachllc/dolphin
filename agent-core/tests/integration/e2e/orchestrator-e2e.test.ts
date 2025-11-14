/**
 * End-to-end integration tests for Orchestrator
 *
 * Tests full workflow execution with state management and persistence
 */

import { describe, it, expect, beforeEach, mock } from "bun:test";
import { Orchestrator } from "../../../src/orchestrator/orchestrator";
import type { TaskInput, TaskSession, WorkflowUpdate } from "../../../src/types/index";

describe("Orchestrator End-to-End", () => {
  let orchestrator: Orchestrator;
  let mockStateStore: unknown;
  let mockEditorWorkflow: unknown;
  let mockArchitectWorkflow: unknown;

  beforeEach(() => {
    // Mock StateStore
    mockStateStore = {
      saveSession: mock(async (session: TaskSession) => {
        console.log("[Test] Saving session:", session.id);
      }),
      loadSession: mock(async (_sessionId: string) => null),
      savePlan: mock(async () => {}),
      loadPlan: mock(async () => null),
    };

    // Mock EditorWorkflow
    mockEditorWorkflow = {
      execute: mock(async function* (_input: TaskInput): AsyncIterableIterator<WorkflowUpdate> {
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
          data: { type: "text", content: "Working on it..." },
        };

        // Simulate some work
        await new Promise((resolve) => setTimeout(resolve, 50));

        yield {
          type: "state_change",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: { state: "complete" },
        };
      }),
    };

    // Mock ArchitectWorkflow with full planning cycle
    mockArchitectWorkflow = {
      execute: mock(async function* (_input: TaskInput): AsyncIterableIterator<WorkflowUpdate> {
        // Research phase
        yield {
          type: "state_change",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: { state: "researching" },
        };

        await new Promise((resolve) => setTimeout(resolve, 50));

        yield {
          type: "progress",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: {
            phase: "research",
            result: {
              findings: "Found relevant files",
              relevantFiles: ["file1.ts", "file2.ts"],
              kbSearches: [{ query: "test", resultsCount: 5 }],
            },
          },
        };

        // Planning phase
        yield {
          type: "state_change",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: { state: "planning" },
        };

        await new Promise((resolve) => setTimeout(resolve, 50));

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
              tokensUsed: 1500,
              estimatedCost: 0.45,
              content: "# Implementation Plan\n\nDetailed plan here...",
              filesToModify: ["file1.ts"],
              filesToCreate: ["file2.ts"],
              steps: ["Step 1", "Step 2"],
              complexity: "medium",
              estimatedTokens: 8000,
            },
          },
        };

        // Await approval
        yield {
          type: "state_change",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: { state: "awaiting_approval" },
        };

        // Note: Workflow will block here until approval
        // Tests must call approveTask() to continue
      }),
    };

    orchestrator = new Orchestrator({
      workspaceRoot: "/test/workspace",
      stateStore: mockStateStore,
      editorWorkflow: mockEditorWorkflow,
      architectWorkflow: mockArchitectWorkflow,
    });
  });

  describe("Editor Mode Flow", () => {
    it("should complete editor mode task end-to-end", async () => {
      const input: TaskInput = {
        mode: "editor",
        message: "Add a comment to the file",
        context: { files: ["test.ts"] },
      };

      // Start task
      const session = await orchestrator.startTask(input);
      expect(session.id).toBeDefined();
      expect(session.mode).toBe("editor");
      expect(session.state).toBe("idle");

      // Subscribe to updates
      const updates: WorkflowUpdate[] = [];
      const subscription = orchestrator.subscribeToUpdates(session.id);

      for await (const update of subscription) {
        updates.push(update);

        if (update.type === "state_change" && update.data.state === "complete") {
          break;
        }
      }

      // Verify workflow progression
      expect(updates.length).toBeGreaterThan(0);

      // Should have executing state
      const executingUpdate = updates.find(
        (u) => u.type === "state_change" && u.data.state === "executing"
      );
      expect(executingUpdate).toBeDefined();

      // Should have complete state
      const completeUpdate = updates.find(
        (u) => u.type === "state_change" && u.data.state === "complete"
      );
      expect(completeUpdate).toBeDefined();

      // Session should be persisted
      expect(mockStateStore.saveSession).toHaveBeenCalled();
    });

    it("should handle cancellation", async () => {
      const input: TaskInput = {
        mode: "editor",
        message: "Task to cancel",
        context: {},
      };

      const session = await orchestrator.startTask(input);

      // Cancel immediately
      await orchestrator.cancelTask(session.id);

      // Check session state
      const updatedSession = await orchestrator.getSession(session.id);
      expect(updatedSession?.state).toBe("cancelled");
    });

    it("should track multiple concurrent sessions", async () => {
      const input1: TaskInput = {
        mode: "editor",
        message: "Task 1",
        context: {},
      };

      const input2: TaskInput = {
        mode: "editor",
        message: "Task 2",
        context: {},
      };

      const session1 = await orchestrator.startTask(input1);
      const session2 = await orchestrator.startTask(input2);

      expect(session1.id).not.toBe(session2.id);

      // Both should be tracked
      const retrieved1 = await orchestrator.getSession(session1.id);
      const retrieved2 = await orchestrator.getSession(session2.id);

      expect(retrieved1).toBeDefined();
      expect(retrieved2).toBeDefined();
    });
  });

  describe("Architect Mode Flow", () => {
    it("should reach awaiting_approval state", async () => {
      const input: TaskInput = {
        mode: "architect",
        message: "Add authentication to the API",
        context: { files: ["api.ts"] },
      };

      const session = await orchestrator.startTask(input);

      // Subscribe to updates
      const updates: WorkflowUpdate[] = [];
      const subscription = orchestrator.subscribeToUpdates(session.id);

      // Collect updates until awaiting_approval
      const updatePromise = (async () => {
        for await (const update of subscription) {
          updates.push(update);

          if (update.type === "state_change" && update.data.state === "awaiting_approval") {
            break;
          }
        }
      })();

      // Wait for approval state
      await updatePromise;

      // Verify progression
      const researchUpdate = updates.find(
        (u) => u.type === "state_change" && u.data.state === "researching"
      );
      expect(researchUpdate).toBeDefined();

      const planningUpdate = updates.find(
        (u) => u.type === "state_change" && u.data.state === "planning"
      );
      expect(planningUpdate).toBeDefined();

      const approvalUpdate = updates.find(
        (u) => u.type === "state_change" && u.data.state === "awaiting_approval"
      );
      expect(approvalUpdate).toBeDefined();

      // Should have plan
      const planProgress = updates.find(
        (u) => u.type === "progress" && u.data.phase === "planning"
      );
      expect(planProgress).toBeDefined();
      expect(planProgress?.data.plan).toBeDefined();
    });

    it("should handle plan approval", async () => {
      const input: TaskInput = {
        mode: "architect",
        message: "Implement feature",
        context: {},
      };

      const session = await orchestrator.startTask(input);

      // Wait for awaiting_approval state
      await new Promise((resolve) => setTimeout(resolve, 200));

      // Approve the plan
      await orchestrator.approveTask(session.id);

      // Verify plan status
      const updatedSession = await orchestrator.getSession(session.id);
      expect(updatedSession?.plan?.status).toBe("approved");
      expect(updatedSession?.plan?.approvedAt).toBeDefined();
    });

    it("should handle plan rejection", async () => {
      const input: TaskInput = {
        mode: "architect",
        message: "Implement feature",
        context: {},
      };

      const session = await orchestrator.startTask(input);

      // Wait for awaiting_approval state
      await new Promise((resolve) => setTimeout(resolve, 200));

      // Reject the plan
      await orchestrator.rejectTask(session.id, "Plan is incomplete");

      // Verify session state
      const updatedSession = await orchestrator.getSession(session.id);
      expect(updatedSession?.state).toBe("cancelled");
      expect(updatedSession?.plan?.status).toBe("rejected");
      expect(updatedSession?.plan?.revisions?.length).toBe(1);
      expect(updatedSession?.plan?.revisions?.[0].rejectedReason).toBe("Plan is incomplete");
    });

    it("should handle plan revision request", async () => {
      const input: TaskInput = {
        mode: "architect",
        message: "Implement feature",
        context: {},
      };

      const session = await orchestrator.startTask(input);

      // Wait for awaiting_approval state
      await new Promise((resolve) => setTimeout(resolve, 200));

      // Request revision
      await orchestrator.revisePlan(session.id, "Add error handling");

      // Verify session state
      const updatedSession = await orchestrator.getSession(session.id);
      expect(updatedSession?.state).toBe("plan_revision");
      expect(updatedSession?.plan?.status).toBe("rejected");
      expect(updatedSession?.plan?.revisions?.length).toBe(1);
      expect(updatedSession?.plan?.revisions?.[0].rejectedReason).toBe("Add error handling");
    });
  });

  describe("State Persistence", () => {
    it("should persist session on creation", async () => {
      const input: TaskInput = {
        mode: "editor",
        message: "Test persistence",
        context: {},
      };

      await orchestrator.startTask(input);

      expect(mockStateStore.saveSession).toHaveBeenCalled();
    });

    it("should persist plan when generated", async () => {
      const input: TaskInput = {
        mode: "architect",
        message: "Generate plan",
        context: {},
      };

      const _session = await orchestrator.startTask(input);

      // Wait for plan to be generated
      await new Promise((resolve) => setTimeout(resolve, 200));

      expect(mockStateStore.savePlan).toHaveBeenCalled();
    });

    it("should persist session after approval", async () => {
      const input: TaskInput = {
        mode: "architect",
        message: "Test approval persistence",
        context: {},
      };

      const session = await orchestrator.startTask(input);

      // Wait for awaiting_approval
      await new Promise((resolve) => setTimeout(resolve, 200));

      // Reset mock call count
      mockStateStore.saveSession.mockClear();

      // Approve
      await orchestrator.approveTask(session.id);

      // Should persist after approval
      expect(mockStateStore.saveSession).toHaveBeenCalled();
    });
  });

  describe("Error Handling", () => {
    it("should handle workflow errors gracefully", async () => {
      // Mock workflow to throw error
      mockEditorWorkflow.execute = mock(async function* () {
        yield {
          type: "state_change",
          sessionId: "test",
          timestamp: new Date().toISOString(),
          data: { state: "executing" },
        };

        throw new Error("Workflow execution failed");
      });

      const input: TaskInput = {
        mode: "editor",
        message: "This will fail",
        context: {},
      };

      const session = await orchestrator.startTask(input);

      // Wait for error to propagate
      await new Promise((resolve) => setTimeout(resolve, 100));

      // Session should be in error state
      const updatedSession = await orchestrator.getSession(session.id);
      expect(updatedSession?.state).toBe("error");
    });

    it("should throw error for invalid session operations", async () => {
      await expect(async () => {
        await orchestrator.approveTask("nonexistent-session");
      }).toThrow("Session not found");

      await expect(async () => {
        await orchestrator.rejectTask("nonexistent-session");
      }).toThrow("Session not found");

      await expect(async () => {
        await orchestrator.cancelTask("nonexistent-session");
      }).toThrow("Session not found");
    });

    it("should throw error for invalid state transitions", async () => {
      const input: TaskInput = {
        mode: "editor",
        message: "Test invalid transition",
        context: {},
      };

      const session = await orchestrator.startTask(input);

      // Cannot approve an editor mode task
      await expect(async () => {
        await orchestrator.approveTask(session.id);
      }).toThrow(/not awaiting approval/);
    });
  });

  describe("Phase Tracking", () => {
    it("should correctly map states to phases", async () => {
      const input: TaskInput = {
        mode: "architect",
        message: "Track phases",
        context: {},
      };

      const session = await orchestrator.startTask(input);

      // Wait for researching state
      await new Promise((resolve) => setTimeout(resolve, 100));

      const phase = await orchestrator.getCurrentPhase(session.id);
      expect(["research", "planning"]).toContain(phase);
    });
  });

  describe("Event Streaming", () => {
    it("should stream all workflow events", async () => {
      const input: TaskInput = {
        mode: "editor",
        message: "Stream events",
        context: {},
      };

      const session = await orchestrator.startTask(input);
      const events: WorkflowUpdate[] = [];

      const subscription = orchestrator.subscribeToUpdates(session.id);

      for await (const update of subscription) {
        events.push(update);

        if (update.type === "state_change" && update.data.state === "complete") {
          break;
        }
      }

      // Should have received multiple events
      expect(events.length).toBeGreaterThan(2);

      // Should have state changes
      const stateChanges = events.filter((e) => e.type === "state_change");
      expect(stateChanges.length).toBeGreaterThan(0);

      // Should have chunks
      const chunks = events.filter((e) => e.type === "chunk");
      expect(chunks.length).toBeGreaterThan(0);
    });
  });
});
