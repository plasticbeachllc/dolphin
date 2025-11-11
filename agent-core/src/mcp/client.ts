// agent-core/src/mcp/client.ts
import { spawn, ChildProcess } from "child_process";

interface MCPMessage {
  jsonrpc: "2.0";
  id?: number;
  method?: string;
  params?: any;
  result?: any;
  error?: any;
}

export class MCPClient {
  private process: ChildProcess | null = null;
  private messageId = 0;
  private pendingRequests = new Map<
    number,
    {
      resolve: (result: any) => void;
      reject: (error: any) => void;
      timeout: NodeJS.Timeout;
    }
  >();

  async start(mcpBridgePath: string): Promise<void> {
    console.error("[MCP Client] Starting MCP Bridge...");
    console.error(`[MCP Client] Bridge path: ${mcpBridgePath}`);

    this.process = spawn("bun", ["run", mcpBridgePath], {
      stdio: ["pipe", "pipe", "pipe"],
      cwd: process.cwd(),
    });

    // Handle stdout (JSON-RPC responses)
    this.process.stdout?.setEncoding("utf-8");
    
    // Line buffering: accumulate chunks until we have complete newline-delimited messages
    let buffer = "";
    this.process.stdout?.on("data", (chunk: string) => {
      // Append new chunk to buffer
      buffer += chunk;
      
      // Split on newlines - creates array where all elements except last are complete lines
      const lines = buffer.split("\n");
      
      // CRITICAL: pop() removes and returns the LAST element
      // - If chunk ended with \n, last element is "" (empty string) → all lines complete
      // - If chunk didn't end with \n, last element is partial data → save for next chunk
      buffer = lines.pop() || "";

      // Process all COMPLETE lines (everything except the partial last element)
      for (const line of lines) {
        if (line.trim()) {
          this.handleOutput(line);
        }
      }
    });

    // Handle stderr (logs)
    this.process.stderr?.setEncoding("utf-8");
    this.process.stderr?.on("data", (chunk: string) => {
      console.error("[MCP Bridge]", chunk);
    });

    // Handle errors
    this.process.on("error", (error) => {
      console.error("[MCP Client] Process error:", error);
    });

    // Handle exit
    this.process.on("exit", (code) => {
      console.error(`[MCP Client] Process exited with code ${code}`);

      // Reject all pending requests
      for (const [id, pending] of this.pendingRequests) {
        clearTimeout(pending.timeout);
        pending.reject(new Error("MCP Bridge process exited"));
      }
      this.pendingRequests.clear();
    });

    console.error("[MCP Client] MCP Bridge started");
  }

  private handleOutput(data: string) {
    try {
      const message: MCPMessage = JSON.parse(data);

      if (message.id !== undefined) {
        const pending = this.pendingRequests.get(message.id);
        if (pending) {
          clearTimeout(pending.timeout);
          this.pendingRequests.delete(message.id);

          if (message.error) {
            pending.reject(
              new Error(message.error.message || "Tool call failed")
            );
          } else {
            pending.resolve(message.result);
          }
        }
      }
    } catch (error) {
      console.error("[MCP Client] Failed to parse response:", data);
    }
  }

  async callTool(toolName: string, args: any, timeout = 20000): Promise<any> {
    if (!this.process || this.process.exitCode !== null) {
      throw new Error("MCP Bridge not running");
    }

    const id = ++this.messageId;

    const message: MCPMessage = {
      jsonrpc: "2.0",
      id,
      method: "tools/call",
      params: {
        name: toolName,
        arguments: args,
      },
    };

    console.error(`[MCP Client] Calling tool: ${toolName}`);

    return new Promise((resolve, reject) => {
      const timeoutHandle = setTimeout(() => {
        this.pendingRequests.delete(id);
        reject(new Error(`Tool call timeout (${timeout}ms): ${toolName}`));
      }, timeout);

      this.pendingRequests.set(id, {
        resolve,
        reject,
        timeout: timeoutHandle,
      });

      this.process!.stdin!.write(JSON.stringify(message) + "\n");
    });
  }

  async listTools(): Promise<any[]> {
    const id = ++this.messageId;

    const message: MCPMessage = {
      jsonrpc: "2.0",
      id,
      method: "tools/list",
    };

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(id);
        reject(new Error("tools/list timeout"));
      }, 5000);

      this.pendingRequests.set(id, {
        resolve: (result) => resolve(result.tools || []),
        reject,
        timeout,
      });

      this.process!.stdin!.write(JSON.stringify(message) + "\n");
    });
  }

  shutdown(): void {
    console.error("[MCP Client] Shutting down...");
    this.process?.kill("SIGTERM");
    this.process = null;
  }
}