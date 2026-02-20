// agent-core/src/storage/conversation-store.ts
import type { Conversation, ConversationMetadata } from "../../../../shared/types/state";
import { TOMLWriter } from "./toml-writer";
import { join as pathJoin } from "path";
import { mkdir, readdir } from "fs/promises";

export class ConversationStore {
  private stateDir: string;
  private workspaceRoot: string;

  constructor(workspaceRoot: string) {
    this.workspaceRoot = workspaceRoot;
    this.stateDir = pathJoin(workspaceRoot, ".dolphin", "state", "conversations");
  }

  async saveConversation(conversation: Conversation): Promise<void> {
    const validated = conversation;
    const convId = validated.conversation.id;
    validated.conversation.updated_at = new Date().toISOString();

    const filepath = pathJoin(this.stateDir, `${convId}.toml`);
    const writer = new TOMLWriter<Conversation>(filepath, this.workspaceRoot);

    await writer.write(validated);

    console.error(`[ConversationStore] Saved conversation: ${convId}`);
  }

  async loadConversation(conversationId: string): Promise<Conversation | null> {
    const filepath = pathJoin(this.stateDir, `${conversationId}.toml`);
    const writer = new TOMLWriter<Conversation>(filepath, this.workspaceRoot);

    const data = await writer.read();
    if (!data) return null;

    return data as Conversation;
  }

  async listConversations(): Promise<string[]> {
    try {
      await mkdir(this.stateDir, { recursive: true });
      const files = await readdir(this.stateDir);
      return files
        .filter((f) => f.endsWith(".toml"))
        .map((f) => f.replace(".toml", ""))
        .sort();
    } catch {
      return [];
    }
  }

  async deleteConversation(conversationId: string): Promise<void> {
    const filepath = pathJoin(this.stateDir, `${conversationId}.toml`);
    const writer = new TOMLWriter<Conversation>(filepath, this.workspaceRoot);
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
    const existingMetadata = conversation.metadata || ({} as ConversationMetadata);
    const updatedConversation: Conversation = {
      ...conversation,
      metadata: {
        ...existingMetadata,
        ...metadata,
      } as ConversationMetadata,
    };

    await this.saveConversation(updatedConversation);
    console.error(`[ConversationStore] Updated metadata for: ${conversationId}`);
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
    try {
      console.error("[ConversationStore] Listing conversations with metadata...");
      const conversationIds = await this.listConversations();
      console.error(`[ConversationStore] Found ${conversationIds.length} conversation IDs`);

      if (conversationIds.length === 0) {
        return [];
      }

      const conversations = await Promise.all(
        conversationIds.map((id) => this.loadConversation(id))
      );

      const filtered = conversations.filter((conv): conv is Conversation => conv !== null);

      const result = filtered.map((conv) => {
        const convMetadata = conv.metadata || {
          title: "Untitled Conversation",
          files: [],
          token_count: 0,
          pinned: false,
        };
        const convId = conv.conversation.id;
        const createdAt = conv.conversation.created_at;
        const updatedAt = conv.conversation.updated_at;
        const messageCount = conv.messages.length;
        return {
          id: convId,
          metadata: convMetadata,
          created_at: createdAt,
          updated_at: updatedAt,
          message_count: messageCount,
        };
      });

      console.error(`[ConversationStore] Returning ${result.length} conversations`);
      return result;
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      console.error(`[ConversationStore] Error listing conversations: ${message}`);
      return [];
    }
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
    const branchIndex = parent.messages.findIndex((m) => m.id === branchPointMessageId);
    if (branchIndex === -1) {
      throw new Error(`Branch point message not found: ${branchPointMessageId}`);
    }

    // Create new conversation with messages up to branch point
    const parentMetadata = parent.metadata || {
      title: "Untitled Conversation",
      files: [],
      token_count: 0,
      pinned: false,
    };

    const workspaceRoot = parent.conversation.workspace_root;
    const parentTitle = parentMetadata.title;
    const slicedMessages = parent.messages.slice(0, branchIndex + 1);
    const summaries = parent.summaries;

    const newConversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: newId,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_root: workspaceRoot,
      },
      metadata: {
        ...parentMetadata,
        parent_conversation_id: parentId,
        branch_point_message_id: branchPointMessageId,
        title: `${parentTitle} (branch)`,
        last_active_at: new Date().toISOString(),
      } as ConversationMetadata,
      messages: slicedMessages,
      summaries: summaries,
    };

    await this.saveConversation(newConversation);
    console.error(`[ConversationStore] Branched conversation ${parentId} -> ${newId}`);

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
    const conversation = parsed as Conversation;

    // Generate new ID to avoid conflicts
    const newId = `conv_${Date.now()}_imported`;
    const importedConversation: Conversation = {
      ...conversation,
      conversation: {
        ...conversation.conversation,
        id: newId,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    };

    await this.saveConversation(importedConversation);
    console.error(`[ConversationStore] Imported conversation as: ${newId}`);

    return importedConversation;
  }

  /**
   * Recalculates token counts from message-level token data
   * Useful for validating metadata or migrating existing conversations
   *
   * @param conversationId - The conversation to recalculate
   * @param updateMetadata - If true, updates the metadata.token_count with the recalculated value
   * @returns Object with total tokens and breakdown by type
   */
  async recalculateTokens(
    conversationId: string,
    updateMetadata: boolean = false
  ): Promise<{
    total: number;
    input: number;
    output: number;
    cacheRead: number;
    cacheWrite: number;
  }> {
    const conversation = await this.loadConversation(conversationId);
    if (!conversation) {
      throw new Error(`Conversation not found: ${conversationId}`);
    }

    let totalInput = 0;
    let totalOutput = 0;
    let totalCacheRead = 0;
    let totalCacheWrite = 0;

    // Sum up tokens from all messages that have token data
    const messages = conversation.messages;
    for (const message of messages) {
      const tokens = message.tokens;
      if (tokens) {
        totalInput += tokens.input || 0;
        totalOutput += tokens.output || 0;
        totalCacheRead += tokens.cacheRead || 0;
        totalCacheWrite += tokens.cacheWrite || 0;
      }
    }

    const total = totalInput + totalOutput;

    // Optionally update metadata if out of sync
    const convMetadata = conversation.metadata;
    if (updateMetadata && convMetadata?.token_count !== total) {
      const currentTokenCount = convMetadata?.token_count || 0;
      console.error(
        `[ConversationStore] Recalculated tokens for ${conversationId}: ${currentTokenCount} -> ${total}`
      );
      await this.updateMetadata(conversationId, { token_count: total });
    }

    return {
      total,
      input: totalInput,
      output: totalOutput,
      cacheRead: totalCacheRead,
      cacheWrite: totalCacheWrite,
    };
  }
}
