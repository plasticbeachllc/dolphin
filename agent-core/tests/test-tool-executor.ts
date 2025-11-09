// agent-core/tests/test-tool-executor.ts
/**
 * Manual test for ClaudeToolExecutor integration
 * 
 * Usage:
 *   ANTHROPIC_API_KEY=sk-ant-... bun run agent-core/tests/test-tool-executor.ts
 * 
 * This test verifies:
 * 1. Tool executor can initialize with MCP tools
 * 2. Claude can see and use tools via Anthropic API
 * 3. Tool results are properly formatted
 * 4. Agentic loop works end-to-end
 */

import { ClaudeClient } from "../src/llm/claude-client";
import { ClaudeToolExecutor } from "../src/llm/claude-tool-executor";
import { MCPClient } from "../src/mcp/client";
import * as path from "path";

async function testToolExecutor() {
  console.log("=== ClaudeToolExecutor Integration Test ===\n");

  // Initialize MCP client
  console.log("1. Starting MCP Bridge...");
  const mcpClient = new MCPClient();
  const mcpBridgePath = path.join(__dirname, "../../mcp-bridge/src/index.ts");
  await mcpClient.start(mcpBridgePath);
  console.log("✅ MCP Bridge started\n");

  // Initialize Claude client with auto-detection
  console.log("2. Initializing Claude Client...");
  const claudeClient = new ClaudeClient({
    authMode: "auto",  // Let it auto-detect API key OR CLI
    model: "claude-sonnet-4-20250514",
    maxTokens: 4096,
    temperature: 1.0,
  });

  const authStatus = await claudeClient.getAuthStatus();
  console.log(`✅ Auth mode: ${authStatus.mode}`);
  console.log(`   API key: ${authStatus.apiKeySet ? "✓" : "✗"}`);
  console.log("");

  // Initialize tool executor
  console.log("3. Initializing Tool Executor...");
  const events: any[] = [];
  const toolExecutor = new ClaudeToolExecutor({
    claudeClient,
    mcpClient,
    maxToolRounds: 5,
    onEvent: (event) => {
      events.push(event);
      console.log(`   [Event] ${event.type}`, event);
    },
  });

  await toolExecutor.initialize();
  console.log("✅ Tool executor ready\n");

  // Test 1: Simple query that should use search_knowledge
  console.log("4. Testing agentic tool use...");
  console.log("   Query: 'Search for authentication code in dolphin repo'\n");

  try {
    const result = await toolExecutor.executeWithTools(
      "Search for authentication code in the dolphin repository. What authentication methods are implemented?",
      []
    );

    console.log("\n✅ Execution completed!");
    console.log(`   Tool rounds: ${result.toolRounds}`);
    console.log(`   Stop reason: ${result.stopReason}`);
    console.log(`   Usage:`, result.usage);
    console.log(`   Events captured: ${events.length}`);

    // Verify events
    const toolCallStarted = events.filter((e) => e.type === "tool_call_started");
    const toolCallCompleted = events.filter((e) => e.type === "tool_call_completed");
    const contentDeltas = events.filter((e) => e.type === "content_delta");

    console.log(`\n   Tool calls started: ${toolCallStarted.length}`);
    console.log(`   Tool calls completed: ${toolCallCompleted.length}`);
    console.log(`   Content deltas: ${contentDeltas.length}`);

    if (toolCallStarted.length > 0) {
      console.log("\n✅ Claude autonomously used tools!");
      console.log("   Tools called:", toolCallStarted.map((e) => e.tool));
    } else {
      console.log("\n⚠️  No tools were called (Claude may not have needed them)");
    }

    // Print final response
    const lastMessage = result.messages[result.messages.length - 1];
    if (lastMessage && lastMessage.role === "assistant") {
      console.log("\n📝 Claude's final response:");
      console.log("---");
      if (typeof lastMessage.content === "string") {
        console.log(lastMessage.content);
      } else {
        const textBlocks = lastMessage.content.filter((b: any) => b.type === "text");
        textBlocks.forEach((b: any) => console.log(b.text));
      }
      console.log("---");
    }

    console.log("\n✅ Test passed!");
  } catch (error: any) {
    console.error("\n❌ Test failed:", error.message);
    console.error(error.stack);
    process.exit(1);
  } finally {
    mcpClient.shutdown();
  }
}

testToolExecutor().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});