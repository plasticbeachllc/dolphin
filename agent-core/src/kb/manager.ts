// agent-core/src/kb/manager.ts
import { spawn, ChildProcess } from "child_process";

export class KBManager {
  private process: ChildProcess | null = null;
  private readonly KB_URL = "http://127.0.0.1:7777";

  async start(workspaceRoot: string): Promise<void> {
    console.error("[KB Manager] Checking if KB is already running...");

    // Check if already running
    if (await this.healthCheck()) {
      console.error("[KB Manager] KB already running");
      return;
    }

    console.error("[KB Manager] Starting KB API...");

    // Start KB process
    this.process = spawn("uv", ["run", "dolphin", "serve"], {
      cwd: workspaceRoot,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
      },
    });

    // Capture logs
    this.process.stdout?.setEncoding("utf-8");
    this.process.stdout?.on("data", (chunk: string) => {
      console.error("[KB stdout]", chunk.trim());
    });

    this.process.stderr?.setEncoding("utf-8");
    this.process.stderr?.on("data", (chunk: string) => {
      console.error("[KB stderr]", chunk.trim());
    });

    this.process.on("error", (error) => {
      console.error("[KB Manager] Process error:", error);
    });

    this.process.on("exit", (code) => {
      console.error(`[KB Manager] Process exited with code ${code}`);
    });

    // Wait for ready
    await this.waitForReady();
    console.error("[KB Manager] KB API ready");
  }

  private async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.KB_URL}/health`, {
        signal: AbortSignal.timeout(2000),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  private async waitForReady(maxAttempts = 30): Promise<void> {
    for (let i = 0; i < maxAttempts; i++) {
      if (await this.healthCheck()) {
        return;
      }

      // Wait 1 second between attempts
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }

    throw new Error("KB API did not become ready within 30 seconds");
  }

  shutdown(): void {
    if (this.process) {
      console.error("[KB Manager] Shutting down KB...");
      this.process.kill("SIGTERM");
      this.process = null;
    }
  }
}