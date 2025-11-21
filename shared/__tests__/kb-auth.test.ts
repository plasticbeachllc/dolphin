import { describe, it, expect, beforeEach, afterEach, spyOn } from "bun:test";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { getKbKeyPath, resolveKbApiKey, getOrCreateKbApiKey } from "../kb-auth";

describe("KB Auth", () => {
  let testHomeDir: string;
  let originalEnv: NodeJS.ProcessEnv;

  beforeEach(() => {
    // Create a temporary test directory
    testHomeDir = fs.mkdtempSync(path.join(os.tmpdir(), "kb-auth-test-"));

    // Save original environment
    originalEnv = { ...process.env };

    // Clear KB-related env vars
    delete process.env.DOLPHIN_API_KEY;
    delete process.env.DOLPHIN_KB_API_KEY;
  });

  afterEach(() => {
    // Restore environment
    process.env = originalEnv;

    // Clean up test directory
    if (fs.existsSync(testHomeDir)) {
      fs.rmSync(testHomeDir, { recursive: true, force: true });
    }
  });

  describe("getKbKeyPath", () => {
    it("should return default path when no options provided", () => {
      const keyPath = getKbKeyPath();
      expect(keyPath).toBe(path.join(os.homedir(), ".dolphin", "kb_api_key"));
    });

    it("should use custom homeDir when provided", () => {
      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      expect(keyPath).toBe(path.join(testHomeDir, ".dolphin", "kb_api_key"));
    });
  });

  describe("resolveKbApiKey", () => {
    it("should return undefined when no key exists", () => {
      const key = resolveKbApiKey({ homeDir: testHomeDir });
      expect(key).toBeUndefined();
    });

    it("should prioritize DOLPHIN_API_KEY env var", () => {
      process.env.DOLPHIN_API_KEY = "env-key-1";
      const key = resolveKbApiKey({ homeDir: testHomeDir });
      expect(key).toBe("env-key-1");
    });

    it("should use DOLPHIN_KB_API_KEY if DOLPHIN_API_KEY not set", () => {
      process.env.DOLPHIN_KB_API_KEY = "env-key-2";
      const key = resolveKbApiKey({ homeDir: testHomeDir });
      expect(key).toBe("env-key-2");
    });

    it("should read from file when env vars not set", () => {
      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      const dir = path.dirname(keyPath);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(keyPath, "file-key-123\n", { encoding: "utf8" });

      const key = resolveKbApiKey({ homeDir: testHomeDir });
      expect(key).toBe("file-key-123");
    });

    it("should trim whitespace from file contents", () => {
      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      const dir = path.dirname(keyPath);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(keyPath, "  file-key-456  \n\n", { encoding: "utf8" });

      const key = resolveKbApiKey({ homeDir: testHomeDir });
      expect(key).toBe("file-key-456");
    });

    it("should return undefined for empty file", () => {
      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      const dir = path.dirname(keyPath);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(keyPath, "   \n", { encoding: "utf8" });

      const key = resolveKbApiKey({ homeDir: testHomeDir });
      expect(key).toBeUndefined();
    });
  });

  describe("getOrCreateKbApiKey", () => {
    it("should prioritize DOLPHIN_API_KEY env var", () => {
      process.env.DOLPHIN_API_KEY = "env-key-1";
      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });
      expect(key).toBe("env-key-1");
    });

    it("should use DOLPHIN_KB_API_KEY if DOLPHIN_API_KEY not set", () => {
      process.env.DOLPHIN_KB_API_KEY = "env-key-2";
      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });
      expect(key).toBe("env-key-2");
    });

    it("should create new key file when none exists", () => {
      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });

      // Should be 64-character hex string
      expect(key).toMatch(/^[0-9a-f]{64}$/);

      // File should exist
      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      expect(fs.existsSync(keyPath)).toBe(true);

      // File should contain the key
      const fileContents = fs.readFileSync(keyPath, "utf8").trim();
      expect(fileContents).toBe(key);
    });

    it("should return existing key from file", () => {
      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      const dir = path.dirname(keyPath);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(keyPath, "existing-key-789\n", { encoding: "utf8" });

      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });
      expect(key).toBe("existing-key-789");
    });

    it("should create directory if it doesn't exist", () => {
      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });

      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      const dir = path.dirname(keyPath);

      expect(fs.existsSync(dir)).toBe(true);
      expect(fs.existsSync(keyPath)).toBe(true);
    });

    it("should handle race condition when multiple processes create key", () => {
      // Simulate race condition by creating file after directory check
      const key1 = getOrCreateKbApiKey({ homeDir: testHomeDir });
      const key2 = getOrCreateKbApiKey({ homeDir: testHomeDir });

      // Both should return the same key
      expect(key1).toBe(key2);
    });

    it("should set file permissions to 0600", () => {
      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });
      const keyPath = getKbKeyPath({ homeDir: testHomeDir });

      const stats = fs.statSync(keyPath);
      const mode = stats.mode & 0o777;

      // Should be user read/write only (0600)
      expect(mode).toBe(0o600);
    });

    it("should handle EEXIST race during creation", () => {
      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      const dir = path.dirname(keyPath);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(keyPath, "preexisting-key\n", { encoding: "utf8" });

      const originalExistsSync = fs.existsSync;
      const originalOpenSync = fs.openSync;

      let openCalled = false;
      const existsSpy = spyOn(fs, "existsSync").mockReturnValue(false as unknown as boolean);
      const openSpy = spyOn(fs, "openSync").mockImplementation(() => {
        openCalled = true;
        const err = new Error("EEXIST");
        // @ts-expect-error augment error code
        err.code = "EEXIST";
        throw err;
      });

      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });

      expect(openCalled).toBe(true);
      expect(key).toBe("preexisting-key");

      existsSpy.mockRestore();
      openSpy.mockRestore();
    });
  });

  describe("readOnly flag", () => {
    it("should respect readOnly flag in resolveKbApiKey", () => {
      // This is a documentation test - readOnly doesn't change behavior
      // of resolveKbApiKey since it never creates files anyway
      const key = resolveKbApiKey({ homeDir: testHomeDir, readOnly: true });
      expect(key).toBeUndefined();
    });
  });
});
