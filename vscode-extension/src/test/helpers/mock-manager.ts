/**
 * Centralized mock management for all tests.
 * Ensures consistent mock usage across test suite.
 */

import { MockKBServer, MockAgentBridge } from "./mock-services";
import { MOCK_KB_CONFIG } from "./test-constants";
import { MockSearchResult, MockMetadataResponse, ToolCall } from "./mock-types";

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

  // Start mock KB server on configured port
  const kbServer = new MockKBServer();
  await kbServer.start(MOCK_KB_CONFIG.PORT);

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
    throw new Error("Mock environment not initialized. Call setupMockEnvironment() first.");
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
    mockEnvironment.agentBridge.shutdown();
    mockEnvironment = null;
  }
}

/**
 * Reset mocks between tests (not full teardown).
 * Call this in setup() or teardown().
 */
export function resetMocks(): void {
  if (mockEnvironment) {
    mockEnvironment.agentBridge.reset();
    mockEnvironment.kbServer.reset();
  }
}

/**
 * Configure mock KB server responses.
 */
export function configureMockKB(config: {
  searchResults?: MockSearchResult[];
  metadata?: MockMetadataResponse;
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
  toolCalls?: ToolCall[];
  shouldError?: boolean;
  error?: Error;
}): void {
  const env = getMockEnvironment();

  if (config.response !== undefined) {
    env.agentBridge.setResponse(config.response);
  }

  if (config.toolCalls !== undefined) {
    env.agentBridge.setToolCalls(config.toolCalls);
  }

  if (config.shouldError && config.error) {
    env.agentBridge.setError(true, config.error.message);
    env.agentBridge.mockError = config.error;
  } else if (config.shouldError) {
    env.agentBridge.setError(true, "Mock agent error");
  }
}
