// agent-core/tests/conversation-store.test.ts
import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { ConversationStore } from "../src/storage/conversation-store";
import { Conversation } from "../../shared/types/state";
import * as fs from "fs/promises";
import * as path from "path";
import * as os from "os";

describe("Conversation Storage", () => {
  let testDir: string;
  let store: ConversationStore;

  beforeEach(async () => {
    testDir = path.join(os.tmpdir(), `dolphin-conv-test-${Date.now()}`);
    await fs.mkdir(testDir, { recursive: true });
    store = new ConversationStore(testDir);
  });

  afterEach(async () => {
    await fs.rm(testDir, { recursive: true, force: true });
  });

  test("saves and loads conversation", async () => {
    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "conv-1",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      messages: [
        {
          id: "msg-1",
          role: "user",
          content: "Hello",
          timestamp: new Date().toISOString(),
        },
        {
          id: "msg-2",
          role: "assistant",
          content: "Hi there!",
          timestamp: new Date().toISOString(),
        },
      ],
    };

    await store.saveConversation(conversation);
    const loaded = await store.loadConversation("conv-1");

    expect(loaded).not.toBeNull();
    expect(loaded?.conversation.id).toBe("conv-1");
    expect(loaded?.messages).toHaveLength(2);
    expect(loaded?.messages[0].role).toBe("user");
    expect(loaded?.messages[1].role).toBe("assistant");
  });

  test("atomic writes prevent corruption", async () => {
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

    // Rapid concurrent writes
    await Promise.all([
      store.saveConversation({
        ...conversation,
        messages: [
          {
            id: "msg-1",
            role: "user",
            content: "Test 1",
            timestamp: new Date().toISOString(),
          },
        ],
      }),
      store.saveConversation({
        ...conversation,
        messages: [
          {
            id: "msg-2",
            role: "user",
            content: "Test 2",
            timestamp: new Date().toISOString(),
          },
        ],
      }),
      store.saveConversation({
        ...conversation,
        messages: [
          {
            id: "msg-3",
            role: "user",
            content: "Test 3",
            timestamp: new Date().toISOString(),
          },
        ],
      }),
    ]);

    // Should not corrupt
    const loaded = await store.loadConversation("conv-2");
    expect(loaded).not.toBeNull();
    expect(loaded?.messages).toHaveLength(1);
    expect(loaded?.messages[0].content).toBeTruthy();
  });

  test("lists all conversations", async () => {
    for (let i = 1; i <= 3; i++) {
      const conversation: Conversation = {
        schema_version: "1.0",
        conversation: {
          id: `conv-${i}`,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          workspace_root: testDir,
        },
        messages: [],
      };

      await store.saveConversation(conversation);
    }

    const conversations = await store.listConversations();
    expect(conversations).toHaveLength(3);
    expect(conversations).toContain("conv-1");
    expect(conversations).toContain("conv-2");
    expect(conversations).toContain("conv-3");
  });

  test("deletes conversation", async () => {
    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "deletable-conv",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      messages: [],
    };

    await store.saveConversation(conversation);
    expect(await store.loadConversation("deletable-conv")).not.toBeNull();

    await store.deleteConversation("deletable-conv");
    expect(await store.loadConversation("deletable-conv")).toBeNull();
  });

  test("getLatestConversation returns most recent", async () => {
    const convIds = ["conv-a", "conv-b", "conv-c"];

    for (const id of convIds) {
      const conversation: Conversation = {
        schema_version: "1.0",
        conversation: {
          id,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          workspace_root: testDir,
        },
        messages: [],
      };

      await store.saveConversation(conversation);
      await new Promise((resolve) => setTimeout(resolve, 10));
    }

    const latest = await store.getLatestConversation();
    expect(latest).not.toBeNull();
    expect(latest?.conversation.id).toBe("conv-c");
  });

  test("getLatestConversation returns null when no conversations", async () => {
    const latest = await store.getLatestConversation();
    expect(latest).toBeNull();
  });

  test("validates conversation schema on save", async () => {
    const invalidConversation = {
      conversation: {
        id: "invalid",
        // Missing required fields
      },
      messages: [],
    } as any;

    await expect(store.saveConversation(invalidConversation)).rejects.toThrow();
  });

  test("validates conversation schema on load", async () => {
    const invalidToml = `
[conversation]
id = "invalid"
# Missing required fields
`;

    const convPath = path.join(
      testDir,
      ".dolphin",
      "state",
      "conversations",
      "invalid.toml"
    );
    await fs.mkdir(path.dirname(convPath), { recursive: true });
    await fs.writeFile(convPath, invalidToml, "utf-8");

    await expect(store.loadConversation("invalid")).rejects.toThrow();
  });

  test("updates timestamp on save", async () => {
    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "timestamp-test",
        created_at: "2024-01-01T00:00:00.000Z",
        updated_at: "2024-01-01T00:00:00.000Z",
        workspace_root: testDir,
      },
      messages: [],
    };

    await store.saveConversation(conversation);
    const loaded = await store.loadConversation("timestamp-test");

    expect(loaded?.conversation.updated_at).not.toBe(
      "2024-01-01T00:00:00.000Z"
    );
    expect(
      new Date(loaded!.conversation.updated_at).getTime()
    ).toBeGreaterThan(new Date("2024-01-01T00:00:00.000Z").getTime());
  });

  test("handles conversation with pinned messages", async () => {
    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "pinned-test",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      messages: [
        {
          id: "msg-1",
          role: "user",
          content: "Important message",
          timestamp: new Date().toISOString(),
          pinned: true,
        },
        {
          id: "msg-2",
          role: "assistant",
          content: "Regular message",
          timestamp: new Date().toISOString(),
        },
      ],
    };

    await store.saveConversation(conversation);
    const loaded = await store.loadConversation("pinned-test");

    expect(loaded?.messages[0].pinned).toBe(true);
    expect(loaded?.messages[1].pinned).toBeUndefined();
  });

  test("handles conversation with summaries", async () => {
    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "summary-test",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      messages: [
        {
          id: "msg-1",
          role: "user",
          content: "Message 1",
          timestamp: new Date().toISOString(),
        },
        {
          id: "msg-2",
          role: "assistant",
          content: "Message 2",
          timestamp: new Date().toISOString(),
        },
      ],
      summaries: [
        {
          range_start: 0,
          range_end: 1,
          key_points: ["Discussed topic A", "Decided on approach B"],
          created_at: new Date().toISOString(),
        },
      ],
    };

    await store.saveConversation(conversation);
    const loaded = await store.loadConversation("summary-test");

    expect(loaded?.summaries).toHaveLength(1);
    expect(loaded?.summaries?.[0].key_points).toHaveLength(2);
    expect(loaded?.summaries?.[0].range_start).toBe(0);
    expect(loaded?.summaries?.[0].range_end).toBe(1);
  });

  test("handles long conversation", async () => {
    const messages = [];
    for (let i = 1; i <= 100; i++) {
      messages.push({
        id: `msg-${i}`,
        role: i % 2 === 1 ? ("user" as const) : ("assistant" as const),
        content: `Message ${i}`,
        timestamp: new Date().toISOString(),
      });
    }

    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "long-conv",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      messages,
    };

    await store.saveConversation(conversation);
    const loaded = await store.loadConversation("long-conv");

    expect(loaded?.messages).toHaveLength(100);
    expect(loaded?.messages[0].content).toBe("Message 1");
    expect(loaded?.messages[99].content).toBe("Message 100");
  });

  test("returns null for non-existent conversation", async () => {
    const loaded = await store.loadConversation("does-not-exist");
    expect(loaded).toBeNull();
  });

  test("listConversations returns empty array when directory doesn't exist", async () => {
    const emptyStore = new ConversationStore(
      path.join(os.tmpdir(), `dolphin-empty-${Date.now()}`)
    );
    const conversations = await emptyStore.listConversations();
    expect(conversations).toEqual([]);
  });
});