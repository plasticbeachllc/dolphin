#!/usr/bin/env bun
/**
 * Test script for context lines feature
 */

import { makeSearchKnowledge } from "./mcp-bridge/src/mcp/tools/search_knowledge.js";

async function main() {
  console.log("Testing context lines feature...\n");

  const { handler } = makeSearchKnowledge();

  // Test with context lines
  const result = await handler({
    input: {
      query: "fetchSnippetsInParallel",
      top_k: 1,
      context_lines_before: 3,
      context_lines_after: 3,
    },
  });

  if (result.isError) {
    console.error("Error:", result.content[0].text);
    process.exit(1);
  }

  // Print summary
  console.log(result.content[0].text);
  console.log("\n" + "=".repeat(80) + "\n");

  // Print prompt-ready content with context
  if (result.content[1] && result.content[1].type === "text") {
    console.log("PROMPT-READY OUTPUT (with context markers):");
    console.log(result.content[1].text);
  }

  console.log("\n" + "=".repeat(80) + "\n");
  console.log("✅ Test completed successfully!");
}

main().catch(console.error);
