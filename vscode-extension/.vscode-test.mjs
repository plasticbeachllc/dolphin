import { defineConfig } from '@vscode/test-cli';

export default defineConfig({
  files: 'out/test/suite/**/*.test.js',
  version: 'stable',
  workspaceFolder: './test-workspace',
  mocha: {
    ui: 'bdd',
    timeout: 10000,
    globals: ['suite', 'test', 'suiteSetup', 'suiteTeardown', 'setup', 'teardown'],
  },
});