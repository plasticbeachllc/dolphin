// agent-core/src/storage/conversation-store.ts
import {
  Conversation,
  ConversationSchema,
  ConversationMetadata
} from "../../../shared/types/state";
import { TOMLWriter } from "./toml-writer";
import * as path from "path";
import * as fs from "fs/promises";

export class ConversationStore {
  private stateDir: string;

  constructor(workspaceRoot: string) {
    this.stateDir = path.join(
      workspaceRoot,
      ".dolphin",
      "state",
      "conversations"
    );
  }

  async saveConversation(conversation: Conversation): Promise<void> {
    const validated = ConversationSchema.parse(conversation);
    validated.conversation.updated_at = new Date().toISOString();

    const filepath = path.join(
      this.stateDir,
      `${conversation.conversation.id}.toml`
    );
    const writer = new TOMLWriter<Conversation>(filepath);

    await writer.write(validated);

    console.error(
      `[ConversationStore] Saved conversation: ${conversation.conversation.id}`
    );
  }

  async loadConversation(conversationId: string): Promise<Conversation | null> {
    const filepath = path.join(this.stateDir, `${conversationId}.toml`);
    const writer = new TOMLWriter<Conversation>(filepath);

    const data = await writer.read();
    if (!data) return null;

    return ConversationSchema.parse(data);
  }

  async listConversations(): Promise<string[]> {
    try {
      await fs.mkdir(this.stateDir, { recursive: true });
      const files = await fs.readdir(this.stateDir);
      return files
        .filter((f) => f.endsWith(".toml"))
        .map((f) => f.replace(".toml", ""))
        .sort();
    } catch {
      return [];
    }
  }

  async deleteConversation(conversationId: string): Promise<void> {
    const filepath = path.join(this.stateDir, `${conversationId}.toml`);
    const writer = new TOMLWriter<Conversation>(filepath);
    await writer.delete();

    console.error(`[ConversationStore] Deleted conversation: ${conversationId}`);
  }

  async getLatestConversation(): Promise<Conversation | null> {
    const conversations = await this.listConversations();
    if (conversations.length === 0) {
      return null;
    }

    return this.loadConversation(conversations[conversations.length - 1]);
  }

  // Phase 5: New methods for metadata management

  async updateMetadata(
    conversationId: string,
    metadata: Partial<ConversationMetadata>
  ): Promise<void> {
    const conversation = await this.loadConversation(conversationId);
    if (!conversation) {
      throw new Error(`Conversation not found: ${conversationId}`);
    }

    // Merge existing metadata with new metadata
    conversation.metadata = {
      ...conversation.metadata,
      ...metadata,
    };

    await this.saveConversation(conversation);
    console.error(
      `[ConversationStore] Updated metadata for: ${conversationId}`
    );
  }

  async listConversationsWithMetadata(): Promise<
    Array<{
      id: string;
      metadata: ConversationMetadata;
      created_at: string;
      updated_at: string;
      message_count: number;
    }>
  > {
    const conversationIds = await this.listConversations();
    const conversations = await Promise.all(
      conversationIds.map((id) => this.loadConversation(id))
    );

    return conversations
      .filter((conv): conv is Conversation => conv !== null)
      .map((conv) => ({
        id: conv.conversation.id,
        metadata: conv.metadata || {
          title: "Untitled Conversation",
          files: [],
          token_count: 0,
          pinned: false,
        },
        created_at: conv.conversation.created_at,
        updated_at: conv.conversation.updated_at,
        message_count: conv.messages.length,
      }));
  }

  async branchConversation(
    parentId: string,
    branchPointMessageId: string,
    newId: string
  ): Promise<Conversation> {
    const parent = await this.loadConversation(parentId);
    if (!parent) {
      throw new Error(`Parent conversation not found: ${parentId}`);
    }

    // Find the branch point
    const branchIndex = parent.messages.findIndex(
      (m) => m.id === branchPointMessageId
    );
    if (branchIndex === -1) {
      throw new Error(
        `Branch point message not found: ${branchPointMessageId}`
      );
    }

    // Create new conversation with messages up to branch point
    const newConversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: newId,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: parent.conversation.workspace_root,
      },
      metadata: {
        ...parent.metadata,
        parent_conversation_id: parentId,
        branch_point_message_id: branchPointMessageId,
        title: `${parent.metadata?.title || "Conversation"} (branch)`,
        last_active_at: new Date().toISOString(),
      },
      messages: parent.messages.slice(0, branchIndex + 1),
      summaries: parent.summaries,
    };

    await this.saveConversation(newConversation);
    console.error(
      `[ConversationStore] Branched conversation ${parentId} -> ${newId}`
    );

    return newConversation;
  }

  async exportConversation(conversationId: string): Promise<string> {
    const conversation = await this.loadConversation(conversationId);
    if (!conversation) {
      throw new Error(`Conversation not found: ${conversationId}`);
    }

    return JSON.stringify(conversation, null, 2);
  }

  async importConversation(data: string): Promise<Conversation> {
    const parsed = JSON.parse(data);
    const conversation = ConversationSchema.parse(parsed);

    // Generate new ID to avoid conflicts
    const newId = `conv_${Date.now()}_imported`;
    conversation.conversation.id = newId;
    conversation.conversation.created_at = new Date().toISOString();
    conversation.conversation.updated_at = new Date().toISOString();

    await this.saveConversation(conversation);
    console.error(`[ConversationStore] Imported conversation as: ${newId}`);

    return conversation;
  }
}