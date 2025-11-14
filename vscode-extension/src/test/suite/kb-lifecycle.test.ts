/**
 * KB lifecycle management tests using mock infrastructure.
 * Tests KB server startup, health checks, and status monitoring with mocks.
 */

import * as assert from "assert";
import * as vscode from "vscode";
import {
  setupMockEnvironment,
  teardownMockEnvironment,
  resetMocks,
  getMockEnvironment,
  configureMockKB,
} from "../helpers/mock-manager";
import { activateExtension, assertCommandExists } from "../helpers/shared-fixtures";
import { TEST_COMMANDS } from "../helpers/test-constants";

describe("KB Lifecycle Management", function () {
  this.timeout(10000);

  before(async () => {
    await setupMockEnvironment();
    await activateExtension();
  });

  after(async () => {
    await teardownMockEnvironment();
  });

  beforeEach(() => {
    resetMocks();
  });

  describe("KB Server Health", () => {
    it("Mock KB server should be running", async () => {
      const { kbServer } = getMockEnvironment();

      assert.ok(kbServer, "KB server mock should be initialized");
      assert.ok(kbServer.port > 0, "KB server should have valid port");
      assert.strictEqual(kbServer.port, 7778, "Should use configured test port");
    });

    it("KB server should respond to health checks", async () => {
      const { kbServer } = getMockEnvironment();

      // Configure KB as healthy
      configureMockKB({ health: true });

      const http = require("http");
      const response = await new Promise<any>((resolve, _reject) => {
        http.get(`http://localhost:${kbServer.port}/health`, (res: any) => {
          let data = "";
          res.on("data", (chunk: any) => {
            data += chunk;
          });
          res.on("end", () => {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
          });
        });
      });

      assert.strictEqual(response.status, 200, "Health check should return 200");
      assert.strictEqual(response.data.status, "ok", "Should return ok status");
    });

    it("KB server should report unhealthy state when configured", async () => {
      const { kbServer } = getMockEnvironment();

      // Configure KB as unhealthy
      configureMockKB({ health: false });

      const http = require("http");
      const response = await new Promise<any>((resolve, _reject) => {
        http.get(`http://localhost:${kbServer.port}/health`, (res: any) => {
          let data = "";
          res.on("data", (chunk: any) => {
            data += chunk;
          });
          res.on("end", () => {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
          });
        });
      });

      assert.strictEqual(response.status, 503, "Unhealthy check should return 503");
      assert.strictEqual(response.data.status, "error", "Should return error status");
    });
  });

  describe("KB Commands", () => {
    it("KB status command should be registered", async () => {
      await assertCommandExists(TEST_COMMANDS.KB_SHOW_STATUS);
    });

    it("KB restart command should be registered", async () => {
      await assertCommandExists(TEST_COMMANDS.KB_RESTART);
    });

    it("KB status command should execute", async () => {
      // Command should execute without throwing
      await vscode.commands.executeCommand(TEST_COMMANDS.KB_SHOW_STATUS);
      // If we get here, command executed (may or may not show UI in headless mode)
    });

    it("KB restart command should execute", async () => {
      // Command should execute without throwing
      await vscode.commands.executeCommand(TEST_COMMANDS.KB_RESTART);
      // If we get here, command executed
    });
  });

  describe("KB API Operations", () => {
    it("KB should handle search requests", async () => {
      const { kbServer } = getMockEnvironment();

      configureMockKB({
        searchResults: [
          {
            chunk_id: "test-1",
            repo: "test-repo",
            path: "file.ts",
            content: "test content",
            score: 0.9,
            line_start: 1,
            line_end: 3,
          },
        ],
      });

      const http = require("http");
      const response = await new Promise<any>((resolve, reject) => {
        const postData = JSON.stringify({ query: "test", top_k: 10 });
        const options = {
          hostname: "localhost",
          port: kbServer.port,
          path: "/search",
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(postData),
          },
        };

        const req = http.request(options, (res: any) => {
          let data = "";
          res.on("data", (chunk: any) => {
            data += chunk;
          });
          res.on("end", () => {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
          });
        });

        req.on("error", reject);
        req.write(postData);
        req.end();
      });

      assert.strictEqual(response.status, 200, "Search should return 200");
      assert.ok(response.data.hits, "Should return hits");
      assert.strictEqual(response.data.hits.length, 1, "Should return configured result");
      assert.strictEqual(
        response.data.hits[0].chunk_id,
        "test-1",
        "Should return configured chunk"
      );
    });

    it("KB should return metadata", async () => {
      const { kbServer } = getMockEnvironment();

      configureMockKB({
        metadata: {
          repos: [{ name: "custom-repo", path: "/custom/path", files: 5, chunks: 25 }],
          total_chunks: 25,
          total_files: 5,
        },
      });

      const http = require("http");
      const response = await new Promise<any>((resolve, _reject) => {
        http.get(`http://localhost:${kbServer.port}/metadata/test`, (res: any) => {
          let data = "";
          res.on("data", (chunk: any) => {
            data += chunk;
          });
          res.on("end", () => {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
          });
        });
      });

      assert.strictEqual(response.status, 200, "Metadata should return 200");
      assert.ok(response.data.repos, "Should have repos");
      assert.strictEqual(response.data.total_chunks, 25, "Should return configured total");
    });

    it("KB should log request history", async () => {
      const { kbServer } = getMockEnvironment();

      const requestsBefore = kbServer.getRequestHistory().length;

      // Make multiple requests
      const http = require("http");
      await new Promise((resolve) => {
        http.get(`http://localhost:${kbServer.port}/health`, (res: any) => {
          res.on("data", () => {});
          res.on("end", resolve);
        });
      });

      await new Promise((resolve) => {
        http.get(`http://localhost:${kbServer.port}/metadata/test`, (res: any) => {
          res.on("data", () => {});
          res.on("end", resolve);
        });
      });

      const requestsAfter = kbServer.getRequestHistory().length;
      assert.strictEqual(requestsAfter - requestsBefore, 2, "Should have logged 2 requests");

      const history = kbServer.getRequestHistory();
      assert.ok(
        history.every((r) => r.timestamp),
        "Each request should have timestamp"
      );
      assert.ok(
        history.every((r) => r.method),
        "Each request should have method"
      );
      assert.ok(
        history.every((r) => r.url),
        "Each request should have URL"
      );
    });
  });

  describe("KB Configuration", () => {
    it("KB configuration keys should be readable via get()", () => {
      // Use inspect() to verify default values exist in package.json
      const config = vscode.workspace.getConfiguration("dolphin");

      // Use inspect() which returns defaultValue, globalValue, workspaceValue, etc.
      const kbDebounceInspect = config.inspect("kb.debounceMs");
      const kbBatchIntervalInspect = config.inspect("kb.batchIntervalMs");
      const autoSyncEnabledInspect = config.inspect("kb.autoSync.enabled");

      // Check that default values are defined in package.json
      assert.ok(kbDebounceInspect?.defaultValue !== undefined, "kb.debounceMs should have a default value");
      assert.ok(kbBatchIntervalInspect?.defaultValue !== undefined, "kb.batchIntervalMs should have a default value");
      assert.ok(autoSyncEnabledInspect?.defaultValue !== undefined, "kb.autoSync.enabled should have a default value");
    });

    it("KB configuration should have valid default types from package.json", () => {
      const config = vscode.workspace.getConfiguration("dolphin");

      // Use inspect() to get default values and verify types
      const kbDebounceInspect = config.inspect<number>("kb.debounceMs");
      const excludePatternsInspect = config.inspect<string[]>("kb.excludePatterns");
      const autoSyncEnabledInspect = config.inspect<boolean>("kb.autoSync.enabled");

      // Verify types match package.json definitions using default values
      if (kbDebounceInspect?.defaultValue !== undefined) {
        assert.strictEqual(
          typeof kbDebounceInspect.defaultValue,
          "number",
          `kb.debounceMs default should be number, got ${typeof kbDebounceInspect.defaultValue}`
        );
      }

      if (excludePatternsInspect?.defaultValue !== undefined) {
        assert.ok(Array.isArray(excludePatternsInspect.defaultValue), "kb.excludePatterns default should be array");
      }

      if (autoSyncEnabledInspect?.defaultValue !== undefined) {
        assert.strictEqual(
          typeof autoSyncEnabledInspect.defaultValue,
          "boolean",
          "kb.autoSync.enabled default should be boolean"
        );
      }
    });
  });

  describe("KB Performance", () => {
    it("KB status checks should be fast", async () => {
      const { kbServer } = getMockEnvironment();

      const startTime = Date.now();

      const http = require("http");
      await new Promise((resolve) => {
        http.get(`http://localhost:${kbServer.port}/health`, (res: any) => {
          res.on("data", () => {});
          res.on("end", resolve);
        });
      });

      const elapsed = Date.now() - startTime;

      // Mock KB should respond very quickly
      assert.ok(elapsed < 1000, `Health check took ${elapsed}ms, should be < 1000ms`);
    });

    it("KB search should be reasonably fast", async () => {
      const { kbServer } = getMockEnvironment();

      const startTime = Date.now();

      const http = require("http");
      await new Promise((resolve, reject) => {
        const postData = JSON.stringify({ query: "test", top_k: 10 });
        const options = {
          hostname: "localhost",
          port: kbServer.port,
          path: "/search",
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(postData),
          },
        };

        const req = http.request(options, (res: any) => {
          res.on("data", () => {});
          res.on("end", resolve);
        });

        req.on("error", reject);
        req.write(postData);
        req.end();
      });

      const elapsed = Date.now() - startTime;

      // Mock KB should respond very quickly
      assert.ok(elapsed < 1000, `Search took ${elapsed}ms, should be < 1000ms`);
    });
  });
});
