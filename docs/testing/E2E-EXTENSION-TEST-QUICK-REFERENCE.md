# E2E Extension Test Refactoring - Quick Reference

**For developers implementing the refactoring plan.**

---

## Common Patterns to Replace

### 1. Activation Testing

❌ **BEFORE (Duplicated in 5 files):**
```typescript
test('Extension should activate', async () => {
  const ext = vscode.extensions.getExtension('pb.dolphin');
  assert.ok(ext);

  if (!ext.isActive) {
    await ext.activate();
  }

  await sleep(1000); // Wait for activation
  assert.ok(ext.isActive);
});
```

✅ **AFTER (Use shared fixture):**
```typescript
import { activateExtension } from '../helpers/shared-fixtures';

test('Extension should activate', async () => {
  const ext = await activateExtension();
  assert.ok(ext.isActive);
});
```

---

### 2. Command Registration Testing

❌ **BEFORE (Duplicated in 4 files):**
```typescript
test('focusInput command should be registered', async () => {
  const commands = await vscode.commands.getCommands(true);
  assert.ok(commands.includes('dolphin.focusInput'));
});

test('newConversation command should be registered', async () => {
  const commands = await vscode.commands.getCommands(true);
  assert.ok(commands.includes('dolphin.newConversation'));
});
// ... repeated for every command
```

✅ **AFTER (Use shared fixture):**
```typescript
import { assertCommandsExist } from '../helpers/shared-fixtures';
import { TEST_COMMANDS } from '../helpers/test-constants';

test('All Phase 1 commands should be registered', async () => {
  await assertCommandsExist([
    TEST_COMMANDS.FOCUS_INPUT,
    TEST_COMMANDS.NEW_CONVERSATION,
    TEST_COMMANDS.SET_API_KEY,
    TEST_COMMANDS.TEST,
  ]);
});
```

---

### 3. False Positive Pattern

❌ **BEFORE (Tests pass when they shouldn't):**
```typescript
test('Command should execute', async () => {
  try {
    await vscode.commands.executeCommand('dolphin.focusInput');
    assert.ok(true, 'Command executed');
  } catch (err) {
    // Still passes! This is wrong!
    const commands = await vscode.commands.getCommands(true);
    assert.ok(commands.includes('dolphin.focusInput'));
  }
});
```

✅ **AFTER (Test actually fails on error):**
```typescript
test('Command should execute', async () => {
  // If command fails, test fails (as it should)
  await vscode.commands.executeCommand('dolphin.focusInput');
  // Add assertions to verify actual behavior
  assert.ok(webviewHasFocus(), 'Webview should have focus');
});
```

---

### 4. Sleep Pattern

❌ **BEFORE (Arbitrary delays):**
```typescript
test('KB should start', async () => {
  await startKB();
  await sleep(5000); // Hope it's ready...
  const status = await getKBStatus();
  assert.ok(status.running);
});
```

✅ **AFTER (Event-driven waiting):**
```typescript
import { waitForCondition } from '../helpers/shared-fixtures';

test('KB should start', async () => {
  await startKB();

  await waitForCondition(
    async () => {
      const status = await getKBStatus();
      return status.running === true;
    },
    {
      timeout: 10000,
      timeoutMessage: 'KB failed to start within 10s'
    }
  );

  const status = await getKBStatus();
  assert.ok(status.running);
});
```

---

### 5. No Behavior Verification

❌ **BEFORE (Tests registration, not behavior):**
```typescript
test('Should create new conversation', async () => {
  await vscode.commands.executeCommand('dolphin.newConversation');
  // That's it. No verification!
});
```

✅ **AFTER (Verifies actual behavior):**
```typescript
test('Should create new conversation and persist to disk', async () => {
  const initialCount = (await getConversations()).length;

  await vscode.commands.executeCommand('dolphin.newConversation');

  // Wait for conversation to be created
  await waitForCondition(
    async () => (await getConversations()).length > initialCount,
    { timeout: 2000 }
  );

  const conversations = await getConversations();
  const newConv = conversations[conversations.length - 1];

  // Verify properties
  assert.ok(newConv.id);
  assert.strictEqual(newConv.messages.length, 0);

  // Verify persistence
  const filePath = getConversationPath(newConv.id);
  const fileExists = await fs.access(filePath)
    .then(() => true)
    .catch(() => false);
  assert.ok(fileExists, 'Conversation file should exist');
});
```

---

### 6. Mock Usage

❌ **BEFORE (No mocks, relies on real services):**
```typescript
test('KB search should work', async function() {
  // Skip if KB not running
  if (!isKBRunning()) {
    this.skip();
  }

  const results = await searchKB('test query');
  assert.ok(results.length > 0);
});
```

✅ **AFTER (Uses mocks consistently):**
```typescript
import { setupMockEnvironment, configureMockKB } from '../helpers/mock-manager';

suite('KB Integration Tests', function() {
  suiteSetup(async () => {
    await setupMockEnvironment();
  });

  test('KB search should work', async () => {
    // Configure mock response
    configureMockKB({
      searchResults: [
        { content: 'Test result', score: 0.9, file_path: 'test.ts' }
      ]
    });

    const results = await searchKB('test query');
    assert.strictEqual(results.length, 1);
    assert.strictEqual(results[0].content, 'Test result');
  });
});
```

---

## Shared Fixtures Cheat Sheet

### Import Statement
```typescript
import {
  activateExtension,
  assertCommandExists,
  assertCommandsExist,
  assertConfigurationExists,
  waitForCondition,
  sleep,
  createTestDocument,
  getExtensionExports,
} from '../helpers/shared-fixtures';

import {
  TEST_COMMANDS,
  TEST_CONFIG_KEYS,
  TEST_TIMEOUTS,
} from '../helpers/test-constants';

import {
  setupMockEnvironment,
  teardownMockEnvironment,
  resetMocks,
  getMockEnvironment,
  configureMockKB,
  configureMockAgent,
} from '../helpers/mock-manager';
```

### Setup Pattern
```typescript
suite('My Test Suite', function() {
  this.timeout(10000);

  suiteSetup(async () => {
    await setupMockEnvironment();
    await activateExtension();
  });

  suiteTeardown(async () => {
    await teardownMockEnvironment();
  });

  setup(() => {
    resetMocks();
  });

  test('My test', async () => {
    // Test code
  });
});
```

### Waiting Helper
```typescript
// Wait for condition (replaces sleep)
await waitForCondition(
  () => someCondition === true,
  {
    timeout: 5000,
    interval: 100,
    timeoutMessage: 'Condition not met'
  }
);

// Async condition
await waitForCondition(
  async () => {
    const status = await getStatus();
    return status.ready === true;
  },
  { timeout: 5000 }
);
```

### Mock Configuration
```typescript
// Configure KB mock
configureMockKB({
  searchResults: [{ content: 'test', score: 0.9 }],
  metadata: { totalChunks: 1000 },
  health: true,
});

// Configure Agent mock
configureMockAgent({
  response: 'Mock agent response',
  toolCalls: [{ name: 'search_knowledge', input: { query: 'test' } }],
  shouldError: false,
});

// Access mock environment
const { kbServer, agentBridge } = getMockEnvironment();
const history = agentBridge.getMessageHistory();
```

---

## File Organization

### Current Structure (Delete These)
```
src/test/suite/
├── phase1-integration.test.ts     ❌ DELETE (replaced)
├── phase2-integration.test.ts     ❌ DELETE (replaced)
├── integration.test.ts            ❌ DELETE (content moved)
├── conversations-e2e.test.ts      ❌ DELETE (refactored)
├── kb-lifecycle.test.ts           ❌ DELETE (refactored)
└── extension.test.ts              ❌ DELETE (replaced)
```

### New Structure (Create These)
```
src/test/
├── unit/                          ✅ Unit tests (fast, mocked)
│   ├── logger.test.ts
│   ├── configuration.test.ts
│   ├── diff-handler.test.ts
│   └── ...
│
├── integration/                   ✅ Integration tests
│   ├── extension-activation.test.ts    (new)
│   ├── commands-registry.test.ts       (new)
│   ├── conversation-workflow.test.ts   (refactored)
│   ├── kb-integration.test.ts          (refactored)
│   └── ...
│
├── e2e/                           ✅ E2E tests (future)
│   └── user-workflow.test.ts           (new)
│
└── helpers/                       ✅ Shared utilities
    ├── shared-fixtures.ts              (new)
    ├── test-constants.ts               (new)
    ├── mock-manager.ts                 (new)
    ├── mock-services.ts                (enhanced)
    └── test-utils.ts                   (existing)
```

---

## Testing Commands

### Run Tests
```bash
# All tests
npm test

# Unit tests only (fast)
npm run test:unit

# Integration tests only
npm run test:integration

# E2E tests only
npm run test:e2e

# With coverage
npm run test:coverage

# Watch mode
npm run test:watch
```

### From justfile
```bash
# Unit tests
just test-unit-extension

# Integration tests
just test-integration-extension

# E2E tests
just test-e2e-extension

# All extension tests
just test-extension-all
```

---

## Checklist for Each Change

Before committing any refactoring:

### Code Quality
- [ ] No duplicated code
- [ ] Uses shared fixtures
- [ ] Uses mocks consistently
- [ ] No arbitrary sleep() calls
- [ ] Tests verify behavior, not just registration
- [ ] No false positives (tests that pass when they should fail)

### Testing
- [ ] All tests pass
- [ ] New tests added for new fixtures
- [ ] Existing behavior preserved
- [ ] Test execution time improved

### Documentation
- [ ] Code comments added for complex logic
- [ ] Test names clearly describe behavior
- [ ] Shared fixtures documented

### Review
- [ ] Self-review completed
- [ ] Peer review requested
- [ ] CI checks passing

---

## Common Mistakes to Avoid

### ❌ Don't: Keep duplicated code
```typescript
// In file 1
const ext = vscode.extensions.getExtension('pb.dolphin');
await ext.activate();

// In file 2
const ext = vscode.extensions.getExtension('pb.dolphin');
await ext.activate();
```

### ✅ Do: Use shared fixtures
```typescript
// In both files
import { activateExtension } from '../helpers/shared-fixtures';
const ext = await activateExtension();
```

---

### ❌ Don't: Use sleep() for waiting
```typescript
await startServer();
await sleep(5000); // Maybe it's ready?
```

### ✅ Do: Wait for actual condition
```typescript
await startServer();
await waitForCondition(
  () => isServerReady(),
  { timeout: 10000 }
);
```

---

### ❌ Don't: Test registration only
```typescript
test('Command exists', async () => {
  const commands = await vscode.commands.getCommands();
  assert.ok(commands.includes('dolphin.test'));
});
```

### ✅ Do: Test actual behavior
```typescript
test('Command creates conversation', async () => {
  await vscode.commands.executeCommand('dolphin.newConversation');

  const conversations = await getConversations();
  assert.ok(conversations.length > 0);
  assert.ok(conversations[0].id);
});
```

---

### ❌ Don't: Skip tests due to environment
```typescript
test('Test with real KB', function() {
  if (!process.env.KB_AVAILABLE) {
    this.skip();
  }
  // Test code
});
```

### ✅ Do: Use mocks for all environments
```typescript
test('Test with mock KB', async () => {
  configureMockKB({ health: true });
  // Test code works everywhere
});
```

---

## Quick Reference Links

- **[Executive Summary](./E2E-EXTENSION-TEST-REFACTORING-SUMMARY.md)** - High-level overview
- **[Full Plan](./E2E-EXTENSION-TEST-REFACTORING-PLAN.md)** - Complete implementation guide
- **[Test Optimization](./TEST_OPTIMIZATION.md)** - Python test lessons
- **[Coverage Plan](./TEST-COVERAGE-IMPROVEMENT-PLAN.md)** - Overall coverage strategy

---

## Getting Help

**Stuck?** Check:
1. This quick reference
2. Full refactoring plan
3. Shared fixtures source code
4. Existing tests that follow new patterns

**Still stuck?** Ask the team or open an issue.

---

## Daily Workflow

### Morning
1. Pull latest from refactoring branch
2. Review today's tasks in plan
3. Set up development environment

### During Work
1. Make incremental changes
2. Run tests after each change
3. Commit working code frequently

### Evening
1. Push changes to branch
2. Update tracking board
3. Note any blockers

### Code Review
1. Self-review using checklist
2. Request peer review
3. Address feedback
4. Merge when approved

---

**Last Updated:** 2025-11-13
**Maintainer:** Engineering Team
