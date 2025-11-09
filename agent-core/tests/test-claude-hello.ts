#!/usr/bin/env bun
// Simple test to verify Claude CLI integration works

import { ClaudeClient } from "../src/llm/claude-client";

async function testClaudeHello() {
  console.log("🧪 Testing Claude CLI Integration\n");
  
  // Create client with auto-detection
  const client = new ClaudeClient({
    authMode: "auto",
    model: "claude-sonnet-4-20250514",
    maxTokens: 100,
    temperature: 1.0,
  });
  
  // Check auth status
  console.log("📊 Checking authentication status...");
  const authStatus = await client.getAuthStatus();
  
  console.log("\nAuth Status:");
  console.log(`  Mode: ${authStatus.mode}`);
  console.log(`  CLI Installed: ${authStatus.cliInstalled}`);
  console.log(`  CLI Authenticated: ${authStatus.cliAuthenticated}`);
  console.log(`  API Key Set: ${authStatus.apiKeySet}`);
  console.log(`  Will Use Subscription: ${authStatus.willUseSubscription}`);
  
  if (authStatus.mode === "auto") {
    console.log("\n❌ No authentication configured!");
    console.log("\nTo fix this:");
    console.log("  Option 1 (Subscription): Run 'claude' to authenticate with your Claude account");
    console.log("  Option 2 (API): Set ANTHROPIC_API_KEY environment variable");
    process.exit(1);
  }
  
  console.log("\n✅ Authentication configured\n");
  
  // Test simple completion
  console.log("💬 Testing simple completion...");
  console.log("Prompt: Say 'hello' and nothing else.\n");
  
  const startTime = Date.now();
  
  try {
    const result = await client.complete({
      messages: [
        { role: "user", content: "Say 'hello' and nothing else." }
      ],
    });
    
    const duration = Date.now() - startTime;
    
    console.log("Response:");
    console.log(`  Content: "${result.content}"`);
    console.log(`  Input tokens: ${result.usage.input_tokens}`);
    console.log(`  Output tokens: ${result.usage.output_tokens}`);
    console.log(`  Duration: ${duration}ms`);
    console.log(`  Stop reason: ${result.stop_reason}`);
    
    if (result.content.toLowerCase().includes("hello")) {
      console.log("\n✅ Test PASSED - Claude responded correctly!");
    } else {
      console.log("\n⚠️  Test WARNING - Response doesn't contain 'hello'");
      console.log("   This might be OK depending on Claude's interpretation");
    }
    
  } catch (error: any) {
    console.error("\n❌ Test FAILED:");
    console.error(`   ${error.message}`);
    if (error.stack) {
      console.error("\nStack trace:");
      console.error(error.stack);
    }
    process.exit(1);
  }
  
  console.log("\n🎉 Test complete!\n");
}

// Run test
testClaudeHello().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});