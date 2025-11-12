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
import type { Message } from "./llm/claude-tool-executor";
import { DiscoveryOrchestrator } from "./orchestration/discovery-phase";
import { PlanningPhase, type PlanningSession } from "./orchestration/planning-phase";
import { isConfirmation } from "./orchestration/markdown-plan-parser";
import type { DiscoveryConfig, DiscoveryResult } from "./orchestration/types";

const execAsync = promisify(exec);

interface Message {
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
  private capabilities = ["kb_search", "file_operations", "planning", "claude_auth", "agentic_tools", "kb_auto_sync", "conversation_persistence", "architect_mode"];
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

  // Phase 5: Conversation persistence
  private conversationStore: ConversationStore;
  private currentConversationId: string | null = null;
  private isFirstUserMessage = true;
  private loadedConversationId: string | null = null; // Track original conversation for delayed branching

  // IPC Transport
  private transport: IPCTransport;

  // EP-11: Architect mode orchestration (Discovery → Planning)
  private discoveryOrchestrator: DiscoveryOrchestrator | null = null;
  private planningPhase: PlanningPhase | null = null;

  // EP-11: Planning session state
  private activePlanningSession: PlanningSession | null = null;
  private currentArchitectPrompt: string | null = null;  // Store original prompt for planning

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
        role: msg.role,
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

    // EP-11: Initialize Discovery Orchestrator for architect mode
    const discoveryConfig: DiscoveryConfig = {
      maxQueries: 5,
      maxResultsPerQuery: 8,  // Increased to get more diverse results
      includeGraphContext: true,
      confidenceThreshold: 0.01,  // Lowered to 0.01 for RRF scores (typically 0.01-0.05 after fusion, vs raw semantic 0.1-0.4)
      timeoutMs: 5000
    };
    this.discoveryOrchestrator = new DiscoveryOrchestrator(
      this.mcpClient,
      this.claudeClient,
      discoveryConfig
    );
    console.error("[Agent Core] Discovery Orchestrator initialized");

    // EP-11: Initialize Planning phase
    this.planningPhase = new PlanningPhase(this.claudeClient, this.workspaceRoot);
    console.error("[Agent Core] Planning phase initialized");

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

        if (contentLength === undefined || Number.isNaN(contentLength)) {
          console.error(`[Agent Core] Missing Content-Length header: ${header}`);
          buffer = buffer.slice(headerEndIndex + delimiterLength);
          continue;
        }

        const messageStartIndex = headerEndIndex + delimiterLength;
        const messageEndIndex = messageStartIndex + contentLength;

        if (buffer.length < messageEndIndex) {
          // Wait for the rest of the message to arrive
          break;
        }

        const messageBuffer = buffer.slice(messageStartIndex, messageEndIndex);
        buffer = buffer.slice(messageEndIndex);

        if (messageBuffer.length > 0) {
          this.handleMessage(messageBuffer.toString("utf-8"));
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

        // EP-11: Check for active planning session (user refining plan)
        if (this.activePlanningSession && request.mode === "code") {
          // Clear session when user explicitly switches to code mode
          this.clearPlanningSession();
          // Fall through to normal code mode handling
        } else if (this.activePlanningSession && request.mode !== "architect") {
          await this.handlePlanningInteraction(request.content);
          return;
        }

        // EP-11: Check for architect mode
        if (request.mode === "architect") {
          await this.handleArchitectMode(request);
          return;
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

  /**
   * EP-11: Handle architect mode requests
   * Runs the 3-phase orchestration workflow starting with discovery
   */
  private async handleArchitectMode(request: ExtensionRequest & { type: "send_message" }) {
    if (!this.discoveryOrchestrator) {
      console.error("[Architect Mode] Discovery orchestrator not initialized");
      this.sendEvent({
        type: "error",
        error: {
          code: "SERVICE_UNAVAILABLE",
          message: "Architect mode not available",
          suggestions: ["Restart the agent", "Check KB service"],
          recoverable: true,
        },
      });
      return;
    }

    if (!this.repoName) {
      console.error("[Architect Mode] Workspace not initialized");
      this.sendEvent({
        type: "error",
        error: {
          code: "SERVICE_UNAVAILABLE",
          message: "Workspace not initialized",
          suggestions: ["Ensure KB is running", "Restart agent"],
          recoverable: true,
        },
      });
      return;
    }

    console.error("[Architect Mode] Starting architect mode workflow...");

    try {
      // Send "thinking" indicator
      this.sendEvent({
        type: "content_delta",
        delta: "# 🏗️ Architect Mode - Discovery Phase\n\nAnalyzing your request and searching the codebase...\n\n"
      });

      // Phase 1: Discovery
      const discoveryResult = await this.discoveryOrchestrator.execute({
        userQuery: request.content,
        workspaceRoot: this.workspaceRoot,
        repoName: this.repoName,
        conversationHistory: this.conversationHistory
      });

      // Format and send discovery results
      const discoveryMessage = this.formatDiscoveryResults(discoveryResult);

      this.sendEvent({
        type: "content_delta",
        delta: discoveryMessage
      });

      console.error("[Architect Mode] Discovery phase completed successfully");

      // Phase 2: Planning (interactive conversation)
      if (!this.planningPhase) {
        throw new Error("Planning phase not initialized");
      }

      this.sendEvent({
        type: "content_delta",
        delta: "\n## 📋 Planning\n\nAnalyzing code and creating implementation plan...\n\n"
      });

      const { session, response } = await this.planningPhase.start(
        request.content,
        discoveryResult
      );

      // Send Claude's response (could be questions or a plan)
      this.sendEvent({
        type: "content_delta",
        delta: response
      });

      // Store session for refinement
      this.activePlanningSession = session;
      this.currentArchitectPrompt = request.content;

      this.sendEvent({
        type: "content_delta",
        delta: "\n\n*Reply with feedback to refine the plan, or say 'confirm' to save it.*\n"
      });

      // Update conversation history
      this.conversationHistory.push({
        role: "user",
        content: request.content
      });

      const fullResponse = discoveryMessage + "\n\n" + response;

      this.conversationHistory.push({
        role: "assistant",
        content: fullResponse
      });

      // Save conversation
      if (this.currentConversationId) {
        await this.saveCurrentConversation();
      }

      // Send completion event
      this.sendEvent({
        type: "task_completed",
        success: true,
        result: {
          mode: "architect",
          phase: "planning",
          confidence: discoveryResult.confidence,
          chunksFound: discoveryResult.retrievedChunks.length,
          hasActivePlanningSession: true
        },
      });

      console.error("[Architect Mode] Planning phase started successfully");
    } catch (error: any) {
      console.error("[Architect Mode] Error:", error);
      this.sendEvent({
        type: "error",
        error: {
          code: "SERVICE_UNAVAILABLE",
          message: error.message,
          suggestions: [
            "Check KB service is running",
            "Try a more specific query",
            "Check network connection"
          ],
          recoverable: true,
        },
      });
    }
  }

  /**
   * Clear active planning session
   */
  private clearPlanningSession() {
    console.error("[Planning] Clearing planning session");
    this.activePlanningSession = null;
    this.currentArchitectPrompt = null;
  }

  /**
   * Handle planning interaction - refine or confirm plan
   */
  private async handlePlanningInteraction(userMessage: string) {
    if (!this.activePlanningSession || !this.planningPhase || !this.currentArchitectPrompt) {
      console.error("[Planning] No active planning session");
      return;
    }

    try {
      // Check if user is confirming the plan using natural language detection
      if (isConfirmation(userMessage) && this.activePlanningSession.parsedPlan) {
        // Save and confirm plan
        this.sendEvent({
          type: "content_delta",
          delta: "\n## ✅ Confirming Plan\n\nSaving plan to `.dolphin/state/plans/`...\n\n"
        });

        const savedPlan = await this.planningPhase.confirm(
          this.activePlanningSession,
          this.currentArchitectPrompt,
          this.workspaceRoot
        );

        this.sendEvent({
          type: "content_delta",
          delta: `**Plan saved!**\n\n`
        });

        this.sendEvent({
          type: "content_delta",
          delta: `- **Plan ID**: \`${savedPlan.planId}\`\n`
        });

        this.sendEvent({
          type: "content_delta",
          delta: `- **Location**: \`${savedPlan.path}\`\n`
        });

        this.sendEvent({
          type: "content_delta",
          delta: `- **Tasks**: ${savedPlan.parsedPlan.tasks.length}\n\n`
        });

        this.sendEvent({
          type: "content_delta",
          delta: "*The plan is now ready for implementation!*\n"
        });

        // Clear planning session
        this.activePlanningSession = null;
        this.currentArchitectPrompt = null;

        // Update conversation
        this.conversationHistory.push({
          role: "user",
          content: userMessage
        });

        this.conversationHistory.push({
          role: "assistant",
          content: `Plan confirmed and saved to ${savedPlan.path}`
        });

        if (this.currentConversationId) {
          await this.saveCurrentConversation();
        }

        this.sendEvent({
          type: "task_completed",
          success: true,
          result: {
            mode: "architect",
            phase: "planning_confirmed",
            planId: savedPlan.planId,
            planPath: savedPlan.path
          }
        });

        return;
      }

      // Otherwise, refine the plan
      this.sendEvent({
        type: "content_delta",
        delta: "\n## 🔄 Refining Plan\n\nUpdating based on your feedback...\n\n"
      });

      const { session, response } = await this.planningPhase.refine(
        this.activePlanningSession,
        userMessage
      );

      // Send Claude's updated response
      this.sendEvent({
        type: "content_delta",
        delta: response
      });

      this.sendEvent({
        type: "content_delta",
        delta: "\n\n*Review the updated plan. Reply with more feedback or say 'confirm' to save it.*\n"
      });

      // Update session
      this.activePlanningSession = session;

      // Update conversation
      this.conversationHistory.push({
        role: "user",
        content: userMessage
      });

      this.conversationHistory.push({
        role: "assistant",
        content: response
      });

      if (this.currentConversationId) {
        await this.saveCurrentConversation();
      }

      this.sendEvent({
        type: "task_completed",
        success: true,
        result: {
          mode: "architect",
          phase: "planning_refined"
        }
      });

    } catch (error: any) {
      console.error("[Planning] Error during interaction:", error);
      this.sendEvent({
        type: "error",
        error: {
          code: "PLANNING_ERROR",
          message: error.message,
          suggestions: ["Try rephrasing your feedback", "Say 'cancel' to exit planning mode"],
          recoverable: true
        }
      });
    }
  }

  /**
   * Format discovery results into a readable message
   */
  private formatDiscoveryResults(result: any): string {
    const parts: string[] = [];

    parts.push("## Discovery Results\n");
    parts.push(result.summary);
    parts.push(`\n**Confidence**: ${(result.confidence * 100).toFixed(0)}%`);
    parts.push(`**Execution Time**: ${result.executionTimeMs}ms\n`);

    // Show queries executed
    if (result.queries && result.queries.length > 0) {
      parts.push("\n### Strategic Queries");
      result.queries.forEach((q: any, i: number) => {
        parts.push(`${i + 1}. **[${q.strategy}]** "${q.text}"`);
      });
      parts.push("");
    }

    // Show gaps identified
    if (result.gaps && result.gaps.length > 0) {
      parts.push("\n### Information Gaps");
      result.gaps.forEach((gap: string) => {
        parts.push(`- ${gap}`);
      });
      parts.push("");
    }

    // Show top results
    if (result.retrievedChunks && result.retrievedChunks.length > 0) {
      parts.push("\n### Relevant Code Found\n");

      const topChunks = result.retrievedChunks.slice(0, 5);
      topChunks.forEach((chunk: any, i: number) => {
        const symbol = chunk.symbol_name ? ` - \`${chunk.symbol_name}\`` : "";
        parts.push(`${i + 1}. **${chunk.path}**#L${chunk.start_line}-L${chunk.end_line}${symbol}`);
        parts.push(`   Score: ${(chunk.score * 100).toFixed(0)}%`);
      });

      if (result.retrievedChunks.length > 5) {
        parts.push(`\n_...and ${result.retrievedChunks.length - 5} more results_`);
      }
    }

    // Show graph context summary
    if (result.graphContext) {
      parts.push("\n### Code Graph Context");
      parts.push(`- **Nodes**: ${result.graphContext.nodes.length} code entities`);
      parts.push(`- **Relationships**: ${result.graphContext.relationships.length} connections`);

      // Summarize relationship types
      const relTypes = new Map();
      for (const rel of result.graphContext.relationships) {
        relTypes.set(rel.type, (relTypes.get(rel.type) || 0) + 1);
      }
      if (relTypes.size > 0) {
        const typeSummary = Array.from(relTypes.entries())
          .map(([type, count]: [string, number]) => `${count} ${type}`)
          .join(", ");
        parts.push(`  - ${typeSummary}`);
      }
    }

    return parts.join("\n");
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
