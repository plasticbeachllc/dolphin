/**
 * agent-core-v2/src/main.ts
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
import * as path from "path";

interface Message {
  jsonrpc: "2.0";
  id?: number;
  method?: string;
  params?: any;
  result?: any;
  error?: any;
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
    "workflow_streaming"
  ];

  private orchestrator: Orchestrator;
  private mcpClient: MCPClient;
  private kbManager: KBManager;
  private workspaceRoot: string;
  private extensionPath?: string;
  private writeQueue: Promise<void> = Promise.resolve();
  private requestIdCounter = 0;

  constructor(workspaceRoot: string, extensionPath?: string) {
    this.workspaceRoot = workspaceRoot;
    this.extensionPath = extensionPath;

    // Initialize KB and MCP (shared with V1 components temporarily)
    this.kbManager = new KBManager();
    this.mcpClient = new MCPClient();

    // Initialize State Store
    const stateStore = new StateStore({
      storagePath: path.join(workspaceRoot, ".dolphin")
    });

    // Initialize Workflows
    const editorWorkflow = new EditorWorkflow({
      workspaceRoot,
      kbUrl: "http://127.0.0.1:7777",
      mcpClient: this.mcpClient
    });

    const architectWorkflow = new ArchitectWorkflow({
      workspaceRoot,
      kbUrl: "http://127.0.0.1:7777",
      mcpClient: this.mcpClient
    });

    // Initialize Orchestrator
    this.orchestrator = new Orchestrator({
      workspaceRoot,
      stateStore,
      editorWorkflow,
      architectWorkflow
    });
  }

  async start() {
    console.error("[Agent Core V2] Starting...");
    console.error(`[Agent Core V2] Version: ${this.version}`);

    // Start KB API
    await this.kbManager.start(this.workspaceRoot, this.extensionPath);

    // Start MCP Bridge
    const mcpBridgePath = path.join(__dirname, "../../mcp-bridge/src/index.ts");
    await this.mcpClient.start(mcpBridgePath);

    // List available tools
    const tools = await this.mcpClient.listTools();
    console.error(
      `[Agent Core V2] Available tools: ${tools.map((t: any) => t.name).join(", ")}`
    );

    // Set up stdio communication using JSON-RPC framing
    let buffer = Buffer.alloc(0);
    process.stdin.on("data", (chunk: Buffer) => {
      buffer = Buffer.concat([buffer, chunk]);

      while (true) {
        const crlfDelimiterIndex = buffer.indexOf("\r\n\r\n");
        const lfDelimiterIndex = buffer.indexOf("\n\n");

        let headerEndIndex = -1;
        let delimiterLength = 0;

        if (crlfDelimiterIndex !== -1 && (lfDelimiterIndex === -1 || crlfDelimiterIndex <= lfDelimiterIndex)) {
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
          const message: Message = JSON.parse(messageBody);
          this.handleMessage(message);
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
      } catch (error: any) {
        this.sendError(message.id!, error);
      }
    }
  }

  private async handleRequest(request: ExtensionRequest): Promise<any> {
    console.error(`[Agent Core V2] Handling request: ${request.method}`);

    switch (request.method) {
      case "sendMessage": {
        const {message, context, mode = "editor"} = request.params;

        // Start task with orchestrator
        const session = await this.orchestrator.startTask({
          mode,
          message,
          context
        });

        // Stream updates to extension
        for await (const update of this.orchestrator.streamUpdates(session.id)) {
          this.sendEvent({
            type: "workflow_update",
            data: update
          });
        }

        return {conversationId: session.id};
      }

      case "getCapabilities":
        return {
          version: this.version,
          capabilities: this.capabilities,
        };

      case "getConversations":
        // TODO: Implement conversation listing via StateStore
        return [];

      case "loadConversation":
        // TODO: Implement conversation loading via StateStore
        return null;

      case "deleteConversation":
        // TODO: Implement conversation deletion via StateStore
        return {success: true};

      case "approveTask":
        const {sessionId} = request.params;
        await this.orchestrator.approveTask(sessionId);
        return {success: true};

      case "requestRevision":
        await this.orchestrator.requestRevision(request.params.sessionId, request.params.feedback);
        return {success: true};

      case "cancelTask":
        await this.orchestrator.cancelTask(request.params.sessionId);
        return {success: true};

      default:
        throw new Error(`Unknown method: ${request.method}`);
    }
  }

  private sendResponse(id: number, result: any) {
    const response: Message = {
      jsonrpc: "2.0",
      id,
      result,
    };
    this.send(response);
  }

  private sendError(id: number, error: any) {
    const response: Message = {
      jsonrpc: "2.0",
      id,
      error: {
        code: -32000,
        message: error.message || String(error),
        data: error.stack,
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
