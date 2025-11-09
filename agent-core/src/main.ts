// agent-core/src/main.ts
import type { AgentEvent, ExtensionRequest } from "../../shared/types/events";
import { MCPClient } from "./mcp/client";
import { KBManager } from "./kb/manager";
import { IndexQueue } from "./kb/index-queue";
import { ClaudeClient } from "./llm/claude-client";
import { ClaudeToolExecutor } from "./llm/claude-tool-executor";
import { BasicPlanner } from "./planner/basic-planner";
import * as path from "path";
import * as fs from "fs";
import { exec } from "child_process";
import { promisify } from "util";
import type { Message } from "./llm/claude-tool-executor";

const execAsync = promisify(exec);

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
  private capabilities = ["kb_search", "file_operations", "planning", "claude_auth", "agentic_tools", "kb_auto_sync"];
  private mcpClient: MCPClient;
  private kbManager: KBManager;
  private indexQueue: IndexQueue | null = null;
  private claudeClient: ClaudeClient;
  private toolExecutor: ClaudeToolExecutor;
  private planner: BasicPlanner;
  private conversationHistory: Message[] = [];
  private workspaceRoot: string;
  private extensionPath?: string;
  private repoName: string | null = null;
  private requestIdCounter = 0;

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
    this.toolExecutor = new ClaudeToolExecutor({
      claudeClient: this.claudeClient,
      mcpClient: this.mcpClient,
      maxToolRounds: 10,
      onEvent: (event) => this.sendEvent(event),
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

    // Initialize KB workspace and index queue
    await this.initializeKBWorkspace();

    // Start MCP Bridge
    const mcpBridgePath = path.join(__dirname, "../../mcp-bridge/src/index.ts");
    await this.mcpClient.start(mcpBridgePath);

    // Initialize tool executor with MCP tools
    await this.toolExecutor.initialize();

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

  private async initializeKBWorkspace() {
    try {
      console.error("[Agent Core] Initializing KB workspace...");

      // Detect workspace name from git
      this.repoName = await this.detectWorkspaceName();
      console.error(`[Agent Core] Workspace name: ${this.repoName}`);

      // Register workspace with KB API
      const KB_URL = "http://127.0.0.1:7777";
      const registerResponse = await fetch(`${KB_URL}/v1/repos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: this.repoName,
          path: this.workspaceRoot,
          default_embed_model: "large",
        }),
      });

      if (!registerResponse.ok) {
        const errorText = await registerResponse.text();
        console.error(`[Agent Core] Failed to register workspace: ${errorText}`);
        // Continue anyway - repo might already be registered
      } else {
        const result = await registerResponse.json();
        console.error(`[Agent Core] ${result.message}`);
      }

      // Initialize index queue
      this.indexQueue = new IndexQueue(KB_URL, this.repoName);

      // Listen to indexing events
      this.indexQueue.on("progress", (count: number) => {
        console.error(`[Agent Core] Indexed ${count} files`);
        this.sendEvent({
          type: "kb_progress",
          data: { indexed: count },
        });
      });

      this.indexQueue.on("complete", () => {
        console.error("[Agent Core] Index queue complete");
        this.sendEvent({
          type: "kb_complete",
          data: {},
        });
      });

      this.indexQueue.on("error", (error: Error) => {
        console.error(`[Agent Core] Index queue error: ${error.message}`);
      });

      console.error("[Agent Core] KB workspace initialized");
    } catch (error: any) {
      console.error(`[Agent Core] KB workspace initialization failed: ${error.message}`);
      // Continue without KB indexing
    }
  }

  private async detectWorkspaceName(): Promise<string> {
    // Try to get workspace name from git remote URL
    try {
      const { stdout } = await execAsync("git remote get-url origin", {
        cwd: this.workspaceRoot,
      });

      const remoteUrl = stdout.trim();

      // Extract repo name from git URL
      // Examples:
      //   git@github.com:user/repo.git -> repo
      //   https://github.com/user/repo.git -> repo
      const match = remoteUrl.match(/\/([^/]+?)(?:\.git)?$/);
      if (match && match[1]) {
        return match[1];
      }
    } catch {
      // Git not available or not a git repo
    }

    // Fallback to directory name
    return path.basename(this.workspaceRoot);
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
      } else if (message.method === "clear_conversation") {
        this.handleClearConversation();
      } else if (message.method === "abort_generation") {
        this.handleAbortGeneration();
      } else if (message.method === "queue_files") {
        this.handleQueueFiles(message);
      } else if (message.method === "get_kb_status") {
        this.handleGetKBStatus(message);
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
        // Check if we can use agentic tools (works with both API key and CLI subscription)
        const authStatus = await this.claudeClient.getAuthStatus();
        
        if (authStatus.mode === "api_key" || authStatus.mode === "claude_cli") {
          // Use agentic tool loop - Claude decides which tools to use
          console.error(`[Agent Core] Using agentic tool execution mode (${authStatus.mode})`);
          
          const result = await this.toolExecutor.executeWithTools(
            request.content,
            this.conversationHistory
          );

          // Update conversation history
          this.conversationHistory = result.messages;

          // Log usage
          console.error(`[Agent Core] Completed in ${result.toolRounds} tool rounds`);
          console.error("[Agent Core] Tokens:", result.usage);

          // Send completion event
          this.sendEvent({
            type: "task_completed",
            success: true,
            result: {
              toolRounds: result.toolRounds,
              stopReason: result.stopReason,
              usage: result.usage,
            },
          });
        } else {
          // Fallback to manual orchestration only if no auth configured
          console.error("[Agent Core] No authentication configured, using manual orchestration");
          
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
        }
      } catch (error: any) {
        console.error("[Agent Core] Error handling message:", error);
        this.sendEvent({
          type: "error",
          error: {
            code: "SERVICE_UNAVAILABLE",
            message: error.message,
            suggestions: [
              "Check Claude authentication (requires API key for tool use)",
              "Check KB is running",
              "Try a different query",
            ],
            recoverable: true,
          },
        });
      }
    }
  }

  private handleClearConversation() {
    this.conversationHistory = [];
    this.sendEvent({
      type: "task_completed",
      success: true,
      result: { message: "Conversation cleared" },
    });
    console.error("[Agent Core] Conversation cleared");
  }
  
  private handleAbortGeneration() {
    console.error("[Agent Core] Abort generation requested");

    // Call abort on tool executor
    this.toolExecutor.abort();

    // Send task completed with abort status
    this.sendEvent({
      type: "task_completed",
      success: false,
      result: { message: "Generation aborted by user" },
    });
  }

  private async handleQueueFiles(message: Message) {
    try {
      const { files, priority = 5 } = message.params || {};

      if (!this.indexQueue) {
        const response: Message = {
          jsonrpc: "2.0",
          id: message.id,
          error: {
            code: -32603,
            message: "Index queue not initialized",
          },
        };
        process.stdout.write(JSON.stringify(response) + "\n");
        return;
      }

      if (!files || !Array.isArray(files)) {
        const response: Message = {
          jsonrpc: "2.0",
          id: message.id,
          error: {
            code: -32602,
            message: "Invalid params: files array required",
          },
        };
        process.stdout.write(JSON.stringify(response) + "\n");
        return;
      }

      // Queue the files
      this.indexQueue.enqueueBatch(files, priority);

      const response: Message = {
        jsonrpc: "2.0",
        id: message.id,
        result: {
          queued: files.length,
          queueDepth: this.indexQueue.getQueueDepth(),
        },
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

  private async handleGetKBStatus(message: Message) {
    try {
      const status = {
        initialized: this.indexQueue !== null,
        repoName: this.repoName,
        queueDepth: this.indexQueue?.getQueueDepth() || 0,
        isIndexing: this.indexQueue?.isIndexing() || false,
      };

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

  private generateRequestId(): string {
    return `req-${Date.now()}-${++this.requestIdCounter}`;
  }

  private sendEvent(event: AgentEvent) {
    // Add requestId if not already present for correlation/logging
    const eventWithId = {
      ...event,
      requestId: (event as any).requestId || this.generateRequestId(),
    };

    const message: Message = {
      jsonrpc: "2.0",
      method: "notify",
      params: eventWithId,
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