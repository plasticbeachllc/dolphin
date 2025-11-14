import { defineConfig } from '@vscode/test-cli';

export default defineConfig({
  files: 'out/test/suite/**/*.test.js',
  version: 'stable',  // Use stable version (>= 1.96.0)
  workspaceFolder: '../',  // Use dolphin project root
  extensionDevelopmentPath: '.',
  mocha: {
    ui: 'bdd',
    timeout: 20000,
  },
});