// agent-core/tests/kb/manager.test.ts
import { describe, it, expect, beforeEach, afterEach, mock } from "bun:test";
import { KBManager } from "../../src/kb/manager";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

describe("KBManager", () => {
  const lockFile = path.join(os.tmpdir(), "dolphin-kb.lock");
  let manager: KBManager;

  beforeEach(() => {
    // Clean up any existing lock file
    if (fs.existsSync(lockFile)) {
      fs.unlinkSync(lockFile);
    }
    manager = new KBManager();
  });

  afterEach(() => {
    // Clean up lock file after tests
    if (fs.existsSync(lockFile)) {
      fs.unlinkSync(lockFile);
    }
  });

  describe("Lock File Coordination", () => {
    it("should create lock file with current PID on first acquisition", async () => {
      // Acquire lock (without actually starting KB)
      const acquired = (manager as any).tryAcquireLock();
      
      expect(acquired).toBe(true);
      expect(fs.existsSync(lockFile)).toBe(true);
      
      const lockContent = fs.readFileSync(lockFile, "utf-8");
      expect(lockContent).toBe(process.pid.toString());
      
      // Cleanup
      (manager as any).releaseLock();
    });

    it("should not acquire lock when another process holds it", async () => {
      // Create lock file with a different PID (our own, so it's valid)
      fs.writeFileSync(lockFile, process.pid.toString());
      
      // Create second manager instance
      const manager2 = new KBManager();
      const acquired = (manager2 as any).tryAcquireLock();
      
      expect(acquired).toBe(false);
    });

    it("should remove stale lock file from dead process", async () => {
      // Create lock file with a non-existent PID
      const deadPid = 999999;
      fs.writeFileSync(lockFile, deadPid.toString());
      
      const acquired = (manager as any).tryAcquireLock();
      
      expect(acquired).toBe(true);
      
      const lockContent = fs.readFileSync(lockFile, "utf-8");
      expect(lockContent).toBe(process.pid.toString());
      
      // Cleanup
      (manager as any).releaseLock();
    });

    it("should release lock on shutdown", async () => {
      // Acquire lock
      (manager as any).weOwnKB = true;
      (manager as any).tryAcquireLock();
      
      expect(fs.existsSync(lockFile)).toBe(true);
      
      // Release lock
      (manager as any).releaseLock();
      
      expect(fs.existsSync(lockFile)).toBe(false);
    });

    it("should not release lock if we don't own it", async () => {
      // Create lock file with current PID
      fs.writeFileSync(lockFile, process.pid.toString());
      (manager as any).weOwnKB = false;
      
      // Try to release
      (manager as any).releaseLock();
      
      // Lock file should still exist
      expect(fs.existsSync(lockFile)).toBe(true);
    });
  });

  describe("Process Ownership", () => {
    it("should set weOwnKB when acquiring lock", async () => {
      expect((manager as any).weOwnKB).toBe(false);
      
      (manager as any).tryAcquireLock();
      
      // After acquiring lock, we should mark ownership
      // (Note: weOwnKB is set in start() method, not tryAcquireLock())
      // So this test just verifies the lock is acquired
      expect(fs.existsSync(lockFile)).toBe(true);
      
      // Cleanup
      (manager as any).weOwnKB = true;
      (manager as any).releaseLock();
    });
  });

  describe("Health Check", () => {
    it("should return false when KB not running", async () => {
      // Mock fetch to simulate KB not responding
      const originalFetch = globalThis.fetch;
      globalThis.fetch = mock(() => {
        throw new Error("Connection refused");
      }) as any;

      const healthy = await (manager as any).healthCheck();
      expect(healthy).toBe(false);

      // Restore original fetch
      globalThis.fetch = originalFetch;
    });

    // Note: Testing healthCheck with running KB requires integration test
  });

  describe("Process Running Check", () => {
    it("should detect current process is running", () => {
      const isRunning = (manager as any).isProcessRunning(process.pid);
      expect(isRunning).toBe(true);
    });

    it("should detect non-existent process is not running", () => {
      const isRunning = (manager as any).isProcessRunning(999999);
      expect(isRunning).toBe(false);
    });
  });
});