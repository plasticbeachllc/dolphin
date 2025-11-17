import * as vscode from "vscode";
import { AgentEvent, ConversationListItem, LoadConversationResult } from "../types/events";
import { AgentBridgeAdapter, AgentAuthOptions } from "./types";
import type { AgentAuthStatusResponse } from "../types/auth";

interface ConversationState {
  id: string;
  metadata: ConversationListItem["metadata"];
  created_at: string;
  updated_at: string;
  message_count: number;
}

export class TestAgentBridge implements AgentBridgeAdapter {
  public readonly onEvent: vscode.Event<AgentEvent>;

  private eventEmitter = new vscode.EventEmitter<AgentEvent>();
  private isDisposed = false;
  private conversations: ConversationState[] = [];

  constructor(private readonly outputChannel: vscode.OutputChannel) {
    this.onEvent = this.eventEmitter.event;

    const now = new Date().toISOString();
    this.conversations = [
      {
        id: "dolphin-test-conversation",
        metadata: {
          title: "Test Conversation",
          files: [],
          token_count: 0,
          pinned: false,
        },
        created_at: now,
        updated_at: now,
        message_count: 0,
      },
    ];
  }

  async start(
    _agentCorePath: string,
    _extensionPath: string,
    _options?: AgentAuthOptions
  ): Promise<void> {
    if (this.isDisposed) {
      throw new Error("TestAgentBridge already disposed");
    }

    this.outputChannel.appendLine("[TestAgentBridge] start() called - using in-memory stub");

    setTimeout(() => {
      if (!this.isDisposed) {
        this.eventEmitter.fire({
          type: "agent_ready",
          version: "test",
          capabilities: ["mock"],
        });
      }
    }, 0);
  }

  shutdown(): void {
    if (this.isDisposed) {
      return;
    }

    try {
      this.outputChannel.appendLine("[TestAgentBridge] shutdown() called");
    } catch {
      // Ignore logging failures during shutdown in tests
    }

    this.isDisposed = true;
    this.eventEmitter.dispose();
    this.conversations = [];
  }

  async sendMessage(content: string, mode?: "code" | "architect"): Promise<void> {
    this.outputChannel.appendLine(
      `[TestAgentBridge] sendMessage(mode=${mode ?? "code"}) called with content length ${content.length}`
    );

    if (this.isDisposed) {
      throw new Error("TestAgentBridge disposed");
    }

    this.eventEmitter.fire({
      type: "content_delta",
      delta: content,
      requestId: "test-request",
    });
    this.eventEmitter.fire({
      type: "task_completed",
      success: true,
      result: content,
    });
  }

  async getAuthStatus(): Promise<AgentAuthStatusResponse> {
    return {
      providers: [
        {
          provider: "test",
          authenticated: true,
          mode: "test",
        },
      ],
    };
  }

  async abortGeneration(): Promise<void> {
    if (this.isDisposed) {
      return;
    }
    this.outputChannel.appendLine("[TestAgentBridge] abortGeneration() called");
    this.eventEmitter.fire({
      type: "task_completed",
      success: false,
      error: {
        code: "COMMAND_NOT_ALLOWED",
        message: "Generation aborted in test mode",
        suggestions: [],
        recoverable: true,
      },
    });
  }

  async clearConversation(): Promise<void> {
    if (this.isDisposed) {
      return;
    }

    this.outputChannel.appendLine("[TestAgentBridge] clearConversation() called");
    this.eventEmitter.fire({ type: "clear_conversation" });
  }

  async listConversations(): Promise<ConversationListItem[]> {
    return this.conversations.map((conversation) => ({
      id: conversation.id,
      metadata: conversation.metadata,
      created_at: conversation.created_at,
      updated_at: conversation.updated_at,
      message_count: conversation.message_count,
    }));
  }

  async loadConversation(conversationId: string): Promise<LoadConversationResult> {
    const conversation = this.conversations.find((c) => c.id === conversationId);
    if (!conversation) {
      throw new Error(`Conversation ${conversationId} not found`);
    }

    return {
      conversation: {
        id: conversation.id,
        title: conversation.metadata.title,
        messages: [],
      },
      branchInfo: undefined,
    };
  }

  async deleteConversation(conversationId: string): Promise<void> {
    this.conversations = this.conversations.filter((c) => c.id !== conversationId);
    this.eventEmitter.fire({ type: "conversation_deleted", conversationId });
  }

  async renameConversation(conversationId: string, newTitle: string): Promise<void> {
    const conversation = this.conversations.find((c) => c.id === conversationId);
    if (!conversation) {
      throw new Error(`Conversation ${conversationId} not found`);
    }

    conversation.metadata.title = newTitle || conversation.metadata.title;
    conversation.updated_at = new Date().toISOString();
    this.eventEmitter.fire({
      type: "conversation_renamed",
      conversationId,
      newTitle: conversation.metadata.title,
    });
  }
}
