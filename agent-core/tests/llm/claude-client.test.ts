// agent-core/tests/llm/claude-client.test.ts
import { describe, test, expect, beforeEach } from "bun:test";
import { ClaudeClient } from "../../src/llm/claude-client";

describe("ClaudeClient Integration", () => {
  test("detects auth mode automatically", async () => {
    const client = new ClaudeClient({
      authMode: "auto",
      model: "claude-sonnet-4-20250514",
      maxTokens: 1000,
    });

    try {
      const mode = await client.detectAuthMode();
      expect(["claude_cli", "api_key"]).toContain(mode);
      console.log(`✅ Detected auth mode: ${mode}`);
    } catch (error: any) {
      // Expected if no auth configured
      expect(error.message).toContain("No authentication configured");
      console.log("ℹ️  No authentication configured (expected in test environment)");
    }
  });

  test("gets auth status", async () => {
    const client = new ClaudeClient({
      authMode: "auto",
      model: "claude-sonnet-4-20250514",
      maxTokens: 1000,
    });

    try {
      const status = await client.getAuthStatus();

      expect(typeof status.cliInstalled).toBe("boolean");
      expect(typeof status.cliAuthenticated).toBe("boolean");
      expect(typeof status.apiKeySet).toBe("boolean");
      expect(typeof status.willUseSubscription).toBe("boolean");
      expect(["claude_cli", "api_key"]).toContain(status.mode);

      console.log("\n📊 Auth Status:");
      console.log(`  Mode: ${status.mode}`);
      console.log(`  CLI Installed: ${status.cliInstalled}`);
      console.log(`  CLI Authenticated: ${status.cliAuthenticated}`);
      console.log(`  API Key Set: ${status.apiKeySet}`);
      console.log(`  Will Use Subscription: ${status.willUseSubscription}`);
    } catch (error: any) {
      // Expected if no auth configured
      expect(error.message).toContain("No authentication configured");
      console.log("ℹ️  No authentication configured (expected in test environment)");
    }
  });

  test("completes chat request with API key", async () => {
    // Skip if no API key
    if (!process.env.ANTHROPIC_API_KEY) {
      console.log("ℹ️  Skipping API test (no ANTHROPIC_API_KEY)");
      return;
    }

    const client = new ClaudeClient({
      authMode: "api_key",
      apiKey: process.env.ANTHROPIC_API_KEY,
      model: "claude-sonnet-4-20250514",
      maxTokens: 100,
    });

    const result = await client.complete({
      messages: [{ role: "user", content: 'Say "hello" and nothing else.' }],
    });

    expect(result.content.toLowerCase()).toContain("hello");
    expect(result.usage.output_tokens).toBeGreaterThan(0);
    console.log(`✅ API completion: ${result.content}`);
    console.log(
      `   Tokens: ${result.usage.input_tokens} in, ${result.usage.output_tokens} out`
    );
  });

  test("formats prompt for CLI correctly", async () => {
    const client = new ClaudeClient({
      authMode: "auto",
      model: "claude-sonnet-4-20250514",
      maxTokens: 1000,
    });

    // Access private method via reflection for testing
    const formatPrompt = (client as any).formatPromptForCLI.bind(client);

    const prompt = formatPrompt({
      system: "You are a helpful assistant.",
      messages: [
        { role: "user", content: "Hello!" },
        { role: "assistant", content: "Hi there!" },
        { role: "user", content: "How are you?" },
      ],
    });

    expect(prompt).toContain("System: You are a helpful assistant.");
    expect(prompt).toContain("Human: Hello!");
    expect(prompt).toContain("Assistant: Hi there!");
    expect(prompt).toContain("Human: How are you?");
    expect(prompt).toContain("Assistant:");
    
    console.log("\n📝 Formatted CLI Prompt:");
    console.log(prompt.substring(0, 200) + "...");
  });

  test("handles missing authentication gracefully", async () => {
    // Temporarily remove API key
    const originalKey = process.env.ANTHROPIC_API_KEY;
    delete process.env.ANTHROPIC_API_KEY;

    const client = new ClaudeClient({
      authMode: "auto",
      model: "claude-sonnet-4-20250514",
      maxTokens: 1000,
    });

    try {
      await client.detectAuthMode();
      // If we get here, CLI is authenticated (valid)
      console.log("✅ CLI authentication available");
    } catch (error: any) {
      // Expected if no auth configured
      expect(error.message).toContain("No authentication configured");
      console.log("✅ Correctly detects missing authentication");
    } finally {
      // Restore API key
      if (originalKey) {
        process.env.ANTHROPIC_API_KEY = originalKey;
      }
    }
  });

  test("streaming returns async generator", async () => {
    // Skip if no API key
    if (!process.env.ANTHROPIC_API_KEY) {
      console.log("ℹ️  Skipping streaming test (no ANTHROPIC_API_KEY)");
      return;
    }

    const client = new ClaudeClient({
      authMode: "api_key",
      apiKey: process.env.ANTHROPIC_API_KEY,
      model: "claude-sonnet-4-20250514",
      maxTokens: 100,
    });

    let chunks = 0;
    let fullContent = "";

    for await (const chunk of client.completeStreaming({
      messages: [{ role: "user", content: 'Say "hello world" and nothing else.' }],
    })) {
      chunks++;
      fullContent += chunk;
    }

    expect(chunks).toBeGreaterThan(0);
    expect(fullContent.toLowerCase()).toContain("hello");
    console.log(`✅ Streaming: ${chunks} chunks received`);
    console.log(`   Content: ${fullContent}`);
  });
});