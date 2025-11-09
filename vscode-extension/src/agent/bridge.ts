// vscode-extension/src/agent/bridge.ts
import { ChildProcess, spawn } from "child_process";
import * as vscode from "vscode";
import type { AgentEvent, ExtensionRequest } from "../types/events";
import {
  StreamMessageReader,
  StreamMessageWriter,
  createMessageConnection,
  MessageConnection,
  NotificationType,
  RequestType,
} from "vscode-jsonrpc/node";

interface Message {
  jsonrpc: "2.0";
  id?: number;
  method?: string;
  params?: any;
  result?: any;
  error?: {
    code: number;
    message: string;
    data?: any;
  };
}

interface WriteQueueItem {
  data: string;
  resolve: () => void;
  reject: (error: Error) => void;
}

export class AgentBridge {
  private process: ChildProcess | null = null;
  private messageId = 0;
  private eventEmitter = new vscode.EventEmitter<AgentEvent>();
  private outputChannel: vscode.OutputChannel;
  private pendingRequests: Map<number, { resolve: (value: any) => void; reject: (error: any) => void; timeout?: NodeJS.Timeout }> = new Map();
  private connection: MessageConnection | null = null;
  private writeQueue: WriteQueueItem[] = [];
  private isWriting = false;
  private restartAttempts = 0;
  private maxRestartAttempts = 3;
  private restartBackoffs = [1000, 3000, 10000]; // 1s, 3s, 10s
  private isShuttingDown = false;

  public readonly onEvent = this.eventEmitter.event;

  constructor() {
    this.outputChannel = vscode.window.createOutputChannel("Dolphin Agent");
  }

  async start(agentCorePath: string, extensionPath: string, apiKey?: string): Promise<void> {
    this.outputChannel.appendLine("[AgentBridge] Starting Agent Core...");
    this.isShuttingDown = false;

    // Find Bun
    const bunPath = await this.findBun();
    if (!bunPath) {
      throw new Error("Bun not found. Please install: https://bun.sh");
    }

    this.outputChannel.appendLine(`[AgentBridge] Using Bun at: ${bunPath}`);
    this.outputChannel.appendLine(
      `[AgentBridge] Agent Core path: ${agentCorePath}`
    );
    this.outputChannel.appendLine(
      `[AgentBridge] Extension path: ${extensionPath}`
    );

    // Spawn Agent Core with workspace root and extension path
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || process.cwd();
    const env = { ...process.env };

    // Add API key to environment if provided
    if (apiKey) {
      env.ANTHROPIC_API_KEY = apiKey;
      this.outputChannel.appendLine("[AgentBridge] API key provided via SecretStorage");
    }

    this.process = spawn(bunPath, ["run", agentCorePath, workspaceRoot, extensionPath], {
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
        const requestId = (params as any).requestId || "unknown";
        this.outputChannel.appendLine(`[AgentBridge] Event: ${params.type} (requestId: ${requestId})`);
        this.eventEmitter.fire(params);
      });

      // Set up error handler
      this.connection.onError((error) => {
        this.outputChannel.appendLine(`[AgentBridge] Connection error: ${error[0]}`);
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
      this.outputChannel.appendLine(
        `[AgentBridge] Process error: ${error.message}`
      );
      if (!this.isShuttingDown) {
        this.handleCrash(agentCorePath, extensionPath, apiKey);
      }
    });

    // Handle exit with auto-recovery
    this.process.on("exit", (code, signal) => {
      this.outputChannel.appendLine(
        `[AgentBridge] Process exited: code=${code}, signal=${signal}`
      );

      // Clean up connection
      if (this.connection) {
        this.connection.dispose();
        this.connection = null;
      }

      // Reject all pending requests
      for (const [id, pending] of this.pendingRequests.entries()) {
        if (pending.timeout) {
          clearTimeout(pending.timeout);
        }
        pending.reject(new Error("Agent process exited"));
      }
      this.pendingRequests.clear();

      if (code !== 0 && code !== null && !this.isShuttingDown) {
        this.handleCrash(agentCorePath, extensionPath, apiKey);
      }
    });

    // Don't wait for ready - let agent start in background
    this.outputChannel.appendLine(
      "[AgentBridge] Agent Core spawned, starting in background..."
    );

    // Start listening for ready signal (non-blocking)
    this.waitForReady().then(() => {
      this.outputChannel.appendLine("[AgentBridge] Agent Core ready!");
      // Reset restart attempts on successful start
      this.restartAttempts = 0;
    }).catch((error) => {
      this.outputChannel.appendLine(`[AgentBridge] Agent startup error: ${error.message}`);
    });
  }

  private async handleCrash(agentCorePath: string, extensionPath: string, apiKey?: string): Promise<void> {
    if (this.restartAttempts >= this.maxRestartAttempts) {
      this.outputChannel.appendLine(
        `[AgentBridge] Maximum restart attempts (${this.maxRestartAttempts}) reached. Not restarting.`
      );
      const action = await vscode.window.showErrorMessage(
        `Dolphin Agent crashed ${this.maxRestartAttempts} times and will not restart automatically. Check Output > Dolphin Agent for details.`,
        "Retry",
        "Cancel"
      );

      if (action === "Retry") {
        this.restartAttempts = 0;
        this.start(agentCorePath, extensionPath, apiKey);
      }
      return;
    }

    const backoff = this.restartBackoffs[this.restartAttempts];
    this.restartAttempts++;

    this.outputChannel.appendLine(
      `[AgentBridge] Attempting restart ${this.restartAttempts}/${this.maxRestartAttempts} in ${backoff}ms...`
    );

    vscode.window.showWarningMessage(
      `Dolphin Agent crashed. Restarting (attempt ${this.restartAttempts}/${this.maxRestartAttempts})...`
    );

    setTimeout(() => {
      this.start(agentCorePath, extensionPath, apiKey);
    }, backoff);
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
      const locations = process.platform === "win32"
        ? [
            `${process.env.LOCALAPPDATA}\\bun\\bin\\bun.exe`,
            `${process.env.USERPROFILE}\\.bun\\bin\\bun.exe`,
          ]
        : [
            "/usr/local/bin/bun",
            "/opt/homebrew/bin/bun",
            `${process.env.HOME}/.bun/bin/bun`,
          ];

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

  private async sendRequest(method: string, params?: any, timeout = 30000): Promise<any> {
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
        .then((result) => {
          const pending = this.pendingRequests.get(id);
          if (pending) {
            if (pending.timeout) {
              clearTimeout(pending.timeout);
            }
            this.pendingRequests.delete(id);
            resolve(result);
          }
        })
        .catch((error) => {
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

  private async sendNotification(method: string, params?: any): Promise<void> {
    if (!this.connection) {
      throw new Error("JSON-RPC connection not established");
    }

    this.outputChannel.appendLine(`[AgentBridge] Sending notification: ${method}`);
    // vscode-jsonrpc handles backpressure and queuing internally
    this.connection.sendNotification(method, params);
  }

  async sendMessage(content: string): Promise<void> {
    const request: ExtensionRequest = {
      type: "send_message",
      messageId: `msg-${this.messageId}`,
      content,
    };

    await this.sendNotification("send_message", request);
  }

  async getAuthStatus(): Promise<any> {
    return this.sendRequest("get_auth_status", undefined, 5000);
  }

  async abortGeneration(): Promise<void> {
    await this.sendNotification("abort_generation");
  }

  async clearConversation(): Promise<void> {
    await this.sendNotification("clear_conversation");
  }

  private async waitForReady(timeout = 60000): Promise<void> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error("Agent Core did not become ready within 45s"));
      }, timeout);

      const disposable = this.onEvent((event) => {
        if (event.type === "agent_ready") {
          clearTimeout(timer);
          disposable.dispose();
          resolve();
        }
      });
    });
  }

  shutdown(): void {
    this.outputChannel.appendLine("[AgentBridge] Shutting down...");
    this.isShuttingDown = true;

    // Dispose connection first
    if (this.connection) {
      this.connection.dispose();
      this.connection = null;
    }

    // Clean up all pending requests
    for (const [id, pending] of this.pendingRequests.entries()) {
      if (pending.timeout) {
        clearTimeout(pending.timeout);
      }
      pending.reject(new Error("Agent bridge is shutting down"));
    }
    this.pendingRequests.clear();

    // Kill the process
    this.process?.kill("SIGTERM");
    this.process = null;
  }
}