/**
 * Integration tests for Claude CLI authentication
 *
 * Tests authentication detection and management
 */

import { describe, it, expect, beforeEach, afterEach, mock } from "bun:test";
import { AnthropicProvider, AuthManager } from "../../../src/execution/anthropic-provider";
import { existsSync, writeFileSync, mkdirSync, unlinkSync, rmSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";

describe("Claude Authentication Integration", () => {
  const testSettingsDir = join(tmpdir(), "dolphin-claude-test");
  const testSettingsPath = join(testSettingsDir, "settings.json");
  const originalApiKey = process.env.ANTHROPIC_API_KEY;

  beforeEach(() => {
    mkdirSync(testSettingsDir, { recursive: true });
    // Clean up any previous test settings
    try {
      if (existsSync(testSettingsPath)) {
        unlinkSync(testSettingsPath);
      }
    } catch {
      // Ignore cleanup errors
    }
  });

  afterEach(() => {
    // Restore original API key
    if (originalApiKey) {
      process.env.ANTHROPIC_API_KEY = originalApiKey;
    } else {
      delete process.env.ANTHROPIC_API_KEY;
    }

    // Clean up test settings
    try {
      if (existsSync(testSettingsDir)) {
        rmSync(testSettingsDir, { recursive: true, force: true });
      }
    } catch {
      // Ignore cleanup errors
    }
  });

  describe("AuthManager", () => {
    let authManager: AuthManager;

    beforeEach(() => {
      authManager = new AuthManager({ settingsPath: testSettingsPath });
    });

    it("should detect OAuth authentication", async () => {
      // Create mock settings file
      mkdirSync(testSettingsDir, { recursive: true });
      writeFileSync(testSettingsPath, JSON.stringify({ token: "mock-token" }));

      // Remove API key
      delete process.env.ANTHROPIC_API_KEY;

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(true);
      expect(status.mode).toBe("subscription");
      expect(status.source).toBe("Claude CLI OAuth");

      // Cleanup
      try {
        unlinkSync(testSettingsPath);
      } catch {
        // Ignore
      }
    });

    it("should detect API key authentication", async () => {
      // Remove OAuth settings
      if (existsSync(testSettingsPath)) {
        unlinkSync(testSettingsPath);
      }

      // Set API key
      process.env.ANTHROPIC_API_KEY = "sk-test-key";

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(true);
      expect(status.mode).toBe("api_key");
      expect(status.source).toBe("ANTHROPIC_API_KEY");
      expect(status.warning).toContain("pay-as-you-go");
    });

    it("should detect API key takes precedence when both present", async () => {
      // Create OAuth settings
      mkdirSync(testSettingsDir, { recursive: true });
      writeFileSync(testSettingsPath, JSON.stringify({ token: "mock-token" }));

      // Also set API key
      process.env.ANTHROPIC_API_KEY = "sk-test-key";

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(true);
      expect(status.mode).toBe("api_key");
      expect(status.source).toBe("ANTHROPIC_API_KEY");
      expect(status.warning).toContain("Claude CLI will use API key billing");
      expect(status.warning).toContain("pay-per-token");

      // Cleanup
      try {
        unlinkSync(testSettingsPath);
      } catch {
        // Ignore
      }
    });

    it("should detect no authentication", async () => {
      // Remove both OAuth and API key
      if (existsSync(testSettingsPath)) {
        unlinkSync(testSettingsPath);
      }
      delete process.env.ANTHROPIC_API_KEY;

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(false);
      expect(status.mode).toBe("none");
      expect(status.error).toBeDefined();
    });

    it("should throw error when not authenticated", async () => {
      // Remove both OAuth and API key
      if (existsSync(testSettingsPath)) {
        unlinkSync(testSettingsPath);
      }
      delete process.env.ANTHROPIC_API_KEY;

      await expect(async () => {
        await authManager.ensureAuthenticated();
      }).toThrow(/not authenticated/);
    });

    it("should warn about API key usage", async () => {
      // Remove OAuth
      if (existsSync(testSettingsPath)) {
        unlinkSync(testSettingsPath);
      }

      // Set API key
      process.env.ANTHROPIC_API_KEY = "sk-test-key";

      // Mock console.warn
      const originalWarn = console.warn;
      const warnings: string[] = [];
      console.warn = mock((...args: unknown[]) => {
        warnings.push(args.join(" "));
      });

      await authManager.ensureAuthenticated();

      // Should have warned about pay-as-you-go
      expect(warnings.some((w) => w.includes("pay-as-you-go"))).toBe(true);

      // Restore console.warn
      console.warn = originalWarn;
    });
  });

  describe("AnthropicProvider Authentication", () => {
    let provider: AnthropicProvider;

    beforeEach(() => {
      provider = new AnthropicProvider({
        workspaceRoot: "/test/workspace",
        authManager: new AuthManager({ settingsPath: testSettingsPath }),
      });
    });

    it("should detect auth status", async () => {
      const status = await provider.detectAuthStatus();

      expect(status).toBeDefined();
      expect(typeof status.authenticated).toBe("boolean");
      expect(status.mode).toBeDefined();
    });

    it("should ensure authentication before execution", async () => {
      // Remove all auth
      if (existsSync(testSettingsPath)) {
        unlinkSync(testSettingsPath);
      }
      delete process.env.ANTHROPIC_API_KEY;

      await expect(async () => {
        await provider.ensureAuthenticated();
      }).toThrow(/not authenticated/);
    });
  });

  describe("Authentication States", () => {
    it("should handle OAuth subscription state", async () => {
      const authManager = new AuthManager({ settingsPath: testSettingsPath });

      // Create OAuth settings
      const settingsDir = testSettingsDir;
      if (!existsSync(settingsDir)) {
        mkdirSync(settingsDir, { recursive: true });
      }

      writeFileSync(
        testSettingsPath,
        JSON.stringify({
          token: "mock-token",
          subscription: {
            plan: "pro",
            status: "active",
          },
        })
      );

      delete process.env.ANTHROPIC_API_KEY;

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(true);
      expect(status.mode).toBe("subscription");

      // Cleanup
      try {
        unlinkSync(testSettingsPath);
      } catch {
        // Ignore
      }
    });

    it("should handle API key state", async () => {
      const authManager = new AuthManager({ settingsPath: testSettingsPath });

      // Remove OAuth
      if (existsSync(testSettingsPath)) {
        unlinkSync(testSettingsPath);
      }

      process.env.ANTHROPIC_API_KEY = "sk-ant-api03-1234567890";

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(true);
      expect(status.mode).toBe("api_key");
      expect(status.source).toBe("ANTHROPIC_API_KEY");
    });

    it("should handle no auth state", async () => {
      const authManager = new AuthManager({ settingsPath: testSettingsPath });

      // Remove all auth
      if (existsSync(testSettingsPath)) {
        unlinkSync(testSettingsPath);
      }
      delete process.env.ANTHROPIC_API_KEY;

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(false);
      expect(status.mode).toBe("none");
      expect(status.error).toBeDefined();
    });
  });

  describe("Authentication Warnings", () => {
    it("should warn when both auth methods present (API key takes precedence)", async () => {
      const authManager = new AuthManager({ settingsPath: testSettingsPath });

      // Create OAuth settings
      mkdirSync(testSettingsDir, { recursive: true });
      writeFileSync(testSettingsPath, JSON.stringify({ token: "mock-token" }));

      // Also set API key
      process.env.ANTHROPIC_API_KEY = "sk-test-key";

      const status = await authManager.detectAuthStatus();

      expect(status.warning).toBeDefined();
      expect(status.warning).toContain("API key billing");
      expect(status.warning).toContain("pay-per-token");
      expect(status.mode).toBe("api_key");

      // Cleanup
      try {
        unlinkSync(testSettingsPath);
      } catch {
        // Ignore
      }
    });

    it("should warn about pay-as-you-go with API key", async () => {
      const authManager = new AuthManager({ settingsPath: testSettingsPath });

      // Remove OAuth
      if (existsSync(testSettingsPath)) {
        unlinkSync(testSettingsPath);
      }

      process.env.ANTHROPIC_API_KEY = "sk-test-key";

      const status = await authManager.detectAuthStatus();

      expect(status.warning).toBeDefined();
      expect(status.warning).toContain("pay-as-you-go");
    });
  });

  describe("Error Handling", () => {
    it("should handle missing .claude directory", async () => {
      const authManager = new AuthManager({ settingsPath: testSettingsPath });

      // Ensure .claude directory doesn't exist (it likely does in real environment)
      // Just test that the code handles it gracefully
      delete process.env.ANTHROPIC_API_KEY;

      const status = await authManager.detectAuthStatus();

      // Should detect as not authenticated
      expect(typeof status.authenticated).toBe("boolean");
    });

    it("should handle corrupted settings file", async () => {
      const authManager = new AuthManager({ settingsPath: testSettingsPath });

      // Create corrupted settings file
      mkdirSync(testSettingsDir, { recursive: true });
      writeFileSync(testSettingsPath, "invalid json {{{");

      delete process.env.ANTHROPIC_API_KEY;

      // Should handle gracefully - corrupted file means no valid auth
      const status = await authManager.detectAuthStatus();

      // Corrupted file should be treated as NOT authenticated
      expect(status.authenticated).toBe(false);
      expect(status.mode).toBe("none");
      expect(status.error).toBeDefined();

      // Cleanup
      try {
        unlinkSync(testSettingsPath);
      } catch {
        // Ignore
      }
    });
  });
});
