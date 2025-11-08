// agent-core/src/storage/conversation-store.ts
import { Conversation, ConversationSchema } from "../../../shared/types/state";
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
}