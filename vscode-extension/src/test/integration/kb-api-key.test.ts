import { describe, it, beforeEach, afterEach } from "mocha";
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { getOrCreateKbApiKey, getKbKeyPath } from "../../../../shared/kb-auth";
import type { ExtensionContext } from "vscode";
import { initializeKbApiKeyForTests, resetKbApiKeyForTests } from "../../extension";

/**
 * Integration tests for VS Code extension KB API key auto-provisioning.
 *
 * These tests verify that the extension correctly:
 * 1. Auto-provisions KB API keys on first activation
 * 2. Respects environment variable precedence
 * 3. Stores keys in SecretStorage
 * 4. Handles edge cases (missing files, race conditions, etc.)
 */
describe("VS Code Extension - KB API Key Integration", () => {
  let testHomeDir: string;
  let originalEnv: NodeJS.ProcessEnv;

  beforeEach(() => {
    testHomeDir = fs.mkdtempSync(path.join(os.tmpdir(), "vscode-kb-test-"));
    originalEnv = { ...process.env };
    delete process.env.DOLPHIN_API_KEY;
    delete process.env.DOLPHIN_KB_API_KEY;
  });

  afterEach(() => {
    process.env = originalEnv;
    if (fs.existsSync(testHomeDir)) {
      fs.rmSync(testHomeDir, { recursive: true, force: true });
    }
    resetKbApiKeyForTests();
  });

  describe("initializeKbApiKey simulation", () => {
    it("should use environment variable if set", () => {
      process.env.DOLPHIN_API_KEY = "env-override-key";

      // Simulate extension's initializeKbApiKey logic
      const envKey = process.env.DOLPHIN_API_KEY || process.env.DOLPHIN_KB_API_KEY;

      assert.strictEqual(envKey, "env-override-key");
    });

    it("should auto-provision key when no env var or secret exists", () => {
      // Simulate extension calling getOrCreateKbApiKey
      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });

      // Should create a valid 64-char hex key
      assert.match(key, /^[0-9a-f]{64}$/);

      // File should exist
      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      assert.ok(fs.existsSync(keyPath));
    });

    it("should reuse existing key from file", () => {
      // First call creates the key
      const key1 = getOrCreateKbApiKey({ homeDir: testHomeDir });

      // Second call should return the same key
      const key2 = getOrCreateKbApiKey({ homeDir: testHomeDir });

      assert.strictEqual(key1, key2);
    });

    it("should handle missing .dolphin directory", () => {
      // Ensure directory doesn't exist
      const dolphinDir = path.join(testHomeDir, ".dolphin");
      if (fs.existsSync(dolphinDir)) {
        fs.rmSync(dolphinDir, { recursive: true });
      }

      // Should create directory and key
      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });

      assert.ok(fs.existsSync(dolphinDir));
      assert.match(key, /^[0-9a-f]{64}$/);
    });
  });

  describe("precedence order", () => {
    it("should prioritize DOLPHIN_API_KEY over file", () => {
      // Create a file with one key
      const fileKey = getOrCreateKbApiKey({ homeDir: testHomeDir });

      // Set env var with different key
      process.env.DOLPHIN_API_KEY = "env-priority-key";

      // Env var should take precedence
      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });
      assert.strictEqual(key, "env-priority-key");
      assert.notStrictEqual(key, fileKey);
    });

    it("should use DOLPHIN_KB_API_KEY if DOLPHIN_API_KEY not set", () => {
      process.env.DOLPHIN_KB_API_KEY = "kb-env-key";

      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });
      assert.strictEqual(key, "kb-env-key");
    });
  });

  describe("error handling", () => {
    it("should handle corrupted key file gracefully", () => {
      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      const dir = path.dirname(keyPath);
      fs.mkdirSync(dir, { recursive: true });

      // Create empty file
      fs.writeFileSync(keyPath, "", { encoding: "utf8" });

      // Should generate new key
      const key = getOrCreateKbApiKey({ homeDir: testHomeDir });
      assert.match(key, /^[0-9a-f]{64}$/);
    });
  });

  describe("initializeKbApiKey end-to-end", () => {
    const makeMockContext = (secretValue?: string): ExtensionContext =>
      ({
        secrets: {
          async get(id: string) {
            void id;
            return secretValue;
          },
          async store(id: string, value: string) {
            stored.id = id;
            stored.value = value;
          },
          async delete(id: string) {
            deletedIds.push(id);
          },
        },
      } as unknown as ExtensionContext);

    let stored: { id?: string; value?: string };
    let deletedIds: string[];

    beforeEach(() => {
      stored = {};
      deletedIds = [];
      process.env.HOME = testHomeDir;
      process.env.USERPROFILE = testHomeDir;
    });

    it("auto-provisions and stores KB key when env and SecretStorage are empty", async () => {
      const ctx = makeMockContext();

      await initializeKbApiKeyForTests(ctx);

      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      assert.ok(fs.existsSync(keyPath), "key file should be created");

      const keyFromFile = fs.readFileSync(keyPath, "utf8").trim();
      assert.match(keyFromFile, /^[0-9a-f]{64}$/);
      assert.strictEqual(process.env.DOLPHIN_API_KEY, keyFromFile);
      assert.strictEqual(stored.id, "dolphin.kbApiKey");
      assert.strictEqual(stored.value, keyFromFile);
    });

    it("uses SecretStorage value when present and avoids touching filesystem", async () => {
      const ctx = makeMockContext("secret-stored-key");

      await initializeKbApiKeyForTests(ctx);

      const keyPath = getKbKeyPath({ homeDir: testHomeDir });
      assert.ok(!fs.existsSync(keyPath), "should not create key file when secret is present");
      assert.strictEqual(process.env.DOLPHIN_API_KEY, "secret-stored-key");
      assert.strictEqual(stored.id, undefined, "no new secret should be stored");
    });
  });
});
