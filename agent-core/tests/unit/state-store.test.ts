/**
 * Unit tests for StateStore
 */

import { describe, it, expect, beforeEach, afterEach } from "bun:test";
import { StateStore } from "../../src/state/state-store";
import { rm, mkdtemp } from "fs/promises";
import { tmpdir } from "os";
import { join } from "path";
import type { TaskSession } from "../../src/types/index";

describe("StateStore", () => {
  let stateStore: StateStore;
  let testStoragePath: string;

  beforeEach(async () => {
    // Create temporary directory in OS temp location
    testStoragePath = await mkdtemp(join(tmpdir(), "dolphin-test-"));
    stateStore = new StateStore({ storagePath: testStoragePath });
  });

  afterEach(async () => {
    // Clean up temporary test directory
    try {
      await rm(testStoragePath, { recursive: true, force: true });
    } catch {}
  });

  describe("saveSession", () => {
    it("should save a session to disk", async () => {
      const session: TaskSession = {
        id: "sess_test_123",
        mode: "editor",
        state: "idle",
        input: {
          mode: "editor",
          message: "Test message",
          context: { files: ["test.ts"] },
        },
        metadata: {
          tokensUsed: 0,
          estimatedCost: 0,
          startedAt: new Date().toISOString(),
        },
      };

      await stateStore.saveSession(session);

      const loaded = await stateStore.loadSession("sess_test_123");
      expect(loaded).not.toBeNull();
      expect(loaded?.id).toBe("sess_test_123");
      expect(loaded?.mode).toBe("editor");
    });

    it("should save session with plan", async () => {
      const session: TaskSession = {
        id: "sess_test_456",
        mode: "architect",
        state: "awaiting_approval",
        input: {
          mode: "architect",
          message: "Test message",
          context: {},
        },
        plan: {
          version: 1,
          status: "pending_approval",
          createdAt: new Date().toISOString(),
          model: "claude-opus-4-20250514",
          tokensUsed: 1000,
          estimatedCost: 0.3,
          content: "# Test Plan",
          filesToModify: ["file1.ts"],
          filesToCreate: ["file2.ts"],
          steps: ["Step 1", "Step 2"],
          complexity: "medium",
          estimatedTokens: 5000,
        },
        metadata: {
          tokensUsed: 1000,
          estimatedCost: 0.3,
          startedAt: new Date().toISOString(),
        },
      };

      await stateStore.saveSession(session);

      const loaded = await stateStore.loadSession("sess_test_456");
      expect(loaded?.plan).toBeDefined();
      expect(loaded?.plan?.version).toBe(1);
    });
  });

  describe("loadSession", () => {
    it("should return null for non-existent session", async () => {
      const loaded = await stateStore.loadSession("nonexistent");
      expect(loaded).toBeNull();
    });

    it("should load saved session correctly", async () => {
      const session: TaskSession = {
        id: "sess_test_789",
        mode: "editor",
        state: "complete",
        input: {
          mode: "editor",
          message: "Test",
          context: {},
        },
        metadata: {
          tokensUsed: 500,
          estimatedCost: 0.05,
          startedAt: new Date().toISOString(),
          completedAt: new Date().toISOString(),
        },
      };

      await stateStore.saveSession(session);
      const loaded = await stateStore.loadSession("sess_test_789");

      expect(loaded?.id).toBe("sess_test_789");
      expect(loaded?.state).toBe("complete");
      expect(loaded?.metadata.tokensUsed).toBe(500);
    });
  });

  describe("savePlan", () => {
    it("should save plan content as markdown", async () => {
      const session: TaskSession = {
        id: "sess_plan_test",
        mode: "architect",
        state: "planning",
        input: {
          mode: "architect",
          message: "Test",
          context: {},
        },
        metadata: {
          tokensUsed: 0,
          estimatedCost: 0,
          startedAt: new Date().toISOString(),
        },
      };

      await stateStore.saveSession(session);

      const plan = {
        version: 1,
        status: "pending_approval" as const,
        createdAt: new Date().toISOString(),
        model: "claude-opus-4-20250514",
        tokensUsed: 1500,
        estimatedCost: 0.45,
        content: "# Implementation Plan\n\n## Overview\n\nTest plan content",
        filesToModify: ["src/test.ts"],
        filesToCreate: [],
        steps: ["Implement feature"],
        complexity: "medium" as const,
        estimatedTokens: 8000,
      };

      await stateStore.savePlan("sess_plan_test", plan);

      const loadedPlan = await stateStore.loadPlan("sess_plan_test");
      expect(loadedPlan).not.toBeNull();
      expect(loadedPlan?.content).toContain("Implementation Plan");
    });
  });

  describe("listSessions", () => {
    it("should return empty array when no sessions exist", async () => {
      const sessions = await stateStore.listSessions();
      expect(sessions).toEqual([]);
    });

    it("should list all saved sessions", async () => {
      const session1: TaskSession = {
        id: "sess_1",
        mode: "editor",
        state: "complete",
        input: {
          mode: "editor",
          message: "First",
          context: {},
        },
        metadata: {
          tokensUsed: 100,
          estimatedCost: 0.01,
          startedAt: new Date().toISOString(),
        },
      };

      const session2: TaskSession = {
        id: "sess_2",
        mode: "architect",
        state: "complete",
        input: {
          mode: "architect",
          message: "Second",
          context: {},
        },
        metadata: {
          tokensUsed: 200,
          estimatedCost: 0.02,
          startedAt: new Date().toISOString(),
        },
      };

      await stateStore.saveSession(session1);
      await stateStore.saveSession(session2);

      const sessions = await stateStore.listSessions();
      expect(sessions.length).toBe(2);
      expect(sessions.map((s) => s.id).sort()).toEqual(["sess_1", "sess_2"]);
    });

    it("should sort sessions by most recent first", async () => {
      const now = Date.now();

      const session1: TaskSession = {
        id: "sess_old",
        mode: "editor",
        state: "complete",
        input: {
          mode: "editor",
          message: "Old",
          context: {},
        },
        metadata: {
          tokensUsed: 100,
          estimatedCost: 0.01,
          startedAt: new Date(now - 10000).toISOString(),
          completedAt: new Date(now - 9000).toISOString(),
        },
      };

      const session2: TaskSession = {
        id: "sess_new",
        mode: "editor",
        state: "complete",
        input: {
          mode: "editor",
          message: "New",
          context: {},
        },
        metadata: {
          tokensUsed: 100,
          estimatedCost: 0.01,
          startedAt: new Date(now - 1000).toISOString(),
          completedAt: new Date(now).toISOString(),
        },
      };

      await stateStore.saveSession(session1);
      await stateStore.saveSession(session2);

      const sessions = await stateStore.listSessions();
      expect(sessions[0].id).toBe("sess_new");
      expect(sessions[1].id).toBe("sess_old");
    });
  });

  describe("deleteSession", () => {
    it("should delete session and associated plans", async () => {
      const session: TaskSession = {
        id: "sess_delete_test",
        mode: "architect",
        state: "complete",
        input: {
          mode: "architect",
          message: "Test",
          context: {},
        },
        metadata: {
          tokensUsed: 0,
          estimatedCost: 0,
          startedAt: new Date().toISOString(),
        },
      };

      await stateStore.saveSession(session);

      const plan = {
        version: 1,
        status: "approved" as const,
        createdAt: new Date().toISOString(),
        model: "claude-opus-4-20250514",
        tokensUsed: 1000,
        estimatedCost: 0.3,
        content: "# Plan",
        filesToModify: [],
        filesToCreate: [],
        steps: [],
        complexity: "low" as const,
        estimatedTokens: 5000,
      };

      await stateStore.savePlan("sess_delete_test", plan);

      await stateStore.deleteSession("sess_delete_test");

      const loaded = await stateStore.loadSession("sess_delete_test");
      expect(loaded).toBeNull();
    });
  });

  describe("getStats", () => {
    it("should return storage statistics", async () => {
      const session: TaskSession = {
        id: "sess_stats_test",
        mode: "editor",
        state: "complete",
        input: {
          mode: "editor",
          message: "Test",
          context: {},
        },
        metadata: {
          tokensUsed: 100,
          estimatedCost: 0.01,
          startedAt: new Date().toISOString(),
        },
      };

      await stateStore.saveSession(session);

      const stats = await stateStore.getStats();
      expect(stats.totalSessions).toBe(1);
      expect(stats.storageSize).toBeGreaterThan(0);
    });
  });
});
