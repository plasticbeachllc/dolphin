#!/usr/bin/env bun
// Debug script to understand Claude CLI behavior

import { spawn } from "child_process";

console.log("🔍 Debugging Claude CLI Authentication\n");

// Test 1: Check if claude is in PATH
console.log("Test 1: Checking if 'claude' command exists...");
const which = spawn("which", ["claude"]);
which.stdout.on("data", (data) => {
  console.log(`  ✅ Claude CLI found at: ${data.toString().trim()}`);
});
which.on("close", (code) => {
  if (code !== 0) {
    console.log("  ❌ 'claude' command not found in PATH");
  }
});

await new Promise((resolve) => setTimeout(resolve, 500));

// Test 2: Check version
console.log("\nTest 2: Checking Claude CLI version...");
const version = spawn("claude", ["--version"]);
version.stdout.on("data", (data) => {
  console.log(`  ✅ Version: ${data.toString().trim()}`);
});
version.stderr.on("data", (data) => {
  console.log(`  ⚠️  stderr: ${data.toString().trim()}`);
});
version.on("close", (code) => {
  console.log(`  Exit code: ${code}`);
});

await new Promise((resolve) => setTimeout(resolve, 500));

// Test 3: Try running claude with a simple prompt
console.log("\nTest 3: Testing actual Claude CLI execution...");
console.log("  Spawning 'claude' process...");

const claude = spawn("claude", [], {
  stdio: ["pipe", "pipe", "pipe"],
});

let receivedOutput = false;
let receivedError = false;

const timeout = setTimeout(() => {
  console.log("  ⏱️  Timeout after 3s");
  claude.kill();
}, 3000);

claude.stdout.on("data", (data) => {
  receivedOutput = true;
  console.log(`  ✅ stdout: ${data.toString().substring(0, 100)}...`);
  clearTimeout(timeout);
  claude.kill();
});

claude.stderr.on("data", (data) => {
  receivedError = true;
  const stderr = data.toString();
  console.log(`  ⚠️  stderr: ${stderr.substring(0, 100)}...`);
  
  if (stderr.includes("not authenticated") || stderr.includes("login required")) {
    console.log("  ❌ Authentication error detected");
    clearTimeout(timeout);
    claude.kill();
  }
});

claude.on("error", (err) => {
  console.log(`  ❌ Process error: ${err.message}`);
  clearTimeout(timeout);
});

claude.on("close", (code) => {
  console.log(`  Process closed with code: ${code}`);
  console.log(`  Received output: ${receivedOutput}`);
  console.log(`  Received error: ${receivedError}`);
});

// Send a test prompt
console.log("  Sending test prompt: 'test'");
claude.stdin.write("test\n");
claude.stdin.end();

await new Promise((resolve) => setTimeout(resolve, 3500));

console.log("\n✅ Debug complete\n");
console.log("If you can run 'claude' manually but this shows no output,");
console.log("the CLI might be waiting for input in a different way.");
process.exit(0);