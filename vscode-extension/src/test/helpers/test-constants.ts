/**
 * Shared test constants to ensure consistency across test files.
 */

/**
 * Command IDs used in tests
 */
export const TEST_COMMANDS = {
  // Phase 1 commands
  FOCUS_INPUT: "dolphin.focusInput",
  NEW_CONVERSATION: "dolphin.newConversation",
  SET_API_KEY: "dolphin.setApiKey",
  TEST: "dolphin.test",

  // Phase 2 commands
  ASK_ABOUT_SELECTION: "dolphin.askAboutSelection",
  REFACTOR_SELECTION: "dolphin.refactorSelection",
  ASK_ABOUT_FILE: "dolphin.askAboutFile",
  ASK_ABOUT_FOLDER: "dolphin.askAboutFolder",
  APPLY_DIFF: "dolphin.applyDiff",

  // KB commands
  KB_SHOW_STATUS: "dolphin.kb.showStatus",
  KB_RESTART: "dolphin.kb.restart",
} as const;

/**
 * Configuration keys used in tests
 */
export const TEST_CONFIG_KEYS = [
  "kb.debounceMs",
  "kb.batchIntervalMs",
  "kb.excludePatterns",
  "kb.autoSync.enabled",
  "kb.autoSync.mode",
  "kb.autoSync.idleTimeMs",
  "kb.autoSync.maxBatchSize",
  "kb.autoSync.checkIntervalMs",
  "model",
  "maxTokens",
  "temperature",
  "useTools",
  "enableTelemetry",
  "logLevel",
] as const;

/**
 * Standard timeouts for different operations
 */
export const TEST_TIMEOUTS = {
  EXTENSION_ACTIVATION: 5000,
  COMMAND_EXECUTION: 2000,
  KB_STARTUP: 10000,
  AGENT_RESPONSE: 15000,
  WEBVIEW_READY: 5000,
} as const;

/**
 * Mock KB server configuration
 */
export const MOCK_KB_CONFIG = {
  PORT: 7778,
  HOST: "localhost",
} as const;
