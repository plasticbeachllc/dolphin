// vscode-extension/src/agent/bridge.ts
import { ChildProcess, spawn } from "child_process";
import * as vscode from "vscode";
import type { AgentEvent, ExtensionRequest } from "../types/events";

interface Message {
  jsonrpc: "2.0";
  id?: number;
  method?: string;
  params?: any;
}

export class AgentBridge {
  private process: ChildProcess | null = null;
  private messageId = 0;
  private eventEmitter = new vscode.EventEmitter<AgentEvent>();
  private outputChannel: vscode.OutputChannel;

  public readonly onEvent = this.eventEmitter.event;

  constructor() {
    this.outputChannel = vscode.window.createOutputChannel("Dolphin Agent");
  }

  async start(agentCorePath: string): Promise<void> {
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

    // Spawn Agent Core
    this.process = spawn(bunPath, ["run", agentCorePath], {
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

    // Wait for ready signal
    this.outputChannel.appendLine(
      "[AgentBridge] Waiting for agent_ready signal..."
    );
    await this.waitForReady();

    this.outputChannel.appendLine("[AgentBridge] Agent Core ready!");
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

  private async waitForReady(timeout = 10000): Promise<void> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error("Agent Core did not become ready within 10s"));
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