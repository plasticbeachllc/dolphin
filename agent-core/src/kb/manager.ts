// agent-core/src/kb/manager.ts
import { spawn, ChildProcess } from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { BundledKBManager } from "./bundled-manager";

export class KBManager {
  private process: ChildProcess | null = null;
  private readonly KB_URL = "http://127.0.0.1:7777";
  private readonly lockFile = path.join(os.tmpdir(), "dolphin-kb.lock");
  private weOwnKB = false;

  async start(workspaceRoot: string, extensionPath?: string): Promise<void> {
    console.error("[KB Manager] Checking if KB is already running...");

    // Check if already running
    if (await this.healthCheck()) {
      console.error("[KB Manager] KB already running (managed by another instance)");
      return;
    }

    console.error("[KB Manager] Attempting to acquire KB ownership...");

    // Try to acquire lock for KB ownership
    if (this.tryAcquireLock()) {
      this.weOwnKB = true;
      console.error("[KB Manager] Lock acquired, starting KB API...");

      // Detect environment based on what's actually available
      const hasBundledUv = extensionPath && this.checkBundledUv(extensionPath);
      const hasDevelopmentSetup = this.checkDevelopmentSetup(workspaceRoot);

      console.error(`[KB Manager] Workspace root: ${workspaceRoot}`);
      console.error(`[KB Manager] Has bundled uv: ${hasBundledUv}`);
      console.error(`[KB Manager] Has development setup: ${hasDevelopmentSetup}`);

      // Start KB process with appropriate command for environment
      if (hasBundledUv) {
        console.error("[KB Manager] Production mode: using bundled uv");
        // Production: Use bundled uv binary
        const bundled = new BundledKBManager(extensionPath!);
        this.process = await bundled.startServer();
      } else if (hasDevelopmentSetup) {
        console.error("[KB Manager] Development mode: using system uv");
        // Find dolphin root (could be workspace or subdirectory)
        const dolphinRoot = this.findDolphinRoot(workspaceRoot);
        console.error(`[KB Manager] Dolphin root: ${dolphinRoot}`);
        
        // Development: Use system uv with dolphin project directory
        this.process = spawn("uv", ["run", "--directory", dolphinRoot, "python", "-m", "kb.cli", "serve"], {
          stdio: ["ignore", "pipe", "pipe"],
          env: {
            ...process.env,
            PYTHONUNBUFFERED: "1",
          },
        });
      } else {
        // Fallback: shouldn't happen
        throw new Error("Neither bundled uv nor development environment found");
      }

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
        this.releaseLock();
      });

      this.process.on("exit", (code) => {
        console.error(`[KB Manager] Process exited with code ${code}`);
        this.releaseLock();
      });

      // Wait for ready
      await this.waitForReady();
      console.error("[KB Manager] KB API ready");
    } else {
      console.error("[KB Manager] Another instance is starting KB, waiting for it...");
      // Another instance is starting KB, just wait for it to be ready
      await this.waitForReady();
      console.error("[KB Manager] KB API ready (managed by another instance)");
    }
  }

  private checkBundledUv(extensionPath: string): boolean {
    const platform = os.platform();
    const arch = os.arch();

    let uvName: string;
    if (platform === "darwin") {
      uvName = arch === "arm64" ? "uv-darwin-arm64" : "uv-darwin-x64";
    } else if (platform === "linux") {
      uvName = "uv-linux-x64";
    } else if (platform === "win32") {
      uvName = "uv-win32-x64.exe";
    } else {
      return false;
    }

    const uvPath = path.join(extensionPath, "dist", "uv", uvName);
    return fs.existsSync(uvPath);
  }

  /**
   * Walk up directory tree to find pyproject.toml
   * Checks both current directory and dolphin subdirectory at each level
   * @returns Path to directory containing pyproject.toml, or null if not found
   */
  private findPyprojectToml(startDir: string): string | null {
    let currentDir = path.resolve(startDir);
    const root = path.parse(currentDir).root;

    while (currentDir !== root) {
      // Check current directory
      if (fs.existsSync(path.join(currentDir, "pyproject.toml"))) {
        return currentDir;
      }

      // Check dolphin subdirectory
      const dolphinPath = path.join(currentDir, "dolphin");
      if (fs.existsSync(path.join(dolphinPath, "pyproject.toml"))) {
        return dolphinPath;
      }

      // Move up one level
      const parentDir = path.dirname(currentDir);
      if (parentDir === currentDir) break; // Reached root
      currentDir = parentDir;
    }

    return null;
  }

  private checkDevelopmentSetup(workspaceRoot: string): boolean {
    return this.findPyprojectToml(workspaceRoot) !== null;
  }

  private findDolphinRoot(workspaceRoot: string): string {
    const projectRoot = this.findPyprojectToml(workspaceRoot);

    if (projectRoot) {
      console.error(`[KB Manager] Found pyproject.toml at: ${projectRoot}`);
      return projectRoot;
    }

    // Fallback to workspace root
    console.error("[KB Manager] WARNING: Could not find dolphin project root with pyproject.toml");
    return workspaceRoot;
  }

  private tryAcquireLock(): boolean {
    try {
      // Check if lock file exists
      if (fs.existsSync(this.lockFile)) {
        // Read PID from lock file
        const lockContent = fs.readFileSync(this.lockFile, "utf-8").trim();
        const pid = parseInt(lockContent, 10);

        if (!isNaN(pid) && this.isProcessRunning(pid)) {
          // Lock is held by a running process
          console.error(`[KB Manager] Lock held by process ${pid}`);
          return false;
        }

        // Stale lock file, remove it
        console.error(`[KB Manager] Removing stale lock file (PID ${pid} not running)`);
        fs.unlinkSync(this.lockFile);
      }

      // Create lock file with our PID
      fs.writeFileSync(this.lockFile, process.pid.toString());
      console.error(`[KB Manager] Lock acquired with PID ${process.pid}`);
      return true;
    } catch (error: any) {
      console.error(`[KB Manager] Failed to acquire lock: ${error.message}`);
      return false;
    }
  }

  private releaseLock(): void {
    if (this.weOwnKB) {
      try {
        if (fs.existsSync(this.lockFile)) {
          // Verify we still own the lock before removing
          const lockContent = fs.readFileSync(this.lockFile, "utf-8").trim();
          const pid = parseInt(lockContent, 10);

          if (pid === process.pid) {
            fs.unlinkSync(this.lockFile);
            console.error(`[KB Manager] Lock released`);
          }
        }
      } catch (error: any) {
        console.error(`[KB Manager] Failed to release lock: ${error.message}`);
      }
      this.weOwnKB = false;
    }
  }

  private isProcessRunning(pid: number): boolean {
    try {
      // Sending signal 0 checks if process exists without actually sending a signal
      process.kill(pid, 0);
      return true;
    } catch {
      return false;
    }
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
    if (this.weOwnKB && this.process) {
      console.error("[KB Manager] Shutting down KB (we own it)...");
      this.process.kill("SIGTERM");
      this.process = null;
      this.releaseLock();
    } else if (!this.weOwnKB) {
      console.error("[KB Manager] Not shutting down KB (managed by another instance)");
    }
  }
}