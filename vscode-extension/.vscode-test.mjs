import { defineConfig } from '@vscode/test-cli';

export default defineConfig({
  files: 'out/test/suite/**/*.test.js',
  version: 'stable',
  workspaceFolder: './test-workspace',
  mocha: {
    ui: 'bdd',
    timeout: 20000, // Increased timeout to allow for config initialization
    globals: ['suite', 'test', 'suiteSetup', 'suiteTeardown', 'setup', 'teardown'],
  },
});