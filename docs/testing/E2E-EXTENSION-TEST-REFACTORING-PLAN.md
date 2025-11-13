# E2E Extension Test Refactoring Plan

**Version:** 1.0
**Date:** 2025-11-13
**Status:** Implementation Ready
**Owner:** Engineering Team

## Executive Summary

This document provides a comprehensive specification and implementation plan to address critical issues in the VSCode extension end-to-end test suite. Based on detailed analysis, the current tests provide a **false sense of security** with a quality score of **3.5/10**. This plan will transform the test suite into a reliable, maintainable, and efficient asset.

### Critical Findings

| Issue | Current State | Target State | Priority |
|-------|--------------|--------------|----------|
| **Code Duplication** | 40-50% duplicated | <10% duplicated | 🔴 CRITICAL |
| **False Positives** | Tests pass when they fail | All failures detected | 🔴 CRITICAL |
| **Mock Usage** | Mocks exist but unused | 100% mock utilization | 🔴 CRITICAL |
| **Test Speed** | 50+ seconds of sleep() | <5 seconds total | 🟠 HIGH |
| **Production Environment** | 3/10 similarity | 7/10 similarity | 🟠 HIGH |
| **Behavior Coverage** | Tests registration only | Tests actual behavior | 🔴 CRITICAL |

### Expected Outcomes

- **Execution Time:** Reduce from ~60s to <15s (75% improvement)
- **Test Quality:** Increase from 3.5/10 to 8/10
- **Maintenance Burden:** Reduce by 60% through deduplication
- **False Positives:** Eliminate 100% of tests that pass when they should fail
- **Coverage:** Increase behavior coverage from ~20% to 80%

---

## Table of Contents

1. [Immediate Actions](#immediate-actions) (Weeks 1-2)
2. [Long-term Improvements](#long-term-improvements) (Weeks 3-4)
3. [Out-of-Scope Future Work](#out-of-scope-future-work)
4. [Implementation Timeline](#implementation-timeline)
5. [Test Architecture](#test-architecture)
6. [Success Metrics](#success-metrics)
7. [Appendices](#appendices)

---

## Immediate Actions

### IA-1: Eliminate Code Duplication (Priority: 🔴 CRITICAL)

**Timeline:** Week 1, Days 1-3
**Effort:** 3 days
**Impact:** 60% reduction in maintenance burden

#### Problem Statement

40-50% of test code is duplicated across 5 test files:
- Extension activation tested in 5 files
- Command registration tested in 4 files
- Same try-catch pattern duplicated 20+ times
- Configuration checks duplicated in 2 files

#### Implementation Plan

##### Step 1.1: Create Shared Test Fixtures (Day 1)

**File:** `vscode-extension/src/test/helpers/shared-fixtures.ts`

```typescript
/**
 * Shared test fixtures to eliminate duplication across test files.
 */

import * as vscode from 'vscode';
import * as assert from 'assert';

/**
 * Extension activation fixture with proper waiting.
 * Use this instead of duplicating activation logic in every test.
 */
export async function activateExtension(): Promise<vscode.Extension<any>> {
  const ext = vscode.extensions.getExtension('pb.dolphin');
  assert.ok(ext, 'Extension should be installed');

  if (!ext.isActive) {
    await ext.activate();
  }

  // Wait for extension to be fully ready
  await waitForExtensionReady(ext);

  return ext;
}

/**
 * Wait for extension to be fully initialized.
 */
async function waitForExtensionReady(ext: vscode.Extension<any>): Promise<void> {
  const maxWait = 5000; // 5 seconds max
  const checkInterval = 100; // Check every 100ms
  let elapsed = 0;

  while (elapsed < maxWait) {
    if (ext.exports?.isReady) {
      return;
    }
    await sleep(checkInterval);
    elapsed += checkInterval;
  }

  // If no isReady flag, just wait a bit for initialization
  await sleep(500);
}

/**
 * Command registration fixture.
 * Use this to verify commands are registered AND executable.
 */
export async function assertCommandExists(
  commandId: string,
  shouldExecute: boolean = true
): Promise<void> {
  const commands = await vscode.commands.getCommands(true);
  assert.ok(
    commands.includes(commandId),
    `Command ${commandId} should be registered`
  );

  if (shouldExecute) {
    // Actually try to execute the command
    try {
      await vscode.commands.executeCommand(commandId);
      // If we get here, command executed (may or may not have done anything)
    } catch (error) {
      assert.fail(
        `Command ${commandId} is registered but failed to execute: ${error}`
      );
    }
  }
}

/**
 * Batch command verification.
 * Use this to check multiple commands at once.
 */
export async function assertCommandsExist(
  commandIds: string[],
  shouldExecute: boolean = false
): Promise<void> {
  const commands = await vscode.commands.getCommands(true);

  for (const commandId of commandIds) {
    assert.ok(
      commands.includes(commandId),
      `Command ${commandId} should be registered`
    );
  }

  if (shouldExecute) {
    for (const commandId of commandIds) {
      try {
        await vscode.commands.executeCommand(commandId);
      } catch (error) {
        assert.fail(
          `Command ${commandId} failed to execute: ${error}`
        );
      }
    }
  }
}

/**
 * Configuration fixture.
 * Use this to verify configuration schema.
 */
export function assertConfigurationExists(keys: string[]): void {
  const config = vscode.workspace.getConfiguration('dolphin');

  for (const key of keys) {
    const info = config.inspect(key);
    assert.ok(
      info !== undefined,
      `Configuration key 'dolphin.${key}' should exist`
    );
  }
}

/**
 * Wait for a condition to be true with timeout.
 * Use this INSTEAD of sleep() for event-driven waiting.
 */
export async function waitForCondition(
  condition: () => boolean | Promise<boolean>,
  options: {
    timeout?: number;
    interval?: number;
    timeoutMessage?: string;
  } = {}
): Promise<void> {
  const timeout = options.timeout ?? 5000;
  const interval = options.interval ?? 100;
  const timeoutMessage = options.timeoutMessage ?? 'Condition not met within timeout';

  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    const result = await Promise.resolve(condition());
    if (result) {
      return;
    }
    await sleep(interval);
  }

  throw new Error(timeoutMessage);
}

/**
 * Sleep helper (use sparingly, prefer waitForCondition).
 */
export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Create a test document with specific content.
 */
export async function createTestDocument(
  content: string,
  language: string = 'typescript'
): Promise<vscode.TextDocument> {
  const doc = await vscode.workspace.openTextDocument({
    content,
    language
  });
  return doc;
}

/**
 * Get extension exports with type safety.
 */
export function getExtensionExports<T = any>(): T {
  const ext = vscode.extensions.getExtension('pb.dolphin');
  assert.ok(ext?.isActive, 'Extension should be active');
  return ext.exports as T;
}
```

**File:** `vscode-extension/src/test/helpers/test-constants.ts`

```typescript
/**
 * Shared test constants to ensure consistency.
 */

export const TEST_COMMANDS = {
  // Phase 1 commands
  FOCUS_INPUT: 'dolphin.focusInput',
  NEW_CONVERSATION: 'dolphin.newConversation',
  SET_API_KEY: 'dolphin.setApiKey',
  TEST: 'dolphin.test',

  // Phase 2 commands
  ASK_ABOUT_SELECTION: 'dolphin.askAboutSelection',
  REFACTOR_SELECTION: 'dolphin.refactorSelection',
  ASK_ABOUT_FILE: 'dolphin.askAboutFile',
  ASK_ABOUT_FOLDER: 'dolphin.askAboutFolder',
  APPLY_DIFF: 'dolphin.applyDiff',

  // KB commands
  KB_SHOW_STATUS: 'dolphin.kb.showStatus',
  KB_RESTART: 'dolphin.kb.restart',
} as const;

export const TEST_CONFIG_KEYS = [
  'kb.debounceMs',
  'kb.batchIntervalMs',
  'kb.excludePatterns',
  'kb.autoSync.enabled',
  'kb.autoSync.mode',
  'kb.autoSync.idleTimeMs',
  'kb.autoSync.maxBatchSize',
  'kb.autoSync.checkIntervalMs',
  'model',
  'maxTokens',
  'temperature',
  'useTools',
  'enableTelemetry',
  'logLevel',
] as const;

export const TEST_TIMEOUTS = {
  EXTENSION_ACTIVATION: 5000,
  COMMAND_EXECUTION: 2000,
  KB_STARTUP: 10000,
  AGENT_RESPONSE: 15000,
} as const;
```

##### Step 1.2: Consolidate Activation Tests (Day 1)

**File:** `vscode-extension/src/test/suite/extension-activation.test.ts` (NEW)

```typescript
/**
 * Consolidated extension activation tests.
 * This replaces duplicated activation tests in 5 different files.
 */

import * as assert from 'assert';
import * as vscode from 'vscode';
import { activateExtension } from '../helpers/shared-fixtures';

suite('Extension Activation', function() {
  this.timeout(10000);

  test('Extension should be present', () => {
    const ext = vscode.extensions.getExtension('pb.dolphin');
    assert.ok(ext, 'Extension should be installed');
  });

  test('Extension should activate successfully', async () => {
    const ext = await activateExtension();
    assert.ok(ext.isActive, 'Extension should be active');
  });

  test('Extension should provide expected exports', async () => {
    const ext = await activateExtension();
    const exports = ext.exports;

    assert.ok(exports, 'Extension should export an API');
    // Add assertions for specific exports you expect
    assert.ok(typeof exports.getWebviewProvider === 'function', 'Should export webview provider getter');
  });

  test('Extension should activate on workspace open (not on startup)', async () => {
    const ext = vscode.extensions.getExtension('pb.dolphin');
    assert.ok(ext, 'Extension should be installed');

    // Extension should use "*" activation event (activate on any command)
    // NOT "onStartupFinished" (which is too eager)
    const packageJSON = ext?.packageJSON;
    assert.ok(packageJSON.activationEvents, 'Should have activation events');

    // Should activate on demand, not on startup
    const hasOnStartup = packageJSON.activationEvents.includes('onStartupFinished');
    assert.strictEqual(hasOnStartup, false, 'Should not activate on startup for performance');
  });
});
```

##### Step 1.3: Consolidate Command Tests (Day 2)

**File:** `vscode-extension/src/test/suite/commands-registry.test.ts` (NEW)

```typescript
/**
 * Consolidated command registration tests.
 * This replaces duplicated command tests in 4 different files.
 */

import { TEST_COMMANDS } from '../helpers/test-constants';
import { assertCommandsExist, activateExtension } from '../helpers/shared-fixtures';

suite('Command Registration', function() {
  this.timeout(10000);

  suiteSetup(async () => {
    await activateExtension();
  });

  test('All Phase 1 commands should be registered', async () => {
    const phase1Commands = [
      TEST_COMMANDS.FOCUS_INPUT,
      TEST_COMMANDS.NEW_CONVERSATION,
      TEST_COMMANDS.SET_API_KEY,
      TEST_COMMANDS.TEST,
    ];

    await assertCommandsExist(phase1Commands);
  });

  test('All Phase 2 commands should be registered', async () => {
    const phase2Commands = [
      TEST_COMMANDS.ASK_ABOUT_SELECTION,
      TEST_COMMANDS.REFACTOR_SELECTION,
      TEST_COMMANDS.ASK_ABOUT_FILE,
      TEST_COMMANDS.ASK_ABOUT_FOLDER,
      TEST_COMMANDS.APPLY_DIFF,
    ];

    await assertCommandsExist(phase2Commands);
  });

  test('All KB commands should be registered', async () => {
    const kbCommands = [
      TEST_COMMANDS.KB_SHOW_STATUS,
      TEST_COMMANDS.KB_RESTART,
    ];

    await assertCommandsExist(kbCommands);
  });
});
```

##### Step 1.4: Delete Duplicated Test Code (Day 3)

**Action Items:**

1. **Remove activation tests from:**
   - `phase1-integration.test.ts` (lines 13-25)
   - `phase2-integration.test.ts` (implicit, checked in setup)
   - `integration.test.ts` (lines 59-65)
   - `conversations-e2e.test.ts` (lines 22-24)
   - `kb-lifecycle.test.ts` (lines 13-24)

2. **Remove command registration tests from:**
   - `phase1-integration.test.ts` (lines 81-111)
   - `phase2-integration.test.ts` (lines 23-70)
   - `conversations-e2e.test.ts` (lines 38-76)
   - `extension.test.ts` (entire file can be replaced)

3. **Update remaining test files to import shared fixtures:**

```typescript
// In all test files
import {
  activateExtension,
  assertCommandExists,
  waitForCondition
} from '../helpers/shared-fixtures';
import { TEST_COMMANDS, TEST_TIMEOUTS } from '../helpers/test-constants';
```

**Success Metrics:**
- ✅ Reduce test code from ~1,463 lines to ~900 lines (38% reduction)
- ✅ All tests pass after refactoring
- ✅ No duplicate activation logic
- ✅ No duplicate command registration logic

---

### IA-2: Use Existing Mock Infrastructure (Priority: 🔴 CRITICAL)

**Timeline:** Week 1, Days 4-5
**Effort:** 2 days
**Impact:** Eliminate environment dependencies, increase test reliability

#### Problem Statement

- `MockKBServer` exists but only used in 1 of 5 test files
- `MockAgentBridge` exists but **NEVER USED AT ALL**
- Tests rely on real dependencies or skip when unavailable
- Tests can't verify actual behavior without mocks

#### Implementation Plan

##### Step 2.1: Create Mock Management System (Day 4)

**File:** `vscode-extension/src/test/helpers/mock-manager.ts` (NEW)

```typescript
/**
 * Centralized mock management for all tests.
 * Ensures consistent mock usage across test suite.
 */

import { MockKBServer } from './mock-services';
import { MockAgentBridge } from './mock-services';

export interface MockEnvironment {
  kbServer: MockKBServer;
  agentBridge: MockAgentBridge;
}

/**
 * Global mock environment (singleton per test run).
 */
let mockEnvironment: MockEnvironment | null = null;

/**
 * Initialize mock environment for tests.
 * Call this in suiteSetup.
 */
export async function setupMockEnvironment(): Promise<MockEnvironment> {
  if (mockEnvironment) {
    return mockEnvironment;
  }

  // Start mock KB server on port 7778
  const kbServer = new MockKBServer(7778);
  await kbServer.start();

  // Create mock agent bridge
  const agentBridge = new MockAgentBridge();

  mockEnvironment = { kbServer, agentBridge };
  return mockEnvironment;
}

/**
 * Get the current mock environment.
 * Throws if not initialized.
 */
export function getMockEnvironment(): MockEnvironment {
  if (!mockEnvironment) {
    throw new Error('Mock environment not initialized. Call setupMockEnvironment() first.');
  }
  return mockEnvironment;
}

/**
 * Cleanup mock environment.
 * Call this in suiteTeardown.
 */
export async function teardownMockEnvironment(): Promise<void> {
  if (mockEnvironment) {
    await mockEnvironment.kbServer.stop();
    mockEnvironment = null;
  }
}

/**
 * Reset mocks between tests (not full teardown).
 * Call this in setup() or teardown().
 */
export function resetMocks(): void {
  if (mockEnvironment) {
    mockEnvironment.kbServer.reset();
    mockEnvironment.agentBridge.reset();
  }
}

/**
 * Configure mock KB server responses.
 */
export function configureMockKB(config: {
  searchResults?: any[];
  metadata?: any;
  health?: boolean;
}): void {
  const env = getMockEnvironment();

  if (config.searchResults !== undefined) {
    env.kbServer.setSearchResults(config.searchResults);
  }

  if (config.metadata !== undefined) {
    env.kbServer.setMetadata(config.metadata);
  }

  if (config.health !== undefined) {
    env.kbServer.setHealthy(config.health);
  }
}

/**
 * Configure mock agent bridge responses.
 */
export function configureMockAgent(config: {
  response?: string;
  toolCalls?: any[];
  shouldError?: boolean;
}): void {
  const env = getMockEnvironment();

  if (config.response !== undefined) {
    env.agentBridge.setResponse(config.response);
  }

  if (config.toolCalls !== undefined) {
    env.agentBridge.setToolCalls(config.toolCalls);
  }

  if (config.shouldError) {
    env.agentBridge.setError(new Error('Mock agent error'));
  }
}
```

##### Step 2.2: Enhance MockAgentBridge (Day 4)

**File:** `vscode-extension/src/test/helpers/mock-services.ts` (UPDATE)

Add methods to MockAgentBridge to make it actually usable:

```typescript
/**
 * Enhanced MockAgentBridge with full feature support.
 */
export class MockAgentBridge {
  private messageHandlers: Map<string, Function> = new Map();
  private eventHandlers: Map<string, Function[]> = new Map();
  private messageHistory: any[] = [];
  private responseQueue: string[] = [];
  private toolCallQueue: any[] = [];
  private shouldError: Error | null = null;

  /**
   * Send a message (simulates user sending message to agent).
   */
  async sendMessage(message: string): Promise<void> {
    this.messageHistory.push({ type: 'user_message', content: message });

    // Simulate processing delay
    await new Promise(resolve => setTimeout(resolve, 50));

    if (this.shouldError) {
      this.emit('error', this.shouldError);
      throw this.shouldError;
    }

    // Emit tool calls if configured
    for (const toolCall of this.toolCallQueue) {
      this.emit('tool_call_started', toolCall);
      await new Promise(resolve => setTimeout(resolve, 20));
      this.emit('tool_call_completed', { ...toolCall, result: 'mock result' });
    }

    // Emit response
    const response = this.responseQueue.shift() || 'Mock agent response';
    this.emit('message_chunk', { content: response });

    await new Promise(resolve => setTimeout(resolve, 20));
    this.emit('task_completed', { message: response });
  }

  /**
   * Register event listener.
   */
  on(event: string, handler: Function): void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, []);
    }
    this.eventHandlers.get(event)!.push(handler);
  }

  /**
   * Emit event to listeners.
   */
  private emit(event: string, data: any): void {
    const handlers = this.eventHandlers.get(event) || [];
    for (const handler of handlers) {
      handler(data);
    }
  }

  /**
   * Get message history.
   */
  getMessageHistory(): any[] {
    return [...this.messageHistory];
  }

  /**
   * Get event history.
   */
  getEventHistory(): any[] {
    return this.messageHistory;
  }

  /**
   * Set next response.
   */
  setResponse(response: string): void {
    this.responseQueue.push(response);
  }

  /**
   * Set tool calls to emit.
   */
  setToolCalls(toolCalls: any[]): void {
    this.toolCallQueue = toolCalls;
  }

  /**
   * Set error to throw.
   */
  setError(error: Error): void {
    this.shouldError = error;
  }

  /**
   * Reset all state.
   */
  reset(): void {
    this.messageHistory = [];
    this.responseQueue = [];
    this.toolCallQueue = [];
    this.shouldError = null;
    this.eventHandlers.clear();
  }

  /**
   * Get KB status (mock).
   */
  async getKBStatus(): Promise<any> {
    return {
      running: true,
      port: 7778,
      totalChunks: 1000,
      repositories: ['test-repo'],
    };
  }
}
```

##### Step 2.3: Update All Tests to Use Mocks (Day 5)

**Update:** `phase1-integration.test.ts`

```typescript
import { setupMockEnvironment, teardownMockEnvironment, resetMocks } from '../helpers/mock-manager';

suite('Phase 1 Integration Tests', function() {
  this.timeout(10000);

  suiteSetup(async () => {
    await setupMockEnvironment();
  });

  suiteTeardown(async () => {
    await teardownMockEnvironment();
  });

  setup(() => {
    resetMocks();
  });

  // Tests now use mocks...
});
```

**Update:** `phase2-integration.test.ts`, `conversations-e2e.test.ts`, `kb-lifecycle.test.ts`

Same pattern as above.

**Success Metrics:**
- ✅ All 5 test files use MockKBServer
- ✅ MockAgentBridge used in conversation tests
- ✅ Zero skipped tests due to missing dependencies
- ✅ Tests run in any environment (no KB server required)

---

### IA-3: Replace Sleep with Event Waiting (Priority: 🔴 CRITICAL)

**Timeline:** Week 1, Day 5 + Week 2, Day 1
**Effort:** 1.5 days
**Impact:** 75% reduction in test execution time

#### Problem Statement

Tests contain 50+ sleep() calls totaling 50+ seconds:
- `kb-lifecycle.test.ts`: 5000ms sleep waiting for KB
- `conversations-e2e.test.ts`: 30+ sleep calls
- `phase2-integration.test.ts`: 15+ sleep calls

#### Implementation Plan

##### Step 3.1: Create Event-Driven Waiting Helpers (Completed in Step 1.1)

Already created `waitForCondition()` in shared-fixtures.ts.

##### Step 3.2: Replace Sleep Calls (Day 5 + Day 1)

**Pattern to find:** `await.*sleep\(`
**Pattern to replace with:** `await waitForCondition(...)`

**Example transformations:**

**Before:**
```typescript
// Wait for KB to start
await sleep(5000);
const status = await getKBStatus();
```

**After:**
```typescript
// Wait for KB to be ready
await waitForCondition(
  async () => {
    const status = await getKBStatus();
    return status.running === true;
  },
  { timeout: 10000, timeoutMessage: 'KB failed to start' }
);
```

**Before:**
```typescript
// Wait for command to complete
await vscode.commands.executeCommand('dolphin.test');
await sleep(1000);
// Now check result
```

**After:**
```typescript
// Wait for command to complete
let commandCompleted = false;
const disposable = someEvent.on('completed', () => {
  commandCompleted = true;
});

await vscode.commands.executeCommand('dolphin.test');
await waitForCondition(
  () => commandCompleted,
  { timeout: 2000, timeoutMessage: 'Command did not complete' }
);

disposable.dispose();
```

**Files to update:**
1. `kb-lifecycle.test.ts` - Replace all sleep calls (6 total)
2. `conversations-e2e.test.ts` - Replace all sleep calls (30+ total)
3. `phase2-integration.test.ts` - Replace all sleep calls (15+ total)
4. `phase1-integration.test.ts` - Replace all sleep calls (5 total)
5. `integration.test.ts` - Replace all sleep calls (2 total)

**Success Metrics:**
- ✅ Zero arbitrary sleep() calls in tests (may keep very short ones <50ms for UI updates)
- ✅ All waits are event-driven or condition-based
- ✅ Test execution time reduced from ~60s to ~15s (75% improvement)

---

### IA-4: Add Real Assertions (Priority: 🔴 CRITICAL)

**Timeline:** Week 2, Days 2-3
**Effort:** 2 days
**Impact:** Eliminate all false positives

#### Problem Statement

Tests accept failures as success:
```typescript
try {
  await vscode.commands.executeCommand('dolphin.focusInput');
  assert.ok(true, 'Command executed');
} catch (err) {
  // Still passes! This is wrong.
  assert.ok(commands.includes('dolphin.focusInput'));
}
```

Tests don't verify behavior:
- Commands execute but results not checked
- Conversations created but files not verified
- KB searches run but results not validated

#### Implementation Plan

##### Step 4.1: Remove Try-Catch Anti-Pattern (Day 2)

**Pattern to find:**
```typescript
try {
  await vscode.commands.executeCommand(...);
  assert.ok(true, ...);
} catch (err) {
  const commands = await vscode.commands.getCommands(true);
  assert.ok(commands.includes(...));
}
```

**Replace with:**
```typescript
// Command should execute successfully
await vscode.commands.executeCommand(...);
// If it throws, test fails (as it should)
```

**Files to update:**
- `phase1-integration.test.ts` (5 occurrences)
- `phase2-integration.test.ts` (8 occurrences)
- `conversations-e2e.test.ts` (6 occurrences)

##### Step 4.2: Add Behavior Verification (Days 2-3)

**Example: Verify conversation persistence**

**Before:**
```typescript
test('Should create new conversation', async () => {
  await vscode.commands.executeCommand('dolphin.newConversation');
  // That's it. No verification!
});
```

**After:**
```typescript
test('Should create new conversation and persist to disk', async () => {
  const stateBefore = await getConversationState();
  const conversationCountBefore = stateBefore.conversations.length;

  await vscode.commands.executeCommand('dolphin.newConversation');

  // Wait for conversation to be created
  await waitForCondition(
    async () => {
      const state = await getConversationState();
      return state.conversations.length > conversationCountBefore;
    },
    { timeout: 2000, timeoutMessage: 'New conversation not created' }
  );

  const stateAfter = await getConversationState();
  const newConversation = stateAfter.conversations[stateAfter.conversations.length - 1];

  // Verify conversation properties
  assert.ok(newConversation.id, 'Conversation should have ID');
  assert.strictEqual(newConversation.messages.length, 0, 'New conversation should have no messages');

  // Verify conversation file exists on disk
  const conversationFile = path.join(
    getExtensionStoragePath(),
    'state',
    'conversations',
    `${newConversation.id}.json`
  );
  const fileExists = await fs.access(conversationFile).then(() => true).catch(() => false);
  assert.ok(fileExists, 'Conversation file should exist on disk');

  // Verify file content matches state
  const fileContent = await fs.readFile(conversationFile, 'utf8');
  const savedConversation = JSON.parse(fileContent);
  assert.deepStrictEqual(savedConversation, newConversation, 'Saved conversation should match state');
});
```

**Example: Verify KB search**

**Before:**
```typescript
test('Should execute KB search', async () => {
  await vscode.commands.executeCommand('dolphin.kb.showStatus');
  // No verification
});
```

**After:**
```typescript
test('Should execute KB search and display results', async () => {
  const { agentBridge } = getMockEnvironment();

  // Configure mock to return search results
  configureMockAgent({
    toolCalls: [{
      name: 'search_knowledge',
      input: { query: 'test' },
    }],
    response: 'Found 5 relevant results about authentication.'
  });

  // Send message that will trigger search
  await agentBridge.sendMessage('How does authentication work?');

  // Verify search was called
  const history = agentBridge.getEventHistory();
  const searchCall = history.find(e =>
    e.type === 'tool_call_started' && e.name === 'search_knowledge'
  );
  assert.ok(searchCall, 'KB search should have been called');

  // Verify response includes search results
  const responseEvent = history.find(e => e.type === 'message_chunk');
  assert.ok(responseEvent, 'Should have received response');
  assert.ok(
    responseEvent.content.includes('authentication'),
    'Response should mention authentication'
  );
});
```

**Files to update:**
- `conversations-e2e.test.ts` - Add file verification for all conversation tests
- `kb-lifecycle.test.ts` - Add actual KB status verification
- `phase2-integration.test.ts` - Add document/selection verification
- `integration.test.ts` - Enhance with actual workflow verification

**Success Metrics:**
- ✅ Zero tests that pass when they should fail
- ✅ All command tests verify actual results
- ✅ All conversation tests verify file persistence
- ✅ All KB tests verify actual status/search

---

### IA-5: Fix Skipped Tests (Priority: 🟠 HIGH)

**Timeline:** Week 2, Day 4
**Effort:** 1 day
**Impact:** Increase effective test coverage

#### Problem Statement

`kb-lifecycle.test.ts` has 6 tests that use `this.skip()` or skip conditionally.

#### Implementation Plan

##### Step 5.1: Analyze Skipped Tests (Day 4)

Review each skipped test and determine:
1. Why is it skipped?
2. Can it be fixed with mocks?
3. Should it be deleted if obsolete?

##### Step 5.2: Fix or Remove (Day 4)

**Pattern 1: Skipped due to missing exports**

```typescript
test('Should access KB manager', function() {
  const ext = vscode.extensions.getExtension('pb.dolphin');
  if (!ext?.exports?.kbManager) {
    this.skip();
  }
  // Test code...
});
```

**Fix: Use mocks instead of relying on exports**

```typescript
test('Should access KB manager', async function() {
  const { kbServer } = getMockEnvironment();

  // Verify KB is accessible
  const status = await kbServer.getStatus();
  assert.ok(status.running, 'KB should be running');
});
```

**Pattern 2: Skipped due to environment**

```typescript
test('Should start KB on port 8000', function() {
  if (process.env.CI) {
    this.skip(); // Can't start real KB in CI
  }
  // Test code...
});
```

**Fix: Use mocks for all environments**

```typescript
test('Should start KB on configured port', async function() {
  const { kbServer } = getMockEnvironment();

  const status = await kbServer.getStatus();
  assert.strictEqual(status.port, 7778, 'KB should run on test port');
});
```

**Pattern 3: Obsolete test**

If test is testing something no longer relevant, DELETE it entirely.

**Success Metrics:**
- ✅ Zero skipped tests in test suite
- ✅ All tests run in all environments (local, CI, headless)

---

## Long-term Improvements

### LTI-1: Separate Test Types (Priority: 🟠 HIGH)

**Timeline:** Week 3, Days 1-3
**Effort:** 3 days
**Impact:** Clear test organization, faster CI

#### Problem Statement

Current structure mixes unit, integration, and e2e tests in same directory.

#### Implementation Plan

##### Step 1.1: Create New Directory Structure (Day 1)

```bash
vscode-extension/src/test/
├── unit/                          # Fast, isolated, fully mocked
│   ├── logger.test.ts             # (existing)
│   ├── configuration.test.ts      # (existing)
│   ├── diff-handler.test.ts       # (existing)
│   ├── code-actions.test.ts       # (existing)
│   ├── drift-detector.test.ts     # (existing)
│   ├── auto-sync-manager.test.ts  # (existing)
│   └── file-watcher-sync.test.ts  # (existing)
│
├── integration/                   # Extension + mocked dependencies
│   ├── extension-activation.test.ts    # (new - consolidated)
│   ├── commands-registry.test.ts       # (new - consolidated)
│   ├── webview-provider.test.ts        # (from webview.test.ts)
│   ├── agent-bridge.test.ts            # (existing)
│   ├── conversation-workflow.test.ts   # (new - from conversations-e2e)
│   └── kb-integration.test.ts          # (new - from kb-lifecycle)
│
├── e2e/                           # Full workflows (future)
│   └── user-workflow.test.ts      # (new)
│
└── helpers/                       # Shared test utilities
    ├── shared-fixtures.ts         # (new)
    ├── test-constants.ts          # (new)
    ├── mock-manager.ts            # (new)
    ├── mock-services.ts           # (existing, enhanced)
    └── test-utils.ts              # (existing)
```

##### Step 1.2: Update Test Configuration (Day 1)

**File:** `.vscode-test.mjs` (UPDATE)

```javascript
import { defineConfig } from '@vscode/test-cli';

export default defineConfig([
  // Unit tests - fast, no VS Code needed (future: could run with pure Node)
  {
    label: 'unit',
    files: 'out/test/unit/**/*.test.js',
    version: 'stable',
    workspaceFolder: './test-workspace',
    mocha: {
      ui: 'bdd',
      timeout: 5000, // Unit tests should be fast
      globals: ['suite', 'test', 'suiteSetup', 'suiteTeardown', 'setup', 'teardown'],
    },
  },

  // Integration tests - needs VS Code API, uses mocks
  {
    label: 'integration',
    files: 'out/test/integration/**/*.test.js',
    version: 'stable',
    workspaceFolder: './test-workspace',
    mocha: {
      ui: 'bdd',
      timeout: 10000, // Integration tests slightly slower
      globals: ['suite', 'test', 'suiteSetup', 'suiteTeardown', 'setup', 'teardown'],
    },
  },

  // E2E tests - full workflows (future)
  {
    label: 'e2e',
    files: 'out/test/e2e/**/*.test.js',
    version: 'stable',
    workspaceFolder: './test-workspace',
    mocha: {
      ui: 'bdd',
      timeout: 30000, // E2E tests can be slower
      globals: ['suite', 'test', 'suiteSetup', 'suiteTeardown', 'setup', 'teardown'],
    },
  },
]);
```

##### Step 1.3: Update Package.json Scripts (Day 2)

**File:** `package.json` (UPDATE)

```json
{
  "scripts": {
    "test": "npm run test:unit && npm run test:integration",
    "test:unit": "vscode-test --label unit",
    "test:integration": "vscode-test --label integration",
    "test:e2e": "vscode-test --label e2e",
    "test:all": "vscode-test",
    "test:watch": "vscode-test --label unit --watch",
    "test:coverage": "c8 --reporter=html --reporter=text npm run test:all"
  }
}
```

##### Step 1.4: Update justfile (Day 2)

**File:** `justfile` (UPDATE)

```bash
# Run VSCode Extension unit tests only (fast)
test-unit-extension:
	@echo "📦 Testing VSCode Extension unit tests..."
	@cd vscode-extension && npm run test:unit || (echo "   ❌ Extension unit tests failed"; exit 1)
	@echo "   ✅ Extension unit tests passed"

# Run VSCode Extension integration tests
test-integration-extension:
	@echo "📦 Testing VSCode Extension integration tests..."
	@cd vscode-extension && npm run test:integration || (echo "   ❌ Extension integration tests failed"; exit 1)
	@echo "   ✅ Extension integration tests passed"

# Run VSCode Extension e2e tests
test-e2e-extension:
	@echo "📦 Testing VSCode Extension E2E tests..."
	@cd vscode-extension && npm run test:e2e || (echo "   ❌ Extension E2E tests failed"; exit 1)
	@echo "   ✅ Extension E2E tests passed"

# Run ALL VSCode Extension tests
test-extension-all:
	@echo "📦 Testing VSCode Extension (all tests)..."
	@cd vscode-extension && npm run test:all || (echo "   ❌ Extension tests failed"; exit 1)
	@echo "   ✅ Extension tests passed"
```

##### Step 1.5: Migrate Existing Tests (Day 3)

Move tests to appropriate directories:

**Unit tests** (already in right place):
- logger.test.ts
- configuration.test.ts
- diff-handler.test.ts
- code-actions.test.ts
- drift-detector.test.ts
- auto-sync-manager.test.ts
- file-watcher-sync.test.ts

**Integration tests** (move/refactor):
- extension-activation.test.ts (new, consolidated)
- commands-registry.test.ts (new, consolidated)
- webview-provider.test.ts (from webview.test.ts)
- agent-bridge.test.ts (existing)
- provider.test.ts (existing)
- commands.test.ts (existing)
- conversation-workflow.test.ts (from conversations-e2e, refactored)
- kb-integration.test.ts (from kb-lifecycle, refactored)

**E2E tests** (create new):
- user-workflow.test.ts (new)

**Delete obsolete files:**
- phase1-integration.test.ts (replaced by extension-activation + commands-registry)
- phase2-integration.test.ts (replaced by commands-registry + integration tests)
- integration.test.ts (content moved to kb-integration)
- conversations-e2e.test.ts (replaced by conversation-workflow)
- kb-lifecycle.test.ts (replaced by kb-integration)
- extension.test.ts (replaced by extension-activation)

**Success Metrics:**
- ✅ Clear separation of unit/integration/e2e tests
- ✅ Can run test types independently
- ✅ Unit tests run in <3s
- ✅ Integration tests run in <12s
- ✅ Total test time <15s

---

### LTI-2: Real E2E Tests with Playwright (Priority: 🟢 MEDIUM)

**Timeline:** Week 3, Days 4-5
**Effort:** 2 days
**Impact:** True end-to-end validation

#### Problem Statement

Current "e2e tests" run in headless VS Code - can't test real UI interactions.

#### Implementation Plan

##### Step 2.1: Install Playwright for VS Code (Day 4)

```bash
cd vscode-extension
npm install --save-dev @playwright/test
npx playwright install
```

**File:** `playwright.config.ts` (NEW)

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './src/test/e2e',
  fullyParallel: false, // E2E tests run sequentially
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // One worker for E2E
  reporter: 'html',
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'vscode-extension',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: 'code --extensionDevelopmentPath=. test-workspace',
    port: 9229, // VS Code debug port
    reuseExistingServer: !process.env.CI,
  },
});
```

##### Step 2.2: Create E2E Test (Day 4-5)

**File:** `src/test/e2e/user-workflow.test.ts` (NEW)

```typescript
/**
 * True end-to-end test using Playwright.
 * Tests the actual VS Code UI and user interactions.
 */

import { test, expect } from '@playwright/test';

test.describe('Complete User Workflow', () => {
  test('User can send message and receive response', async ({ page }) => {
    // Step 1: Open VS Code with extension
    // (Handled by webServer in playwright.config.ts)

    // Step 2: Wait for extension to load
    await page.waitForSelector('[aria-label="Dolphin"]', { timeout: 10000 });

    // Step 3: Click on Dolphin sidebar icon
    await page.click('[aria-label="Dolphin"]');

    // Step 4: Wait for webview to load
    await page.waitForSelector('iframe.webview', { timeout: 5000 });

    // Step 5: Switch to webview frame
    const webviewFrame = page.frameLocator('iframe.webview');

    // Step 6: Type message in input
    const input = webviewFrame.locator('input[placeholder*="message"]');
    await input.fill('What is this project about?');

    // Step 7: Send message
    const sendButton = webviewFrame.locator('button:has-text("Send")');
    await sendButton.click();

    // Step 8: Wait for response
    const responseMessage = webviewFrame.locator('.message.assistant').first();
    await expect(responseMessage).toBeVisible({ timeout: 15000 });

    // Step 9: Verify response contains content
    const responseText = await responseMessage.textContent();
    expect(responseText).toBeTruthy();
    expect(responseText!.length).toBeGreaterThan(10);
  });

  test('User can create new conversation', async ({ page }) => {
    await page.waitForSelector('[aria-label="Dolphin"]');
    await page.click('[aria-label="Dolphin"]');

    const webviewFrame = page.frameLocator('iframe.webview');

    // Click new conversation button
    const newConvButton = webviewFrame.locator('button[aria-label="New Conversation"]');
    await newConvButton.click();

    // Verify conversation list updated
    const conversations = webviewFrame.locator('.conversation-item');
    const count = await conversations.count();
    expect(count).toBeGreaterThan(0);
  });

  test('User can search knowledge base from context menu', async ({ page }) => {
    await page.waitForSelector('[aria-label="Dolphin"]');

    // Step 1: Open a file in editor
    await page.keyboard.press('Control+P'); // Quick open
    await page.keyboard.type('package.json');
    await page.keyboard.press('Enter');

    // Step 2: Select some text
    await page.keyboard.press('Control+A'); // Select all

    // Step 3: Right-click to open context menu
    await page.click('.monaco-editor', { button: 'right' });

    // Step 4: Click "Dolphin: Ask About Selection"
    await page.click('text="Dolphin: Ask About Selection"');

    // Step 5: Verify Dolphin panel opens
    const webviewFrame = page.frameLocator('iframe.webview');
    const input = webviewFrame.locator('input[placeholder*="message"]');
    await expect(input).toBeVisible({ timeout: 5000 });

    // Step 6: Verify message was pre-filled with selection context
    const inputValue = await input.inputValue();
    expect(inputValue).toContain('package.json');
  });
});
```

##### Step 2.3: Update Package.json (Day 5)

```json
{
  "scripts": {
    "test:e2e:playwright": "playwright test",
    "test:e2e:playwright:ui": "playwright test --ui",
    "test:e2e:playwright:debug": "playwright test --debug"
  }
}
```

**Success Metrics:**
- ✅ Playwright tests run successfully
- ✅ Tests interact with real VS Code UI
- ✅ Tests verify actual user workflows
- ✅ Screenshots captured on failure

---

### LTI-3: Performance Benchmarking (Priority: 🟢 MEDIUM)

**Timeline:** Week 4, Days 1-2
**Effort:** 2 days
**Impact:** Prevent performance regressions

#### Implementation Plan

##### Step 3.1: Create Performance Test Suite (Day 1)

**File:** `src/test/performance/extension-perf.test.ts` (NEW)

```typescript
/**
 * Performance benchmarks for extension operations.
 */

import * as assert from 'assert';
import { performance } from 'perf_hooks';
import { setupMockEnvironment, teardownMockEnvironment } from '../helpers/mock-manager';
import { activateExtension } from '../helpers/shared-fixtures';

suite('Extension Performance Benchmarks', function() {
  this.timeout(30000);

  suiteSetup(async () => {
    await setupMockEnvironment();
    await activateExtension();
  });

  suiteTeardown(async () => {
    await teardownMockEnvironment();
  });

  test('Extension activation should complete in <2s', async () => {
    // Measure activation time
    const start = performance.now();
    await activateExtension();
    const end = performance.now();

    const activationTime = end - start;
    console.log(`Extension activation time: ${activationTime.toFixed(2)}ms`);

    assert.ok(activationTime < 2000, `Activation took ${activationTime}ms, should be <2000ms`);
  });

  test('KB search should return results in <500ms', async () => {
    const { agentBridge } = getMockEnvironment();

    const start = performance.now();
    await agentBridge.sendMessage('search test query');
    const end = performance.now();

    const searchTime = end - start;
    console.log(`KB search time: ${searchTime.toFixed(2)}ms`);

    assert.ok(searchTime < 500, `Search took ${searchTime}ms, should be <500ms`);
  });

  test('Conversation save should complete in <100ms', async () => {
    const times: number[] = [];

    // Run 10 times to get average
    for (let i = 0; i < 10; i++) {
      const start = performance.now();
      await saveConversation({ id: `test-${i}`, messages: [] });
      const end = performance.now();
      times.push(end - start);
    }

    const avgTime = times.reduce((a, b) => a + b, 0) / times.length;
    console.log(`Average conversation save time: ${avgTime.toFixed(2)}ms`);

    assert.ok(avgTime < 100, `Save took ${avgTime}ms average, should be <100ms`);
  });

  test('Memory usage should not increase with repeated operations', async () => {
    const initialMemory = process.memoryUsage().heapUsed;

    // Perform 100 operations
    for (let i = 0; i < 100; i++) {
      await vscode.commands.executeCommand('dolphin.newConversation');
    }

    // Force garbage collection if available
    if (global.gc) {
      global.gc();
    }

    const finalMemory = process.memoryUsage().heapUsed;
    const memoryIncrease = finalMemory - initialMemory;
    const memoryIncreaseMB = memoryIncrease / 1024 / 1024;

    console.log(`Memory increase: ${memoryIncreaseMB.toFixed(2)}MB`);

    // Should not leak more than 10MB
    assert.ok(memoryIncreaseMB < 10, `Memory increased by ${memoryIncreaseMB}MB, should be <10MB`);
  });
});
```

##### Step 3.2: Create Performance Tracking (Day 2)

**File:** `scripts/track-performance.js` (NEW)

```javascript
/**
 * Track performance metrics over time.
 */

const fs = require('fs');
const path = require('path');

const METRICS_FILE = path.join(__dirname, '../.test-metrics.json');

function loadMetrics() {
  if (!fs.existsSync(METRICS_FILE)) {
    return { runs: [] };
  }
  return JSON.parse(fs.readFileSync(METRICS_FILE, 'utf8'));
}

function saveMetrics(metrics) {
  fs.writeFileSync(METRICS_FILE, JSON.stringify(metrics, null, 2));
}

function recordTestRun(results) {
  const metrics = loadMetrics();

  metrics.runs.push({
    timestamp: new Date().toISOString(),
    commit: process.env.GIT_COMMIT || 'unknown',
    totalTime: results.totalTime,
    testCount: results.testCount,
    passRate: results.passRate,
    activationTime: results.activationTime,
    searchTime: results.searchTime,
  });

  // Keep last 100 runs
  if (metrics.runs.length > 100) {
    metrics.runs = metrics.runs.slice(-100);
  }

  saveMetrics(metrics);
}

function checkForRegressions() {
  const metrics = loadMetrics();

  if (metrics.runs.length < 2) {
    console.log('Not enough data for regression check');
    return;
  }

  const recent = metrics.runs.slice(-5); // Last 5 runs
  const baseline = metrics.runs.slice(-10, -5); // Previous 5 runs

  const recentAvg = recent.reduce((sum, r) => sum + r.totalTime, 0) / recent.length;
  const baselineAvg = baseline.reduce((sum, r) => sum + r.totalTime, 0) / baseline.length;

  const regressionPercent = ((recentAvg - baselineAvg) / baselineAvg) * 100;

  if (regressionPercent > 10) {
    console.error(`⚠️  Performance regression detected: ${regressionPercent.toFixed(1)}% slower`);
    process.exit(1);
  } else {
    console.log(`✅ Performance check passed (${regressionPercent.toFixed(1)}% change)`);
  }
}

module.exports = { recordTestRun, checkForRegressions };
```

**Success Metrics:**
- ✅ Performance benchmarks run in CI
- ✅ Regressions detected automatically
- ✅ Performance metrics tracked over time

---

### LTI-4: Coverage Reporting (Priority: 🟢 MEDIUM)

**Timeline:** Week 4, Days 3-4
**Effort:** 2 days
**Impact:** Visibility into test coverage

#### Implementation Plan

##### Step 4.1: Install Coverage Tools (Day 3)

```bash
npm install --save-dev c8 nyc
```

##### Step 4.2: Configure Coverage (Day 3)

**File:** `package.json` (UPDATE)

```json
{
  "scripts": {
    "test:coverage": "c8 --reporter=html --reporter=text --reporter=lcov npm run test:all",
    "test:coverage:unit": "c8 --reporter=text npm run test:unit",
    "test:coverage:integration": "c8 --reporter=text npm run test:integration"
  },
  "c8": {
    "include": [
      "src/**/*.ts"
    ],
    "exclude": [
      "src/test/**",
      "**/*.test.ts",
      "**/*.d.ts"
    ],
    "reporter": [
      "html",
      "text",
      "lcov"
    ],
    "check-coverage": true,
    "lines": 70,
    "functions": 70,
    "branches": 65,
    "statements": 70
  }
}
```

##### Step 4.3: Add Coverage Badge (Day 4)

**File:** `.github/workflows/test.yml` (UPDATE)

```yaml
name: Test Extension

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-node@v3
        with:
          node-version: 18

      - name: Install dependencies
        working-directory: vscode-extension
        run: npm ci

      - name: Run tests with coverage
        working-directory: vscode-extension
        run: npm run test:coverage

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./vscode-extension/coverage/lcov.info
          flags: vscode-extension

      - name: Check coverage thresholds
        working-directory: vscode-extension
        run: npx c8 check-coverage
```

**File:** `README.md` (UPDATE)

Add coverage badge:
```markdown
[![Coverage](https://codecov.io/gh/yourusername/dolphin/branch/main/graph/badge.svg?flag=vscode-extension)](https://codecov.io/gh/yourusername/dolphin)
```

**Success Metrics:**
- ✅ Coverage reports generated
- ✅ Coverage tracked in CI
- ✅ Coverage badge in README
- ✅ Coverage thresholds enforced

---

## Out-of-Scope Future Work

The following improvements are valuable but beyond the scope of this immediate refactoring:

### OOS-1: Visual Regression Testing

**Description:** Use Playwright to capture screenshots and detect UI changes.

**Why valuable:**
- Catch unintended visual changes
- Ensure UI consistency across updates
- Document visual state

**Implementation approach:**
```typescript
test('Webview visual regression', async ({ page }) => {
  await page.goto('http://localhost:3000/webview');
  await expect(page).toHaveScreenshot('webview-initial.png');
});
```

**Effort estimate:** 2-3 days

---

### OOS-2: Test Data Builders

**Description:** Create fluent builders for test data to reduce boilerplate.

**Why valuable:**
- Easier test creation
- Consistent test data
- Reduced duplication

**Implementation approach:**
```typescript
class ConversationBuilder {
  private conversation: Conversation = {
    id: uuidv4(),
    messages: [],
    createdAt: new Date(),
  };

  withMessage(role: 'user' | 'assistant', content: string): this {
    this.conversation.messages.push({ role, content });
    return this;
  }

  withId(id: string): this {
    this.conversation.id = id;
    return this;
  }

  build(): Conversation {
    return this.conversation;
  }
}

// Usage
const conversation = new ConversationBuilder()
  .withMessage('user', 'Hello')
  .withMessage('assistant', 'Hi there!')
  .build();
```

**Effort estimate:** 3-4 days

---

### OOS-3: Contract Testing

**Description:** Test contracts between extension and KB API to catch breaking changes.

**Why valuable:**
- Catch API contract violations early
- Enable independent development
- Document API expectations

**Implementation approach:**
```typescript
import { Pact } from '@pact-foundation/pact';

test('KB search contract', async () => {
  const provider = new Pact({
    consumer: 'VSCode Extension',
    provider: 'KB API',
  });

  await provider.addInteraction({
    state: 'repository is indexed',
    uponReceiving: 'a search request',
    withRequest: {
      method: 'POST',
      path: '/search',
      body: { query: 'test' },
    },
    willRespondWith: {
      status: 200,
      body: {
        results: Matchers.eachLike({
          content: Matchers.string(),
          score: Matchers.decimal(),
        }),
      },
    },
  });

  // Run test against mock
  const client = new KBClient('http://localhost:1234');
  const results = await client.search('test');

  await provider.verify();
});
```

**Effort estimate:** 4-5 days

---

### OOS-4: Mutation Testing

**Description:** Use mutation testing to verify test quality (tests catch intentional bugs).

**Why valuable:**
- Validate tests actually test behavior
- Find weak spots in test coverage
- Increase confidence in test suite

**Implementation approach:**
```bash
npm install --save-dev stryker-cli @stryker-mutator/typescript-checker

# Run mutation testing
npx stryker run
```

**Effort estimate:** 2-3 days

---

### OOS-5: Fuzz Testing

**Description:** Use fuzzing to find edge cases and crashes.

**Why valuable:**
- Find unexpected bugs
- Test error handling
- Increase robustness

**Implementation approach:**
```typescript
import { fc } from 'fast-check';

test('Parser handles arbitrary input', () => {
  fc.assert(
    fc.property(fc.string(), (input) => {
      // Should never crash
      expect(() => parser.parse(input)).not.toThrow();
    })
  );
});
```

**Effort estimate:** 3-4 days

---

### OOS-6: Multi-Version Testing

**Description:** Test extension against multiple VS Code versions.

**Why valuable:**
- Ensure compatibility
- Catch version-specific issues
- Support wider user base

**Implementation approach:**
```yaml
# .github/workflows/test.yml
strategy:
  matrix:
    vscode-version: ['1.85.0', '1.90.0', 'stable', 'insiders']

steps:
  - name: Test with VS Code ${{ matrix.vscode-version }}
    run: npm test -- --version ${{ matrix.vscode-version }}
```

**Effort estimate:** 1-2 days

---

### OOS-7: Load Testing

**Description:** Test extension performance under heavy load.

**Why valuable:**
- Find scalability limits
- Optimize for large projects
- Prevent performance issues

**Implementation approach:**
```typescript
test('Extension handles 1000 conversations', async () => {
  for (let i = 0; i < 1000; i++) {
    await createConversation(`conversation-${i}`);
  }

  const startTime = performance.now();
  const conversations = await loadAllConversations();
  const loadTime = performance.now() - startTime;

  expect(loadTime).toBeLessThan(1000); // Should load in <1s
  expect(conversations.length).toBe(1000);
});
```

**Effort estimate:** 2-3 days

---

## Implementation Timeline

### Week 1: Immediate Actions (Part 1)

**Monday:**
- ✅ Create shared-fixtures.ts
- ✅ Create test-constants.ts
- ✅ Create extension-activation.test.ts
- ✅ Create commands-registry.test.ts

**Tuesday:**
- ✅ Delete duplicated activation tests
- ✅ Delete duplicated command tests
- ✅ Update remaining files to use shared fixtures

**Wednesday:**
- ✅ Run all tests to verify no regressions
- ✅ Fix any issues from refactoring

**Thursday:**
- ✅ Create mock-manager.ts
- ✅ Enhance MockAgentBridge with full features
- ✅ Update mock-services.ts

**Friday:**
- ✅ Update all test files to use mock-manager
- ✅ Start replacing sleep() with waitForCondition()

---

### Week 2: Immediate Actions (Part 2)

**Monday:**
- ✅ Finish replacing sleep() with waitForCondition()
- ✅ Run performance tests to verify improvement

**Tuesday:**
- ✅ Remove try-catch anti-pattern from all tests
- ✅ Add behavior verification to conversation tests

**Wednesday:**
- ✅ Add behavior verification to KB tests
- ✅ Add behavior verification to command tests

**Thursday:**
- ✅ Fix or remove all skipped tests
- ✅ Run full test suite to verify no regressions

**Friday:**
- ✅ Code review for immediate actions
- ✅ Document changes
- ✅ Update test documentation

---

### Week 3: Long-term Improvements (Part 1)

**Monday:**
- ✅ Create new directory structure (unit/integration/e2e)
- ✅ Update .vscode-test.mjs configuration
- ✅ Update package.json scripts

**Tuesday:**
- ✅ Update justfile with new test commands
- ✅ Move tests to appropriate directories

**Wednesday:**
- ✅ Delete obsolete test files
- ✅ Run all tests to verify organization
- ✅ Update CI configuration

**Thursday:**
- ✅ Install Playwright
- ✅ Configure Playwright for VS Code testing
- ✅ Create first Playwright e2e test

**Friday:**
- ✅ Create additional Playwright tests
- ✅ Verify Playwright tests run successfully
- ✅ Document Playwright setup

---

### Week 4: Long-term Improvements (Part 2)

**Monday:**
- ✅ Create performance test suite
- ✅ Add performance benchmarks

**Tuesday:**
- ✅ Create performance tracking script
- ✅ Add performance regression checks
- ✅ Update CI to track performance

**Wednesday:**
- ✅ Install coverage tools (c8)
- ✅ Configure coverage reporting
- ✅ Update CI to collect coverage

**Thursday:**
- ✅ Add coverage badge to README
- ✅ Configure coverage thresholds
- ✅ Generate initial coverage report

**Friday:**
- ✅ Final code review
- ✅ Update all documentation
- ✅ Team training session
- ✅ Retrospective

---

## Test Architecture

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     VSCode Extension Tests                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ Unit Tests  │  │ Integration Tests│  │  E2E Tests     │  │
│  │             │  │                  │  │                │  │
│  │ • Isolated  │  │ • Extension +    │  │ • Full UI      │  │
│  │ • Mocked    │  │   Mocks          │  │ • Real env     │  │
│  │ • Fast      │  │ • Moderate speed │  │ • Slow         │  │
│  │ • <3s total │  │ • <12s total     │  │ • <30s total   │  │
│  └─────────────┘  └──────────────────┘  └────────────────┘  │
│         │                  │                      │          │
│         └──────────────────┼──────────────────────┘          │
│                            │                                 │
│                            ▼                                 │
│                  ┌──────────────────┐                        │
│                  │ Shared Fixtures  │                        │
│                  │                  │                        │
│                  │ • Activation     │                        │
│                  │ • Commands       │                        │
│                  │ • Waiting        │                        │
│                  │ • Test utils     │                        │
│                  └──────────────────┘                        │
│                            │                                 │
│                            ▼                                 │
│                  ┌──────────────────┐                        │
│                  │  Mock Manager    │                        │
│                  │                  │                        │
│                  │ • KB Server      │                        │
│                  │ • Agent Bridge   │                        │
│                  │ • Configuration  │                        │
│                  └──────────────────┘                        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Test Pyramid

```
        ┌─────────┐
       /  E2E (5)  \      • Slow, expensive
      /_____________\     • Full workflows
     /               \    • Real environment
    / Integration(15)\   • Extension + mocks
   /___________________\  • Moderate speed
  /                     \
 /    Unit Tests (30)    \• Fast, isolated
/________________________\• Fully mocked
```

**Target distribution:**
- Unit: 60% (30 tests)
- Integration: 30% (15 tests)
- E2E: 10% (5 tests)

### Mock Strategy

**Always Mock:**
- External APIs (Claude API, KB API)
- File system for non-critical tests
- Network calls
- Time-dependent operations

**Sometimes Mock:**
- VS Code API (mock for unit, real for integration)
- Extension storage (mock for unit, real for integration)

**Never Mock:**
- Core business logic
- Data structures
- Utility functions

---

## Success Metrics

### Quantitative Metrics

| Metric | Before | Target | Actual |
|--------|--------|--------|--------|
| **Test Execution Time** | ~60s | <15s | TBD |
| **Code Duplication** | 40-50% | <10% | TBD |
| **Test Quality Score** | 3.5/10 | 8/10 | TBD |
| **False Positive Rate** | ~30% | 0% | TBD |
| **Test Coverage** | ~20% behavior | 80% behavior | TBD |
| **Mock Utilization** | 20% | 100% | TBD |
| **Skipped Tests** | 6 tests | 0 tests | TBD |
| **Total Test Count** | ~50 tests | ~50 tests | TBD |
| **Lines of Test Code** | ~1,463 | ~900 | TBD |

### Qualitative Metrics

**Developer Experience:**
- ✅ Tests run quickly during development
- ✅ Test failures clearly indicate problem
- ✅ Easy to add new tests
- ✅ Tests provide confidence in changes

**Maintainability:**
- ✅ Minimal duplication
- ✅ Clear test organization
- ✅ Consistent patterns
- ✅ Good documentation

**Reliability:**
- ✅ Tests pass consistently
- ✅ No flaky tests
- ✅ No environment dependencies
- ✅ Clear error messages

---

## Appendices

### Appendix A: Test Naming Conventions

**Unit Tests:**
```typescript
// Format: should_<expected_behavior>_when_<condition>
test('should_return_configuration_value_when_key_exists', () => {...});
test('should_throw_error_when_configuration_key_missing', () => {...});
```

**Integration Tests:**
```typescript
// Format: <action>_should_<expected_result>
test('activating_extension_should_register_all_commands', () => {...});
test('sending_message_should_trigger_kb_search', () => {...});
```

**E2E Tests:**
```typescript
// Format: user_can_<action>_<expected_outcome>
test('user_can_send_message_and_receive_response', () => {...});
test('user_can_create_new_conversation', () => {...});
```

---

### Appendix B: Test File Template

**Unit Test Template:**

```typescript
/**
 * Unit tests for [component name].
 */

import * as assert from 'assert';
import { [ComponentName] } from '../../[path]';

suite('[Component Name] Unit Tests', () => {
  let component: ComponentName;

  setup(() => {
    // Initialize component before each test
    component = new ComponentName();
  });

  teardown(() => {
    // Cleanup after each test
    component.dispose();
  });

  test('should_[expected_behavior]_when_[condition]', () => {
    // Arrange
    const input = 'test input';

    // Act
    const result = component.method(input);

    // Assert
    assert.strictEqual(result, 'expected output');
  });
});
```

**Integration Test Template:**

```typescript
/**
 * Integration tests for [workflow name].
 */

import * as assert from 'assert';
import * as vscode from 'vscode';
import { setupMockEnvironment, teardownMockEnvironment, resetMocks } from '../helpers/mock-manager';
import { activateExtension } from '../helpers/shared-fixtures';

suite('[Workflow Name] Integration Tests', function() {
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

  test('[action]_should_[expected_result]', async () => {
    // Arrange
    configureMockKB({ searchResults: [...] });

    // Act
    await vscode.commands.executeCommand('dolphin.test');

    // Assert
    const { kbServer } = getMockEnvironment();
    const calls = kbServer.getRequestHistory();
    assert.strictEqual(calls.length, 1);
  });
});
```

---

### Appendix C: CI/CD Integration

**GitHub Actions Workflow:**

```yaml
name: VSCode Extension Tests

on: [push, pull_request]

jobs:
  unit-tests:
    name: Unit Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-node@v3
        with:
          node-version: 18
          cache: 'npm'
          cache-dependency-path: vscode-extension/package-lock.json

      - name: Install dependencies
        working-directory: vscode-extension
        run: npm ci

      - name: Compile TypeScript
        working-directory: vscode-extension
        run: npm run compile

      - name: Run unit tests
        working-directory: vscode-extension
        run: npm run test:unit

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: unit-test-results
          path: vscode-extension/test-results/

  integration-tests:
    name: Integration Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-node@v3
        with:
          node-version: 18
          cache: 'npm'
          cache-dependency-path: vscode-extension/package-lock.json

      - name: Install dependencies
        working-directory: vscode-extension
        run: npm ci

      - name: Compile TypeScript
        working-directory: vscode-extension
        run: npm run compile

      - name: Run integration tests
        working-directory: vscode-extension
        run: npm run test:integration

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: integration-test-results
          path: vscode-extension/test-results/

  coverage:
    name: Test Coverage
    runs-on: ubuntu-latest
    needs: [unit-tests, integration-tests]
    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-node@v3
        with:
          node-version: 18
          cache: 'npm'
          cache-dependency-path: vscode-extension/package-lock.json

      - name: Install dependencies
        working-directory: vscode-extension
        run: npm ci

      - name: Compile TypeScript
        working-directory: vscode-extension
        run: npm run compile

      - name: Run tests with coverage
        working-directory: vscode-extension
        run: npm run test:coverage

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./vscode-extension/coverage/lcov.info
          flags: vscode-extension

      - name: Check coverage thresholds
        working-directory: vscode-extension
        run: npx c8 check-coverage

  performance:
    name: Performance Tests
    runs-on: ubuntu-latest
    needs: [unit-tests, integration-tests]
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0 # Need history for regression check

      - uses: actions/setup-node@v3
        with:
          node-version: 18
          cache: 'npm'
          cache-dependency-path: vscode-extension/package-lock.json

      - name: Install dependencies
        working-directory: vscode-extension
        run: npm ci

      - name: Run performance tests
        working-directory: vscode-extension
        run: npm run test:performance

      - name: Check for performance regressions
        working-directory: vscode-extension
        run: node scripts/check-performance-regression.js
```

---

### Appendix D: Troubleshooting Guide

**Problem: Tests fail after refactoring**

1. Check that all imports are updated
2. Verify shared fixtures are being used correctly
3. Ensure mocks are properly initialized
4. Run tests individually to isolate issue

**Problem: Tests are still slow**

1. Check for remaining sleep() calls: `grep -r "sleep(" src/test/`
2. Verify mocks are being used, not real services
3. Check for synchronous file operations
4. Profile tests: `npm run test:unit -- --reporter json > profile.json`

**Problem: Tests are flaky**

1. Check for race conditions (missing awaits)
2. Verify proper cleanup in teardown
3. Ensure tests don't depend on execution order
4. Check for shared mutable state

**Problem: Mock not working**

1. Verify mock-manager is initialized in suiteSetup
2. Check that resetMocks() is called in setup()
3. Ensure extension is using mock port (7778)
4. Verify mock responses are configured

---

### Appendix E: Rollback Plan

If issues arise during refactoring:

**Phase 1: Preserve Original Tests**

During refactoring, keep original test files with `.backup` extension:
```bash
cp phase1-integration.test.ts phase1-integration.test.ts.backup
```

**Phase 2: Git Safety**

Create a refactoring branch:
```bash
git checkout -b test-refactoring
git commit -m "Save point before refactoring"
```

**Phase 3: Incremental Rollback**

If specific change causes issues:
```bash
# Roll back specific file
git checkout HEAD -- src/test/suite/conversations-e2e.test.ts

# Or roll back entire commit
git revert <commit-hash>
```

**Phase 4: Full Rollback**

If refactoring needs to be abandoned:
```bash
git checkout main
git branch -D test-refactoring
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-13 | Engineering Team | Initial comprehensive plan |

---

## Next Steps

1. **Review & Approval** (1 day)
   - Team reviews plan
   - Stakeholders approve scope
   - Timeline confirmed

2. **Branch Creation** (1 day)
   - Create `test-refactoring` branch
   - Set up tracking
   - Configure CI for branch

3. **Begin Implementation** (Week 1)
   - Start with IA-1 (Eliminate Duplication)
   - Daily stand-ups to track progress
   - Code reviews for each major change

4. **Continuous Validation**
   - Run full test suite after each change
   - Track metrics in shared document
   - Update plan as needed

5. **Final Review & Merge** (End of Week 4)
   - Comprehensive testing
   - Documentation updates
   - Team training
   - Merge to main

---

**Questions or Concerns?**

Contact the engineering team or open an issue in the repository.
