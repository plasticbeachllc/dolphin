import * as path from "path";
import { runTests } from "@vscode/test-electron";

async function main() {
  try {
    // The folder containing the Extension Manifest package.json
    // Passed to `--extensionDevelopmentPath`
    const extensionDevelopmentPath = path.resolve(__dirname, "../../");

    // The path to the extension test runner script
    // Passed to --extensionTestsPath
    const extensionTestsPath = path.resolve(__dirname, "./suite/index");

    // Use the dolphin project root as workspace (has pyproject.toml and KB setup)
    // This allows E2E tests to run with full KB functionality
    const workspacePath = path.resolve(__dirname, "../../../"); // dolphin-develop-backend/

    // Download VS Code, unzip it and run the integration test
    console.log("Starting E2E tests...");
    console.log("Extension path:", extensionDevelopmentPath);
    console.log("Tests path:", extensionTestsPath);
    console.log("Workspace path:", workspacePath);
    console.log("Using VS Code stable version (>= 1.96.0)");

    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath,
      version: "stable", // Use stable version (>= 1.96.0 required by extension)
      // No custom launch args - use defaults for compatibility with all VSCode versions
    });

    console.log("All tests passed!");
  } catch (err) {
    console.error("Failed to run tests:", err);
    process.exit(1);
  }
}

main();
