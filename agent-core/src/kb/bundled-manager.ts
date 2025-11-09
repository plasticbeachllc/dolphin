// agent-core/src/kb/bundled-manager.ts
import * as path from "path";
import * as fs from "fs";
import { spawn, ChildProcess } from "child_process";
import * as os from "os";

export class BundledKBManager {
  private extensionPath: string;
  private uvBinary: string;
  private cacheDir: string;

  constructor(extensionPath: string) {
    this.extensionPath = extensionPath;
    
    // Get bundled uv binary for current platform
    const platform = this.getPlatformString();
    const uvName = platform.startsWith("win32") ? `uv-${platform}.exe` : `uv-${platform}`;
    this.uvBinary = path.join(extensionPath, "dist", "uv", uvName);
    
    console.error(`[Bundled KB] Looking for uv at: ${this.uvBinary}`);
    
    if (!fs.existsSync(this.uvBinary)) {
      throw new Error(`Unsupported platform: ${platform}. Expected ${this.uvBinary}`);
    }
    
    // Make executable on Unix
    if (process.platform !== "win32") {
      try {
        fs.chmodSync(this.uvBinary, 0o755);
      } catch (error: any) {
        console.error(`[Bundled KB] Warning: Could not chmod uv binary: ${error.message}`);
      }
    }
    
    // Use extension's global storage for uv cache
    this.cacheDir = path.join(extensionPath, ".uv-cache");
    if (!fs.existsSync(this.cacheDir)) {
      fs.mkdirSync(this.cacheDir, { recursive: true });
    }
    
    console.error(`[Bundled KB] Initialized with platform: ${platform}`);
    console.error(`[Bundled KB] UV binary: ${this.uvBinary}`);
    console.error(`[Bundled KB] Cache directory: ${this.cacheDir}`);
  }

  async startServer(): Promise<ChildProcess> {
    console.error("[Bundled KB] Starting KB server with bundled uv...");
    
    // Use uv run with inline dependency specification
    // uv will handle: Python installation, venv creation, package installation
    const proc = spawn(
      this.uvBinary,
      [
        "run",
        "--with", "pb-dolphin",  // Install pb-dolphin if not cached
        "python", "-m", "kb.cli", "serve"
      ],
      {
        stdio: ["ignore", "pipe", "pipe"],
        env: {
          ...process.env,
          UV_CACHE_DIR: this.cacheDir,       // Use extension's cache
          PYTHONUNBUFFERED: "1",
        },
      }
    );
    
    console.error("[Bundled KB] Server process spawned");
    return proc;
  }

  private getPlatformString(): string {
    const platform = os.platform();
    const arch = os.arch();
    
    if (platform === "darwin") {
      return arch === "arm64" ? "darwin-arm64" : "darwin-x64";
    } else if (platform === "linux") {
      return "linux-x64";
    } else if (platform === "win32") {
      return "win32-x64";
    }
    
    throw new Error(`Unsupported platform: ${platform}-${arch}`);
  }
}