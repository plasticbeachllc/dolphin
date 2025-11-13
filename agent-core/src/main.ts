// agent-core/src/main.ts
import type { AgentEvent, ExtensionRequest } from "../../shared/types/events";
import { MCPClient } from "./mcp/client";
import { KBManager } from "./kb/manager";
import { IndexQueue } from "./kb/index-queue";
import { ClaudeClient } from "./llm/claude-client";
import { ClaudeToolExecutor } from "./llm/claude-tool-executor";
import { BasicPlanner } from "./planner/basic-planner";
import { ConversationStore } from "./storage/conversation-store";
import type { Conversation, ConversationMessage } from "../../shared/types/state";
import { IPCTransport } from "../../shared/ipc";
import * as path from "path";
import * as fs from "fs";
import { exec } from "child_process";
import { promisify } from "util";
import { randomBytes } from "crypto";
import type { Message as LLMMessage } from "./llm/claude-tool-executor";

const execAsync = promisify(exec);

interface IPCMessage {
  jsonrpc: "2.0";
  id?: number;
  method?: string;
  params?: any;
  result?: any;
  error?: any;
}

/**
 * AgentCore handles the main agent logic and IPC with the VS Code extension.
 *
 * IPC Implementation:
 * - Uses vscode-jsonrpc for robust message framing (LSP-style)
 * - Supports pluggable serialization (JSON/MessagePack via DOLPHIN_IPC_FORMAT env var)
 * - Security hardening: payload size limits, buffer limits, max pending requests
 * - Correlation IDs (requestId) added to all notifications for event tracking
 */
class AgentCore {
  private version = "0.1.0";
  private capabilities = ["kb_search", "file_operations", "planning", "claude_auth", "agentic_tools", "kb_auto_sync", "conversation_persistence"];
  private mcpClient: MCPClient;
  private kbManager: KBManager;
  private indexQueue: IndexQueue | null = null;
  private claudeClient: ClaudeClient;
  private toolExecutor: ClaudeToolExecutor;
  private planner: BasicPlanner;
  private conversationHistory: LLMMessage[] = [];
  private workspaceRoot: string;
  private extensionPath?: string;
  private repoName: string | null = null;
  private requestIdCounter = 0;

  // Phase 5: Conversation persistence
  private conversationStore: ConversationStore;
  private currentConversationId: string | null = null;
  private isFirstUserMessage = true;
  private loadedConversationId: string | null = null; // Track original conversation for delayed branching

  // IPC Transport
  private transport: IPCTransport;

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

    // Initialize conversation store
    this.conversationStore = new ConversationStore(workspaceRoot);

    // Initialize IPC transport
    this.transport = new IPCTransport({
      input: process.stdin,
      output: process.stdout,
      serializationFormat: (process.env.DOLPHIN_IPC_FORMAT as any) || 'json',
      security: {
        maxMessageSize: 100 * 1024 * 1024, // 100 MB
        maxBufferSize: 50 * 1024 * 1024,    // 50 MB
        maxPendingRequests: 1000,
      },
      enableMetrics: process.env.DOLPHIN_IPC_METRICS === 'true',
    });

    // Register method handlers
    this.setupIPCHandlers();
  }

  /**
   * Setup IPC method handlers
   */
  private setupIPCHandlers() {
    this.transport.onMethod('send_message', async (params) => {
      await this.handleSendMessage(params as ExtensionRequest);
      return { success: true };
    });

    this.transport.onMethod('get_auth_status', async () => {
      return await this.claudeClient.getAuthStatus();
    });

    this.transport.onMethod('clear_conversation', async () => {
      this.handleClearConversation();
      return { success: true };
    });

    this.transport.onMethod('abort_generation', async () => {
      this.handleAbortGeneration();
      return { success: true };
    });

    this.transport.onMethod('queue_files', async (params) => {
      const { files, priority = 5 } = params || {};

      if (!this.indexQueue) {
        throw new Error('Index queue not initialized');
      }

      if (!files || !Array.isArray(files)) {
        throw new Error('Invalid params: files array required');
      }

      this.indexQueue.enqueueBatch(files, priority);

      return {
        queued: files.length,
        queueDepth: this.indexQueue.getQueueDepth(),
      };
    });

    this.transport.onMethod('get_kb_status', async () => {
      return {
        initialized: this.indexQueue !== null,
        repoName: this.repoName,
        queueDepth: this.indexQueue?.getQueueDepth() || 0,
        isIndexing: this.indexQueue?.isIndexing() || false,
      };
    });

    this.transport.onMethod('list_conversations', async () => {
      const conversations = await this.conversationStore.listConversationsWithMetadata();
      return { conversations };
    });

    this.transport.onMethod('load_conversation', async (params) => {
      const { conversationId } = params || {};

      if (!conversationId) {
        throw new Error('Invalid params: conversationId required');
      }

      const conversation = await this.conversationStore.loadConversation(conversationId);

      if (!conversation) {
        throw new Error(`Conversation not found: ${conversationId}`);
      }

      // Don't branch yet - just load into memory
      this.loadedConversationId = conversationId;
      this.isFirstUserMessage = true;

      // Restore conversation history
      this.conversationHistory = conversation.messages.map((msg) => ({
        role: msg.role as "user" | "assistant",
        content: msg.content,
      }));

      return {
        conversation: conversation,
        branchInfo: null,
      };
    });

    this.transport.onMethod('delete_conversation', async (params) => {
      const { conversationId } = params || {};

      if (!conversationId) {
        throw new Error('Invalid params: conversationId required');
      }

      await this.conversationStore.deleteConversation(conversationId);

      // Clear if it was the current conversation
      if (this.currentConversationId === conversationId) {
        this.currentConversationId = null;
        this.conversationHistory = [];
        this.isFirstUserMessage = true;
      }

      return { success: true };
    });

    this.transport.onMethod('rename_conversation', async (params) => {
      const { conversationId, newTitle } = params || {};

      if (!conversationId || !newTitle) {
        throw new Error('Invalid params: conversationId and newTitle required');
      }

      await this.conversationStore.updateMetadata(conversationId, {
        title: newTitle,
      });

      return { success: true };
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

    // Handle process signals
    process.on("SIGTERM", () => this.shutdown());
    process.on("SIGINT", () => this.shutdown());

    // Send ready signal
    this.sendEvent({
      type: "agent_ready",
      version: this.version,
      capabilities: this.capabilities,
    });

    const ipcFormat = this.transport.getSerializationFormat();
    console.error(`[Agent Core] Ready and listening on stdin (using ${ipcFormat} serialization)`);
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
          type: "tool_call_progress" as const,
          toolId: "kb-indexing",
          chunk: `Indexed ${count} files`,
        });
      });

      this.indexQueue.on("complete", () => {
        console.error("[Agent Core] Index queue complete");
        this.sendEvent({
          type: "tool_call_completed" as const,
          toolId: "kb-indexing",
          result: { success: true },
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


  private async handleSendMessage(request: ExtensionRequest) {
    if (request.type === "send_message") {
      try {
        // Phase 5: Create conversation or branch on first user message
        if (this.isFirstUserMessage) {
          if (this.loadedConversationId) {
            // Branch the loaded conversation now that user is sending a message
            await this.branchLoadedConversation();
          } else {
            // Create new conversation
            await this.createNewConversation(request.content);
          }
          this.isFirstUserMessage = false;
        }
        
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

          // Phase 5: Auto-save conversation after tool execution rounds
          if (this.currentConversationId) {
            await this.saveCurrentConversation(result.usage);
          }

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
    this.currentConversationId = null;
    this.loadedConversationId = null;
    this.isFirstUserMessage = true;
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

  // Phase 5: Conversation Management Methods
  
  private generateConversationId(): string {
    const timestamp = Date.now();
    const shortId = randomBytes(3).toString("hex");
    return `conv_${timestamp}_${shortId}`;
  }
  
  private generateConversationTitle(firstUserMessage: string): string {
    // Use first 50 chars of first user message
    const maxLength = 50;
    const trimmed = firstUserMessage.trim();
    if (trimmed.length <= maxLength) {
      return trimmed;
    }
    return trimmed.substring(0, maxLength) + "...";
  }
  
  private async branchLoadedConversation(): Promise<void> {
    if (!this.loadedConversationId) {
      console.error("[Agent Core] No loaded conversation to branch");
      return;
    }
    
    const originalConversation = await this.conversationStore.loadConversation(this.loadedConversationId);
    if (!originalConversation) {
      console.error(`[Agent Core] Failed to load conversation: ${this.loadedConversationId}`);
      return;
    }
    
    // Create branch
    const branchId = this.generateConversationId();
    const branchConversation = await this.conversationStore.branchConversation(
      this.loadedConversationId,
      originalConversation.messages[originalConversation.messages.length - 1]?.id || "root",
      branchId
    );
    
    // Set as current conversation
    this.currentConversationId = branchId;
    this.loadedConversationId = null; // Clear the loaded conversation tracking
    
    console.error(`[Agent Core] Branched conversation ${this.loadedConversationId} to ${branchId} on first message`);
  }
  
  private async createNewConversation(firstUserMessage: string): Promise<void> {
    const conversationId = this.generateConversationId();
    const title = this.generateConversationTitle(firstUserMessage);
    const now = new Date().toISOString();
    
    this.currentConversationId = conversationId;
    
    const conversation: Conversation = {
      schema_version: "1.0",
      conversation: {
        id: conversationId,
        created_at: now,
        updated_at: now,
        workspace_root: this.workspaceRoot,
      },
      metadata: {
        title,
        files: [],
        token_count: 0,
        pinned: false,
        last_active_at: now,
      },
      messages: [],
      summaries: [],
    };
    
    await this.conversationStore.saveConversation(conversation);
    console.error(`[Agent Core] Created new conversation: ${conversationId} - "${title}"`);
  }
  
  private async saveCurrentConversation(usage?: { inputTokens: number; outputTokens: number; cacheReadTokens?: number; cacheWriteTokens?: number }): Promise<void> {
    if (!this.currentConversationId) {
      console.error("[Agent Core] No active conversation to save");
      return;
    }

    const conversation = await this.conversationStore.loadConversation(this.currentConversationId);
    if (!conversation) {
      console.error(`[Agent Core] Failed to load conversation: ${this.currentConversationId}`);
      return;
    }

    const existingMessageCount = conversation.messages.length;
    const currentMessageCount = this.conversationHistory.length;

    // Only process new messages (those not already saved)
    if (currentMessageCount > existingMessageCount) {
      const newMessages = this.conversationHistory.slice(existingMessageCount);

      // Convert new Message[] to ConversationMessage[]
      const newConversationMessages: ConversationMessage[] = newMessages.map((msg, index) => {
        let content = "";
        if (typeof msg.content === "string") {
          content = msg.content;
        } else if (Array.isArray(msg.content)) {
          // Extract text from content blocks
          content = msg.content
            .filter((block: any) => block.type === "text")
            .map((block: any) => block.text)
            .join("\n");
        }

        const conversationMessage: ConversationMessage = {
          id: `msg_${Date.now()}_${existingMessageCount + index}`,
          role: msg.role,
          content,
          timestamp: new Date().toISOString(),
          pinned: false,
        };

        // Attach tokens to the last message (assistant's response) if usage data is provided
        if (usage && index === newMessages.length - 1 && msg.role === "assistant") {
          conversationMessage.tokens = {
            input: usage.inputTokens,
            output: usage.outputTokens,
            cacheRead: usage.cacheReadTokens,
            cacheWrite: usage.cacheWriteTokens,
          };
        }

        return conversationMessage;
      });

      // Append new messages to existing ones
      conversation.messages.push(...newConversationMessages);
    }

    conversation.conversation.updated_at = new Date().toISOString();

    // Update metadata with ACCUMULATED token count
    const currentTotal = conversation.metadata?.token_count || 0;
    const newTokens = usage ? usage.inputTokens + usage.outputTokens : 0;
    const lastActiveAt = new Date().toISOString();
    const updatedMetadata = {
      ...(conversation.metadata ?? {}),
      last_active_at: lastActiveAt,
      token_count: currentTotal + newTokens,
    };

    await this.conversationStore.updateMetadata(
      this.currentConversationId,
      updatedMetadata,
    );

    conversation.metadata = updatedMetadata;

    await this.conversationStore.saveConversation(conversation);
    console.error(`[Agent Core] Saved conversation: ${this.currentConversationId} (${conversation.messages.length} messages, ${currentTotal + newTokens} total tokens)`);
  }
  
  /**
   * Generate a unique request ID for correlation/logging.
   */
  private generateRequestId(): string {
    return `req-${Date.now()}-${++this.requestIdCounter}`;
  }

  /**
   * Send an event notification to the extension.
   * Automatically adds correlation ID (requestId) for event tracking.
   */
  private sendEvent(event: AgentEvent) {
    // Add requestId if not already present for correlation/logging
    const eventWithId = {
      ...event,
      requestId: (event as any).requestId || this.generateRequestId(),
    };

    // Send notification via transport (fire-and-forget)
    this.transport.notify("notify", eventWithId).catch(error => {
      console.error("[Agent Core] Error sending event:", error);
    });
  }

  private shutdown() {
    console.error("[Agent Core] Shutting down...");
    this.kbManager.shutdown();
    this.mcpClient.shutdown();
    this.transport.dispose();
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
