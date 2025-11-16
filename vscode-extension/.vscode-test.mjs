import { defineConfig } from '@vscode/test-cli';

const version = process.env.VSCODE_TEST_VERSION || '1.106.0';

export default defineConfig({
  files: 'out/test/suite/**/*.test.js',
  version,  // Pin to a specific VS Code build to avoid network downloads
  workspaceFolder: '../',  // Use dolphin project root
  extensionDevelopmentPath: '.',
  mocha: {
    ui: 'bdd',
    timeout: 20000,
  },
});
