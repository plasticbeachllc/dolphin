#!/usr/bin/env bun
/**
 * Integration Test Runner for Dolphin v2 Phase 1
 *
 * Runs all integration tests and validates Phase 1 success criteria
 */

import { spawn } from "child_process";
import { existsSync } from "fs";
import { join } from "path";

// ANSI color codes
const colors = {
  reset: "\x1b[0m",
  bright: "\x1b[1m",
  green: "\x1b[32m",
  red: "\x1b[31m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  cyan: "\x1b[36m",
};

interface TestResult {
  suite: string;
  passed: number;
  failed: number;
  duration: number;
}

/**
 * Run test suite
 */
async function runTestSuite(suitePath: string): Promise<TestResult> {
  return new Promise((resolve) => {
    const startTime = Date.now();
    let passed = 0;
    let failed = 0;

    const process = spawn("bun", ["test", suitePath], {
      stdio: ["inherit", "pipe", "pipe"],
    });

    let stdout = "";
    let _stderr = "";

    process.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
      process.stdout.write(chunk);
    });

    process.stderr.on("data", (chunk) => {
      _stderr += chunk.toString();
      process.stderr.write(chunk);
    });

    process.on("close", (_code) => {
      const duration = Date.now() - startTime;

      // Parse test results from output
      const passMatch = stdout.match(/(\d+) pass/);
      const failMatch = stdout.match(/(\d+) fail/);

      passed = passMatch ? parseInt(passMatch[1]) : 0;
      failed = failMatch ? parseInt(failMatch[1]) : 0;

      resolve({
        suite: suitePath,
        passed,
        failed,
        duration,
      });
    });
  });
}

/**
 * Print header
 */
function printHeader() {
  console.log();
  console.log(
    colors.bright +
      colors.cyan +
      "╔════════════════════════════════════════════════════════╗" +
      colors.reset
  );
  console.log(
    colors.bright +
      colors.cyan +
      "║  Dolphin v2 Phase 1 Integration Test Suite           ║" +
      colors.reset
  );
  console.log(
    colors.bright +
      colors.cyan +
      "╚════════════════════════════════════════════════════════╝" +
      colors.reset
  );
  console.log();
}

/**
 * Print test results
 */
function printResults(results: TestResult[]) {
  console.log();
  console.log(
    colors.bright + "═══════════════════════════════════════════════════════════" + colors.reset
  );
  console.log(colors.bright + "  Test Results Summary" + colors.reset);
  console.log(
    colors.bright + "═══════════════════════════════════════════════════════════" + colors.reset
  );
  console.log();

  let totalPassed = 0;
  let totalFailed = 0;
  let totalDuration = 0;

  for (const result of results) {
    const suiteName = result.suite.split("/").pop()?.replace(".test.ts", "") || "unknown";
    const status = result.failed === 0 ? colors.green + "✓ PASS" : colors.red + "✗ FAIL";

    console.log(`${status}${colors.reset}  ${suiteName}`);
    console.log(`       ${result.passed} passed, ${result.failed} failed (${result.duration}ms)`);
    console.log();

    totalPassed += result.passed;
    totalFailed += result.failed;
    totalDuration += result.duration;
  }

  console.log(
    colors.bright + "───────────────────────────────────────────────────────────" + colors.reset
  );
  console.log(colors.bright + `  Total: ${totalPassed + totalFailed} tests` + colors.reset);
  console.log(colors.green + `  Passed: ${totalPassed}` + colors.reset);
  console.log(colors.red + `  Failed: ${totalFailed}` + colors.reset);
  console.log(colors.cyan + `  Duration: ${totalDuration}ms` + colors.reset);
  console.log(
    colors.bright + "═══════════════════════════════════════════════════════════" + colors.reset
  );
  console.log();
}

/**
 * Validate Phase 1 success criteria
 */
function validateSuccessCriteria(results: TestResult[]) {
  console.log(
    colors.bright +
      colors.blue +
      "═══════════════════════════════════════════════════════════" +
      colors.reset
  );
  console.log(colors.bright + colors.blue + "  Phase 1 Success Criteria Validation" + colors.reset);
  console.log(
    colors.bright +
      colors.blue +
      "═══════════════════════════════════════════════════════════" +
      colors.reset
  );
  console.log();

  const criteria = [
    {
      name: "Editor Mode end-to-end execution",
      check: () => results.some((r) => r.suite.includes("editor-workflow") && r.failed === 0),
    },
    {
      name: "Claude CLI subprocess spawning",
      check: () => results.some((r) => r.suite.includes("claude") && r.failed === 0),
    },
    {
      name: "KB search integration",
      check: () => results.some((r) => r.suite.includes("kb-integration") && r.failed === 0),
    },
    {
      name: "State persistence in TOML",
      check: () => results.some((r) => r.suite.includes("orchestrator") && r.failed === 0),
    },
    {
      name: "100+ tests passing",
      check: () => {
        const totalTests = results.reduce((sum, r) => sum + r.passed + r.failed, 0);
        return totalTests >= 100 && results.every((r) => r.failed === 0);
      },
    },
    {
      name: "Authentication detection",
      check: () => results.some((r) => r.suite.includes("claude-auth") && r.failed === 0),
    },
  ];

  let allPassed = true;

  for (const criterion of criteria) {
    const passed = criterion.check();
    const status = passed ? colors.green + "✓" : colors.red + "✗";
    console.log(`${status} ${criterion.name}${colors.reset}`);

    if (!passed) {
      allPassed = false;
    }
  }

  console.log();
  console.log(
    colors.bright + "───────────────────────────────────────────────────────────" + colors.reset
  );

  if (allPassed) {
    console.log(
      colors.green + colors.bright + "  ✓ Phase 1 SUCCESS - All criteria met!" + colors.reset
    );
  } else {
    console.log(
      colors.yellow + colors.bright + "  ⚠ Phase 1 PARTIAL - Some criteria not met" + colors.reset
    );
  }

  console.log(
    colors.bright + "═══════════════════════════════════════════════════════════" + colors.reset
  );
  console.log();

  return allPassed;
}

/**
 * Main test runner
 */
async function main() {
  printHeader();

  const testSuites = [
    "tests/unit/orchestrator.test.ts",
    "tests/unit/state-store.test.ts",
    "tests/unit/json-rpc.test.ts",
    "tests/integration/editor-workflow.test.ts",
    "tests/integration/orchestrator-e2e.test.ts",
    "tests/integration/kb-integration.test.ts",
    "tests/integration/claude-auth.test.ts",
  ];

  console.log(colors.bright + "Running test suites..." + colors.reset);
  console.log();

  const results: TestResult[] = [];

  for (const suite of testSuites) {
    const suitePath = join(process.cwd(), suite);

    if (!existsSync(suitePath)) {
      console.log(colors.yellow + `⚠ Skipping ${suite} (not found)` + colors.reset);
      continue;
    }

    console.log(colors.cyan + `→ Running ${suite}...` + colors.reset);
    const result = await runTestSuite(suitePath);
    results.push(result);
  }

  printResults(results);
  validateSuccessCriteria(results);

  // Exit with error code if any tests failed
  const anyFailed = results.some((r) => r.failed > 0);
  process.exit(anyFailed ? 1 : 0);
}

// Run if called directly
if (import.meta.main) {
  main().catch((error) => {
    console.error(colors.red + "Error running tests:" + colors.reset, error);
    process.exit(1);
  });
}
