/**
 * agent-core/src/main.ts
 *
 * JSON-RPC stdio entry point for Dolphin V2
 *
 * This module provides the IPC layer between the VSCode extension and the V2 Orchestrator.
 * It handles JSON-RPC communication over stdin/stdout and translates between the extension's
 * event model and the V2 Orchestrator's async iterator pattern.
 */

import type { AgentEvent, ExtensionRequest } from "../../shared/types/events";
import { Orchestrator } from "./orchestrator/orchestrator";
import { EditorWorkflow } from "./workflows/editor-workflow";
import { ArchitectWorkflow } from "./workflows/architect-workflow";
import { StateStore } from "./state/state-store";
import { MCPClient } from "./mcp/mcp-client";
import { KBManager } from "./kb/kb-manager";
import type { ChatProvider } from "./execution/chat-provider";
import { createChatProvider } from "./execution/provider-factory";
import { ContextBuilder } from "./context/context-builder";
import { PromptBuilder } from "./prompts/prompt-builder";
import { PlanStore } from "./storage/plan-store";
import { join as pathJoin } from "path";
import { loadProviderSettings } from "./utils/provider-settings";

interface Message {
  jsonrpc: "2.0";
  id?: number;
  method?: string;
  params?: unknown;
  result?: unknown;
  error?: {
    code: number;
    message: string;
    data?: unknown;
  };
}

/**
 * AgentCoreV2 - Main entry point that bridges JSON-RPC stdio to Orchestrator
 */
class AgentCoreV2 {
  private version = "2.0.0";
  private capabilities = [
    "kb_search",
    "file_operations",
    "planning",
    "claude_auth",
    "agentic_tools",
    "kb_auto_sync",
    "conversation_persistence",
    "architect_mode",
    "multi_model",
    "workflow_streaming",
  ];

  private orchestrator: Orchestrator | null = null;
  private editorProvider: ChatProvider | null = null;
  private architectProvider: ChatProvider | null = null;
  private workflowsReady: Promise<void> | null = null;
  private mcpClient: MCPClient;
  private kbManager: KBManager;
  private workspaceRoot: string;
  private extensionPath?: string;
  private writeQueue: Promise<void> = Promise.resolve();
  private requestIdCounter = 0;
  private contextBuilder: ContextBuilder;
  private promptBuilder: PromptBuilder;
  private stateStore: StateStore;
  private planStore: PlanStore;

  constructor(workspaceRoot: string, extensionPath?: string) {
    this.workspaceRoot = workspaceRoot;
    this.extensionPath = extensionPath;

    // Initialize KB Manager
    this.kbManager = new KBManager();

    // Initialize MCP Client
    this.mcpClient = new MCPClient();

    // Initialize Context Builder
    this.contextBuilder = new ContextBuilder({
      workspaceRoot,
      kbUrl: "http://127.0.0.1:7777",
    });

    // Initialize Prompt Builder
    this.promptBuilder = new PromptBuilder();

    // Initialize State Store
    this.stateStore = new StateStore({
      storagePath: pathJoin(workspaceRoot, ".dolphin"),
    });

    // Initialize Plan Store (for architect workflow)
    this.planStore = new PlanStore(workspaceRoot);
  }

  private async ensureWorkflowsReady(): Promise<void> {
    if (this.orchestrator) {
      return;
    }

    if (!this.workflowsReady) {
      this.workflowsReady = (async () => {
        const providerSettings = loadProviderSettings();

        this.editorProvider = await createChatProvider({
          workspaceRoot: this.workspaceRoot,
          mcpClient: this.mcpClient,
          maxToolRounds: 10,
          settings: providerSettings,
          defaultOpenAIModel: "gpt-5.1-codex",
        });

        let architectProvider: ChatProvider = this.editorProvider;
        if (!providerSettings.model && this.editorProvider.getProviderMetadata().provider === "openai") {
          architectProvider = await createChatProvider({
            workspaceRoot: this.workspaceRoot,
            mcpClient: this.mcpClient,
            maxToolRounds: 10,
            settings: providerSettings,
            defaultOpenAIModel: "gpt-5.1",
          });
        }

        this.architectProvider = architectProvider;

        const editorWorkflow = new EditorWorkflow({
          chatProvider: this.editorProvider,
          contextBuilder: this.contextBuilder,
          promptBuilder: this.promptBuilder,
          stateStore: this.stateStore,
          workspaceRoot: this.workspaceRoot,
        });

        const architectWorkflow = new ArchitectWorkflow({
          chatProvider: this.architectProvider,
          contextBuilder: this.contextBuilder,
          promptBuilder: this.promptBuilder,
          stateStore: this.stateStore,
          planStore: this.planStore,
          workspaceRoot: this.workspaceRoot,
        });

        this.orchestrator = new Orchestrator({
          workspaceRoot: this.workspaceRoot,
          stateStore: this.stateStore,
          editorWorkflow,
          architectWorkflow,
        });
      })();
    }

    await this.workflowsReady;
  }

  private getProvidersWithLabels(): Array<{ labels: string[]; provider: ChatProvider }> {
    const entries: Array<{ label: string; provider: ChatProvider }> = [];
    if (this.editorProvider) {
      entries.push({ label: "editor", provider: this.editorProvider });
    }
    if (this.architectProvider) {
      entries.push({ label: "architect", provider: this.architectProvider });
    }

    const grouped = new Map<ChatProvider, string[]>();
    for (const entry of entries) {
      const labels = grouped.get(entry.provider) ?? [];
      labels.push(entry.label);
      grouped.set(entry.provider, labels);
    }

    return Array.from(grouped.entries()).map(([provider, labels]) => ({ provider, labels }));
  }

  private getUniqueProviders(): ChatProvider[] {
    return this.getProvidersWithLabels().map(({ provider }) => provider);
  }

  async start() {
    console.error("[Agent Core V2] Starting...");
    console.error(`[Agent Core V2] Version: ${this.version}`);
    console.error(`[Agent Core V2] Workspace: ${this.workspaceRoot}`);

    // Start KB API
    console.error("[Agent Core V2] Starting Knowledge Bank...");
    await this.kbManager.start(this.workspaceRoot, this.extensionPath);

    // Start MCP Bridge
    console.error("[Agent Core V2] Starting MCP Bridge...");
    const mcpBridgePath = pathJoin(__dirname, "../../mcp-bridge/src/index.ts");
    await this.mcpClient.start(mcpBridgePath);

    await this.ensureWorkflowsReady();
    if (!this.editorProvider || !this.architectProvider) {
      throw new Error("Chat providers failed to initialize");
    }

    console.error("[Agent Core V2] Initializing chat providers...");
    const uniqueProviders = this.getUniqueProviders();
    for (const provider of uniqueProviders) {
      await provider.initialize();
    }

    // List available tools
    const tools = await this.mcpClient.listTools();
    console.error(
      `[Agent Core V2] Available tools: ${tools.map((t: { name: string }) => t.name).join(", ")}`
    );

    for (const { labels, provider } of this.getProvidersWithLabels()) {
      const providerInfo = provider.getProviderMetadata();
      const authStatus = await provider.detectAuthStatus();
      console.error(
        `[Agent Core V2] ${labels.join("+")} provider: ${providerInfo.provider} (model=${providerInfo.model})`
      );
      if (authStatus.authenticated) {
        console.error(`[Agent Core V2] Authenticated via ${authStatus.mode}`);
      } else {
        console.error(`[Agent Core V2] Authentication missing: ${authStatus.error ?? "unknown"}`);
      }
    }

    // Set up stdio communication using JSON-RPC framing
    let buffer = Buffer.alloc(0);
    process.stdin.on("data", (chunk: Buffer) => {
      buffer = Buffer.concat([buffer, chunk]);

      while (true) {
        const crlfDelimiterIndex = buffer.indexOf("\r\n\r\n");
        const lfDelimiterIndex = buffer.indexOf("\n\n");

        let headerEndIndex = -1;
        let delimiterLength = 0;

        if (
          crlfDelimiterIndex !== -1 &&
          (lfDelimiterIndex === -1 || crlfDelimiterIndex <= lfDelimiterIndex)
        ) {
          headerEndIndex = crlfDelimiterIndex;
          delimiterLength = 4;
        } else if (lfDelimiterIndex !== -1) {
          headerEndIndex = lfDelimiterIndex;
          delimiterLength = 2;
        }

        if (headerEndIndex === -1) {
          break;
        }

        const header = buffer.slice(0, headerEndIndex).toString("utf-8");
        const headers = header.split(/\r?\n/);
        let contentLength: number | undefined;

        for (const line of headers) {
          const match = line.match(/^Content-Length:\s*(\d+)/i);
          if (match) {
            contentLength = Number.parseInt(match[1], 10);
            break;
          }
        }

        if (contentLength === undefined) {
          console.error("[Agent Core V2] Invalid message: no Content-Length header");
          buffer = buffer.slice(headerEndIndex + delimiterLength);
          continue;
        }

        const totalMessageLength = headerEndIndex + delimiterLength + contentLength;

        if (buffer.length < totalMessageLength) {
          break;
        }

        const messageBody = buffer
          .slice(headerEndIndex + delimiterLength, totalMessageLength)
          .toString("utf-8");

        buffer = buffer.slice(totalMessageLength);

        try {
          const message = JSON.parse(messageBody) as Message;
          void this.handleMessage(message);
        } catch (error) {
          console.error("[Agent Core V2] Failed to parse message:", error);
        }
      }
    });

    process.stdin.on("end", () => {
      console.error("[Agent Core V2] stdin closed, shutting down...");
      this.shutdown();
    });

    console.error("[Agent Core V2] Ready for requests");
    this.sendEvent({
      type: "ready",
      data: {
        version: this.version,
        capabilities: this.capabilities,
      },
    });
  }

  private async handleMessage(message: Message) {
    if (message.method) {
      // Handle request
      const request = message as ExtensionRequest;
      try {
        const result = await this.handleRequest(request);
        this.sendResponse(message.id!, result);
      } catch (error: unknown) {
        this.sendError(message.id!, error);
      }
    }
  }

  private async handleRequest(request: ExtensionRequest): Promise<unknown> {
    console.error(`[Agent Core V2] Handling request: ${request.method}`);
    await this.ensureWorkflowsReady();
    if (!this.orchestrator) {
      throw new Error("Orchestrator not initialized");
    }

    switch (request.method) {
      case "sendMessage":
      case "send_message": {
        const params = request.params as { message: string; context?: unknown; mode?: string };
        const { message, context, mode = "editor" } = params;

        // Start task with orchestrator
        const session = await this.orchestrator.startTask({
          mode: mode as "editor" | "architect",
          message,
          context,
        });

        // Stream updates to extension in background
        void (async () => {
          try {
            for await (const update of this.orchestrator.subscribeToUpdates(session.id)) {
              this.sendEvent({
                type: "workflow_update",
                data: update,
              });
            }
          } catch (error) {
            console.error(`[Agent Core V2] Error streaming updates:`, error);
          }
        })();

        return { conversationId: session.id };
      }

      case "getCapabilities":
      case "get_capabilities":
        return {
          version: this.version,
          capabilities: this.capabilities,
        };

      case "getConversations":
      case "get_conversations":
        // TODO: Implement conversation listing via StateStore
        return [];

      case "loadConversation":
      case "load_conversation": {
        const params = request.params as { conversationId: string };
        const { conversationId } = params;
        const session = await this.orchestrator.getSession(conversationId);
        return session;
      }

      case "deleteConversation":
      case "delete_conversation":
        // TODO: Implement conversation deletion via StateStore
        return { success: true };

      case "approveTask":
      case "approve_task": {
        const params = request.params as { sessionId: string };
        await this.orchestrator.approveTask(params.sessionId);
        return { success: true };
      }

      case "rejectTask":
      case "reject_task": {
        const params = request.params as { sessionId: string; feedback?: string };
        await this.orchestrator.rejectTask(params.sessionId, params.feedback);
        return { success: true };
      }

      case "requestRevision":
      case "request_revision": {
        const params = request.params as { sessionId: string; feedback: string };
        await this.orchestrator.revisePlan(params.sessionId, params.feedback);
        return { success: true };
      }

      case "cancelTask":
      case "cancel_task": {
        const params = request.params as { sessionId: string };
        await this.orchestrator.cancelTask(params.sessionId);
        return { success: true };
      }

      default:
        throw new Error(`Unknown method: ${request.method}`);
    }
  }

  private sendResponse(id: number, result: unknown) {
    const response: Message = {
      jsonrpc: "2.0",
      id,
      result,
    };
    this.send(response);
  }

  private sendError(id: number, error: unknown) {
    const errorObj = error as { message?: string; stack?: string };
    const response: Message = {
      jsonrpc: "2.0",
      id,
      error: {
        code: -32000,
        message: errorObj.message || String(error),
        data: errorObj.stack,
      },
    };
    this.send(response);
  }

  private sendEvent(event: AgentEvent) {
    const notification: Message = {
      jsonrpc: "2.0",
      method: "event",
      params: {
        ...event,
        requestId: this.requestIdCounter++,
      },
    };
    this.send(notification);
  }

  private send(message: Message) {
    this.writeQueue = this.writeQueue.then(async () => {
      const body = JSON.stringify(message);
      const header = `Content-Length: ${Buffer.byteLength(body, "utf-8")}\r\n\r\n`;
      process.stdout.write(header + body);
    });
  }

  private shutdown() {
    console.error("[Agent Core V2] Shutting down...");
    for (const provider of this.getUniqueProviders()) {
      provider.abort();
    }
    this.mcpClient.shutdown();
    this.kbManager.shutdown();
    process.exit(0);
  }
}

// Start the agent
const workspaceRoot = process.argv[2] || process.cwd();
const extensionPath = process.argv[3];

const agent = new AgentCoreV2(workspaceRoot, extensionPath);
agent.start().catch((error) => {
  console.error("[Agent Core V2] Fatal error:", error);
  process.exit(1);
});
