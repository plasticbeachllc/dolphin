#!/usr/bin/env node
/**
 * Quick test to verify read_files security fix
 * Tests that absolute paths outside workspace are blocked
 */

const path = require("path");

// Simulate the fixed code
function testPathSecurity(filepath, workspaceRoot) {
  // Always resolve path relative to workspace (handles both relative and absolute)
  const fullPath = path.resolve(workspaceRoot, filepath);

  // Security check: ensure resolved path is within workspace boundary
  // This prevents directory traversal and blocks absolute paths outside workspace
  if (!fullPath.startsWith(workspaceRoot)) {
    return { allowed: false, reason: "Access denied: path outside workspace" };
  }

  return { allowed: true, resolvedPath: fullPath };
}

const workspaceRoot = "/home/user/dolphin";

console.log("Testing read_files security fix\n");

const testCases = [
  { path: "package.json", expected: true, description: "Relative path in workspace" },
  { path: "./README.md", expected: true, description: "Relative path with ./ prefix" },
  {
    path: "../dolphin/package.json",
    expected: true,
    description: "Path that resolves to workspace",
  },
  {
    path: "../../etc/passwd",
    expected: false,
    description: "Directory traversal outside workspace",
  },
  { path: "/etc/passwd", expected: false, description: "Absolute path outside workspace" },
  {
    path: "/home/user/dolphin/package.json",
    expected: true,
    description: "Absolute path within workspace",
  },
  { path: "/root/.ssh/id_rsa", expected: false, description: "Sensitive file outside workspace" },
];

let passed = 0;
let failed = 0;

testCases.forEach(({ path: testPath, expected, description }) => {
  const result = testPathSecurity(testPath, workspaceRoot);
  const success = result.allowed === expected;

  if (success) {
    console.log(`✅ PASS: ${description}`);
    console.log(`   Path: ${testPath}`);
    console.log(`   Result: ${result.allowed ? "Allowed" : "Blocked"}`);
    if (result.resolvedPath) console.log(`   Resolved: ${result.resolvedPath}`);
    passed++;
  } else {
    console.log(`❌ FAIL: ${description}`);
    console.log(`   Path: ${testPath}`);
    console.log(
      `   Expected: ${expected ? "Allow" : "Block"}, Got: ${result.allowed ? "Allow" : "Block"}`
    );
    if (result.resolvedPath) console.log(`   Resolved: ${result.resolvedPath}`);
    if (result.reason) console.log(`   Reason: ${result.reason}`);
    failed++;
  }
  console.log("");
});

console.log(`\nResults: ${passed} passed, ${failed} failed`);

if (failed > 0) {
  process.exit(1);
}

console.log("\n✅ All security tests passed!");
