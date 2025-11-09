// agent-core/src/main.ts
import type { AgentEvent, ExtensionRequest } from "../../shared/types/events";
import { MCPClient } from "./mcp/client";
import { KBManager } from "./kb/manager";
import { ClaudeClient } from "./llm/claude-client";
import { BasicPlanner } from "./planner/basic-planner";
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
  private capabilities = ["kb_search", "file_operations", "planning", "claude_auth"];
  private mcpClient: MCPClient;
  private kbManager: KBManager;
  private claudeClient: ClaudeClient;
  private planner: BasicPlanner;
  private workspaceRoot: string;
  private extensionPath?: string;

  constructor(workspaceRoot: string, extensionPath?: string) {
    this.workspaceRoot = workspaceRoot;
    this.extensionPath = extensionPath;
    this.mcpClient = new MCPClient();
    this.kbManager = new KBManager();
    this.claudeClient = new ClaudeClient({
      authMode: "auto",
      model: "claude-sonnet-4-20250514",
      maxTokens: 8000,
      temperature: 1.0,
    });
    this.planner = new BasicPlanner(this.claudeClient, {
      enableStreaming: true,
      maxTokens: 8000,
      temperature: 1.0,
    });
  }

  async start() {
    console.error("[Agent Core] Starting...");
    console.error(`[Agent Core] Version: ${this.version}`);

    // Check Claude authentication
    await this.checkClaudeAuth();

    // Start KB API first
    await this.kbManager.start(this.workspaceRoot, this.extensionPath);

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

  private async checkClaudeAuth() {
    try {
      const authStatus = await this.claudeClient.getAuthStatus();
      
      console.error("\n📊 Claude Authentication Status:");
      console.error(`  Mode: ${authStatus.mode}`);
      console.error(`  CLI Installed: ${authStatus.cliInstalled}`);
      console.error(`  CLI Authenticated: ${authStatus.cliAuthenticated}`);
      console.error(`  API Key Set: ${authStatus.apiKeySet}`);
      console.error(`  Will Use Subscription: ${authStatus.willUseSubscription}`);
      console.error("");
      
      if (authStatus.willUseSubscription) {
        console.error("✅ Using Claude subscription (no API costs)");
      } else if (authStatus.apiKeySet) {
        console.error("💳 Using API key (pay-per-token billing)");
      } else {
        console.error("⚠️  No authentication configured");
        console.error("   Install Claude CLI or set ANTHROPIC_API_KEY");
      }
      console.error("");
    } catch (error: any) {
      console.error("⚠️  Claude authentication check failed:", error.message);
      console.error("   Agent will continue without Claude integration");
    }
  }

  private handleMessage(data: string) {
    try {
      const message: Message = JSON.parse(data);
      console.error(`[Agent Core] Received: ${message.method || "response"}`);

      if (message.method === "send_message") {
        this.handleSendMessage(message.params as ExtensionRequest);
      } else if (message.method === "get_auth_status") {
        this.handleGetAuthStatus(message);
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

  private async handleGetAuthStatus(message: Message) {
    try {
      const status = await this.claudeClient.getAuthStatus();
      
      const response: Message = {
        jsonrpc: "2.0",
        id: message.id,
        result: status,
      };
      
      process.stdout.write(JSON.stringify(response) + "\n");
    } catch (error: any) {
      const response: Message = {
        jsonrpc: "2.0",
        id: message.id,
        error: {
          code: -32603,
          message: error.message,
        },
      };
      
      process.stdout.write(JSON.stringify(response) + "\n");
    }
  }

  private async handleSendMessage(request: ExtensionRequest) {
    if (request.type === "send_message") {
      try {
        // Step 1: Search Knowledge Bank for context
        this.sendEvent({
          type: "tool_call_started",
          toolId: "kb-search-1",
          tool: "search_knowledge",
          input: { query: request.content, top_k: 3 },
        });

        const kbResult = await this.mcpClient.callTool("search_knowledge", {
          query: request.content,
          top_k: 3,
        });

        this.sendEvent({
          type: "tool_call_completed",
          toolId: "kb-search-1",
          result: kbResult,
          executionTime: 247,
        });

        // Parse KB results
        let kbContext = "";
        if (kbResult.content && Array.isArray(kbResult.content)) {
          const textBlock = kbResult.content.find((block: any) => block.type === "text");
          if (textBlock && textBlock.text) {
            kbContext = textBlock.text;
          }
        }

        // Step 2: Use planner to generate Claude response with KB context
        await this.planner.processMessage(
          {
            userMessage: request.content,
            kbResults: kbContext,
          },
          (event: AgentEvent) => {
            this.sendEvent(event);
          }
        );
      } catch (error: any) {
        console.error("[Agent Core] Error handling message:", error);
        this.sendEvent({
          type: "error",
          error: {
            code: "SERVICE_UNAVAILABLE",
            message: error.message,
            suggestions: [
              "Check Claude authentication",
              "Check KB is running",
              "Try a different query",
            ],
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

// Get workspace root and extension path from command line args
const workspaceRoot = process.argv[2] || process.cwd();
const extensionPath = process.argv[3]; // Optional - only provided in production
const agent = new AgentCore(workspaceRoot, extensionPath);
agent.start().catch((error) => {
  console.error("[Agent Core] Fatal error:", error);
  process.exit(1);
});