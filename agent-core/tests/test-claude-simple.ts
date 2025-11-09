#!/usr/bin/env bun
/**
 * Simple test to verify Claude CLI spawning works
 */

import { spawn } from "child_process";
import * as readline from "readline";

async function testSimpleSpawn() {
  console.log("Testing simple Claude CLI spawn...\n");

  const child = spawn("claude", [
    "-p",
    "--system-prompt", "You are a helpful assistant.",
    "--verbose",
    "--output-format", "stream-json",
    "--max-turns", "1",
    "--model", "claude-sonnet-4-20250514"
  ], {
    stdio: ["pipe", "pipe", "pipe"],
  });

  console.log("✓ Process spawned successfully");

  // Setup readline for output
  const rl = readline.createInterface({
    input: child.stdout,
  });

  // Handle stderr
  child.stderr.setEncoding("utf-8");
  child.stderr.on("data", (data) => {
    console.log("[stderr]", data.toString());
  });

  // Handle errors
  child.on("error", (err) => {
    console.error("❌ Process error:", err);
    process.exit(1);
  });

  child.on("close", (code) => {
    console.log(`\n✓ Process exited with code ${code}`);
  });

  // Send messages
  const messages = [
    { role: "user", content: "What is 2+2? Answer in one short sentence." }
  ];

  console.log("✓ Sending messages to stdin...");
  child.stdin.write(JSON.stringify(messages), "utf8");
  child.stdin.end();

  console.log("✓ Waiting for output...\n");

  // Read output
  for await (const line of rl) {
    console.log("[stdout]", line);
    
    try {
      const parsed = JSON.parse(line);
      console.log("  Parsed:", JSON.stringify(parsed, null, 2));
    } catch {
      console.log("  (not JSON)");
    }
  }
}

testSimpleSpawn().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});