// vscode-extension/src/agent/bridge.ts
import { ChildProcess, spawn, SpawnOptionsWithoutStdio } from "child_process";
import * as vscode from "vscode";
import type {
  AgentEvent,
  ExtensionRequest,
  ConversationListItem,
  LoadConversationResult,
} from "../types/events";
import {
  StreamMessageReader,
  StreamMessageWriter,
  createMessageConnection,
  MessageConnection,
} from "vscode-jsonrpc/node";
import { AgentBridgeAdapter, AgentAuthOptions, AgentEnvironmentLayers } from "./types";
import type { AgentAuthStatusResponse } from "../types/auth";

export function mergeAgentEnvironment(
  baseEnv: NodeJS.ProcessEnv,
  layers?: AgentEnvironmentLayers
): NodeJS.ProcessEnv {
  const merged: NodeJS.ProcessEnv = { ...baseEnv };

  const applyLayer = (layer?: Record<string, string | undefined>) => {
    if (!layer) {
      return;
    }
    for (const [key, value] of Object.entries(layer)) {
      if (!key || typeof value !== "string") {
        continue;
      }
      merged[key] = value;
    }
  };

  // Merge order matters: defaults override inherited env, extension overrides beat defaults.
  applyLayer(layers?.defaults);
  applyLayer(layers?.overrides);

  return merged;
}

/**
 * AgentBridge manages communication with the Agent Core process via JSON-RPC.
 *
 * Phase 7 IPC Robustness Features:
 * - Uses vscode-jsonrpc for reliable message framing and backpressure handling
 * - Automatically recovers from crashes with exponential backoff (1s, 3s, 10s)
 * - Includes correlation IDs (requestId) in all notifications for event tracking
 * - Handles message chunking/boundary issues via StreamMessageReader
 */
export class AgentBridge implements AgentBridgeAdapter {
  private process: ChildProcess | null = null;
  private messageId = 0;
  private eventEmitter = new vscode.EventEmitter<AgentEvent>();
  private outputChannel: vscode.OutputChannel;
  private pendingRequests: Map<
    number,
    {
      resolve: (value: unknown) => void;
      reject: (error: unknown) => void;
      timeout?: NodeJS.Timeout;
    }
  > = new Map();
  private connection: MessageConnection | null = null;
  private restartAttempts = 0;
  private maxRestartAttempts = 3;
  private restartBackoffs = [1000, 3000, 10000]; // 1s, 3s, 10s
  private isShuttingDown = false;
  private restartTimers: NodeJS.Timeout[] = []; // Track restart timers for cleanup
  private readonly spawnImpl: (
    command: string,
    args?: readonly string[] | undefined,
    options?: SpawnOptionsWithoutStdio | undefined
  ) => ChildProcess;

  public readonly onEvent = this.eventEmitter.event;

  constructor(outputChannel: vscode.OutputChannel, spawnFn: typeof spawn = spawn) {
    this.outputChannel = outputChannel;
    this.spawnImpl = spawnFn;
  }

  async start(
    agentCorePath: string,
    extensionPath: string,
    options?: AgentAuthOptions
  ): Promise<void> {
    this.outputChannel.appendLine("[AgentBridge] Starting Agent Core...");
    this.isShuttingDown = false;

    // Find Bun
    const bunPath = await this.findBun();
    if (!bunPath) {
      throw new Error("Bun not found. Please install: https://bun.sh");
    }

    this.outputChannel.appendLine(`[AgentBridge] Using Bun at: ${bunPath}`);
    this.outputChannel.appendLine(`[AgentBridge] Agent Core path: ${agentCorePath}`);
    this.outputChannel.appendLine(`[AgentBridge] Extension path: ${extensionPath}`);

    // Spawn Agent Core with workspace root and extension path
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || process.cwd();
    const authLayer: Record<string, string | undefined> = {};
    if (options?.anthropicApiKey) {
      authLayer.ANTHROPIC_API_KEY = options.anthropicApiKey;
    }
    if (options?.openaiApiKey) {
      authLayer.OPENAI_API_KEY = options.openaiApiKey;
    }
    if (options?.kbApiKey) {
      authLayer.DOLPHIN_API_KEY = options.kbApiKey;
    }

    const env = mergeAgentEnvironment(process.env, {
      defaults: options?.env?.defaults,
      overrides: { ...options?.env?.overrides, ...authLayer },
    });

    if (authLayer.ANTHROPIC_API_KEY) {
      this.outputChannel.appendLine(
        "[AgentBridge] Anthropic API key provided via SecretStorage"
      );
    }

    if (authLayer.OPENAI_API_KEY) {
      this.outputChannel.appendLine("[AgentBridge] OpenAI API key provided via SecretStorage");
    }

    if (authLayer.DOLPHIN_API_KEY) {
      this.outputChannel.appendLine("[AgentBridge] KB API key provided for agent HTTP calls");
    }

    this.outputChannel.appendLine(
      `[AgentBridge] Provider env → provider=${env.DOLPHIN_LLM_PROVIDER ?? "inherit"}, model=${
        env.DOLPHIN_LLM_MODEL ?? "inherit"
      }`
    );

    this.process = this.spawnImpl(bunPath, ["run", agentCorePath, workspaceRoot, extensionPath], {
      stdio: ["pipe", "pipe", "pipe"],
      env,
    });

    // Set up JSON-RPC connection using vscode-jsonrpc
    if (this.process.stdout && this.process.stdin) {
      const reader = new StreamMessageReader(this.process.stdout);
      const writer = new StreamMessageWriter(this.process.stdin);
      this.connection = createMessageConnection(reader, writer);

      // Set up notification handler for agent events
      this.connection.onNotification("notify", (params: AgentEvent) => {
        const requestId = (params as Record<string, unknown>).requestId || "unknown";
        this.outputChannel.appendLine(
          `[AgentBridge] Event: ${params.type} (requestId: ${requestId})`
        );
        this.eventEmitter.fire(params);
      });

      // Set up error handler
      this.connection.onError((error: unknown) => {
        const errorMessage =
          Array.isArray(error) && error.length > 0 ? String(error[0]) : String(error);
        this.outputChannel.appendLine(`[AgentBridge] Connection error: ${errorMessage}`);
      });

      // Set up close handler
      this.connection.onClose(() => {
        this.outputChannel.appendLine("[AgentBridge] Connection closed");
        this.connection = null;
      });

      // Start listening
      this.connection.listen();
      this.outputChannel.appendLine("[AgentBridge] JSON-RPC connection established");
    }

    // Set up stderr handling (logs)
    this.process.stderr?.setEncoding("utf-8");
    this.process.stderr?.on("data", (chunk: string) => {
      this.outputChannel.append(chunk);
    });

    // Handle errors with auto-recovery
    this.process.on("error", (error) => {
      this.outputChannel.appendLine(`[AgentBridge] Process error: ${error.message}`);
      if (!this.isShuttingDown) {
        this.handleCrash(agentCorePath, extensionPath, options);
      }
    });

    // Handle exit with auto-recovery
    this.process.on("exit", (code, signal) => {
      this.outputChannel.appendLine(`[AgentBridge] Process exited: code=${code}, signal=${signal}`);

      // Clean up connection
      if (this.connection) {
        this.connection.dispose();
        this.connection = null;
      }

      // Reject all pending requests
      for (const [_id, pending] of this.pendingRequests.entries()) {
        if (pending.timeout) {
          clearTimeout(pending.timeout);
        }
        pending.reject(new Error("Agent process exited"));
      }
      this.pendingRequests.clear();

      if (code !== 0 && code !== null && !this.isShuttingDown) {
        this.handleCrash(agentCorePath, extensionPath, options);
      }
    });

    // Don't wait for ready - let agent start in background
    this.outputChannel.appendLine("[AgentBridge] Agent Core spawned, starting in background...");

    // Start listening for ready signal (non-blocking)
    this.waitForReady()
      .then(() => {
        this.outputChannel.appendLine("[AgentBridge] Agent Core ready!");
        // Reset restart attempts on successful start
        this.restartAttempts = 0;
      })
      .catch((error) => {
        this.outputChannel.appendLine(`[AgentBridge] Agent startup error: ${error.message}`);
      });
  }

  private async handleCrash(
    agentCorePath: string,
    extensionPath: string,
    options?: AgentAuthOptions
  ): Promise<void> {
    // Check if we're shutting down before doing anything
    if (this.isShuttingDown) {
      return;
    }

    if (this.restartAttempts >= this.maxRestartAttempts) {
      try {
        this.outputChannel.appendLine(
          `[AgentBridge] Maximum restart attempts (${this.maxRestartAttempts}) reached. Not restarting.`
        );
      } catch {
        // Output channel may be disposed
      }

      const action = await vscode.window.showErrorMessage(
        `Dolphin Agent crashed ${this.maxRestartAttempts} times and will not restart automatically. Check Output > Dolphin Agent for details.`,
        "Retry",
        "Cancel"
      );

      if (action === "Retry" && !this.isShuttingDown) {
        this.restartAttempts = 0;
        this.start(agentCorePath, extensionPath, options);
      }
      return;
    }

    const backoff = this.restartBackoffs[this.restartAttempts];
    this.restartAttempts++;

    try {
      this.outputChannel.appendLine(
        `[AgentBridge] Attempting restart ${this.restartAttempts}/${this.maxRestartAttempts} in ${backoff}ms...`
      );
    } catch {
      // Output channel may be disposed
    }

    vscode.window.showWarningMessage(
      `Dolphin Agent crashed. Restarting (attempt ${this.restartAttempts}/${this.maxRestartAttempts})...`
    );

    // Store timer so we can cancel it on shutdown
    const timer = setTimeout(() => {
      // Remove this timer from the list
      const index = this.restartTimers.indexOf(timer);
      if (index > -1) {
        this.restartTimers.splice(index, 1);
      }

      // Only restart if not shutting down
      if (!this.isShuttingDown) {
        this.start(agentCorePath, extensionPath, options);
      }
    }, backoff);

    this.restartTimers.push(timer);
  }

  private async findBun(): Promise<string | null> {
    const { exec } = require("child_process");
    const { promisify } = require("util");
    const execAsync = promisify(exec);

    try {
      // On Windows, use 'where' instead of 'which'
      const command = process.platform === "win32" ? "where bun" : "which bun";
      const { stdout } = await execAsync(command);
      return stdout.trim().split(/\r?\n/)[0]; // Take first result on Windows
    } catch {
      // Try common locations
      const fs = require("fs");
      const locations =
        process.platform === "win32"
          ? [
              `${process.env.LOCALAPPDATA}\\bun\\bin\\bun.exe`,
              `${process.env.USERPROFILE}\\.bun\\bin\\bun.exe`,
            ]
          : ["/usr/local/bin/bun", "/opt/homebrew/bin/bun", `${process.env.HOME}/.bun/bin/bun`];

      for (const loc of locations) {
        try {
          if (fs.existsSync(loc)) {
            return loc;
          }
        } catch {}
      }
    }

    return null;
  }

  private async sendRequest(method: string, params?: unknown, timeout = 20000): Promise<unknown> {
    if (!this.connection) {
      throw new Error("JSON-RPC connection not established");
    }

    const id = ++this.messageId;
    this.outputChannel.appendLine(`[AgentBridge] Sending request: ${method} (id: ${id})`);

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        const pending = this.pendingRequests.get(id);
        if (pending) {
          this.pendingRequests.delete(id);
          reject(new Error(`Request timeout: ${method}`));
        }
      }, timeout);

      this.pendingRequests.set(id, { resolve, reject, timeout: timer });

      // Send via connection (vscode-jsonrpc handles backpressure internally)
      this.connection!.sendRequest(method, params)
        .then((result: unknown) => {
          const pending = this.pendingRequests.get(id);
          if (pending) {
            if (pending.timeout) {
              clearTimeout(pending.timeout);
            }
            this.pendingRequests.delete(id);
            resolve(result);
          }
        })
        .catch((error: unknown) => {
          const pending = this.pendingRequests.get(id);
          if (pending) {
            if (pending.timeout) {
              clearTimeout(pending.timeout);
            }
            this.pendingRequests.delete(id);
            reject(error);
          }
        });
    });
  }

  private async sendNotification(method: string, params?: unknown): Promise<void> {
    if (!this.connection) {
      throw new Error("JSON-RPC connection not established");
    }

    this.outputChannel.appendLine(`[AgentBridge] Sending notification: ${method}`);
    // vscode-jsonrpc handles backpressure and queuing internally
    this.connection.sendNotification(method, params);
  }

  async sendMessage(content: string, mode?: "code" | "architect"): Promise<void> {
    const request: ExtensionRequest = {
      type: "send_message",
      messageId: `msg-${this.messageId}`,
      content,
      mode,
    };

    await this.sendNotification("send_message", request);
  }

  async getAuthStatus(): Promise<AgentAuthStatusResponse> {
    return (await this.sendRequest("get_auth_status", undefined, 3000)) as AgentAuthStatusResponse;
  }

  async abortGeneration(): Promise<void> {
    await this.sendNotification("abort_generation");
  }

  async clearConversation(): Promise<void> {
    await this.sendNotification("clear_conversation");
  }

  // Phase 5: Conversation Management Methods

  async listConversations(): Promise<ConversationListItem[]> {
    const result = (await this.sendRequest("list_conversations", undefined, 3000)) as {
      conversations?: ConversationListItem[];
    };
    return result.conversations || [];
  }

  async loadConversation(conversationId: string): Promise<LoadConversationResult> {
    const result = await this.sendRequest("load_conversation", { conversationId }, 5000);
    return result as LoadConversationResult;
  }

  async deleteConversation(conversationId: string): Promise<void> {
    await this.sendRequest("delete_conversation", { conversationId }, 3000);
  }

  async renameConversation(conversationId: string, newTitle: string): Promise<void> {
    await this.sendRequest("rename_conversation", { conversationId, newTitle }, 3000);
  }

  /**
   * Wait for agent to be ready (public helper for tests and consumers)
   */
  public async waitForReady(timeout = 60000): Promise<void> {
    return new Promise((resolve, reject) => {
      // Check if already shutting down
      if (this.isShuttingDown) {
        reject(new Error("Agent bridge is shutting down"));
        return;
      }

      const timer = setTimeout(() => {
        disposable.dispose();
        reject(new Error("Agent Core did not become ready within 60s"));
      }, timeout);

      const disposable = this.onEvent((event) => {
        // Double-check we're not shutting down when event arrives
        if (this.isShuttingDown) {
          clearTimeout(timer);
          disposable.dispose();
          reject(new Error("Agent bridge is shutting down"));
          return;
        }

        if (event.type === "agent_ready") {
          clearTimeout(timer);
          disposable.dispose();
          resolve();
        }
      });
    });
  }

  shutdown(): void {
    this.isShuttingDown = true;

    // Try to log shutdown, but don't fail if channel is disposed
    try {
      this.outputChannel.appendLine("[AgentBridge] Shutting down...");
    } catch {
      // Output channel may already be disposed in tests
    }

    // Cancel all restart timers to prevent async operations after disposal
    for (const timer of this.restartTimers) {
      clearTimeout(timer);
    }
    this.restartTimers = [];

    // Dispose connection first
    if (this.connection) {
      this.connection.dispose();
      this.connection = null;
    }

    // Clean up all pending requests
    for (const [_id, pending] of this.pendingRequests.entries()) {
      if (pending.timeout) {
        clearTimeout(pending.timeout);
      }
      pending.reject(new Error("Agent bridge is shutting down"));
    }
    this.pendingRequests.clear();

    // Dispose event emitter to prevent new event listeners
    this.eventEmitter.dispose();

    // Kill the process
    this.process?.kill("SIGTERM");
    this.process = null;
  }
}
