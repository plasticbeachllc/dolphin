#!/usr/bin/env bun

// Integration test harness for MCP Bridge with real REST retriever
// Usage: Run the FastAPI retriever on 127.0.0.1:7777 first, then run this script

import { makeSearchKnowledge } from "../mcp/tools/search_knowledge.js";
import { makeChunkGet } from "../mcp/tools/chunk_get.js";
import { makeFileLines } from "../mcp/tools/file_lines.js";
import { makeStoreInfo } from "../mcp/tools/store_info.js";
import { makeGetMetadata } from "../mcp/tools/get_metadata.js";
import { makeListRepos } from "../mcp/tools/list_repos.js";
import { makeKbHealth } from "../mcp/tools/kb_health.js";
import { initLogger } from "../util/logger.js";

function parseHitsJson(
  content: Array<{ type: string; text?: string }>
): { hits?: unknown[] } | null {
  const jsonBlock = content.find(
    (block) => block.type === "text" && String(block.text).includes("```json")
  );
  if (!jsonBlock?.text) return null;
  const match = String(jsonBlock.text).match(/```json\n([\s\S]*?)\n```/);
  if (!match) return null;
  return JSON.parse(match[1]) as { hits?: unknown[] };
}

async function runIntegrationTests() {
  console.log("🚀 Starting MCP Bridge Integration Tests...\n");

  await initLogger();

  const tests = [
    {
      name: "search - smoke test",
      tool: makeSearchKnowledge(),
      input: { query: "test" },
    },
    {
      name: "chunk_get - smoke test",
      tool: makeChunkGet(),
      input: { chunk_id: "1" },
    },
    {
      name: "file_lines - smoke test",
      tool: makeFileLines(),
      input: { repo: "repoa", path: "src/a.ts", start: 1, end: 10 },
    },
    {
      name: "store.info - smoke test",
      tool: makeStoreInfo(),
      input: {},
    },
    {
      name: "repos.list - smoke test",
      tool: makeListRepos(),
      input: {},
    },
    {
      name: "health - smoke test",
      tool: makeKbHealth(),
      input: { check: "shallow" },
    },
    {
      name: "metadata.get - smoke test",
      tool: makeGetMetadata(),
      input: { chunk_id: "1" },
    },
  ];

  let passed = 0;
  let failed = 0;

  for (const test of tests) {
    console.log(`📋 Running: ${test.name}`);

    try {
      const startTime = Date.now();
      const result = await test.tool.handler({ input: test.input });
      const latency = Date.now() - startTime;

      if (result.isError) {
        console.log(`  ❌ FAILED: ${result.content[0]?.text || "Unknown error"}`);
        failed++;
      } else {
        console.log(`  ✅ PASSED (${latency}ms)`);

        // Log some details for successful tests
        if (test.name.includes("search")) {
          const hits = parseHitsJson(result.content)?.hits ?? [];
          console.log(`    Found ${hits.length} hits`);
        } else if (test.name.includes("chunk_get") || test.name.includes("file_lines")) {
          console.log(`    Content length: ${result.content[0]?.text?.length || 0} chars`);
        }

        passed++;
      }
    } catch (error) {
      console.log(`  ❌ ERROR: ${error.message}`);
      failed++;
    }

    console.log(""); // Empty line for readability
  }

  // Test pagination with multiple calls
  console.log("📋 Running: search - pagination test");
  try {
    const { handler } = makeSearchKnowledge();
    const firstPage = await handler({ input: { query: "test", top_k: 2 } });

    if (firstPage.isError) {
      console.log(`  ❌ First page failed: ${firstPage.content[0]?.text}`);
      failed++;
    } else if (firstPage._meta?.cursor) {
      const secondPage = await handler({
        input: {
          query: "test",
          top_k: 2,
          cursor: firstPage._meta.cursor,
        },
      });

      if (secondPage.isError) {
        console.log(`  ❌ Second page failed: ${secondPage.content[0]?.text}`);
        failed++;
      } else {
        console.log("  ✅ Pagination test passed");
        passed++;
      }
    } else {
      console.log("  ⚠️  No cursor for pagination test (expected if no more results)");
      passed++; // Not a failure, just no pagination needed
    }
  } catch (error) {
    console.log(`  ❌ Pagination error: ${error.message}`);
    failed++;
  }

  console.log("\n📊 Test Summary:");
  console.log(`   ✅ Passed: ${passed}`);
  console.log(`   ❌ Failed: ${failed}`);
  console.log(`   📈 Success Rate: ${((passed / (passed + failed)) * 100).toFixed(1)}%`);

  if (failed > 0) {
    console.log(
      "\n❌ Some integration tests failed. Make sure the REST retriever is running on 127.0.0.1:7777"
    );
    process.exit(1);
  } else {
    console.log("\n🎉 All integration tests passed!");
    process.exit(0);
  }
}

// Check if REST server is available before running tests
async function checkRestServer() {
  try {
    const response = await fetch("http://127.0.0.1:7777/health");
    return response.ok;
  } catch {
    return false;
  }
}

// Main execution
async function main() {
  const serverAvailable = await checkRestServer();

  if (!serverAvailable) {
    console.log("❌ REST retriever not found at http://127.0.0.1:7777");
    console.log("   Please start the FastAPI retriever first, then run this script.");
    console.log("   Example command: uvicorn main:app --host 127.0.0.1 --port 7777");
    process.exit(1);
  }

  await runIntegrationTests();
}

main().catch(console.error);
