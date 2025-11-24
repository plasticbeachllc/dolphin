import { defineConfig } from '@vscode/test-cli';

const version = process.env.VSCODE_TEST_VERSION || '1.106.0';

const headlessLaunchArgs = [
  '--disable-gpu',
  '--disable-gpu-compositing',
  '--disable-renderer-backgrounding',
  '--disable-software-rasterizer',
  '--disable-dev-shm-usage',
  '--disable-features=CalculateNativeWinOcclusion',
];

const baseConfig = {
  version, // Pin to a specific VS Code build to avoid network downloads
  workspaceFolder: '../', // Use dolphin project root
  extensionDevelopmentPath: '.',
  launchArgs: headlessLaunchArgs, // Ensure tests run in headless CI environments
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
  withLabel('all', 'out/**/src/test/**/*.test.js'),
  withLabel('unit', 'out/**/src/test/suite/unit/**/*.test.js'),
  withLabel('integration', 'out/**/src/test/suite/integration/**/*.test.js'),
  withLabel('e2e', 'out/**/src/test/suite/e2e/**/*.test.js'),
]);
