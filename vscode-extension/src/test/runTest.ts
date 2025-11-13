import * as path from 'path';
import { runTests } from '@vscode/test-electron';

async function main() {
  try {
    // The folder containing the Extension Manifest package.json
    // Passed to `--extensionDevelopmentPath`
    const extensionDevelopmentPath = path.resolve(__dirname, '../../');

    // The path to the extension test runner script
    // Passed to --extensionTestsPath
    const extensionTestsPath = path.resolve(__dirname, './suite/index');

    // Use the dolphin project root as workspace (has pyproject.toml and KB setup)
    // This allows E2E tests to run with full KB functionality
    const workspacePath = path.resolve(__dirname, '../../../'); // dolphin-develop-backend/

    // Download VS Code, unzip it and run the integration test
    console.log('Starting E2E tests...');
    console.log('Extension path:', extensionDevelopmentPath);
    console.log('Tests path:', extensionTestsPath);
    console.log('Workspace path:', workspacePath);
    console.log('Using VS Code 1.85.0 (last version with working test args)');

    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath,
      version: '1.85.0', // Last stable version that works with @vscode/test-electron args
      launchArgs: [
        workspacePath, // Open dolphin project root as workspace
        '--disable-extensions', // Disable other extensions
        '--verbose', // Enable verbose logging
        '--log', 'trace', // Enable trace logging
      ],
      extensionTestsEnv: {
        ELECTRON_ENABLE_LOGGING: '1',
        VSCODE_LOG_LEVEL: 'trace',
      },
    });

    console.log('All tests passed!');
  } catch (err) {
    console.error('Failed to run tests:', err);
    process.exit(1);
  }
}

main();
