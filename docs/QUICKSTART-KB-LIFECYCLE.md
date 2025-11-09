# Quick Start: KB Lifecycle Management Implementation

**Goal:** Implement automatic KB server lifecycle management in the VSCode extension.

**Time Estimate:** 4-6 hours for Phase 1

---

## 🎯 What We're Building

### Current State (Broken)
```bash
# Terminal 1: User must manually start KB
uv run dolphin serve

# Terminal 2: Then start extension
F5 in VSCode
```

**Problem:** Extension fails if KB not running → "Agent Core did not become ready within 10s"

### Target State (Working)
```bash
# User just starts extension
F5 in VSCode

# Extension automatically:
# 1. Checks if KB running
# 2. Starts KB if needed
# 3. Waits for KB ready
# 4. ✅ Everything works!
```

---

## 📋 Implementation Checklist

### Phase 1: Core Functionality (Today)

#### Step 1: Add Health Check Method (30 min)
**File:** [`agent-core/src/kb/manager.ts`](../agent-core/src/kb/manager.ts)

```typescript
private async isKBRunning(): Promise<boolean> {
  try {
    const response = await fetch("http://localhost:8000/health");
    return response.ok;
  } catch {
    return false;
  }
}
```

**Test:**
```typescript
// In tests/kb/manager.test.ts
it("should detect running KB", async () => {
  // Start KB manually
  // Call isKBRunning()
  // Expect true
});
```

#### Step 2: Add Subprocess Spawning (1 hour)
**File:** [`agent-core/src/kb/manager.ts`](../agent-core/src/kb/manager.ts)

```typescript
import { spawn, type ChildProcess } from "child_process";

private kbProcess: ChildProcess | null = null;

private async spawnKBServer(): Promise<ChildProcess> {
  console.error("[KB Manager] Spawning KB server...");
  
  // Determine KB path (for now, assume sibling directory)
  const kbPath = path.resolve(__dirname, "../../../../kb");
  
  // Spawn: uv run python -m kb.api.server
  const process = spawn("uv", ["run", "python", "-m", "kb.api.server"], {
    cwd: kbPath,
    stdio: ["ignore", "pipe", "pipe"],
  });
  
  // Log KB output
  process.stdout?.on("data", (data) => {
    console.error(`[KB Server] ${data}`);
  });
  
  process.stderr?.on("data", (data) => {
    console.error(`[KB Server ERROR] ${data}`);
  });
  
  process.on("error", (error) => {
    console.error(`[KB Server] Failed to start:`, error);
  });
  
  process.on("exit", (code) => {
    console.error(`[KB Server] Exited with code ${code}`);
    this.kbProcess = null;
  });
  
  return process;
}
```

**Test:**
```typescript
it("should spawn KB subprocess", async () => {
  const process = await manager.spawnKBServer();
  expect(process).toBeDefined();
  expect(process.pid).toBeGreaterThan(0);
  
  // Cleanup
  process.kill("SIGTERM");
});
```

#### Step 3: Add Wait for Ready (45 min)
**File:** [`agent-core/src/kb/manager.ts`](../agent-core/src/kb/manager.ts)

```typescript
private async waitForKBReady(timeout = 30000): Promise<void> {
  console.error("[KB Manager] Waiting for KB to be ready...");
  
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await this.isKBRunning()) {
      console.error("[KB Manager] ✅ KB is ready!");
      return;
    }
    
    // Poll every 500ms
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  
  throw new Error(`KB failed to start within ${timeout / 1000}s`);
}
```

**Test:**
```typescript
it("should wait for KB to be ready", async () => {
  // Spawn KB
  await manager.spawnKBServer();
  
  // Wait for ready
  await manager.waitForKBReady();
  
  // Verify KB responding
  const health = await fetch("http://localhost:8000/health");
  expect(health.ok).toBe(true);
});
```

#### Step 4: Update start() Method (30 min)
**File:** [`agent-core/src/kb/manager.ts`](../agent-core/src/kb/manager.ts)

```typescript
async start(workspaceRoot: string) {
  console.error("[KB Manager] Starting KB...");
  
  // 1. Check if already running
  if (await this.isKBRunning()) {
    console.error("[KB Manager] KB already running (external)");
    return;
  }
  
  // 2. Spawn KB subprocess
  this.kbProcess = await this.spawnKBServer();
  
  // 3. Wait for health check
  await this.waitForKBReady();
  
  console.error("[KB Manager] ✅ KB started successfully");
}
```

#### Step 5: Add Cleanup Method (15 min)
**File:** [`agent-core/src/kb/manager.ts`](../agent-core/src/kb/manager.ts)

```typescript
shutdown() {
  if (this.kbProcess) {
    console.error("[KB Manager] Shutting down KB...");
    this.kbProcess.kill("SIGTERM");
    this.kbProcess = null;
  }
}
```

**Integration:** Call `shutdown()` from AgentCore cleanup:

**File:** [`agent-core/src/main.ts`](../agent-core/src/main.ts)

```typescript
// In AgentCore class
shutdown() {
  this.kbManager.shutdown();
  this.mcpClient?.close();
}
```

**File:** [`vscode-extension/src/agent/bridge.ts`](../vscode-extension/src/agent/bridge.ts)

```typescript
// In AgentBridge.stop()
dispose() {
  if (this.agentProcess) {
    // Send shutdown message
    this.agentProcess.stdin?.write(
      JSON.stringify({ jsonrpc: "2.0", method: "shutdown" }) + "\n"
    );
    
    // Kill after 2s if not responding
    setTimeout(() => {
      if (this.agentProcess) {
        this.agentProcess.kill("SIGTERM");
      }
    }, 2000);
  }
}
```

---

## 🧪 Testing Strategy

### Unit Tests
```bash
cd agent-core
bun test tests/kb/manager.test.ts
```

**Expected:**
- ✅ `isKBRunning()` detects running KB
- ✅ `spawnKBServer()` starts subprocess
- ✅ `waitForKBReady()` waits for health check
- ✅ `shutdown()` cleans up process

### Integration Test
```bash
# 1. Stop any running KB
pkill -f "kb.api.server"

# 2. Start extension in VSCode (F5)

# 3. Check VSCode Output → Dolphin
# Expected logs:
# [KB Manager] Starting KB...
# [KB Manager] Spawning KB server...
# [KB Server] Uvicorn running on http://127.0.0.1:8000
# [KB Manager] Waiting for KB to be ready...
# [KB Manager] ✅ KB is ready!
# [KB Manager] ✅ KB started successfully
# [Agent Core] Agent ready!
```

### End-to-End Test
```bash
# 1. KB should be auto-started
# 2. Send message in chat: "What is Dolphin?"
# 3. Expected:
#    - KB search executes
#    - Claude response generated
#    - Task completes successfully
```

---

## 🚨 Known Issues & Solutions

### Issue 1: KB Path Resolution
**Problem:** Extension doesn't know where KB code is located

**Solution (Development):**
```typescript
// Use relative path from agent-core to kb/
const kbPath = path.resolve(__dirname, "../../../../kb");
```

**Solution (Production):**
```typescript
// Use bundled KB in extension directory
const kbPath = path.resolve(extensionPath, "kb-server");
```

### Issue 2: Python/uv Not in PATH
**Problem:** `spawn("uv", ...)` fails if uv not installed or not in PATH

**Solution:**
```typescript
// Check for uv before spawning
const hasUv = await which("uv").catch(() => null);
if (!hasUv) {
  throw new Error(
    "uv not found. Please install uv: https://github.com/astral-sh/uv"
  );
}
```

### Issue 3: Port Already in Use
**Problem:** Port 8000 occupied by another process

**Solution (Phase 2):**
- Try ports 8000, 8001, 8002
- Or fail gracefully with clear error message

### Issue 4: KB Crashes Mid-Session
**Problem:** KB subprocess crashes, extension stops working

**Solution (Phase 2):**
- Monitor KB process exit events
- Auto-restart on crash
- Show user notification

---

## 📊 Success Criteria

### Phase 1 Complete When:
- [ ] `isKBRunning()` implemented and tested
- [ ] `spawnKBServer()` implemented and tested
- [ ] `waitForKBReady()` implemented and tested
- [ ] `shutdown()` implemented and tested
- [ ] Extension starts successfully without manual KB startup
- [ ] End-to-end chat flow works
- [ ] KB process cleaned up on extension shutdown

### Verification:
```bash
# 1. Clean state
pkill -f "kb.api.server"

# 2. Start extension (F5)
# 3. Verify logs show KB auto-started
# 4. Send test message
# 5. Verify response received
# 6. Close extension
# 7. Verify KB process terminated
```

---

## 📝 Code Changes Summary

### Files to Modify:
1. [`agent-core/src/kb/manager.ts`](../agent-core/src/kb/manager.ts) - Add lifecycle methods
2. [`agent-core/src/main.ts`](../agent-core/src/main.ts) - Add shutdown handler
3. [`vscode-extension/src/agent/bridge.ts`](../vscode-extension/src/agent/bridge.ts) - Add cleanup

### Files to Create:
1. `agent-core/tests/kb/manager.test.ts` - Unit tests

### Estimated Lines of Code:
- KB Manager: +120 lines
- Tests: +80 lines
- Main.ts: +10 lines
- Bridge.ts: +15 lines

**Total:** ~225 lines of new code

---

## 🔄 Development Workflow

### Step-by-Step:
```bash
# 1. Create feature branch
git checkout -b feature/kb-lifecycle

# 2. Implement health check
# 3. Test health check
# 4. Commit: "feat: add KB health check"

# 5. Implement subprocess spawning
# 6. Test spawning
# 7. Commit: "feat: add KB subprocess spawning"

# 8. Implement wait for ready
# 9. Test wait logic
# 10. Commit: "feat: add KB ready wait logic"

# 11. Update start() method
# 12. Test auto-start
# 13. Commit: "feat: implement KB auto-start"

# 14. Add shutdown method
# 15. Test cleanup
# 16. Commit: "feat: add KB cleanup on shutdown"

# 17. Run full test suite
bun test

# 18. Manual E2E test
# 19. Update documentation
# 20. Commit: "docs: update for KB auto-start"

# 21. Create PR
git push origin feature/kb-lifecycle
```

---

## 📚 References

- **Full Plan:** [`KB-LIFECYCLE-MANAGEMENT.md`](KB-LIFECYCLE-MANAGEMENT.md)
- **Architecture:** [`ARCHITECTURE.md`](ARCHITECTURE.md#kb-lifecycle-management)
- **Testing Guide:** [`TESTING-GUIDE.md`](TESTING-GUIDE.md)
- **Implementation Status:** [`IMPLEMENTATION-STATUS.md`](IMPLEMENTATION-STATUS.md)

---

**Ready to Start?** Begin with Step 1: Health Check Method

**Questions?** Review the full plan in [`KB-LIFECYCLE-MANAGEMENT.md`](KB-LIFECYCLE-MANAGEMENT.md)

**Estimated Completion:** 4-6 hours for working auto-start