import * as path from "path";
import * as vscode from "vscode";
import Mocha from "mocha";
import { glob } from "glob";
import "./setup";

/**
 * Wait for VSCode's configuration system to be ready
 */
async function waitForConfigSystem(): Promise<void> {
  const maxAttempts = 10;
  const delayMs = 500;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      // Try to access configuration
      vscode.workspace.getConfiguration("dolphin");
      console.log("Configuration system is ready");
      return;
    } catch {
      console.log(`Config not ready (attempt ${attempt + 1}/${maxAttempts}), waiting...`);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }

  console.warn("Configuration system may not be fully ready, proceeding with tests");
}

export async function run(): Promise<void> {
  // Wait for VSCode's configuration system to be ready
  // This prevents "Exit prior to config file resolving" errors
  console.log("Waiting for VSCode configuration system to initialize...");
  await waitForConfigSystem();
  console.log("Configuration system ready, loading tests...");

  // Create the mocha test runner
  const mocha = new Mocha({
    ui: "bdd",
    color: true,
    timeout: 5000, // 5 seconds default timeout (reduced from 10s)
    reporter: "spec", // Use spec reporter for detailed output
  });

  // CRITICAL: Expose Mocha globals before loading test files
  mocha.suite.emit("pre-require", global, null, mocha);

  // Verify globals are set
  const globalRecord = global as Record<string, unknown>;
  console.log("Mocha globals set:", {
    describe: typeof globalRecord.describe,
    it: typeof globalRecord.it,
    suite: typeof globalRecord.suite,
    test: typeof globalRecord.test,
  });

  const testsRoot = path.resolve(__dirname, ".");

  console.log("Tests root:", testsRoot);
  console.log("Looking for test files...");

  // Find all test files (ignore stale JS directly under testsRoot)
  const files = await glob("{unit,integration,e2e}/**/*.test.js", { cwd: testsRoot });

  console.log("Found test files:", files);

  if (files.length === 0) {
    console.error("No test files found!");
    throw new Error("No test files found");
  }

  // Add files to the test suite
  files.forEach((f) => {
    const fullPath = path.resolve(testsRoot, f);
    console.log("Adding test file:", fullPath);
    mocha.addFile(fullPath);
  });

  return new Promise<void>((resolve, reject) => {
    try {
      // Run the mocha test
      console.log("Running tests...");
      const runner = mocha.run((failures: number) => {
        console.log(`Test run completed with ${failures} failure(s)`);
        if (failures > 0) {
          console.error(`${failures} tests failed.`);
          reject(new Error(`${failures} tests failed.`));
        } else {
          console.log("All tests passed!");
          resolve();
        }
      });

      // Add event handlers to capture test output
      runner.on("start", () => {
        console.log("Test runner started");
      });

      runner.on("test", (test) => {
        console.log(`Running test: ${test.fullTitle()}`);
      });

      runner.on("pass", (test) => {
        console.log(`✓ ${test.fullTitle()}`);
      });

      runner.on("fail", (test, err) => {
        console.error(`✗ ${test.fullTitle()}`);
        console.error(`  Error: ${err.message}`);
        console.error(`  Stack: ${err.stack}`);
      });

      runner.on("end", () => {
        console.log("Test runner finished");
      });
    } catch (err) {
      console.error("Error running tests:", err);
      reject(err);
    }
  });
}
