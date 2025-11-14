/**
 * Integration tests using mock KB server.
 * Tests the extension with mocked external dependencies.
 */

import * as assert from "assert";
import * as vscode from "vscode";
import {
  waitForExtensionActivation,
  makeHttpGetRequest,
  makeHttpPostRequest,
} from "../../../helpers/test-utils";
import { MockKBServer } from "../../../helpers/mock-services";
import { MockHealthResponse, MockSearchResponse, MockSearchRequest } from "../../../helpers/mock-types";

describe("Integration Tests", () => {
  let mockServer: MockKBServer;

  describe("Integration Tests with Mock KB", function () {
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

    it("Mock KB API server should be running and healthy", async () => {
      assert.ok(mockServer, "Mock server should be initialized");
      assert.ok(mockServer.port > 0, "Mock server should have a port assigned");

      // Test health endpoint using the new HTTP helper with timeout
      const response = await makeHttpGetRequest<MockHealthResponse>(
        `http://localhost:${mockServer.port}/health`,
        3000 // 3 second timeout
      );

      assert.strictEqual(response.status, 200, "Health check should return 200");
      assert.strictEqual(response.data.status, "ok", "Health check should return ok status");
      assert.strictEqual(
        response.data.mock,
        true,
        "Health check should indicate this is a mock server"
      );
    });

    it("Extension should be active", async () => {
      const extension = vscode.extensions.getExtension("pb.dolphin");
      assert.ok(extension, "Extension should exist");
      assert.ok(extension.isActive, "Extension should be active");
    });

    it("Mock KB API should handle search requests", async function () {
      this.timeout(5000);

      const searchRequest: MockSearchRequest = {
        query: "test search",
        top_k: 10,
      };

      const postData = JSON.stringify(searchRequest);
      const response = await makeHttpPostRequest<MockSearchResponse>(
        {
          hostname: "localhost",
          port: mockServer.port,
          path: "/search",
          headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(postData),
          },
        },
        postData,
        3000 // 3 second timeout
      );

      assert.strictEqual(response.status, 200, "Search should return 200");
      assert.ok(response.data.hits, "Search should return hits");
      assert.ok(Array.isArray(response.data.hits), "Hits should be an array");
      assert.ok(response.data.hits.length > 0, "Should return at least one hit");
      assert.strictEqual(response.data.complete, true, "Search should be marked as complete");
    });

    it("Complete workflow: Extension activation → Commands → Mock KB", async () => {
      // 1. Verify extension is active
      const extension = vscode.extensions.getExtension("pb.dolphin");
      assert.ok(extension?.isActive, "Extension should be active");

      // 2. Verify commands are registered
      const commands = await vscode.commands.getCommands(true);
      const dolphinCommands = commands.filter((cmd) => cmd.startsWith("dolphin."));
      assert.ok(dolphinCommands.length >= 10, "At least 10 Dolphin commands should be registered");

      // Verify specific commands
      assert.ok(commands.includes("dolphin.focusInput"), "focusInput command should be registered");
      assert.ok(
        commands.includes("dolphin.newConversation"),
        "newConversation command should be registered"
      );
      assert.ok(
        commands.includes("dolphin.kb.showStatus"),
        "KB status command should be registered"
      );

      // 3. Verify package.json contributions are correct
      const packageJSON = extension!.packageJSON;
      assert.ok(packageJSON.contributes.viewsContainers, "Should have viewsContainers");
      assert.ok(packageJSON.contributes.views, "Should have views");
      assert.ok(packageJSON.contributes.commands, "Should have commands");

      // 4. Verify mock KB is accessible
      const requestsBefore = mockServer.getRequestHistory().length;

      // Make a request to KB
      const http = require("http");
      await new Promise((resolve) => {
        http.get(`http://localhost:${mockServer.port}/health`, (res: unknown) => {
          (res as { on: (event: string, callback: (data: unknown) => void) => void }).on("data", () => {});
          (res as { on: (event: string, callback: (data: unknown) => void) => void }).on("end", resolve);
        });
      });

      // Verify request was logged
      const requestsAfter = mockServer.getRequestHistory().length;
      assert.ok(requestsAfter > requestsBefore, "KB should have logged the request");
    });
    // Placeholder helper functions - these should be implemented properly
    async function setupMockEnvironment() {
      mockServer = new MockKBServer();
      await mockServer.start();
    }

    async function teardownMockEnvironment() {
      if (mockServer) {
        await mockServer.stop();
      }
    }

    async function activateExtension() {
      await waitForExtensionActivation();
    }

    function resetMocks() {
      if (mockServer) {
        mockServer.reset();
      }
    }
  });
});
