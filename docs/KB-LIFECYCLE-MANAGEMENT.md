# KB Lifecycle Management Implementation Plan

**Date:** November 9, 2025  
**Phase:** Day 4 continuation - Production readiness  
**Status:** Planning → Implementation

## 🎯 Objective

Enable the VSCode extension to automatically manage the Knowledge Bank (KB) server lifecycle, providing a zero-configuration experience for end users.

## 📋 Current Architecture

### Current Flow (Development)
```
User manually starts:
  → Terminal 1: uv run dolphin serve
  → Terminal 2: VSCode extension (F5)
  → Extension connects to existing KB on localhost:8000
```

**Problems:**
- ❌ Users must manually start KB
- ❌ Two-step setup process
- ❌ KB and extension versions can drift
- ❌ Unclear error messages when KB not running

### Target Flow (Production)
```
User installs extension:
  → Extension activates
  → KBManager checks localhost:8000
  → If KB not running, spawns bundled KB server
  → Extension ready! Zero config needed.
```

**Benefits:**
- ✅ One-click installation
- ✅ Automatic KB startup/shutdown
- ✅ Version locked (KB bundled with extension)
- ✅ Clear error messages with auto-recovery

## 🏗️ Architecture Design

### Component: KBManager Enhancement

**File:** [`agent-core/src/kb/manager.ts`](../agent-core/src/kb/manager.ts)

**New Responsibilities:**
1. **Health Check**: Ping `http://localhost:8000/health` to detect KB
2. **Auto-Start**: Spawn KB subprocess if not running
3. **Process Management**: Track KB subprocess for cleanup
4. **Error Handling**: Graceful degradation if KB fails

**Current Implementation:**
```typescript
export class KBManager {
  async start(workspaceRoot: string) {
    console.error("[KB Manager] Starting KB API...");
    // TODO: Currently assumes KB is already running
  }
}
```

**Target Implementation:**
```typescript
export class KBManager {
  private kbProcess: ChildProcess | null = null;
  
  async start(workspaceRoot: string) {
    // 1. Check if KB already running
    if (await this.isKBRunning()) {
      console.error("[KB Manager] KB already running");
      return;
    }
    
    // 2. Spawn KB subprocess
    this.kbProcess = await this.spawnKBServer();
    
    // 3. Wait for health check
    await this.waitForKBReady();
    
    console.error("[KB Manager] KB started successfully");
  }
  
  private async isKBRunning(): Promise<boolean> {
    try {
      const response = await fetch("http://localhost:8000/health");
      return response.ok;
    } catch {
      return false;
    }
  }
  
  private async spawnKBServer(): Promise<ChildProcess> {
    // Spawn: uv run python -m kb.api.server
    const process = spawn("uv", ["run", "python", "-m", "kb.api.server"], {
      cwd: this.kbServerPath,
      stdio: ["ignore", "pipe", "pipe"],
    });
    
    // Handle logs
    process.stdout?.on("data", (data) => {
      console.error(`[KB Server] ${data}`);
    });
    
    return process;
  }
  
  private async waitForKBReady(timeout = 30000): Promise<void> {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      if (await this.isKBRunning()) {
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    throw new Error("KB failed to start within 30s");
  }
  
  shutdown() {
    if (this.kbProcess) {
      this.kbProcess.kill("SIGTERM");
      this.kbProcess = null;
    }
  }
}
```

## 📦 Extension Packaging Strategy

### Option 1: Bundle KB Code (Recommended)

Package KB Python code with the extension and use system Python.

**Structure:**
```
vscode-extension/
├── kb-server/              # KB Python package (copied from ../kb)
│   ├── kb/
│   │   ├── __init__.py
│   │   ├── api/
│   │   ├── chunkers/
│   │   ├── embeddings/
│   │   ├── retrieval/
│   │   └── store/
│   ├── pyproject.toml
│   └── requirements.txt
├── agent-core/
└── webview/
```

**Build Script** (`vscode-extension/scripts/bundle-kb.sh`):
```bash
#!/bin/bash
set -e

echo "Bundling KB server with extension..."

# Copy KB code
rm -rf kb-server
cp -r ../kb kb-server

# Create minimal requirements.txt
cd kb-server
uv export --no-hashes > requirements.txt

echo "✅ KB bundled successfully"
```

**package.json update:**
```json
{
  "scripts": {
    "bundle-kb": "bash scripts/bundle-kb.sh",
    "package": "npm run bundle-kb && vsce package"
  }
}
```

### Option 2: Download KB on First Run

Extension downloads KB on first activation.

**Pros:**
- Smaller extension size
- Easier updates

**Cons:**
- Requires internet on first run
- More complex activation logic

**Recommendation:** Use Option 1 for v1.0

## 🔄 Startup Flow

### Detailed Activation Sequence

```
1. Extension Activates
   ↓
2. AgentBridge.start()
   ↓
3. Spawn Agent Core (Bun)
   ↓
4. Agent Core: KBManager.start()
   ↓
5. Check localhost:8000/health
   ├─ Running? ✅ Continue
   └─ Not running? ↓
       6. Spawn KB subprocess
          ↓
       7. Poll /health every 500ms (max 30s)
          ↓
       8. KB Ready ✅
   ↓
9. Agent Core sends agent_ready event
   ↓
10. Extension ready!
```

### Error Scenarios

| Scenario | Detection | Recovery |
|----------|-----------|----------|
| KB fails to start | Health check timeout | Show error, offer manual KB start |
| KB crashes mid-session | API calls fail | Restart KB subprocess, retry |
| Port 8000 already in use | Spawn error | Try port 8001, or fail gracefully |
| Python not installed | Spawn error | Guide user to install Python |
| KB deps missing | KB logs error | Guide user to run `uv sync` |

## 🛠️ Implementation Tasks

### Phase 1: Core Functionality (Day 4)
- [ ] Implement `isKBRunning()` health check
- [ ] Implement `spawnKBServer()` subprocess spawning
- [ ] Implement `waitForKBReady()` with timeout
- [ ] Add `shutdown()` cleanup
- [ ] Test with manual KB stop/start

### Phase 2: Error Handling (Day 5)
- [ ] Add retry logic for health checks
- [ ] Graceful degradation when KB unavailable
- [ ] User-friendly error messages
- [ ] Extension settings for KB port/path
- [ ] Test failure scenarios

### Phase 3: Packaging (Week 2)
- [ ] Create `bundle-kb.sh` script
- [ ] Update `package.json` scripts
- [ ] Test packaged extension (.vsix)
- [ ] Verify KB bundled correctly
- [ ] Test on clean machine

### Phase 4: Production Hardening (Week 2)
- [ ] Add KB logs to output channel
- [ ] KB restart on crash
- [ ] Port conflict resolution
- [ ] Performance monitoring
- [ ] Documentation updates

## 🧪 Testing Strategy

### Manual Testing

**Test 1: Fresh Install**
```bash
# 1. Stop any running KB
pkill -f "kb.api.server"

# 2. Install extension
code --install-extension dolphin-x.x.x.vsix

# 3. Activate extension
# Expected: KB starts automatically, extension ready
```

**Test 2: KB Already Running**
```bash
# 1. Start KB manually
uv run dolphin serve

# 2. Activate extension
# Expected: Extension detects existing KB, no second instance
```

**Test 3: KB Crash Recovery**
```bash
# 1. Activate extension (KB starts)
# 2. Kill KB process: pkill -f "kb.api.server"
# 3. Send message in extension
# Expected: Extension detects crash, restarts KB, retries message
```

### Automated Tests

**Unit Tests** (`agent-core/tests/kb/manager.test.ts`):
```typescript
describe("KBManager", () => {
  it("should detect running KB", async () => { ... });
  it("should spawn KB if not running", async () => { ... });
  it("should wait for KB health check", async () => { ... });
  it("should timeout if KB fails to start", async () => { ... });
  it("should cleanup KB on shutdown", async () => { ... });
});
```

## 📊 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Zero-config success** | >95% | Users who don't need to manually start KB |
| **Startup time** | <5s | Time from activation to ready (with KB start) |
| **Crash recovery** | <2s | Time to detect and restart KB |
| **Error clarity** | >90% | Users who understand error messages |

## 🚀 Rollout Plan

### Alpha (Current)
- Developer testing only
- Manual KB startup required
- Document limitations

### Beta (Week 2)
- Bundled KB in extension
- Auto-start enabled
- Early adopter testing
- Feedback collection

### v1.0 (Week 6)
- Production-ready packaging
- Robust error handling
- Complete documentation
- VSCode marketplace release

## 📚 Documentation Updates Needed

1. **README.md**: Update installation instructions (remove manual KB start)
2. **TESTING-GUIDE.md**: Update with auto-start behavior
3. **ARCHITECTURE.md**: Add KB lifecycle section
4. **Troubleshooting Guide**: Add KB startup issues

## 🔗 References

- Original roadmap: [`updated-implementation-roadmap.md`](private/vscode-architecture/claude-cli/updated-implementation-roadmap.md)
- Current state: [`day3-claude-integration-summary.md`](day3-claude-integration-summary.md)
- Testing guide: [`TESTING-GUIDE.md`](TESTING-GUIDE.md)

---

**Status:** Ready for implementation  
**Next Step:** Implement KBManager health check and subprocess spawning  
**Estimated Time:** 4-6 hours for Phase 1