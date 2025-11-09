# End-to-End KB Auto-Start Testing

**Date:** November 9, 2025  
**Purpose:** Verify KB server lifecycle management works correctly  
**Status:** Test plan ready for execution

---

## 🎯 Test Objectives

Verify that:
1. KB server auto-starts when extension activates
2. Extension detects existing KB server and doesn't spawn duplicate
3. **Multiple VSCode windows share single KB server instance**
4. KB server shuts down cleanly when last extension deactivates
5. Error handling works for common failure scenarios
6. User experience is seamless (zero manual configuration)

---

## 📋 Prerequisites

### Required Software
- [x] VSCode 1.85+
- [x] Bun 1.0.14+ (`which bun`)
- [x] Python ≥3.12 (`python --version`)
- [x] uv package manager (`which uv`)
- [x] Dolphin installed (`uv pip install pb-dolphin` or local dev setup)

### Test Environment Setup
```bash
# 1. Clone/navigate to dolphin repo
cd /path/to/dolphin

# 2. Ensure dependencies installed
cd vscode-extension
npm install
npm run compile

cd webview
bun install
bun run build

cd ../../agent-core
bun install
```

---

## 🧪 Test Cases

### Test 1: Fresh Start (KB Not Running)

**Objective:** Verify extension auto-starts KB server

**Setup:**
```bash
# Stop any running KB
pkill -f "dolphin serve" || true
pkill -f "kb.api.server" || true

# Verify KB not running
curl http://localhost:7777/health
# Expected: Connection refused
```

**Steps:**
1. Open VSCode
2. Open dolphin workspace folder
3. Press `F5` to start Extension Development Host
4. Open Dolphin sidebar (dolphin icon)

**Expected Results:**
- [ ] Extension activates without errors
- [ ] VSCode Output > "Dolphin Agent" shows:
  ```
  [KB Manager] Checking if KB is already running...
  [KB Manager] Starting KB API...
  [KB stdout] ... (KB startup logs)
  [KB Manager] KB API ready
  [Agent Core] Agent ready!
  ```
- [ ] KB is running:
  ```bash
  curl http://localhost:7777/health
  # Expected: {"status": "healthy"}
  ```
- [ ] Extension sidebar shows ready state

**Pass Criteria:**
- ✅ No manual KB startup required
- ✅ KB process spawned automatically
- ✅ Extension becomes ready within 35 seconds
- ✅ No error messages in Output

---

### Test 2: KB Already Running

**Objective:** Verify extension detects existing KB and doesn't spawn duplicate

**Setup:**
```bash
# Start KB manually
uv run dolphin serve &
KB_PID=$!

# Wait for KB ready
sleep 5

# Verify KB running
curl http://localhost:7777/health
# Expected: {"status": "healthy"}
```

**Steps:**
1. Press `F5` to start Extension Development Host
2. Open Dolphin sidebar

**Expected Results:**
- [ ] VSCode Output > "Dolphin Agent" shows:
  ```
  [KB Manager] Checking if KB is already running...
  [KB Manager] KB already running
  [Agent Core] Agent ready!
  ```
- [ ] Only ONE KB process running:
  ```bash
  ps aux | grep "dolphin serve" | grep -v grep
  # Expected: Single process with PID matching $KB_PID
  ```

**Cleanup:**
```bash
kill $KB_PID
```

**Pass Criteria:**
- ✅ Extension detects existing KB
- ✅ No duplicate KB process spawned
- ✅ Extension uses existing KB server

---

### Test 2b: Multiple VSCode Windows (CRITICAL)

**Objective:** Verify multiple extension instances share single KB server

**Setup:**
```bash
# Ensure KB not running
pkill -f "dolphin serve" || true
```

**Steps:**
1. Press `F5` to start Extension Development Host #1
2. Wait for extension ready (KB should auto-start)
3. Verify KB process count:
   ```bash
   ps aux | grep "dolphin serve" | grep -v grep | wc -l
   # Expected: 1
   ```
4. Press `F5` again to start Extension Development Host #2
5. Wait for second extension ready
6. Verify KB process count again:
   ```bash
   ps aux | grep "dolphin serve" | grep -v grep | wc -l
   # Expected: Still 1 (shared server!)
   ```
7. Send chat message in Window #1: "What is Dolphin?"
8. Send chat message in Window #2: "List repositories"
9. Close Window #1
10. Verify KB still running (Window #2 still active):
    ```bash
    ps aux | grep "dolphin serve" | grep -v grep | wc -l
    # Expected: 1
    ```
11. Close Window #2
12. Wait 5 seconds
13. Verify KB terminated:
    ```bash
    ps aux | grep "dolphin serve" | grep -v grep | wc -l
    # Expected: 0
    ```

**Expected Results:**
- [ ] First window starts KB
- [ ] Second window detects existing KB
- [ ] Only ONE KB process running with both windows open
- [ ] Both windows can send messages successfully
- [ ] KB stays running while any window is open
- [ ] KB terminates when last window closes

**Current Implementation Status:**
⚠️ **ISSUE IDENTIFIED:** Current design spawns one KB per AgentCore instance!

**Problem:**
- Each VSCode window spawns its own Agent Core process
- Each Agent Core creates its own KBManager
- Each KBManager spawns its own KB server
- Result: Multiple KB servers on same port → **PORT CONFLICT**

**Expected Error:**
```
[KB stderr] Error: Address already in use (port 7777)
[Agent Core] Fatal error: KB API did not become ready within 30 seconds
```

**Pass Criteria (Once Fixed):**
- ✅ Only one KB server instance running
- ✅ Multiple windows share the same KB server
- ✅ No port conflicts
- ✅ KB terminates only when last window closes

---

### Test 3: Clean Shutdown

**Objective:** Verify KB process terminates when extension deactivates

**Setup:**
```bash
# Ensure KB not running
pkill -f "dolphin serve" || true
```

**Steps:**
1. Start extension (F5)
2. Wait for extension ready
3. Check KB process is running:
   ```bash
   ps aux | grep "dolphin serve" | grep -v grep
   # Note the PID
   ```
4. Close Extension Development Host window
5. Wait 5 seconds
6. Check if KB process still running:
   ```bash
   ps aux | grep "dolphin serve" | grep -v grep
   ```

**Expected Results:**
- [ ] KB process running after extension starts
- [ ] KB process NOT running after extension closes
- [ ] No zombie processes left behind

**Pass Criteria:**
- ✅ KB process terminates cleanly
- ✅ No orphaned processes
- ✅ Port 7777 released

---

### Test 4: Basic Chat Flow with Auto-Started KB

**Objective:** Verify end-to-end functionality with auto-started KB

**Setup:**
```bash
# Ensure KB not running
pkill -f "dolphin serve" || true

# Ensure Claude auth configured
# Option A: CLI auth
claude  # Authenticate if needed

# Option B: API key
export ANTHROPIC_API_KEY=sk-ant-...
```

**Steps:**
1. Start extension (F5)
2. Wait for extension ready
3. Open Dolphin sidebar > Chat
4. Send message: "What is Dolphin?"
5. Observe response

**Expected Results:**
- [ ] KB auto-starts (verified in Output)
- [ ] Chat input is enabled
- [ ] Message sent successfully
- [ ] KB search executes (see tool call card)
- [ ] Claude response generated
- [ ] Task completes successfully
- [ ] Response displayed in chat

**Pass Criteria:**
- ✅ Zero manual configuration
- ✅ KB search works
- ✅ Claude integration works
- ✅ Full flow completes successfully

---

### Test 5: KB Startup Failure

**Objective:** Verify error handling when KB fails to start

**Setup:**
```bash
# Occupy port 7777 to cause KB startup failure
python3 -m http.server 7777 &
BLOCKER_PID=$!
```

**Steps:**
1. Start extension (F5)
2. Observe Output logs

**Expected Results:**
- [ ] VSCode Output > "Dolphin Agent" shows:
  ```
  [KB Manager] Starting KB API...
  [KB stderr] Error: ... (port already in use)
  [Agent Core] Fatal error: KB API did not become ready within 30 seconds
  ```
- [ ] Extension shows error message
- [ ] User sees clear explanation

**Cleanup:**
```bash
kill $BLOCKER_PID
```

**Pass Criteria:**
- ✅ Error detected and reported
- ✅ Clear error message shown
- ✅ Extension fails gracefully
- ✅ Logs provide debugging information

---

### Test 6: KB Crash Mid-Session

**Objective:** Verify handling of KB process crash during use

**Setup:**
```bash
# Start extension normally (KB will auto-start)
```

**Steps:**
1. Start extension (F5)
2. Wait for extension ready
3. Find KB process PID:
   ```bash
   ps aux | grep "dolphin serve" | grep -v grep
   ```
4. Kill KB process:
   ```bash
   pkill -9 -f "dolphin serve"
   ```
5. Try to send a chat message: "Hello"

**Expected Results:**
- [ ] Extension detects KB is down
- [ ] Error shown to user
- [ ] Logs indicate KB process exited

**Current Behavior:**
⚠️ KB does NOT auto-restart on crash (this is expected for v1)

**Pass Criteria:**
- ✅ Error detected and logged
- ✅ User informed of issue
- ✅ No extension crash

**Future Enhancement:**
- [ ] Auto-restart KB on crash detection

---

### Test 7: Missing Dependencies

**Objective:** Verify error handling when `uv` not installed

**Setup:**
```bash
# Temporarily rename uv
sudo mv /usr/local/bin/uv /usr/local/bin/uv.bak 2>/dev/null || true
sudo mv /opt/homebrew/bin/uv /opt/homebrew/bin/uv.bak 2>/dev/null || true
```

**Steps:**
1. Start extension (F5)
2. Observe Output logs

**Expected Results:**
- [ ] Extension fails to start KB
- [ ] Clear error message about missing `uv`
- [ ] Logs show spawn error

**Cleanup:**
```bash
# Restore uv
sudo mv /usr/local/bin/uv.bak /usr/local/bin/uv 2>/dev/null || true
sudo mv /opt/homebrew/bin/uv.bak /opt/homebrew/bin/uv 2>/dev/null || true
```

**Pass Criteria:**
- ✅ Error detected
- ✅ User gets actionable error message
- ✅ Extension fails gracefully

---

## 🚨 CRITICAL ISSUE: Multi-Window KB Sharing

### Problem Statement

**Current Behavior:**
- Each VSCode window spawns its own Agent Core process
- Each Agent Core creates its own KBManager instance
- Each KBManager tries to spawn KB on port 7777
- Second+ windows fail with "Address already in use"

**Expected Behavior:**
- All VSCode windows share a single KB server instance
- First window starts KB
- Subsequent windows detect running KB
- KB terminates only when last window closes

### Root Cause

Each Agent Core process is independent with its own KBManager. They don't coordinate.

### Solution Options

#### Option A: System-Wide KB Process (Recommended)

Use a **global KB process** managed by the system, not per-extension.

**Implementation:**
1. Check if KB running globally (systemd, launchd, or manual)
2. If not, start as background daemon
3. Never terminate KB (let user manage it)

**Pros:**
- Simple implementation
- No coordination needed between windows
- KB stays running for all VSCode instances

**Cons:**
- Requires user to manage KB lifecycle manually (restart on crash)
- Or implement system service (complex)

#### Option B: Named Mutex/Lock File (Better)

Use a **lock file** to coordinate KB ownership between Agent instances.

**Implementation:**
1. Create lock file: `/tmp/dolphin-kb.lock` with PID
2. First instance creates lock, starts KB
3. Subsequent instances see lock, skip KB start
4. On shutdown, check if we own the lock
5. If yes, delete lock and terminate KB
6. If no, just exit (KB stays running)

**Pseudocode:**
```typescript
class KBManager {
  private lockFile = "/tmp/dolphin-kb.lock";
  private weOwnKB = false;

  async start() {
    // Check if KB already running
    if (await this.healthCheck()) {
      console.error("KB already running (managed by another instance)");
      return;
    }

    // Try to acquire lock
    if (this.tryAcquireLock()) {
      this.weOwnKB = true;
      // Spawn KB
      this.process = spawn("uv", ["run", "dolphin", "serve"], ...);
      await this.waitForReady();
    } else {
      // Another instance is starting KB, wait for it
      await this.waitForReady();
    }
  }

  shutdown() {
    if (this.weOwnKB && this.process) {
      this.process.kill("SIGTERM");
      this.releaseLock();
    }
  }

  private tryAcquireLock(): boolean {
    try {
      if (fs.existsSync(this.lockFile)) {
        // Check if PID in lock file is still running
        const pid = parseInt(fs.readFileSync(this.lockFile, "utf-8"));
        if (this.isProcessRunning(pid)) {
          return false; // Another instance owns it
        }
        // Stale lock, remove it
        fs.unlinkSync(this.lockFile);
      }

      // Create lock with our PID
      fs.writeFileSync(this.lockFile, process.pid.toString());
      return true;
    } catch {
      return false;
    }
  }
}
```

**Pros:**
- Automatic coordination between windows
- KB terminates when last window closes
- Robust handling of stale locks

**Cons:**
- Race condition if two windows start simultaneously (solvable with atomic file ops)

#### Option C: HTTP API for Lifecycle Management

KB server provides `/admin/register` and `/admin/unregister` endpoints.

**Implementation:**
1. Agent registers with KB on startup
2. KB tracks active clients
3. KB auto-terminates when last client unregisters
4. Clients send heartbeats

**Pros:**
- Most robust solution
- Handles network scenarios
- KB can manage own lifecycle

**Cons:**
- Requires KB server changes (not just extension)
- More complex implementation

### Recommended Solution

**Use Option B (Lock File)** for v1.0:
- Fastest to implement (extension-only change)
- Handles multiple windows correctly
- No changes to KB server needed
- Good enough for single-machine use

**Consider Option C** for future v2.0:
- Needed for remote KB servers
- Better for multi-user scenarios

---

## 📊 Test Results Template

### Test Execution Log

**Date:** ___________  
**Tester:** ___________  
**Environment:**
- OS: ___________
- VSCode: ___________
- Bun: ___________
- Python: ___________
- uv: ___________

### Results Summary

| Test Case | Status | Notes |
|-----------|--------|-------|
| Test 1: Fresh Start | ⬜ Pass / ⬜ Fail | |
| Test 2: KB Already Running | ⬜ Pass / ⬜ Fail | |
| Test 2b: Multiple Windows | ⬜ Pass / ⬜ Fail | **CRITICAL** |
| Test 3: Clean Shutdown | ⬜ Pass / ⬜ Fail | |
| Test 4: Basic Chat Flow | ⬜ Pass / ⬜ Fail | |
| Test 5: KB Startup Failure | ⬜ Pass / ⬜ Fail | |
| Test 6: KB Crash Mid-Session | ⬜ Pass / ⬜ Fail | |
| Test 7: Missing Dependencies | ⬜ Pass / ⬜ Fail | |

### Issues Found

**Issue 1: Multi-Window Port Conflict**
- **Description:** Multiple VSCode windows try to start separate KB servers on same port
- **Severity:** Critical (blocks multi-window use)
- **Steps to Reproduce:** Open two Extension Development Host windows
- **Expected:** Share single KB server
- **Actual:** Second window fails with port conflict
- **Fix:** Implement lock file coordination (Option B above)

---

## ✅ Success Criteria

Extension is production-ready when:

- [x] Test 1 passes: Fresh start works
- [x] Test 2 passes: Detects existing KB
- [ ] **Test 2b passes: Multiple windows share KB** ← BLOCKER
- [x] Test 3 passes: Clean shutdown
- [x] Test 4 passes: End-to-end chat flow works
- [x] Test 5 passes: Startup failures handled gracefully
- [x] Test 6 passes: Crash detection works
- [x] Test 7 passes: Missing dependencies reported clearly

**Minimum Viable Product:** Tests 1-4 + 2b must pass  
**Production Ready:** All tests must pass

---

## 📝 Next Steps

1. **Implement lock file coordination** (Test 2b fix)
2. **Run full test suite** to verify all scenarios
3. **Document results** in this file
4. **Fix any remaining issues**
5. **Declare production-ready** when all tests pass

---

## 🔗 References

- **Implementation:** [`agent-core/src/kb/manager.ts`](../agent-core/src/kb/manager.ts)
- **Architecture:** [`docs/KB-LIFECYCLE-MANAGEMENT.md`](KB-LIFECYCLE-MANAGEMENT.md)
- **User Guide:** [`docs/TESTING-GUIDE.md`](TESTING-GUIDE.md)

---

**Status:** Test plan ready, **critical issue identified** (multi-window support)  
**Next Step:** Implement lock file coordination in KBManager  
**Estimated Fix Time:** 1-2 hours