#!/usr/bin/env bun
/**
 * End-to-end integration test for MCP Bridge with real REST API
 *
 * Prerequisites:
 * 1. kb-api server running on http://127.0.0.1:7777
 * 2. At least one repository indexed
 *
 * Run: bun run test-integration.ts
 */

import { makeSearchKnowledge } from "./src/mcp/tools/search_knowledge.js";
import { makeFetchChunk } from "./src/mcp/tools/fetch_chunk.js";
import { makeFetchLines } from "./src/mcp/tools/fetch_lines.js";
import { makeGetVectorStoreInfo } from "./src/mcp/tools/get_vector_store_info.js";
import { restListRepos } from "./src/rest/client.js";
import { runBridgeSmokeSuite } from "./src/tests/bridge_smoke_suite.js";

async function main() {
  console.log("🧪 MCP Bridge Integration Test\n");

  const report = await runBridgeSmokeSuite(
    {
      listRepos: restListRepos,
      makeSearchKnowledge,
      makeFetchChunk,
      makeFetchLines,
      makeGetVectorStoreInfo,
    },
    {
      log: (message) => console.log(message),
    }
  );

  console.log("\n📊 Test Summary:");
  for (const entry of report.entries) {
    if (entry.status === "passed") {
      console.log(`   ✅ ${entry.name} (${entry.duration_ms}ms)`);
    } else {
      console.log(`   ❌ ${entry.name}: ${entry.error ?? "unknown error"}`);
    }
  }
  console.log(`\n   ✅ Passed: ${report.passed}`);
  console.log(`   ❌ Failed: ${report.failed}`);

  if (report.failed > 0) {
    console.log("\n❌ One or more smoke tests failed. Ensure kb-api is reachable at 127.0.0.1:7777.");
    process.exit(1);
  }

  console.log("\n🎉 All integration tests completed successfully!");
}

main().catch((error) => {
  console.error("Unexpected integration test error", error);
  process.exit(1);
});
