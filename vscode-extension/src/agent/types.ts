import * as vscode from "vscode";
import { AgentEvent, ConversationListItem, LoadConversationResult } from "../types/events";

export interface AgentAuthOptions {
  anthropicApiKey?: string | null;
  openaiApiKey?: string | null;
  kbApiKey?: string | null;
}

export interface AgentBridgeAdapter {
  start(agentCorePath: string, extensionPath: string, options?: AgentAuthOptions): Promise<void>;
  shutdown(): void;
  readonly onEvent: vscode.Event<AgentEvent>;
  sendMessage(content: string, mode?: "code" | "architect"): Promise<void>;
  getAuthStatus(): Promise<unknown>;
  abortGeneration(): Promise<void>;
  clearConversation(): Promise<void>;
  listConversations(): Promise<ConversationListItem[]>;
  loadConversation(conversationId: string): Promise<LoadConversationResult>;
  deleteConversation(conversationId: string): Promise<void>;
  renameConversation(conversationId: string, newTitle: string): Promise<void>;
}
