// agent-core/tests/llm/claude-cli-detector.test.ts
import { describe, test, expect, beforeEach } from "bun:test";
import { ClaudeCLIDetector } from "../../src/llm/claude-cli-detector";

describe("ClaudeCLIDetector", () => {
  let detector: ClaudeCLIDetector;

  beforeEach(() => {
    detector = new ClaudeCLIDetector();
  });

  test("detects CLI installation", async () => {
    const installed = await detector.isInstalled();
    expect(typeof installed).toBe("boolean");
    
    if (installed) {
      console.log("✅ Claude CLI is installed");
    } else {
      console.log("ℹ️  Claude CLI not installed (expected on CI)");
    }
  });

  test("gets CLI version if installed", async () => {
    const version = await detector.getVersion();
    
    if (version) {
      expect(version).toMatch(/\d+\.\d+/);
      console.log(`✅ Claude CLI version: ${version}`);
    } else {
      console.log("ℹ️  No CLI version (CLI not installed)");
    }
  });

  test("checks authentication status", async () => {
    const authenticated = await detector.isAuthenticated();
    expect(typeof authenticated).toBe("boolean");
    
    if (authenticated) {
      console.log("✅ Claude CLI is authenticated");
    } else {
      console.log("ℹ️  Claude CLI not authenticated (expected if not set up)");
    }
  });

  test("detects API key env var", async () => {
    const originalKey = process.env.ANTHROPIC_API_KEY;

    // Test with API key set
    process.env.ANTHROPIC_API_KEY = "test-key";
    const willUseAPIKey = await detector.willUseAPIKey();
    expect(willUseAPIKey).toBe(true);

    // Test without API key
    delete process.env.ANTHROPIC_API_KEY;
    const willUseSubscription = await detector.willUseAPIKey();
    expect(willUseSubscription).toBe(false);

    // Restore
    if (originalKey) {
      process.env.ANTHROPIC_API_KEY = originalKey;
    }
  });

  test("gets auth method", async () => {
    const method = await detector.getAuthMethod();
    expect(["subscription", "api_key", "none"]).toContain(method);
    console.log(`✅ Auth method: ${method}`);
  });

  test("gets complete status", async () => {
    const status = await detector.getStatus();

    expect(typeof status.cliInstalled).toBe("boolean");
    expect(typeof status.cliAuthenticated).toBe("boolean");
    expect(typeof status.apiKeySet).toBe("boolean");
    expect(typeof status.willUseSubscription).toBe("boolean");
    expect(Array.isArray(status.warnings)).toBe(true);
    expect(["subscription", "api_key", "none"]).toContain(status.authMethod);

    console.log("\n📊 Complete Auth Status:");
    console.log(`  CLI Installed: ${status.cliInstalled}`);
    console.log(`  CLI Version: ${status.cliVersion || "N/A"}`);
    console.log(`  CLI Authenticated: ${status.cliAuthenticated}`);
    console.log(`  Auth Method: ${status.authMethod}`);
    console.log(`  API Key Set: ${status.apiKeySet}`);
    console.log(`  Will Use Subscription: ${status.willUseSubscription}`);
    
    if (status.warnings.length > 0) {
      console.log("\n⚠️  Warnings:");
      status.warnings.forEach((warning) => console.log(`  - ${warning}`));
    }
  });

  test("warns when API key overrides subscription", async () => {
    const originalKey = process.env.ANTHROPIC_API_KEY;
    
    // Simulate having both subscription and API key
    process.env.ANTHROPIC_API_KEY = "test-key";
    
    const status = await detector.getStatus();
    
    if (status.cliAuthenticated) {
      // Should have warning about API key overriding subscription
      expect(status.warnings.some(w => w.includes("ANTHROPIC_API_KEY"))).toBe(true);
      expect(status.willUseSubscription).toBe(false);
    }
    
    // Restore
    if (originalKey) {
      process.env.ANTHROPIC_API_KEY = originalKey;
    } else {
      delete process.env.ANTHROPIC_API_KEY;
    }
  });
});