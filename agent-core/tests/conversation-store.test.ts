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

  // Phase 5: Metadata Management Tests

  test("updateMetadata updates specific fields", async () => {
    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "metadata-test",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      metadata: {
        title: "Original Title",
        files: ["file1.ts"],
        token_count: 100,
        pinned: false,
      },
      messages: [],
    };

    await store.saveConversation(conversation);

    // Update only title
    await store.updateMetadata("metadata-test", {
      title: "Updated Title",
      pinned: true,
    });

    const loaded = await store.loadConversation("metadata-test");
    expect(loaded?.metadata?.title).toBe("Updated Title");
    expect(loaded?.metadata?.pinned).toBe(true);
    expect(loaded?.metadata?.files).toEqual(["file1.ts"]); // Unchanged
    expect(loaded?.metadata?.token_count).toBe(100); // Unchanged
  });

  test("updateMetadata throws error for non-existent conversation", async () => {
    await expect(
      store.updateMetadata("does-not-exist", { title: "New Title" })
    ).rejects.toThrow("Conversation not found");
  });

  test("updateMetadata handles partial metadata updates", async () => {
    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "partial-update",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      metadata: {
        title: "Title",
        files: [],
        token_count: 0,
        pinned: false,
      },
      messages: [],
    };

    await store.saveConversation(conversation);

    // Update only token count
    await store.updateMetadata("partial-update", {
      token_count: 500,
    });

    const loaded = await store.loadConversation("partial-update");
    expect(loaded?.metadata?.token_count).toBe(500);
    expect(loaded?.metadata?.title).toBe("Title"); // Unchanged
  });

  test("listConversationsWithMetadata returns enriched conversation list", async () => {
    const conversations = [
      {
        id: "conv-meta-1",
        title: "First Conversation",
        messageCount: 2,
      },
      {
        id: "conv-meta-2",
        title: "Second Conversation",
        messageCount: 5,
      },
      {
        id: "conv-meta-3",
        title: "Third Conversation",
        messageCount: 0,
      },
    ];

    for (const conv of conversations) {
      const messages = [];
      for (let i = 0; i < conv.messageCount; i++) {
        messages.push({
          id: `msg-${i}`,
          role: i % 2 === 0 ? ("user" as const) : ("assistant" as const),
          content: `Message ${i}`,
          timestamp: new Date().toISOString(),
        });
      }

      const conversation: Conversation = {
        schema_version: "1.0",
        conversation: {
          id: conv.id,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          workspace_root: testDir,
        },
        metadata: {
          title: conv.title,
          files: [],
          token_count: 0,
          pinned: false,
        },
        messages,
      };

      await store.saveConversation(conversation);
    }

    const list = await store.listConversationsWithMetadata();

    expect(list).toHaveLength(3);
    expect(list[0].id).toBe("conv-meta-1");
    expect(list[0].metadata.title).toBe("First Conversation");
    expect(list[0].message_count).toBe(2);
    expect(list[1].message_count).toBe(5);
    expect(list[2].message_count).toBe(0);
  });

  test("listConversationsWithMetadata handles conversations without metadata", async () => {
    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "no-metadata",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      messages: [],
    };

    await store.saveConversation(conversation);

    const list = await store.listConversationsWithMetadata();

    expect(list).toHaveLength(1);
    expect(list[0].metadata).toBeDefined();
    expect(list[0].metadata.title).toBe("Untitled Conversation");
    expect(list[0].metadata.files).toEqual([]);
    expect(list[0].metadata.token_count).toBe(0);
    expect(list[0].metadata.pinned).toBe(false);
  });

  test("listConversationsWithMetadata returns empty array when no conversations", async () => {
    const list = await store.listConversationsWithMetadata();
    expect(list).toEqual([]);
  });

  // Phase 5: Branching Tests

  test("branchConversation creates new conversation from branch point", async () => {
    const parent: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "parent-conv",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      metadata: {
        title: "Parent Conversation",
        files: ["file.ts"],
        token_count: 100,
        pinned: false,
      },
      messages: [
        {
          id: "msg-1",
          role: "user",
          content: "First message",
          timestamp: new Date().toISOString(),
        },
        {
          id: "msg-2",
          role: "assistant",
          content: "First response",
          timestamp: new Date().toISOString(),
        },
        {
          id: "msg-3",
          role: "user",
          content: "Second message",
          timestamp: new Date().toISOString(),
        },
        {
          id: "msg-4",
          role: "assistant",
          content: "Second response",
          timestamp: new Date().toISOString(),
        },
      ],
    };

    await store.saveConversation(parent);

    const branch = await store.branchConversation(
      "parent-conv",
      "msg-2",
      "branch-conv"
    );

    expect(branch.conversation.id).toBe("branch-conv");
    expect(branch.metadata?.parent_conversation_id).toBe("parent-conv");
    expect(branch.metadata?.branch_point_message_id).toBe("msg-2");
    expect(branch.metadata?.title).toBe("Parent Conversation (branch)");
    expect(branch.messages).toHaveLength(2); // Only up to msg-2
    expect(branch.messages[0].id).toBe("msg-1");
    expect(branch.messages[1].id).toBe("msg-2");
  });

  test("branchConversation preserves parent metadata", async () => {
    const parent: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "parent-with-metadata",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      metadata: {
        title: "Important Conversation",
        files: ["important.ts", "data.json"],
        token_count: 500,
        pinned: true,
      },
      messages: [
        {
          id: "msg-1",
          role: "user",
          content: "Message",
          timestamp: new Date().toISOString(),
        },
      ],
    };

    await store.saveConversation(parent);

    const branch = await store.branchConversation(
      "parent-with-metadata",
      "msg-1",
      "branch-with-metadata"
    );

    expect(branch.metadata?.files).toEqual(["important.ts", "data.json"]);
    expect(branch.metadata?.token_count).toBe(500);
    // pinned should be preserved from parent
    expect(branch.metadata?.pinned).toBe(true);
  });

  test("branchConversation throws error for non-existent parent", async () => {
    await expect(
      store.branchConversation("does-not-exist", "msg-1", "new-branch")
    ).rejects.toThrow("Parent conversation not found");
  });

  test("branchConversation throws error for invalid branch point", async () => {
    const parent: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "parent-invalid-branch",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      messages: [
        {
          id: "msg-1",
          role: "user",
          content: "Message",
          timestamp: new Date().toISOString(),
        },
      ],
    };

    await store.saveConversation(parent);

    await expect(
      store.branchConversation(
        "parent-invalid-branch",
        "invalid-msg-id",
        "new-branch"
      )
    ).rejects.toThrow("Branch point message not found");
  });

  test("branchConversation preserves summaries", async () => {
    const parent: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "parent-with-summaries",
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
          content: "Response 1",
          timestamp: new Date().toISOString(),
        },
      ],
      summaries: [
        {
          range_start: 0,
          range_end: 1,
          key_points: ["Discussed feature A", "Decided on approach B"],
          created_at: new Date().toISOString(),
        },
      ],
    };

    await store.saveConversation(parent);

    const branch = await store.branchConversation(
      "parent-with-summaries",
      "msg-2",
      "branch-with-summaries"
    );

    expect(branch.summaries).toHaveLength(1);
    expect(branch.summaries?.[0].key_points).toEqual([
      "Discussed feature A",
      "Decided on approach B",
    ]);
  });

  // Phase 5: Import/Export Tests

  test("exportConversation returns JSON string", async () => {
    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "export-test",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      metadata: {
        title: "Export Test",
        files: ["file.ts"],
        token_count: 100,
        pinned: false,
      },
      messages: [
        {
          id: "msg-1",
          role: "user",
          content: "Test message",
          timestamp: new Date().toISOString(),
        },
      ],
    };

    await store.saveConversation(conversation);

    const exported = await store.exportConversation("export-test");

    expect(typeof exported).toBe("string");
    const parsed = JSON.parse(exported);
    expect(parsed.conversation.id).toBe("export-test");
    expect(parsed.metadata.title).toBe("Export Test");
    expect(parsed.messages).toHaveLength(1);
  });

  test("exportConversation throws error for non-existent conversation", async () => {
    await expect(
      store.exportConversation("does-not-exist")
    ).rejects.toThrow("Conversation not found");
  });

  test("importConversation creates new conversation with new ID", async () => {
    const originalConversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "original-conv",
        created_at: "2024-01-01T00:00:00.000Z",
        updated_at: "2024-01-01T00:00:00.000Z",
        workspace_root: "/original/path",
      },
      metadata: {
        title: "Imported Conversation",
        files: ["imported.ts"],
        token_count: 200,
        pinned: false,
      },
      messages: [
        {
          id: "msg-1",
          role: "user",
          content: "Imported message",
          timestamp: new Date().toISOString(),
        },
      ],
    };

    const exported = JSON.stringify(originalConversation);
    const imported = await store.importConversation(exported);

    // Should have new ID
    expect(imported.conversation.id).not.toBe("original-conv");
    expect(imported.conversation.id).toContain("imported");

    // Should preserve metadata and messages
    expect(imported.metadata?.title).toBe("Imported Conversation");
    expect(imported.metadata?.files).toEqual(["imported.ts"]);
    expect(imported.messages).toHaveLength(1);
    expect(imported.messages[0].content).toBe("Imported message");

    // Should update timestamps
    expect(imported.conversation.created_at).not.toBe(
      "2024-01-01T00:00:00.000Z"
    );
    expect(imported.conversation.updated_at).not.toBe(
      "2024-01-01T00:00:00.000Z"
    );

    // Should be saved to store
    const loaded = await store.loadConversation(imported.conversation.id);
    expect(loaded).not.toBeNull();
    expect(loaded?.metadata?.title).toBe("Imported Conversation");
  });

  test("importConversation validates schema", async () => {
    const invalidData = JSON.stringify({
      conversation: {
        id: "invalid",
        // Missing required fields
      },
      messages: [],
    });

    await expect(store.importConversation(invalidData)).rejects.toThrow();
  });

  test("importConversation handles invalid JSON", async () => {
    const invalidJSON = "{ invalid json }";

    await expect(store.importConversation(invalidJSON)).rejects.toThrow();
  });

  test("export and import round-trip preserves all data", async () => {
    const original: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: "roundtrip-test",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: testDir,
      },
      metadata: {
        title: "Round Trip Test",
        files: ["file1.ts", "file2.ts"],
        token_count: 350,
        pinned: true,
      },
      messages: [
        {
          id: "msg-1",
          role: "user",
          content: "First message",
          timestamp: new Date().toISOString(),
        },
        {
          id: "msg-2",
          role: "assistant",
          content: "First response",
          timestamp: new Date().toISOString(),
          pinned: true,
        },
      ],
      summaries: [
        {
          range_start: 0,
          range_end: 1,
          key_points: ["Key point 1", "Key point 2"],
          created_at: new Date().toISOString(),
        },
      ],
    };

    await store.saveConversation(original);

    const exported = await store.exportConversation("roundtrip-test");
    const imported = await store.importConversation(exported);

    // Verify all data preserved (except IDs and timestamps)
    expect(imported.metadata?.title).toBe(original.metadata?.title);
    expect(imported.metadata?.files).toEqual(original.metadata?.files);
    expect(imported.metadata?.token_count).toBe(original.metadata?.token_count);
    expect(imported.metadata?.pinned).toBe(original.metadata?.pinned);
    expect(imported.messages).toHaveLength(original.messages.length);
    expect(imported.messages[0].content).toBe(original.messages[0].content);
    expect(imported.messages[1].pinned).toBe(original.messages[1].pinned);
    expect(imported.summaries).toHaveLength(original.summaries?.length || 0);
    expect(imported.summaries?.[0].key_points).toEqual(
      original.summaries?.[0].key_points
    );
  });
});