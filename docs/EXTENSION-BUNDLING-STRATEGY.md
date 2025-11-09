# Extension Bundling Strategy

## Overview

This document outlines the simplified strategy for bundling the Dolphin Python environment with the VSCode extension using **`uv` exclusively**.

## Approach: Bundle uv Only (Recommended)

### Why This Works Best

- **uv is self-contained**: Single binary (~10MB) manages Python, environments, and packages
- **uv handles everything**: Python installation, virtual environments, dependency resolution
- **Zero complexity**: No need to bundle wheels or Python interpreters
- **Fast**: uv's Rust implementation makes environment creation extremely fast
- **Cross-platform**: Single approach works on Windows, macOS, Linux
- **Always up-to-date**: uv fetches latest compatible packages when needed

### Implementation

**Just bundle the `uv` binary!** That's it. uv handles the rest.

## Directory Structure

```
vscode-extension/
├── dist/
│   └── uv/                     # Bundled uv binaries
│       ├── uv-darwin-arm64     # macOS ARM
│       ├── uv-darwin-x64       # macOS Intel
│       ├── uv-linux-x64        # Linux
│       └── uv-win32-x64.exe    # Windows
└── out/
    └── kb/
        └── bundled-manager.js
```

## Extension Build Process

```bash
#!/bin/bash
# scripts/bundle-uv.sh

# Download uv for all platforms
mkdir -p vscode-extension/dist/uv

# macOS ARM64
curl -LsSf https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz | \
  tar xz -C vscode-extension/dist/uv
mv vscode-extension/dist/uv/uv vscode-extension/dist/uv/uv-darwin-arm64

# macOS x64
curl -LsSf https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-apple-darwin.tar.gz | \
  tar xz -C vscode-extension/dist/uv
mv vscode-extension/dist/uv/uv vscode-extension/dist/uv/uv-darwin-x64

# Linux x64
curl -LsSf https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz | \
  tar xz -C vscode-extension/dist/uv
mv vscode-extension/dist/uv/uv vscode-extension/dist/uv/uv-linux-x64

# Windows x64
curl -LsSf https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip -o uv-win.zip
unzip -j uv-win.zip -d vscode-extension/dist/uv
mv vscode-extension/dist/uv/uv.exe vscode-extension/dist/uv/uv-win32-x64.exe
rm uv-win.zip

echo "✅ uv binaries bundled for all platforms"
```

That's it! No wheels, no Python interpreter, just uv.

## Runtime Setup - BundledKBManager

```typescript
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
    
    if (!fs.existsSync(this.uvBinary)) {
      throw new Error(`Unsupported platform: ${platform}. Expected ${this.uvBinary}`);
    }
    
    // Make executable on Unix
    if (process.platform !== "win32") {
      fs.chmodSync(this.uvBinary, 0o755);
    }
    
    // Use extension's global storage for uv cache
    this.cacheDir = path.join(extensionPath, ".uv-cache");
    if (!fs.existsSync(this.cacheDir)) {
      fs.mkdirSync(this.cacheDir, { recursive: true });
    }
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
```

**That's all you need!** uv handles:
- Python installation (if needed)
- Virtual environment creation
- Package installation from PyPI
- Dependency resolution
- Caching for fast subsequent launches

## Updated KBManager Integration

```typescript
// agent-core/src/kb/manager.ts (updated start method)
async start(workspaceRoot: string, extensionPath?: string): Promise<void> {
  if (await this.healthCheck()) {
    console.error("[KB Manager] KB already running");
    return;
  }

  if (this.tryAcquireLock()) {
    this.weOwnKB = true;
    
    // 1. Production with bundled uv
    if (extensionPath && !this.isDevelopment(workspaceRoot)) {
      console.error("[KB Manager] Using bundled uv");
      const bundled = new BundledKBManager(extensionPath);
      this.process = await bundled.startServer();
    }
    // 2. Development mode
    else if (this.isDevelopment(workspaceRoot)) {
      console.error("[KB Manager] Development mode: using system uv");
      this.process = spawn("uv", ["run", "--directory", workspaceRoot, "python", "-m", "kb.cli", "serve"]);
    }
    // 3. Fallback (shouldn't happen)
    else {
      throw new Error("Neither bundled uv nor development environment found");
    }
    
    // ... rest of setup
  }
}

private isDevelopment(workspaceRoot: string): boolean {
  return fs.existsSync(path.join(workspaceRoot, "pyproject.toml"));
}
```

## Extension Package Size

| Component | Size per Platform |
|-----------|-------------------|
| uv binary | ~10 MB |
| **Total** | **~10 MB** |

Much simpler than bundling wheels!

**First Launch:**
- uv downloads Python (~20 MB)
- uv installs pb-dolphin + deps (~200 MB)
- Total download: ~220 MB
- Time: ~10-30 seconds (one-time)

**Subsequent Launches:**
- Uses cached environment
- Startup time: <1 second

## Build Script Integration

Update `vscode-extension/package.json`:

```json
{
  "scripts": {
    "bundle-uv": "bash ../scripts/bundle-uv.sh",
    "vscode:prepublish": "npm run compile && npm run bundle-uv",
    "package": "vsce package --target darwin-arm64 darwin-x64 linux-x64 win32-x64"
  }
}
```

## Testing

```bash
# Build extension with bundled uv
cd vscode-extension
npm run vscode:prepublish

# Package for all platforms
npm run package

# Test .vsix in clean environment
code --install-extension dolphin-darwin-arm64-*.vsix
```

## Pros & Cons

### Pros
✅ **Tiny package size** - Extension is only ~10 MB
✅ **Zero manual setup** - Users just install extension
✅ **Always up-to-date** - uv fetches latest compatible packages
✅ **Cross-platform** - Single approach for all OSes
✅ **Simple build** - Just download uv binaries
✅ **Fast** - uv is extremely fast at environment creation
✅ **Reliable** - uv handles all edge cases (Python versions, platform differences)

### Cons
❌ **First launch needs internet** - To download Python + packages (~220 MB)
❌ **First launch slower** - ~10-30 seconds vs instant
❌ **Requires internet once** - After that works offline

## Recommendation

**Bundle only `uv`** - Let it handle everything else:

1. Bundle uv binaries for all platforms in extension (~40 MB total for 4 platforms)
2. On first activation, uv automatically:
   - Downloads appropriate Python version
   - Creates virtual environment
   - Installs pb-dolphin from PyPI
   - Caches everything in `.uv-cache` directory
3. Subsequent activations use cached environment (<1s startup)

**Benefits:**
- **10 MB extension** vs 200-600 MB with bundled wheels
- **Always latest packages** - uv fetches from PyPI
- **Zero maintenance** - No wheel bundling, no versioning issues
- **Works everywhere** - uv handles platform differences

## User Experience

### First Install
```
1. User installs extension from Marketplace (~10 MB download)
2. User opens VSCode → Extension activates
3. Loading banner shows: "Setting up Dolphin environment..."
4. uv downloads Python + dependencies (~220 MB, 10-30s)
5. Banner updates: "Dolphin ready!" → Disappears
6. Extension fully functional
```

### Subsequent Uses
```
1. User opens VSCode → Extension activates
2. Uses cached environment (<1s)
3. Fully functional immediately
```

Perfect balance of small package size and zero-configuration user experience! 🚀