# End-to-End Testing Guide

This document provides a comprehensive guide to the Dolphin E2E testing framework for the VS Code extension.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Framework Architecture](#framework-architecture)
- [Test Structure](#test-structure)
- [Writing Tests](#writing-tests)
- [Running Tests](#running-tests)
- [CI/CD Integration](#cicd-integration)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

The Dolphin E2E testing framework provides comprehensive test coverage for the VS Code extension, ensuring:

- ✅ Extension activates correctly
- ✅ Commands are registered and executable
- ✅ Webview UI loads properly
- ✅ Integration with backend services works
- ✅ End-to-end workflows function as expected

### Design Principles

1. **Lightweight** - Minimal dependencies, fast execution
2. **Extensible** - Easy to add new tests and helpers
3. **Maintainable** - Clear structure, good documentation
4. **Isolated** - Tests run independently, mock external services
5. **Reliable** - Works in both local and CI environments

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- Bun (for webview build)
- VS Code (will be downloaded automatically for tests)

### Installation

```bash
# From root directory
npm install

# Install webview dependencies
cd vscode-extension/webview
bun install
cd ../..

# Build the webview
cd vscode-extension/webview
bun run build
cd ../..

# Install extension dependencies
cd vscode-extension
npm install
cd ..
```

### Running Tests

```bash
# From root directory
npm run test:e2e

# Or from vscode-extension directory
cd vscode-extension
npm test
```

## Framework Architecture

### Directory Structure

```
vscode-extension/src/test/
├── suite/                      # Test suites
│   ├── index.ts               # Test discovery and runner
│   ├── extension.test.ts      # Extension activation
│   ├── webview.test.ts        # Webview UI
│   ├── commands.test.ts       # Command execution
│   └── integration.test.ts    # Integration tests
├── helpers/                    # Utilities
│   ├── test-utils.ts          # Common helpers
│   └── mock-services.ts       # Mock implementations
├── runTest.ts                 # Test runner
└── README.md                  # Documentation
```

### Test Levels

The framework provides multiple test levels:

#### Level 1: Activation Tests
- **Speed:** Very fast (< 5s)
- **Scope:** Extension loading, basic setup
- **Dependencies:** None (isolated)

#### Level 2: Command Tests
- **Speed:** Fast (< 10s)
- **Scope:** Command registration and execution
- **Dependencies:** Activated extension

#### Level 3: Webview Tests
- **Speed:** Fast (< 10s)
- **Scope:** UI contributions, view providers
- **Dependencies:** Activated extension, built webview

#### Level 4: Integration Tests
- **Speed:** Medium (< 30s)
- **Scope:** Full workflows with mock services
- **Dependencies:** Mock KB API, Agent Bridge

#### Level 5: Full E2E (Future)
- **Speed:** Slow (> 60s)
- **Scope:** Real services, complete workflows
- **Dependencies:** Running KB API, Agent Core

## Test Structure

### Basic Test File Structure

```typescript
import * as assert from 'assert';
import * as vscode from 'vscode';
import { waitForExtensionActivation, sleep } from '../helpers/test-utils';

suite('Test Suite Name', () => {
  // Setup before all tests
  suiteSetup(async function () {
    this.timeout(15000);
    await waitForExtensionActivation();
  });

  // Cleanup after all tests
  suiteTeardown(async function () {
    // Cleanup code
  });

  // Individual test
  test('Test case description', async function () {
    this.timeout(10000);

    // Arrange
    const extension = vscode.extensions.getExtension('pb.dolphin');

    // Act
    const result = await vscode.commands.executeCommand('dolphin.test');

    // Assert
    assert.ok(extension, 'Extension should exist');
  });
});
```

### Test Naming Conventions

- **Suite names:** Describe the component or feature being tested
  - ✅ "Extension Activation Tests"
  - ✅ "Webview Tests"
  - ✅ "Integration Tests"

- **Test names:** Describe the expected behavior
  - ✅ "Should activate successfully"
  - ✅ "Should register commands"
  - ❌ "Test 1"

## Writing Tests

### Using Test Utilities

#### Wait for Extension Activation

```typescript
import { waitForExtensionActivation } from '../helpers/test-utils';

const extension = await waitForExtensionActivation();
assert.ok(extension.isActive);
```

#### Wait for Conditions

```typescript
import { waitFor } from '../helpers/test-utils';

await waitFor(() => someCondition === true, 5000, 100);
```

#### Sleep

```typescript
import { sleep } from '../helpers/test-utils';

await sleep(1000); // Wait 1 second
```

#### Create Test Workspace

```typescript
import { createTestWorkspace, cleanupTestWorkspace } from '../helpers/test-utils';

const workspace = await createTestWorkspace();
// ... use workspace ...
await cleanupTestWorkspace(workspace);
```

### Using Mock Services

#### Mock KB API Server

```typescript
import { MockKBServer } from '../helpers/mock-services';

let mockServer: MockKBServer;

suiteSetup(async function () {
  mockServer = new MockKBServer();
  await mockServer.start(7778);
});

suiteTeardown(async function () {
  await mockServer.stop();
});

test('Should handle search', async function () {
  // Make request to mockServer.port
});
```

#### Mock Agent Bridge

```typescript
import { MockAgentBridge } from '../helpers/mock-services';

const mockBridge = new MockAgentBridge();

mockBridge.onEvent((event) => {
  console.log('Event:', event);
});

await mockBridge.sendMessage('Hello');
mockBridge.shutdown();
```

### Testing Asynchronous Code

Always use `async/await` and set appropriate timeouts:

```typescript
test('Async test', async function () {
  this.timeout(10000); // 10 second timeout

  const result = await someAsyncOperation();

  assert.ok(result);
});
```

### Testing Error Conditions

```typescript
test('Should handle errors', async function () {
  try {
    await vscode.commands.executeCommand('invalid.command');
    assert.fail('Should have thrown error');
  } catch (err) {
    assert.ok(err, 'Should throw error for invalid command');
  }
});
```

### Headless Mode Considerations

Some operations fail in headless mode (CI environments):

```typescript
test('Command test with headless fallback', async function () {
  try {
    await vscode.commands.executeCommand('dolphin.focusInput');
    assert.ok(true, 'Command executed');
  } catch (err) {
    // In headless mode, just check command is registered
    const commands = await vscode.commands.getCommands(true);
    assert.ok(commands.includes('dolphin.focusInput'));
  }
});
```

## Running Tests

### Local Development

```bash
# Run all E2E tests
npm run test:e2e

# Run specific test file (after compilation)
cd vscode-extension
npm run compile
npx mocha out/test/suite/extension.test.js
```

### With Verbose Output

```bash
cd vscode-extension
npm run compile && node out/test/runTest.js
```

### In Watch Mode

```bash
# Terminal 1: Watch and compile
cd vscode-extension
npm run watch

# Terminal 2: Run tests (manually after changes)
npm test
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Setup Bun
        uses: oven-sh/setup-bun@v1

      - name: Install dependencies
        run: npm install

      - name: Build webview
        run: |
          cd vscode-extension/webview
          bun install
          bun run build

      - name: Run E2E tests
        run: npm run test:e2e
        env:
          DISPLAY: ':99.0'

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: vscode-extension/test-results/
```

### CI Environment Setup

For headless environments, ensure:

1. **Xvfb is running** (for Linux):
   ```bash
   export DISPLAY=:99.0
   Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &
   ```

2. **Disable GPU** (pass to test runner):
   ```typescript
   launchArgs: ['--disable-gpu', '--no-sandbox']
   ```

## Best Practices

### 1. Test Isolation

- Each test should be independent
- Clean up resources after tests
- Don't rely on test execution order

```typescript
suite('Isolated Tests', () => {
  let resource: any;

  setup(async function () {
    resource = await createResource();
  });

  teardown(async function () {
    await cleanupResource(resource);
  });

  test('Test 1', async function () {
    // Uses fresh resource
  });

  test('Test 2', async function () {
    // Uses fresh resource
  });
});
```

### 2. Appropriate Timeouts

- Extension activation: 15 seconds
- Command execution: 10 seconds
- Simple operations: 5 seconds
- Integration tests: 30 seconds

```typescript
suiteSetup(async function () {
  this.timeout(15000); // Suite-level timeout
});

test('Long running test', async function () {
  this.timeout(30000); // Test-level timeout
});
```

### 3. Descriptive Assertions

```typescript
// ❌ Bad
assert.ok(result);

// ✅ Good
assert.ok(result, 'Result should be defined');
assert.strictEqual(result.status, 'ok', 'Status should be ok');
```

### 4. Test Organization

Group related tests:

```typescript
suite('Extension Tests', () => {
  suite('Activation', () => {
    test('Should activate');
    test('Should register commands');
  });

  suite('Commands', () => {
    test('Should execute focusInput');
    test('Should execute newConversation');
  });
});
```

### 5. Mock External Dependencies

Don't depend on real services in E2E tests:

```typescript
// ✅ Good - Use mock
const mockServer = new MockKBServer();
await mockServer.start();

// ❌ Bad - Depend on real service
// Assumes KB API is running on localhost:7777
```

### 6. Version Control

Don't commit:
- `node_modules/`
- `.vscode-test/` (downloaded VS Code)
- `out/` (compiled test files)

Do commit:
- Test source files (`src/test/`)
- Test documentation
- Mock implementations

## Troubleshooting

### Test Discovery Issues

**Problem:** Tests not found

**Solution:**
```bash
# Ensure tests are compiled
npm run compile

# Check test files follow naming convention
ls out/test/suite/*.test.js
```

### Extension Activation Timeout

**Problem:** Extension doesn't activate within timeout

**Causes:**
- Webview not built
- Missing dependencies
- Extension error

**Solution:**
```bash
# Build webview
cd vscode-extension/webview
bun run build

# Check for errors
cat vscode-extension/out/extension.js

# Increase timeout
this.timeout(20000);
```

### Webview Tests Failing

**Problem:** Webview focus fails

**Solution:**
- Expected in headless mode
- Check command registration instead
- See `webview.test.ts` for patterns

### Mock Server Port Conflicts

**Problem:** Port already in use

**Solution:**
```typescript
// Use dynamic port (0 = auto-assign)
await mockServer.start(0);
console.log('Server on port:', mockServer.port);

// Or use different port
await mockServer.start(7779);
```

### VS Code Download Issues

**Problem:** @vscode/test-electron fails to download VS Code

**Solution:**
```bash
# Clear cache
rm -rf ~/.vscode-test

# Run tests again
npm test
```

### Import/Module Errors

**Problem:** Cannot find module

**Solution:**
```bash
# Install dependencies
npm install

# Check TypeScript config
cat tsconfig.json

# Rebuild
npm run compile
```

## Advanced Topics

### Custom Test Reporters

```typescript
// suite/index.ts
const mocha = new Mocha({
  ui: 'bdd',
  color: true,
  reporter: 'spec', // or 'json', 'junit', etc.
});
```

### Code Coverage

Add Istanbul/nyc for coverage:

```bash
npm install --save-dev nyc

# Run with coverage
npx nyc npm test
```

### Performance Testing

```typescript
test('Performance test', async function () {
  const start = Date.now();

  await someOperation();

  const duration = Date.now() - start;
  assert.ok(duration < 1000, `Should complete in < 1s (took ${duration}ms)`);
});
```

### Debugging Tests

```typescript
// Add breakpoints in VS Code
// Launch config in .vscode/launch.json:
{
  "name": "Extension Tests",
  "type": "extensionHost",
  "request": "launch",
  "args": [
    "--extensionDevelopmentPath=${workspaceFolder}/vscode-extension",
    "--extensionTestsPath=${workspaceFolder}/vscode-extension/out/test/suite/index"
  ]
}
```

## Resources

- [VS Code Extension Testing](https://code.visualstudio.com/api/working-with-extensions/testing-extension)
- [Mocha Documentation](https://mochajs.org/)
- [Node Assert API](https://nodejs.org/api/assert.html)
- [Dolphin Testing Guide](/tests/TESTING.md)
- [Dolphin Architecture](/docs/ARCHITECTURE.md)

---

**Questions or Issues?**

- Check existing tests in `vscode-extension/src/test/suite/`
- Review helper functions in `vscode-extension/src/test/helpers/`
- See the [README](/vscode-extension/src/test/README.md) for more examples
