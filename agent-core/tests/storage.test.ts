// agent-core/tests/storage.test.ts
import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { PlanStore } from "../src/storage/plan-store";
import { ConversationStore } from "../src/storage/conversation-store";
import { Plan, Conversation } from "../../shared/types/state";
import * as fs from "fs/promises";
import * as path from "path";
import * as os from "os";

describe("Storage Integration", () => {
  let testDir: string;
  let planStore: PlanStore;
  let conversationStore: ConversationStore;

  beforeEach(async () => {
    testDir = path.join(os.tmpdir(), `dolphin-integration-test-${Date.now()}`);
    await fs.mkdir(testDir, { recursive: true });
    planStore = new PlanStore(testDir);
    conversationStore = new ConversationStore(testDir);
  });

  afterEach(async () => {
    await fs.rm(testDir, { recursive: true, force: true });
  });

  test("creates .dolphin directory structure", async () => {
    const plan: Plan = {
      schema_version: "1.0",
      plan: {
        id: "test-plan",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: "pending",
        mode: "architect",
        task: "Test task",
        workspace_root: testDir,
      },
      steps: [],
    };

    await planStore.savePlan(plan);

    // Check directory structure
    const dolphinDir = path.join(testDir, ".dolphin");
    const stateDir = path.join(dolphinDir, "state");
    const plansDir = path.join(stateDir, "plans");

    expect(await fs.access(dolphinDir).then(() => true).catch(() => false)).toBe(true);
    expect(await fs.access(stateDir).then(() => true).catch(() => false)).toBe(true);
    expect(await fs.access(plansDir).then(() => true).catch(() => false)).toBe(true);
  });

  test("plans and conversations are isolated", async () => {
    const plan: Plan = {
      schema_version: "1.0",
      plan: {
        id: "plan-1",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: "pending",
        mode: "architect",
        task: "Test",
        workspace_root: testDir,
      },
      steps: [],
    };

    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "conv-1",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      messages: [],
    };

    await planStore.savePlan(plan);
    await conversationStore.saveConversation(conversation);

    const plans = await planStore.listPlans();
    const conversations = await conversationStore.listConversations();

    expect(plans).toHaveLength(1);
    expect(conversations).toHaveLength(1);
    expect(plans[0]).toBe("plan-1");
    expect(conversations[0]).toBe("conv-1");
  });

  test("atomic writes prevent corruption across stores", async () => {
    const plan: Plan = {
      schema_version: "1.0",
      plan: {
        id: "plan-2",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: "pending",
        mode: "editor",
        task: "Concurrent test",
        workspace_root: testDir,
      },
      steps: [],
    };

    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "conv-2",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      messages: [],
    };

    // Concurrent writes to different stores
    await Promise.all([
      planStore.savePlan(plan),
      conversationStore.saveConversation(conversation),
      planStore.savePlan({ ...plan, plan: { ...plan.plan, task: "Updated 1" } }),
      conversationStore.saveConversation({
        ...conversation,
        messages: [
          {
            id: "msg-1",
            role: "user",
            content: "Test",
            timestamp: new Date().toISOString(),
          },
        ],
      }),
    ]);

    const loadedPlan = await planStore.loadPlan("plan-2");
    const loadedConv = await conversationStore.loadConversation("conv-2");

    expect(loadedPlan).not.toBeNull();
    expect(loadedConv).not.toBeNull();
    expect(loadedPlan?.plan.task).toBeTruthy();
  });

  test("handles rapid updates to same plan", async () => {
    const basePlan: Plan = {
      schema_version: "1.0",
      plan: {
        id: "rapid-plan",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: "pending",
        mode: "architect",
        task: "Initial task",
        workspace_root: testDir,
      },
      steps: [],
    };

    // Save initial
    await planStore.savePlan(basePlan);

    // Rapid updates
    for (let i = 1; i <= 10; i++) {
      await planStore.savePlan({
        ...basePlan,
        plan: { ...basePlan.plan, task: `Task ${i}` },
      });
    }

    const loaded = await planStore.loadPlan("rapid-plan");
    expect(loaded).not.toBeNull();
    expect(loaded?.plan.task).toBeTruthy();
  });

  test("loads plan with complex steps", async () => {
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
          description: "KB search",
          action_type: "tool_call",
          tool: "search_knowledge",
          status: "completed",
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          input: { query: "test", top_k: 5 },
          output: { hits: 3 },
        },
        {
          id: "step-2",
          order: 2,
          description: "Generate code",
          action_type: "llm_generation",
          status: "running",
          started_at: new Date().toISOString(),
        },
      ],
    };

    await planStore.savePlan(plan);
    const loaded = await planStore.loadPlan("complex-plan");

    expect(loaded?.steps).toHaveLength(2);
    expect(loaded?.steps[0].status).toBe("completed");
    expect(loaded?.steps[0].output).toEqual({ hits: 3 });
    expect(loaded?.steps[1].status).toBe("running");
  });

  test("loads conversation with messages and summaries", async () => {
    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "full-conv",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      messages: [
        {
          id: "msg-1",
          role: "user",
          content: "Create a new feature",
          timestamp: new Date().toISOString(),
          pinned: true,
        },
        {
          id: "msg-2",
          role: "assistant",
          content: "I'll help with that",
          timestamp: new Date().toISOString(),
        },
      ],
      summaries: [
        {
          range_start: 0,
          range_end: 1,
          key_points: ["Feature request", "Initial response"],
          created_at: new Date().toISOString(),
        },
      ],
    };

    await conversationStore.saveConversation(conversation);
    const loaded = await conversationStore.loadConversation("full-conv");

    expect(loaded?.messages).toHaveLength(2);
    expect(loaded?.messages[0].pinned).toBe(true);
    expect(loaded?.summaries).toHaveLength(1);
    expect(loaded?.summaries?.[0].key_points).toHaveLength(2);
  });

  test("updates preserve data integrity", async () => {
    const plan: Plan = {
      schema_version: "1.0",
      plan: {
        id: "update-plan",
        created_at: "2024-01-01T00:00:00.000Z",
        updated_at: "2024-01-01T00:00:00.000Z",
        status: "pending",
        mode: "architect",
        task: "Initial task",
        workspace_root: testDir,
      },
      steps: [
        {
          id: "step-1",
          order: 1,
          description: "Step 1",
          action_type: "tool_call",
          status: "pending",
        },
      ],
    };

    await planStore.savePlan(plan);

    // Update plan
    const updatedPlan = {
      ...plan,
      plan: { ...plan.plan, status: "executing" as const },
      steps: [
        {
          ...plan.steps[0],
          status: "completed" as const,
          completed_at: new Date().toISOString(),
        },
      ],
    };

    await planStore.savePlan(updatedPlan);

    const loaded = await planStore.loadPlan("update-plan");

    expect(loaded?.plan.status).toBe("executing");
    expect(loaded?.steps[0].status).toBe("completed");
    expect(loaded?.steps[0].completed_at).toBeTruthy();
    expect(loaded?.plan.updated_at).not.toBe("2024-01-01T00:00:00.000Z");
  });

  test("deleted items don't affect other items", async () => {
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
      await planStore.savePlan(plan);
    }

    // Delete middle plan
    await planStore.deletePlan("plan-2");

    const plans = await planStore.listPlans();
    expect(plans).toHaveLength(2);
    expect(plans).toContain("plan-1");
    expect(plans).not.toContain("plan-2");
    expect(plans).toContain("plan-3");

    // Verify remaining plans are intact
    const plan1 = await planStore.loadPlan("plan-1");
    const plan3 = await planStore.loadPlan("plan-3");

    expect(plan1?.plan.task).toBe("Task 1");
    expect(plan3?.plan.task).toBe("Task 3");
  });

  test("handles empty workspace gracefully", async () => {
    const plans = await planStore.listPlans();
    const conversations = await conversationStore.listConversations();

    expect(plans).toEqual([]);
    expect(conversations).toEqual([]);

    const latestPlan = await planStore.getLatestPlan();
    const latestConv = await conversationStore.getLatestConversation();

    expect(latestPlan).toBeNull();
    expect(latestConv).toBeNull();
  });

  test("workspace root is respected", async () => {
    const plan: Plan = {
      schema_version: "1.0",
      plan: {
        id: "workspace-test",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: "pending",
        mode: "architect",
        task: "Test",
        workspace_root: testDir,
      },
      steps: [],
    };

    await planStore.savePlan(plan);

    // Verify file is in correct location
    const expectedPath = path.join(
      testDir,
      ".dolphin",
      "state",
      "plans",
      "workspace-test.toml"
    );

    const exists = await fs
      .access(expectedPath)
      .then(() => true)
      .catch(() => false);

    expect(exists).toBe(true);

    const loaded = await planStore.loadPlan("workspace-test");
    expect(loaded?.plan.workspace_root).toBe(testDir);
  });
});