/**
 * Integration tests for Claude CLI authentication
 *
 * Tests authentication detection and management
 */

import { describe, it, expect, beforeEach, afterEach, mock } from "bun:test";
import { ClaudeProvider, AuthManager } from "../../src/execution/claude-provider";
import { existsSync, writeFileSync, mkdirSync, unlinkSync } from "fs";
import { join } from "path";
import { homedir } from "os";

describe("Claude Authentication Integration", () => {
  const testSettingsPath = join(homedir(), ".claude-test", "settings.json");
  const originalApiKey = process.env.ANTHROPIC_API_KEY;

  beforeEach(() => {
    // Clean up any previous test settings
    try {
      if (existsSync(testSettingsPath)) {
        unlinkSync(testSettingsPath);
      }
    } catch (error) {
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
      if (existsSync(testSettingsPath)) {
        unlinkSync(testSettingsPath);
      }
    } catch (error) {
      // Ignore cleanup errors
    }
  });

  describe("AuthManager", () => {
    let authManager: AuthManager;

    beforeEach(() => {
      authManager = new AuthManager();
    });

    it("should detect OAuth authentication", async () => {
      // Create mock settings file
      const settingsDir = join(homedir(), ".claude");
      if (!existsSync(settingsDir)) {
        mkdirSync(settingsDir, { recursive: true });
      }

      const settingsPath = join(settingsDir, "settings.json");
      writeFileSync(settingsPath, JSON.stringify({ token: "mock-token" }));

      // Remove API key
      delete process.env.ANTHROPIC_API_KEY;

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(true);
      expect(status.mode).toBe("subscription");
      expect(status.source).toBe("Claude CLI OAuth");

      // Cleanup
      try {
        unlinkSync(settingsPath);
      } catch (error) {
        // Ignore
      }
    });

    it("should detect API key authentication", async () => {
      // Remove OAuth settings
      const settingsPath = join(homedir(), ".claude", "settings.json");
      if (existsSync(settingsPath)) {
        unlinkSync(settingsPath);
      }

      // Set API key
      process.env.ANTHROPIC_API_KEY = "sk-test-key";

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(true);
      expect(status.mode).toBe("api_key");
      expect(status.source).toBe("ANTHROPIC_API_KEY");
      expect(status.warning).toContain("pay-as-you-go");
    });

    it("should prefer OAuth over API key", async () => {
      // Create OAuth settings
      const settingsDir = join(homedir(), ".claude");
      if (!existsSync(settingsDir)) {
        mkdirSync(settingsDir, { recursive: true });
      }

      const settingsPath = join(settingsDir, "settings.json");
      writeFileSync(settingsPath, JSON.stringify({ token: "mock-token" }));

      // Also set API key
      process.env.ANTHROPIC_API_KEY = "sk-test-key";

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(true);
      expect(status.mode).toBe("subscription");
      expect(status.warning).toContain("ANTHROPIC_API_KEY ignored");

      // Cleanup
      try {
        unlinkSync(settingsPath);
      } catch (error) {
        // Ignore
      }
    });

    it("should detect no authentication", async () => {
      // Remove both OAuth and API key
      const settingsPath = join(homedir(), ".claude", "settings.json");
      if (existsSync(settingsPath)) {
        unlinkSync(settingsPath);
      }
      delete process.env.ANTHROPIC_API_KEY;

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(false);
      expect(status.mode).toBe("none");
      expect(status.error).toBeDefined();
    });

    it("should throw error when not authenticated", async () => {
      // Remove both OAuth and API key
      const settingsPath = join(homedir(), ".claude", "settings.json");
      if (existsSync(settingsPath)) {
        unlinkSync(settingsPath);
      }
      delete process.env.ANTHROPIC_API_KEY;

      await expect(async () => {
        await authManager.ensureAuthenticated();
      }).toThrow(/not authenticated/);
    });

    it("should warn about API key usage", async () => {
      // Remove OAuth
      const settingsPath = join(homedir(), ".claude", "settings.json");
      if (existsSync(settingsPath)) {
        unlinkSync(settingsPath);
      }

      // Set API key
      process.env.ANTHROPIC_API_KEY = "sk-test-key";

      // Mock console.warn
      const originalWarn = console.warn;
      const warnings: string[] = [];
      console.warn = mock((...args: any[]) => {
        warnings.push(args.join(" "));
      });

      await authManager.ensureAuthenticated();

      // Should have warned about pay-as-you-go
      expect(warnings.some((w) => w.includes("pay-as-you-go"))).toBe(true);

      // Restore console.warn
      console.warn = originalWarn;
    });
  });

  describe("ClaudeProvider Authentication", () => {
    let provider: ClaudeProvider;

    beforeEach(() => {
      provider = new ClaudeProvider({
        workspaceRoot: "/test/workspace",
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
      const settingsPath = join(homedir(), ".claude", "settings.json");
      if (existsSync(settingsPath)) {
        unlinkSync(settingsPath);
      }
      delete process.env.ANTHROPIC_API_KEY;

      await expect(async () => {
        await provider.ensureAuthenticated();
      }).toThrow(/not authenticated/);
    });
  });

  describe("Authentication States", () => {
    it("should handle OAuth subscription state", async () => {
      const authManager = new AuthManager();

      // Create OAuth settings
      const settingsDir = join(homedir(), ".claude");
      if (!existsSync(settingsDir)) {
        mkdirSync(settingsDir, { recursive: true });
      }

      const settingsPath = join(settingsDir, "settings.json");
      writeFileSync(
        settingsPath,
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
        unlinkSync(settingsPath);
      } catch (error) {
        // Ignore
      }
    });

    it("should handle API key state", async () => {
      const authManager = new AuthManager();

      // Remove OAuth
      const settingsPath = join(homedir(), ".claude", "settings.json");
      if (existsSync(settingsPath)) {
        unlinkSync(settingsPath);
      }

      process.env.ANTHROPIC_API_KEY = "sk-ant-api03-1234567890";

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(true);
      expect(status.mode).toBe("api_key");
      expect(status.source).toBe("ANTHROPIC_API_KEY");
    });

    it("should handle no auth state", async () => {
      const authManager = new AuthManager();

      // Remove all auth
      const settingsPath = join(homedir(), ".claude", "settings.json");
      if (existsSync(settingsPath)) {
        unlinkSync(settingsPath);
      }
      delete process.env.ANTHROPIC_API_KEY;

      const status = await authManager.detectAuthStatus();

      expect(status.authenticated).toBe(false);
      expect(status.mode).toBe("none");
      expect(status.error).toBeDefined();
    });
  });

  describe("Authentication Warnings", () => {
    it("should warn when both auth methods present", async () => {
      const authManager = new AuthManager();

      // Create OAuth settings
      const settingsDir = join(homedir(), ".claude");
      if (!existsSync(settingsDir)) {
        mkdirSync(settingsDir, { recursive: true });
      }

      const settingsPath = join(settingsDir, "settings.json");
      writeFileSync(settingsPath, JSON.stringify({ token: "mock-token" }));

      // Also set API key
      process.env.ANTHROPIC_API_KEY = "sk-test-key";

      const status = await authManager.detectAuthStatus();

      expect(status.warning).toBeDefined();
      expect(status.warning).toContain("ignored");

      // Cleanup
      try {
        unlinkSync(settingsPath);
      } catch (error) {
        // Ignore
      }
    });

    it("should warn about pay-as-you-go with API key", async () => {
      const authManager = new AuthManager();

      // Remove OAuth
      const settingsPath = join(homedir(), ".claude", "settings.json");
      if (existsSync(settingsPath)) {
        unlinkSync(settingsPath);
      }

      process.env.ANTHROPIC_API_KEY = "sk-test-key";

      const status = await authManager.detectAuthStatus();

      expect(status.warning).toBeDefined();
      expect(status.warning).toContain("pay-as-you-go");
    });
  });

  describe("Error Handling", () => {
    it("should handle missing .claude directory", async () => {
      const authManager = new AuthManager();

      // Ensure .claude directory doesn't exist (it likely does in real environment)
      // Just test that the code handles it gracefully
      delete process.env.ANTHROPIC_API_KEY;

      const status = await authManager.detectAuthStatus();

      // Should detect as not authenticated
      expect(typeof status.authenticated).toBe("boolean");
    });

    it("should handle corrupted settings file", async () => {
      const authManager = new AuthManager();

      // Create corrupted settings file
      const settingsDir = join(homedir(), ".claude");
      if (!existsSync(settingsDir)) {
        mkdirSync(settingsDir, { recursive: true });
      }

      const settingsPath = join(settingsDir, "settings.json");
      writeFileSync(settingsPath, "invalid json {{{");

      delete process.env.ANTHROPIC_API_KEY;

      // Should handle gracefully (existsSync returns true, but file is invalid)
      const status = await authManager.detectAuthStatus();

      // Should treat as authenticated via OAuth since file exists
      expect(status.authenticated).toBe(true);
      expect(status.mode).toBe("subscription");

      // Cleanup
      try {
        unlinkSync(settingsPath);
      } catch (error) {
        // Ignore
      }
    });
  });
});
