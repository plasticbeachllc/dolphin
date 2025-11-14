import * as vscode from "vscode";
import * as http from "http";
import { HttpTestResponse } from "./mock-types";

/**
 * Wait for a condition to be true with timeout
 */
export async function waitFor(
  condition: () => boolean,
  timeout = 5000,
  interval = 100
): Promise<void> {
  const startTime = Date.now();

  while (!condition()) {
    if (Date.now() - startTime > timeout) {
      throw new Error(`Timeout waiting for condition after ${timeout}ms`);
    }
    await sleep(interval);
  }
}

/**
 * Sleep for a given number of milliseconds
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Get the Dolphin extension
 */
export function getDolphinExtension(): vscode.Extension<any> | undefined {
  return vscode.extensions.getExtension("pb.dolphin");
}

/**
 * Wait for extension to be activated
 */
export async function waitForExtensionActivation(
  timeout = 10000,
  waitForAgent = false
): Promise<vscode.Extension<any>> {
  const extension = getDolphinExtension();

  if (!extension) {
    throw new Error("Dolphin extension not found");
  }

  if (!extension.isActive) {
    await extension.activate();
  }

  await waitFor(() => extension.isActive, timeout);

  // Optionally wait for agent bridge to be ready (for E2E tests that need it)
  if (waitForAgent) {
    // Note: In real implementation, you would get the actual agent bridge instance
    // For now, we skip this as it requires accessing the extension's internal state
    // Tests that need agent bridge should use mock-manager.ts instead
  }

  return extension;
}

/**
 * Get a webview by view ID
 */
export async function getWebview(viewId: string, _timeout = 5000): Promise<void> {
  // Execute command to focus the webview, which will cause it to load
  await vscode.commands.executeCommand(`${viewId}.focus`);
  await sleep(500); // Give it time to render
}

/**
 * Create a temporary workspace folder for testing
 */
export async function createTestWorkspace(): Promise<vscode.Uri> {
  const tmpDir = require("os").tmpdir();
  const testDir = require("path").join(tmpDir, `dolphin-test-${Date.now()}`);
  const fs = require("fs").promises;

  await fs.mkdir(testDir, { recursive: true });

  return vscode.Uri.file(testDir);
}

/**
 * Clean up test workspace
 */
export async function cleanupTestWorkspace(uri: vscode.Uri): Promise<void> {
  const fs = require("fs").promises;
  try {
    await fs.rm(uri.fsPath, { recursive: true, force: true });
  } catch (err) {
    console.warn("Failed to cleanup test workspace:", err);
  }
}

/**
 * Assert that a value is defined (TypeScript type guard)
 */
export function assertDefined<T>(
  value: T | undefined | null,
  message?: string
): asserts value is T {
  if (value === undefined || value === null) {
    throw new Error(message || "Expected value to be defined");
  }
}

/**
 * Get output channel content
 */
export function captureOutputChannel(name: string): {
  getContent: () => string;
  dispose: () => void;
} {
  const content: string[] = [];
  const _originalAppendLine = vscode.window.createOutputChannel(name).appendLine;

  // Note: This is a simplified version. In real implementation,
  // you'd need to hook into the actual output channel.

  return {
    getContent: () => content.join("\n"),
    dispose: () => {},
  };
}

/**
 * Make an HTTP GET request with timeout handling
 * @param url The URL to fetch
 * @param timeout Timeout in milliseconds (default: 2000ms)
 * @returns Promise resolving to the response with status and parsed JSON data
 */
export async function makeHttpGetRequest<T = any>(
  url: string,
  timeout: number = 2000
): Promise<HttpTestResponse<T>> {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      let data = "";

      res.on("data", (chunk) => {
        data += chunk;
      });

      res.on("end", () => {
        try {
          const parsedData = data ? JSON.parse(data) : null;
          resolve({
            status: res.statusCode || 0,
            data: parsedData,
            headers: res.headers as Record<string, string>,
          });
        } catch (err) {
          reject(
            new Error(
              `Failed to parse JSON response: ${err instanceof Error ? err.message : String(err)}`
            )
          );
        }
      });
    });

    // Set timeout
    req.setTimeout(timeout);

    req.on("timeout", () => {
      req.destroy();
      reject(new Error(`Request timed out after ${timeout}ms`));
    });

    req.on("error", (err) => {
      reject(err);
    });
  });
}

/**
 * Make an HTTP POST request with timeout handling
 * @param options HTTP request options (hostname, port, path, headers)
 * @param postData The data to send in the request body
 * @param timeout Timeout in milliseconds (default: 2000ms)
 * @returns Promise resolving to the response with status and parsed JSON data
 */
export async function makeHttpPostRequest<T = any>(
  options: http.RequestOptions,
  postData: string,
  timeout: number = 2000
): Promise<HttpTestResponse<T>> {
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        ...options,
        method: "POST",
      },
      (res) => {
        let data = "";

        res.on("data", (chunk) => {
          data += chunk;
        });

        res.on("end", () => {
          try {
            const parsedData = data ? JSON.parse(data) : null;
            resolve({
              status: res.statusCode || 0,
              data: parsedData,
              headers: res.headers as Record<string, string>,
            });
          } catch (err) {
            reject(
              new Error(
                `Failed to parse JSON response: ${err instanceof Error ? err.message : String(err)}`
              )
            );
          }
        });
      }
    );

    // Set timeout
    req.setTimeout(timeout);

    req.on("timeout", () => {
      req.destroy();
      reject(new Error(`Request timed out after ${timeout}ms`));
    });

    req.on("error", (err) => {
      reject(err);
    });

    if (postData) {
      req.write(postData);
    }
    req.end();
  });
}

/**
 * Make a generic HTTP request with full control and timeout handling
 * @param options HTTP request options
 * @param postData Optional data to send (for POST/PUT requests)
 * @param timeout Timeout in milliseconds (default: 2000ms)
 * @returns Promise resolving to the response with status and parsed JSON data
 */
export async function makeHttpRequest<T = any>(
  options: http.RequestOptions,
  postData?: string,
  timeout: number = 2000
): Promise<HttpTestResponse<T>> {
  return new Promise((resolve, reject) => {
    const req = http.request(options, (res) => {
      let data = "";

      res.on("data", (chunk) => {
        data += chunk;
      });

      res.on("end", () => {
        try {
          const parsedData = data ? JSON.parse(data) : null;
          resolve({
            status: res.statusCode || 0,
            data: parsedData,
            headers: res.headers as Record<string, string>,
          });
        } catch (err) {
          reject(
            new Error(
              `Failed to parse JSON response: ${err instanceof Error ? err.message : String(err)}`
            )
          );
        }
      });
    });

    // Set timeout
    req.setTimeout(timeout);

    req.on("timeout", () => {
      req.destroy();
      reject(new Error(`Request timed out after ${timeout}ms`));
    });

    req.on("error", (err) => {
      reject(err);
    });

    if (postData) {
      req.write(postData);
    }
    req.end();
  });
}

/**
 * Assert that a command executes successfully within a timeout
 * @param commandId The VS Code command ID to execute
 * @param args Optional arguments to pass to the command
 * @param timeout Timeout in milliseconds (default: 2000ms)
 */
export async function assertCommandExecutes(
  commandId: string,
  args?: any[],
  timeout: number = 2000
): Promise<any> {
  return Promise.race([
    vscode.commands.executeCommand(commandId, ...(args || [])),
    new Promise((_, reject) =>
      setTimeout(
        () => reject(new Error(`Command ${commandId} timed out after ${timeout}ms`)),
        timeout
      )
    ),
  ]);
}
