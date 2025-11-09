# Dolphin VS Code Extension E2E Testing Framework

This directory contains the end-to-end (E2E) testing framework for the Dolphin VS Code extension. The framework is designed to be lightweight, extensible, and easy to maintain.

## 📁 Directory Structure

```
vscode-extension/src/test/
├── suite/                      # Test suites
│   ├── index.ts               # Test suite entry point
│   ├── extension.test.ts      # Extension activation tests
│   ├── webview.test.ts        # Webview rendering tests
│   ├── commands.test.ts       # Command execution tests
│   └── integration.test.ts    # Integration tests with mock services
├── helpers/                    # Test utilities
│   ├── test-utils.ts          # Common test helper functions
│   └── mock-services.ts       # Mock services (KB API, Agent Bridge)
├── runTest.ts                 # Test runner (downloads VS Code, runs tests)
└── README.md                  # This file
```

## 🚀 Quick Start

### Running Tests

From the **vscode-extension** directory:

```bash
# Install dependencies (if not already done)
npm install

# Compile the extension and tests
npm run compile

# Run all E2E tests
npm test
```

From the **root** directory:

```bash
# Run E2E tests only
npm run test:e2e

# Run all tests (agent-core, mcp-bridge, kb, and E2E)
npm run test:all
```

### First Time Setup

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Build the webview:**
   ```bash
   cd webview
   bun install
   bun run build
   cd ..
   ```

3. **Compile the extension:**
   ```bash
   npm run compile
   ```

4. **Run tests:**
   ```bash
   npm test
   ```

## 📝 Test Coverage

### Extension Activation Tests (`extension.test.ts`)

Tests the core extension activation flow:

- ✅ Extension is present and discoverable
- ✅ Extension activates successfully
- ✅ Commands are registered correctly
- ✅ Output channel is created
- ✅ Webview view provider is registered

### Webview Tests (`webview.test.ts`)

Tests the webview UI integration:

- ✅ Chat view can be focused
- ✅ Activity bar contributions are correct
- ✅ Chat view contributions are properly defined
- ✅ Keybindings are registered correctly

### Command Tests (`commands.test.ts`)

Tests command execution:

- ✅ `dolphin.focusInput` command works
- ✅ `dolphin.newConversation` command works
- ✅ `dolphin.test` command works
- ✅ All registered commands are executable

### Integration Tests (`integration.test.ts`)

Tests integration with mock services:

- ✅ Mock KB API server starts and responds
- ✅ Extension activates with mock server running
- ✅ Mock KB API handles search requests
- ✅ Complete workflow (activation → webview → commands)

## 🛠️ Test Utilities

### Helper Functions (`test-utils.ts`)

Common utilities for writing tests:

```typescript
// Wait for a condition to be true
await waitFor(() => someCondition, timeout, interval);

// Sleep for a given time
await sleep(1000); // 1 second

// Get Dolphin extension
const extension = getDolphinExtension();

// Wait for extension activation
const extension = await waitForExtensionActivation();

// Get a webview
await getWebview('dolphin.chatView');

// Create test workspace
const workspaceUri = await createTestWorkspace();

// Clean up test workspace
await cleanupTestWorkspace(workspaceUri);

// Assert that a value is defined
assertDefined(value, 'Value should be defined');
```

### Mock Services (`mock-services.ts`)

Mock implementations for testing:

#### MockKBServer

A lightweight HTTP server that mocks the Knowledge Base API:

```typescript
import { MockKBServer } from '../helpers/mock-services';

const mockServer = new MockKBServer();
await mockServer.start(7778); // Start on port 7778

// ... run tests ...

await mockServer.stop();
```

**Endpoints:**
- `GET /health` - Health check
- `POST /search` - Search knowledge base
- `GET /metadata/:id` - Get metadata
- `GET /chunks/:id` - Fetch chunk

#### MockAgentBridge

A mock implementation of the Agent Bridge for testing:

```typescript
import { MockAgentBridge } from '../helpers/mock-services';

const mockBridge = new MockAgentBridge();

// Listen for events
mockBridge.onEvent((event) => {
  console.log('Event:', event);
});

// Send message
await mockBridge.sendMessage('Hello');

// Clean up
mockBridge.shutdown();
```

## ✍️ Writing New Tests

### Basic Test Structure

```typescript
import * as assert from 'assert';
import * as vscode from 'vscode';
import { waitForExtensionActivation, sleep } from '../helpers/test-utils';

suite('My Test Suite', () => {
  suiteSetup(async function () {
    // Setup before all tests in this suite
    this.timeout(15000);
    await waitForExtensionActivation();
  });

  suiteTeardown(async function () {
    // Cleanup after all tests in this suite
  });

  test('My test case', async function () {
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

### Testing with Mock Services

```typescript
import { MockKBServer } from '../helpers/mock-services';

suite('Integration Tests with Mock KB', () => {
  let mockServer: MockKBServer;

  suiteSetup(async function () {
    this.timeout(15000);
    mockServer = new MockKBServer();
    await mockServer.start(7778);
  });

  suiteTeardown(async function () {
    await mockServer.stop();
  });

  test('Should interact with mock KB API', async function () {
    // Your test here
  });
});
```

### Adding New Test Files

1. Create a new file in `suite/` with the `.test.ts` suffix
2. Follow the test structure above
3. Import necessary helpers from `../helpers/`
4. The test will automatically be discovered and run

## 🎯 Best Practices

### Test Isolation

- Each test should be independent
- Use `suiteSetup` and `suiteTeardown` for shared setup/cleanup
- Clean up resources (workspaces, servers, etc.) after tests

### Timeouts

- Set appropriate timeouts using `this.timeout(ms)`
- Extension activation: 15 seconds
- Command execution: 10 seconds
- Simple assertions: 5 seconds (default)

### Headless Mode Considerations

Some tests may behave differently in headless mode (CI environments):

- Webview focusing may fail if not visible
- Use try-catch for operations that require UI visibility
- Test command registration rather than execution for UI commands

### Async/Await

- Always use `async/await` for asynchronous operations
- Don't forget to `await` helper functions like `sleep()` and `waitFor()`

### Assertions

- Use descriptive assertion messages
- Prefer `assert.strictEqual` over `assert.equal` for type safety
- Use `assert.ok` for truthy checks

## 🔧 Troubleshooting

### Tests Failing to Run

**Problem:** `npm test` fails with module not found

**Solution:**
```bash
npm install
npm run compile
```

### Extension Not Activating

**Problem:** Extension activation timeout

**Solution:**
- Check that the webview is built: `cd webview && bun run build`
- Increase timeout in test: `this.timeout(20000)`
- Check for errors in the Output channel

### Webview Tests Failing

**Problem:** Webview focus commands fail

**Solution:**
- These may fail in headless mode (expected)
- Tests should check for command registration instead
- Use the pattern from `webview.test.ts`

### Mock Server Issues

**Problem:** Mock server port conflicts

**Solution:**
- Use a different port: `mockServer.start(7779)`
- Ensure previous tests clean up servers properly

## 📊 Coverage Goals

Current coverage:
- ✅ Extension activation
- ✅ Command registration
- ✅ Webview contributions
- ✅ Mock service integration

Future improvements:
- [ ] Webview messaging (webview ↔ extension)
- [ ] Agent Core integration (full flow)
- [ ] File operations through MCP
- [ ] State persistence tests
- [ ] Error handling scenarios

## 🏗️ Architecture

### Test Levels

1. **Activation Tests** - Fast, isolated tests for extension loading
2. **Command Tests** - Test command registration and execution
3. **Webview Tests** - Test webview UI integration
4. **Integration Tests** - Test with mock external services
5. **Full E2E** (future) - Optional tests with real services

### Dependencies

- **@vscode/test-electron** - VS Code test runner
- **mocha** - Test framework
- **glob** - File pattern matching for test discovery
- **Built-in assert** - Assertion library

### Test Execution Flow

```
npm test
  ↓
runTest.ts
  ↓
Downloads VS Code (if needed)
  ↓
Launches VS Code with extension
  ↓
suite/index.ts (discovers tests)
  ↓
Runs all *.test.ts files
  ↓
Reports results
```

## 🤝 Contributing

When adding new tests:

1. Follow existing patterns in `suite/*.test.ts`
2. Add helper functions to `helpers/test-utils.ts`
3. Document new test utilities in this README
4. Ensure tests pass in both local and headless environments
5. Update coverage goals if adding new test areas

## 📚 Related Documentation

- [VS Code Extension Testing Guide](https://code.visualstudio.com/api/working-with-extensions/testing-extension)
- [Mocha Documentation](https://mochajs.org/)
- [Dolphin Architecture](../../../docs/ARCHITECTURE.md)
- [Python Testing Guide](../../../tests/TESTING.md)

## 🎓 Examples

### Example: Testing Extension Activation

```typescript
test('Extension should activate successfully', async function () {
  this.timeout(15000);

  const extension = await waitForExtensionActivation();

  assert.ok(extension, 'Extension should be defined');
  assert.strictEqual(extension.isActive, true, 'Extension should be activated');
});
```

### Example: Testing Commands

```typescript
test('Should execute command', async function () {
  this.timeout(10000);

  await waitForExtensionActivation();

  try {
    await vscode.commands.executeCommand('dolphin.test');
    assert.ok(true, 'Command executed successfully');
  } catch (err) {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(commands.includes('dolphin.test'), 'Command should be registered');
  }
});
```

### Example: Testing with Mock Server

```typescript
test('Should handle search request', async function () {
  this.timeout(5000);

  const http = require('http');
  const searchRequest = { query: 'test', top_k: 10 };

  const response = await new Promise((resolve, reject) => {
    const postData = JSON.stringify(searchRequest);
    const options = {
      hostname: 'localhost',
      port: mockServer.port,
      path: '/search',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
      },
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        resolve({ status: res.statusCode, data: JSON.parse(data) });
      });
    });

    req.on('error', reject);
    req.write(postData);
    req.end();
  });

  assert.strictEqual(response.status, 200, 'Should return 200');
  assert.ok(Array.isArray(response.data.hits), 'Should return hits array');
});
```

---

**Happy Testing! 🧪**
