/**
 * Centralized mock management for all tests.
 * Ensures consistent mock usage across test suite.
 */

import { MockKBServer, MockAgentBridge } from "./mock-services";
import { MOCK_KB_CONFIG } from "./test-constants";
import { MockSearchResult, MockMetadataResponse, ToolCall } from "./mock-types";
import type { AgentBridgeAdapter } from "../../agent/types";
import type { AgentEvent, ConversationListItem, LoadConversationResult } from "../../types/events";
import * as vscode from "vscode";

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

  const kbBaseUrl = `http://${MOCK_KB_CONFIG.HOST}:${kbServer.port}`;
  process.env.DOLPHIN_KB_BASE_URL = kbBaseUrl;
  process.env.DOLPHIN_KB_API_BASE_URL = kbBaseUrl;

  // Create mock agent bridge
  const agentBridge = new MockAgentBridge();

  mockEnvironment = { kbServer, agentBridge };
  return mockEnvironment;
}

/**
 * Provide an AgentBridgeAdapter-compatible wrapper around the MockAgentBridge
 * so integration tests can use the shared mock infrastructure without spinning
 * up real processes.
 */
export function createMockAgentBridgeAdapter(
  overrides: Partial<AgentBridgeAdapter> = {}
): AgentBridgeAdapter {
  const { agentBridge } = getMockEnvironment();

  const onEvent: vscode.Event<AgentEvent> = ((listener, thisArgs, disposables) => {
    const disposable = agentBridge.onEvent(listener);
    if (disposables) {
      disposables.push(disposable);
    }
    return disposable;
  }) as vscode.Event<AgentEvent>;

  const baseAdapter: AgentBridgeAdapter = {
    start: async () => {},
    stop: async () => {
      agentBridge.shutdown();
    },
    shutdown: async () => {
      agentBridge.shutdown();
    },
    onEvent,
    sendMessage: (content: string, mode?: "code" | "architect") =>
      agentBridge.sendMessage(content, mode),
    getAuthStatus: async () => ({
      providers: [
        {
          provider: "mock",
          authenticated: true,
          mode: "test",
        },
      ],
    }),
    abortGeneration: async () => Promise.resolve(),
    clearConversation: async () => Promise.resolve(),
    listConversations: async (): Promise<ConversationListItem[]> => [],
    loadConversation: async (conversationId: string): Promise<LoadConversationResult> => ({
      conversation: {
        id: conversationId,
        messages: [],
        title: "Mock conversation",
      },
    }),
    deleteConversation: async () => Promise.resolve(),
    renameConversation: async () => Promise.resolve(),
  };

  return {
    ...baseAdapter,
    ...overrides,
  };
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
    await mockEnvironment.agentBridge.shutdown();
    mockEnvironment = null;
  }

  delete process.env.DOLPHIN_KB_BASE_URL;
  delete process.env.DOLPHIN_KB_API_BASE_URL;
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
