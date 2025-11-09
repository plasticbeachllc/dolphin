#!/usr/bin/env bun
/**
 * Test Claude Code integration end-to-end
 * 
 * This test verifies that:
 * 1. Claude CLI is detected correctly
 * 2. Subprocess spawning works
 * 3. JSON-RPC responses are parsed properly
 * 4. Authentication mode is detected (subscription vs API)
 */

import { ClaudeClient } from "../src/llm/claude-client";
import { ClaudeCLIDetector } from "../src/llm/claude-cli-detector";

async function main() {
  console.log("=== Claude Code Integration Test ===\n");

  // Step 1: Check CLI installation
  console.log("Step 1: Checking Claude CLI installation...");
  const detector = new ClaudeCLIDetector();
  
  const isInstalled = await detector.isInstalled();
  console.log(`  ✓ CLI installed: ${isInstalled}`);
  
  if (!isInstalled) {
    console.log("\n❌ Claude CLI not installed. Install it from:");
    console.log("   https://docs.anthropic.com/en/docs/claude-code/setup");
    process.exit(1);
  }

  const isAuthenticated = await detector.isAuthenticated();
  console.log(`  ✓ CLI authenticated: ${isAuthenticated}`);

  const willUseAPIKey = await detector.willUseAPIKey();
  console.log(`  ✓ Will use API key: ${willUseAPIKey}`);

  if (willUseAPIKey) {
    console.log("\n⚠️  Warning: ANTHROPIC_API_KEY is set.");
    console.log("   CLI will use API mode instead of subscription.");
    console.log("   Unset it to use subscription: unset ANTHROPIC_API_KEY");
  }

  // Step 2: Initialize Claude Client
  console.log("\nStep 2: Initializing ClaudeClient...");
  const client = new ClaudeClient({
    model: "claude-sonnet-4-20250514",
    maxTokens: 1024,
    authMode: "auto",
  });

  // Step 3: Detect auth mode
  console.log("\nStep 3: Detecting authentication mode...");
  const authMode = await client.detectAuthMode();
  console.log(`  ✓ Auth mode: ${authMode}`);

  // Step 4: Get auth status
  console.log("\nStep 4: Getting detailed auth status...");
  const status = await client.getAuthStatus();
  console.log(`  ✓ Mode: ${status.mode}`);
  console.log(`  ✓ CLI Installed: ${status.cliInstalled}`);
  console.log(`  ✓ CLI Authenticated: ${status.cliAuthenticated}`);
  console.log(`  ✓ API Key Set: ${status.apiKeySet}`);
  console.log(`  ✓ Will Use Subscription: ${status.willUseSubscription}`);

  // Step 5: Test simple completion
  console.log("\nStep 5: Testing simple completion...");
  console.log("  Sending: 'What is 2+2?'");
  
  const startTime = Date.now();
  
  try {
    const result = await client.complete({
      messages: [
        { role: "user", content: "What is 2+2? Answer in one short sentence." }
      ],
      system: "You are a helpful math assistant.",
      maxTokens: 100,
    });

    const duration = Date.now() - startTime;

    console.log(`\n  ✓ Response received in ${duration}ms:`);
    console.log(`    "${result.content.trim()}"`);
    console.log(`\n  ✓ Usage:`);
    console.log(`    Input tokens: ${result.usage.input_tokens}`);
    console.log(`    Output tokens: ${result.usage.output_tokens}`);
    
    if (result.usage.cache_read_tokens) {
      console.log(`    Cache read tokens: ${result.usage.cache_read_tokens}`);
    }
    if (result.usage.cache_write_tokens) {
      console.log(`    Cache write tokens: ${result.usage.cache_write_tokens}`);
    }

    if (result.isPaidUsage !== undefined) {
      console.log(`\n  ✓ Billing:`);
      console.log(`    Paid usage: ${result.isPaidUsage}`);
      if (result.totalCostUsd !== undefined) {
        console.log(`    Total cost: $${result.totalCostUsd.toFixed(4)}`);
      }
    }

    console.log(`\n  ✓ Stop reason: ${result.stop_reason || 'N/A'}`);

    // Success!
    console.log("\n✅ All tests passed!\n");
    
    if (authMode === "claude_cli" && !willUseAPIKey) {
      console.log("🎉 You're using Claude Code CLI with your subscription!");
      console.log("   This means NO API costs for this usage!");
    } else if (authMode === "claude_cli" && willUseAPIKey) {
      console.log("⚠️  You're using Claude Code CLI but with an API key.");
      console.log("   This will incur API costs. To use subscription:");
      console.log("   1. Run: unset ANTHROPIC_API_KEY");
      console.log("   2. Run this test again");
    } else {
      console.log("💰 You're using Anthropic API (pay-per-token mode).");
    }

  } catch (error: any) {
    console.error("\n❌ Test failed:");
    console.error(`   ${error.message}`);
    
    if (error.message.includes("ENOENT")) {
      console.error("\n   Looks like the Claude CLI couldn't be spawned.");
      console.error("   Make sure 'claude' is in your PATH.");
    }
    
    process.exit(1);
  }
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});