import { defineConfig } from '@vscode/test-cli';

const version = process.env.VSCODE_TEST_VERSION || '1.106.0';

const baseConfig = {
  version, // Pin to a specific VS Code build to avoid network downloads
  workspaceFolder: '../', // Use dolphin project root
  extensionDevelopmentPath: '.',
  env: {
    DOLPHIN_TEST_ENV: '1',
    DOLPHIN_KB_BASE_URL: process.env.DOLPHIN_KB_BASE_URL || 'http://127.0.0.1:7778',
  },
  mocha: {
    ui: 'bdd',
    timeout: 20000,
  },
};

const withLabel = (label, files) => ({
  ...baseConfig,
  label,
  files,
});

export default defineConfig([
  withLabel('all', 'out/test/suite/{unit,integration,e2e}/**/*.test.js'),
  withLabel('unit', 'out/test/suite/unit/**/*.test.js'),
  withLabel('integration', 'out/test/suite/integration/**/*.test.js'),
  withLabel('e2e', 'out/test/suite/e2e/**/*.test.js'),
]);
