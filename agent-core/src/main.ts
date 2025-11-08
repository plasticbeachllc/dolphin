// agent-core/src/main.ts
import type { AgentEvent, ExtensionRequest } from "../../shared/types/events";
import { MCPClient } from "./mcp/client";
import { KBManager } from "./kb/manager";
import * as path from "path";

interface Message {
  jsonrpc: "2.0";
  id?: number;
  method?: string;
  params?: any;
  result?: any;
  error?: any;
}

class AgentCore {
  private version = "0.1.0";
  private capabilities = ["kb_search", "file_operations", "planning"];
  private mcpClient: MCPClient;
  private kbManager: KBManager;
  private workspaceRoot: string;

  constructor(workspaceRoot: string) {
    this.workspaceRoot = workspaceRoot;
    this.mcpClient = new MCPClient();
    this.kbManager = new KBManager();
  }

  async start() {
    console.error("[Agent Core] Starting...");
    console.error(`[Agent Core] Version: ${this.version}`);

    // Start KB API first
    await this.kbManager.start(this.workspaceRoot);

    // Start MCP Bridge
    const mcpBridgePath = path.join(__dirname, "../../mcp-bridge/src/index.ts");
    await this.mcpClient.start(mcpBridgePath);

    // List available tools
    const tools = await this.mcpClient.listTools();
    console.error(
      `[Agent Core] Available tools: ${tools.map((t: any) => t.name).join(", ")}`
    );

    // Set up stdio communication
    process.stdin.setEncoding("utf-8");

    let buffer = "";
    process.stdin.on("data", (chunk: string) => {
      buffer += chunk;
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.trim()) {
          this.handleMessage(line);
        }
      }
    });

    // Handle process signals
    process.on("SIGTERM", () => this.shutdown());
    process.on("SIGINT", () => this.shutdown());

    // Send ready signal
    this.sendEvent({
      type: "agent_ready",
      version: this.version,
      capabilities: this.capabilities,
    });

    console.error("[Agent Core] Ready and listening on stdin");
  }

  private handleMessage(data: string) {
    try {
      const message: Message = JSON.parse(data);
      console.error(`[Agent Core] Received: ${message.method || "response"}`);

      if (message.method === "send_message") {
        this.handleSendMessage(message.params as ExtensionRequest);
      }
    } catch (error) {
      console.error("[Agent Core] Parse error:", error);
      this.sendEvent({
        type: "error",
        error: {
          code: "SERVICE_UNAVAILABLE",
          message: "Failed to parse message",
          suggestions: ["Check message format"],
          recoverable: true,
        },
      });
    }
  }

  private async handleSendMessage(request: ExtensionRequest) {
    if (request.type === "send_message") {
      try {
        // Test KB search
        this.sendEvent({
          type: "tool_call_started",
          toolId: "tool-1",
          tool: "search_knowledge",
          input: { query: request.content, top_k: 3 },
        });

        const result = await this.mcpClient.callTool("search_knowledge", {
          query: request.content,
          top_k: 3,
        });

        this.sendEvent({
          type: "tool_call_completed",
          toolId: "tool-1",
          result,
          executionTime: 247,
        });

        // Parse the result - handle MCP response structure
        if (!result.content || !Array.isArray(result.content) || result.content.length === 0) {
          throw new Error("Invalid MCP response: no content");
        }

        // MCP returns content blocks - find the text block with search results
        const textBlock = result.content.find((block: any) => block.type === "text");
        if (!textBlock || !textBlock.text) {
          throw new Error("Invalid MCP response: no text content");
        }

        // The text block contains a summary, not the full results
        // Use _meta for structured data if available
        let hitCount = 0;
        let hits: any[] = [];

        if (result._meta && result._meta.hits) {
          hits = result._meta.hits;
          hitCount = hits.length;
        }

        this.sendEvent({
          type: "content_delta",
          delta: `I found ${hitCount} relevant code snippets. Here's what I learned:\n\n`,
        });

        if (hitCount > 0) {
          for (const hit of hits) {
            this.sendEvent({
              type: "content_delta",
              delta: `- ${hit.path} (lines ${hit.start_line}-${hit.end_line}, score: ${hit.score.toFixed(2)})\n`,
            });
          }
        }

        this.sendEvent({
          type: "task_completed",
          success: true,
          result: { hits: hitCount },
        });
      } catch (error: any) {
        console.error("[Agent Core] Error handling message:", error);
        this.sendEvent({
          type: "error",
          error: {
            code: "SERVICE_UNAVAILABLE",
            message: error.message,
            suggestions: ["Check KB is running", "Try a different query"],
            recoverable: true,
          },
        });
      }
    }
  }

  private sendEvent(event: AgentEvent) {
    const message: Message = {
      jsonrpc: "2.0",
      method: "notify",
      params: event,
    };

    process.stdout.write(JSON.stringify(message) + "\n");
  }

  private shutdown() {
    console.error("[Agent Core] Shutting down...");
    this.kbManager.shutdown();
    this.mcpClient.shutdown();
    process.exit(0);
  }
}

// Get workspace root from command line arg or current directory
const workspaceRoot = process.argv[2] || process.cwd();
const agent = new AgentCore(workspaceRoot);
agent.start().catch((error) => {
  console.error("[Agent Core] Fatal error:", error);
  process.exit(1);
});