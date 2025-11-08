// agent-core/tests/plan-store.test.ts
import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { PlanStore } from "../src/storage/plan-store";
import { Plan } from "../../shared/types/state";
import * as fs from "fs/promises";
import * as path from "path";
import * as os from "os";

describe("Plan Storage", () => {
  let testDir: string;
  let store: PlanStore;

  beforeEach(async () => {
    testDir = path.join(os.tmpdir(), `dolphin-test-${Date.now()}`);
    await fs.mkdir(testDir, { recursive: true });
    store = new PlanStore(testDir);
  });

  afterEach(async () => {
    await fs.rm(testDir, { recursive: true, force: true });
  });

  test("saves and loads plan", async () => {
    const plan: Plan = {
      schema_version: "1.0",
      plan: {
        id: "test-plan-1",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: "pending",
        mode: "architect",
        task: "Test task",
        workspace_root: testDir,
      },
      steps: [
        {
          id: "step-1",
          order: 1,
          description: "Test step",
          action_type: "tool_call",
          tool: "test_tool",
          status: "pending",
        },
      ],
    };

    await store.savePlan(plan);
    const loaded = await store.loadPlan("test-plan-1");

    expect(loaded).not.toBeNull();
    expect(loaded?.plan.id).toBe("test-plan-1");
    expect(loaded?.steps).toHaveLength(1);
  });

  test("atomic writes prevent corruption", async () => {
    const plan: Plan = {
      schema_version: "1.0",
      plan: {
        id: "test-plan-2",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: "pending",
        mode: "editor",
        task: "Concurrent test",
        workspace_root: testDir,
      },
      steps: [],
    };

    // Rapid concurrent writes
    await Promise.all([
      store.savePlan({ ...plan, plan: { ...plan.plan, task: "Task 1" } }),
      store.savePlan({ ...plan, plan: { ...plan.plan, task: "Task 2" } }),
      store.savePlan({ ...plan, plan: { ...plan.plan, task: "Task 3" } }),
    ]);

    // Should not corrupt
    const loaded = await store.loadPlan("test-plan-2");
    expect(loaded).not.toBeNull();
    expect(loaded?.plan.task).toBeTruthy();
  });

  test("lists all plans", async () => {
    // Create multiple plans
    for (let i = 1; i <= 3; i++) {
      const plan: Plan = {
        schema_version: "1.0",
        plan: {
          id: `plan-${i}`,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          status: "pending",
          mode: "architect",
          task: `Task ${i}`,
          workspace_root: testDir,
        },
        steps: [],
      };

      await store.savePlan(plan);
    }

    const plans = await store.listPlans();
    expect(plans).toHaveLength(3);
    expect(plans).toContain("plan-1");
    expect(plans).toContain("plan-2");
    expect(plans).toContain("plan-3");
  });

  test("deletes plan", async () => {
    const plan: Plan = {
      schema_version: "1.0",
      plan: {
        id: "deletable-plan",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: "pending",
        mode: "architect",
        task: "Delete me",
        workspace_root: testDir,
      },
      steps: [],
    };

    await store.savePlan(plan);
    expect(await store.loadPlan("deletable-plan")).not.toBeNull();

    await store.deletePlan("deletable-plan");
    expect(await store.loadPlan("deletable-plan")).toBeNull();
  });

  test("getLatestPlan returns most recent", async () => {
    // Create plans with different IDs (sorted alphabetically)
    const planIds = ["plan-a", "plan-b", "plan-c"];

    for (const id of planIds) {
      const plan: Plan = {
        schema_version: "1.0",
        plan: {
          id,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          status: "pending",
          mode: "architect",
          task: `Task ${id}`,
          workspace_root: testDir,
        },
        steps: [],
      };

      await store.savePlan(plan);
      // Small delay to ensure different timestamps
      await new Promise((resolve) => setTimeout(resolve, 10));
    }

    const latest = await store.getLatestPlan();
    expect(latest).not.toBeNull();
    expect(latest?.plan.id).toBe("plan-c"); // Last alphabetically
  });

  test("getLatestPlan returns null when no plans", async () => {
    const latest = await store.getLatestPlan();
    expect(latest).toBeNull();
  });

  test("validates plan schema on save", async () => {
    const invalidPlan = {
      plan: {
        id: "invalid",
        // Missing required fields
      },
      steps: [],
    } as any;

    await expect(store.savePlan(invalidPlan)).rejects.toThrow();
  });

  test("validates plan schema on load", async () => {
    // Manually write an invalid TOML file
    const invalidToml = `
[plan]
id = "invalid"
# Missing required fields like status, mode, task
`;

    const planPath = path.join(
      testDir,
      ".dolphin",
      "state",
      "plans",
      "invalid.toml"
    );
    await fs.mkdir(path.dirname(planPath), { recursive: true });
    await fs.writeFile(planPath, invalidToml, "utf-8");

    await expect(store.loadPlan("invalid")).rejects.toThrow();
  });

  test("updates timestamp on save", async () => {
    const plan: Plan = {
      schema_version: "1.0",
      plan: {
        id: "timestamp-test",
        created_at: "2024-01-01T00:00:00.000Z",
        updated_at: "2024-01-01T00:00:00.000Z",
        status: "pending",
        mode: "architect",
        task: "Timestamp test",
        workspace_root: testDir,
      },
      steps: [],
    };

    await store.savePlan(plan);
    const loaded = await store.loadPlan("timestamp-test");

    expect(loaded?.plan.updated_at).not.toBe("2024-01-01T00:00:00.000Z");
    expect(new Date(loaded!.plan.updated_at).getTime()).toBeGreaterThan(
      new Date("2024-01-01T00:00:00.000Z").getTime()
    );
  });

  test("handles complex plan with multiple steps", async () => {
    const plan: Plan = {
      schema_version: "1.0",
      plan: {
        id: "complex-plan",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: "executing",
        mode: "architect",
        task: "Complex multi-step task",
        workspace_root: testDir,
      },
      steps: [
        {
          id: "step-1",
          order: 1,
          description: "Read files",
          action_type: "tool_call",
          tool: "read_files",
          status: "completed",
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          input: { paths: ["src/main.ts"] },
          output: { files_read: 1 },
        },
        {
          id: "step-2",
          order: 2,
          description: "Generate plan",
          action_type: "llm_generation",
          status: "running",
          started_at: new Date().toISOString(),
        },
        {
          id: "step-3",
          order: 3,
          description: "Write file",
          action_type: "tool_call",
          tool: "file_write",
          status: "pending",
        },
      ],
    };

    await store.savePlan(plan);
    const loaded = await store.loadPlan("complex-plan");

    expect(loaded).not.toBeNull();
    expect(loaded?.steps).toHaveLength(3);
    expect(loaded?.steps[0].status).toBe("completed");
    expect(loaded?.steps[1].status).toBe("running");
    expect(loaded?.steps[2].status).toBe("pending");
    expect(loaded?.steps[0].output).toEqual({ files_read: 1 });
  });

  test("returns null for non-existent plan", async () => {
    const loaded = await store.loadPlan("does-not-exist");
    expect(loaded).toBeNull();
  });

  test("listPlans returns empty array when directory doesn't exist", async () => {
    const emptyStore = new PlanStore(
      path.join(os.tmpdir(), `dolphin-empty-${Date.now()}`)
    );
    const plans = await emptyStore.listPlans();
    expect(plans).toEqual([]);
  });
});