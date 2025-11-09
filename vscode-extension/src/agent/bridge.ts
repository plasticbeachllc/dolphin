// vscode-extension/src/agent/bridge.ts
import { ChildProcess, spawn } from "child_process";
import * as vscode from "vscode";
import type { AgentEvent, ExtensionRequest } from "../types/events";

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

export class AgentBridge {
  private process: ChildProcess | null = null;
  private messageId = 0;
  private eventEmitter = new vscode.EventEmitter<AgentEvent>();
  private outputChannel: vscode.OutputChannel;
  private pendingRequests: Map<number, { resolve: (value: any) => void; reject: (error: any) => void }> = new Map();

  public readonly onEvent = this.eventEmitter.event;

  constructor() {
    this.outputChannel = vscode.window.createOutputChannel("Dolphin Agent");
  }

  async start(agentCorePath: string, extensionPath: string): Promise<void> {
    this.outputChannel.appendLine("[AgentBridge] Starting Agent Core...");

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
    this.process = spawn(bunPath, ["run", agentCorePath, workspaceRoot, extensionPath], {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env },
    });

    // Set up stdout handling (JSON-RPC messages)
    this.process.stdout?.setEncoding("utf-8");
    let buffer = "";
    this.process.stdout?.on("data", (chunk: string) => {
      buffer += chunk;
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.trim()) {
          this.handleOutput(line);
        }
      }
    });

    // Set up stderr handling (logs)
    this.process.stderr?.setEncoding("utf-8");
    this.process.stderr?.on("data", (chunk: string) => {
      this.outputChannel.append(chunk);
    });

    // Handle errors
    this.process.on("error", (error) => {
      this.outputChannel.appendLine(
        `[AgentBridge] Process error: ${error.message}`
      );
      vscode.window.showErrorMessage(`Dolphin Agent error: ${error.message}`);
    });

    // Handle exit
    this.process.on("exit", (code, signal) => {
      this.outputChannel.appendLine(
        `[AgentBridge] Process exited: code=${code}, signal=${signal}`
      );

      if (code !== 0 && code !== null) {
        vscode.window.showErrorMessage(
          `Dolphin Agent crashed (exit code ${code}). Check Output > Dolphin Agent for details.`
        );
      }
    });

    // Don't wait for ready - let agent start in background
    this.outputChannel.appendLine(
      "[AgentBridge] Agent Core spawned, starting in background..."
    );
    
    // Start listening for ready signal (non-blocking)
    this.waitForReady().then(() => {
      this.outputChannel.appendLine("[AgentBridge] Agent Core ready!");
    }).catch((error) => {
      this.outputChannel.appendLine(`[AgentBridge] Agent startup error: ${error.message}`);
    });
  }

  private async findBun(): Promise<string | null> {
    const { exec } = require("child_process");
    const { promisify } = require("util");
    const execAsync = promisify(exec);

    try {
      const { stdout } = await execAsync("which bun");
      return stdout.trim();
    } catch {
      // Try common locations
      const fs = require("fs");
      const locations = [
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

  private handleOutput(data: string) {
    try {
      const message: Message = JSON.parse(data);

      // Handle JSON-RPC responses (with id)
      if (message.id !== undefined && message.result !== undefined) {
        const pending = this.pendingRequests.get(message.id);
        if (pending) {
          pending.resolve(message.result);
          this.pendingRequests.delete(message.id);
        }
        return;
      }

      // Handle JSON-RPC errors
      if (message.id !== undefined && message.error !== undefined) {
        const pending = this.pendingRequests.get(message.id);
        if (pending) {
          pending.reject(new Error(message.error.message || "Unknown error"));
          this.pendingRequests.delete(message.id);
        }
        return;
      }

      // Handle notifications (events)
      if (message.method === "notify" && message.params) {
        const event = message.params as AgentEvent;
        this.outputChannel.appendLine(`[AgentBridge] Event: ${event.type}`);
        this.eventEmitter.fire(event);
      }
    } catch (error) {
      this.outputChannel.appendLine(
        `[AgentBridge] Failed to parse message: ${data}`
      );
    }
  }

  async sendMessage(content: string): Promise<void> {
    if (!this.process || this.process.exitCode !== null) {
      throw new Error("Agent process not running");
    }

    const request: ExtensionRequest = {
      type: "send_message",
      messageId: `msg-${this.messageId++}`,
      content,
    };

    const message: Message = {
      jsonrpc: "2.0",
      id: this.messageId,
      method: "send_message",
      params: request,
    };

    const json = JSON.stringify(message) + "\n";
    this.outputChannel.appendLine(`[AgentBridge] Sending: ${message.method}`);

    this.process.stdin?.write(json);
  }

  async getAuthStatus(): Promise<any> {
    if (!this.process || this.process.exitCode !== null) {
      throw new Error("Agent process not running");
    }

    const id = ++this.messageId;
    const message: Message = {
      jsonrpc: "2.0",
      id,
      method: "get_auth_status",
    };

    const json = JSON.stringify(message) + "\n";
    this.outputChannel.appendLine(`[AgentBridge] Requesting auth status (id: ${id})`);

    // Create promise for response
    const promise = new Promise<any>((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });

      // Timeout after 5 seconds
      setTimeout(() => {
        if (this.pendingRequests.has(id)) {
          this.pendingRequests.delete(id);
          reject(new Error("Auth status request timeout"));
        }
      }, 5000);
    });

    // Send request
    this.process.stdin?.write(json);

    return promise;
  }

  async abortGeneration(): Promise<void> {
    if (!this.process || this.process.exitCode !== null) {
      throw new Error("Agent process not running");
    }

    const message = {
      jsonrpc: "2.0",
      id: ++this.messageId,
      method: "abort_generation",
      params: {}
    };

    const json = JSON.stringify(message) + "\n";
    this.outputChannel.appendLine(`[AgentBridge] Sending abort_generation`);

    this.process.stdin?.write(json);
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
    this.process?.kill("SIGTERM");
    this.process = null;
  }
}