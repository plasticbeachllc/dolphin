/**
 * Shared test fixtures to eliminate duplication across test files.
 * These fixtures provide common functionality for extension testing.
 */

import * as vscode from "vscode";
import * as assert from "assert";
import { sleep } from "./test-utils";
import { ExtensionExports } from "./mock-types";
import { MOCK_KB_CONFIG } from "./test-constants";

/**
 * Extension activation fixture with proper waiting.
 * Use this instead of duplicating activation logic in every test.
 */
export async function activateExtension(): Promise<vscode.Extension<ExtensionExports>> {
  const ext = vscode.extensions.getExtension("pb.dolphin");
  assert.ok(ext, "Extension should be installed");

  // Ensure KB base URL points to the mock server for any test that activates the extension
  if (!process.env.DOLPHIN_KB_BASE_URL || !process.env.DOLPHIN_KB_API_BASE_URL) {
    const kbBase = `http://${MOCK_KB_CONFIG.HOST}:${MOCK_KB_CONFIG.PORT}`;
    process.env.DOLPHIN_KB_BASE_URL = kbBase;
    process.env.DOLPHIN_KB_API_BASE_URL = kbBase;
  }

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
async function waitForExtensionReady(ext: vscode.Extension<ExtensionExports>): Promise<void> {
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
  shouldExecute: boolean = false
): Promise<void> {
  const commands = await vscode.commands.getCommands(true);
  assert.ok(commands.includes(commandId), `Command ${commandId} should be registered`);

  if (shouldExecute) {
    // Actually try to execute the command
    // Note: Some commands may fail in headless test environment
    // This just verifies they're executable, not that they succeed
    await vscode.commands.executeCommand(commandId);
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
    assert.ok(commands.includes(commandId), `Command ${commandId} should be registered`);
  }

  if (shouldExecute) {
    for (const commandId of commandIds) {
      await vscode.commands.executeCommand(commandId);
    }
  }
}

/**
 * Configuration fixture.
 * Use this to verify configuration schema.
 */
export function assertConfigurationExists(keys: string[]): void {
  const config = vscode.workspace.getConfiguration("dolphin");

  for (const key of keys) {
    const info = config.inspect(key);
    assert.ok(info !== undefined, `Configuration key 'dolphin.${key}' should exist`);
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
  const timeoutMessage = options.timeoutMessage ?? "Condition not met within timeout";

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
 * Create a test document with specific content.
 */
export async function createTestDocument(
  content: string,
  language: string = "typescript"
): Promise<vscode.TextDocument> {
  const doc = await vscode.workspace.openTextDocument({
    content,
    language,
  });
  return doc;
}

/**
 * Get extension exports with type safety.
 */
export function getExtensionExports<T = unknown>(): T | undefined {
  const ext = vscode.extensions.getExtension("pb.dolphin");
  if (!ext?.isActive) {
    return undefined;
  }
  return ext.exports as T;
}

/**
 * Wait for webview to be ready.
 */
export async function waitForWebviewReady(timeout: number = 5000): Promise<void> {
  await waitForCondition(
    () => {
      const exports = getExtensionExports() as ExtensionExports | undefined;
      return exports?.webviewProvider !== undefined;
    },
    { timeout, timeoutMessage: "Webview provider not ready" }
  );
}
