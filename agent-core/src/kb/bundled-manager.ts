// agent-core/src/kb/bundled-manager.ts
import { join as pathJoin } from "path";
import { existsSync, chmodSync, mkdirSync } from "fs";
import { spawn, type ChildProcess } from "child_process";
import { platform as osPlatform, arch as osArch } from "os";

export class BundledKBManager {
  private extensionPath: string;
  private uvBinary: string;
  private cacheDir: string;

  constructor(extensionPath: string) {
    this.extensionPath = extensionPath;

    // Get bundled uv binary for current platform
    const platform = this.getPlatformString();
    const uvName = platform.startsWith("win32") ? `uv-${platform}.exe` : `uv-${platform}`;
    this.uvBinary = pathJoin(extensionPath, "dist", "uv", uvName);

    console.error(`[Bundled KB] Looking for uv at: ${this.uvBinary}`);

    if (!existsSync(this.uvBinary)) {
      throw new Error(`Unsupported platform: ${platform}. Expected ${this.uvBinary}`);
    }

    // Make executable on Unix
    if (process.platform !== "win32") {
      try {
        chmodSync(this.uvBinary, 0o755);
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        console.error(`[Bundled KB] Warning: Could not chmod uv binary: ${message}`);
      }
    }

    // Use extension's global storage for uv cache
    this.cacheDir = pathJoin(extensionPath, ".uv-cache");
    if (!existsSync(this.cacheDir)) {
      mkdirSync(this.cacheDir, { recursive: true });
    }

    console.error(`[Bundled KB] Initialized with platform: ${platform}`);
    console.error(`[Bundled KB] UV binary: ${this.uvBinary}`);
    console.error(`[Bundled KB] Cache directory: ${this.cacheDir}`);
  }

  async startServer(): Promise<ChildProcess> {
    console.error("[Bundled KB] Starting KB server with bundled uv...");

    // Use local source directory for development
    // This allows hot-reloading of KB code changes without reinstalling the package
    const kbDir = pathJoin(this.extensionPath, "..", "kb");

    // Check if we're in development mode (kb directory exists at expected location)
    const isDevelopment = existsSync(kbDir);

    if (isDevelopment) {
      console.error("[Bundled KB] Development mode: using local kb directory at", kbDir);
    } else {
      console.error("[Bundled KB] Production mode: using installed pb-dolphin package");
    }

    // Use uv run with inline dependency specification or local directory
    const args = isDevelopment
      ? ["run", "--directory", kbDir, "python", "-m", "kb.cli", "serve"]
      : ["run", "--with", "pb-dolphin", "python", "-m", "kb.cli", "serve"];

    const proc = spawn(this.uvBinary, args, {
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...(process.env as Record<string, string | undefined>),
        UV_CACHE_DIR: this.cacheDir, // Use extension's cache
        PYTHONUNBUFFERED: "1",
      },
    });

    console.error("[Bundled KB] Server process spawned");
    return proc;
  }

  private getPlatformString(): string {
    const platform = osPlatform();
    const arch = osArch();

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
