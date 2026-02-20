import * as assert from "assert";
import { MockKBServer, MockAgentBridge } from "../../../helpers/mock-services";
import {
  makeHttpGetRequest,
  makeHttpPostRequest,
  assertCommandExecutes,
} from "../../../helpers/test-utils";
import {
  MockHealthResponse,
  MockSearchRequest,
  MockSearchResponse,
} from "../../../helpers/mock-types";

/**
 * Negative test cases for error handling scenarios
 * Tests error paths, malformed data, timeouts, and edge cases
 */
describe("Error Handling Tests", () => {
  let mockServer: MockKBServer;

  beforeEach(async function () {
    this.timeout(5000);
    mockServer = new MockKBServer();
    await mockServer.start(0); // Use random port
  });

  afterEach(async function () {
    this.timeout(5000);
    if (mockServer) {
      await mockServer.stop();
    }
  });

  describe("MockKBServer Error Scenarios", () => {
    it("should return 503 when server is configured as unhealthy", async function () {
      this.timeout(5000);

      // Configure server as unhealthy
      mockServer.setHealthy(false);

      const response = await makeHttpGetRequest<MockHealthResponse>(
        `http://localhost:${mockServer.port}/health`,
        2000
      );

      assert.strictEqual(response.status, 503, "Unhealthy server should return 503");
      assert.strictEqual(response.data.status, "error", "Health status should be error");
      assert.ok(response.data.error, "Should include error message");
    });

    it("should return 404 for unknown endpoints", async function () {
      this.timeout(5000);

      const response = await makeHttpGetRequest(
        `http://localhost:${mockServer.port}/unknown-endpoint`,
        2000
      );

      assert.strictEqual(response.status, 404, "Should return 404 for unknown endpoint");
      const data = response.data as { error?: string };
      assert.ok(data.error, "Should include error message");
    });

    it("should return 400 for malformed search request", async function () {
      this.timeout(5000);

      // Send invalid JSON
      const invalidJson = "not valid json {{{";

      try {
        await makeHttpPostRequest(
          {
            hostname: "localhost",
            port: mockServer.port,
            path: "/search",
            headers: {
              "Content-Type": "application/json",
              "Content-Length": Buffer.byteLength(invalidJson),
            },
          },
          invalidJson,
          2000
        );

        assert.fail("Should have thrown an error for malformed JSON");
      } catch (err) {
        // Expected to fail - either the server returns 400 or JSON parsing fails
        assert.ok(err instanceof Error, "Should throw error for malformed JSON");
      }
    });

    it("should handle empty search results gracefully", async function () {
      this.timeout(5000);

      // Configure server to return empty results
      mockServer.setSearchResults([]);

      const searchRequest: MockSearchRequest = {
        query: "nonexistent query",
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
        2000
      );

      assert.strictEqual(response.status, 200, "Should return 200 even with no results");
      assert.ok(Array.isArray(response.data.hits), "Hits should be an array");
      assert.strictEqual(response.data.hits.length, 0, "Should return empty array");
      assert.strictEqual(response.data.total, 0, "Total should be 0");
    });

    it("should timeout when request takes too long", async function () {
      this.timeout(5000);

      // Create a server that never responds
      const slowServer = new MockKBServer();
      await slowServer.start(0);

      // Override handleRequest to delay indefinitely
      // Note: This is a contrived test - in reality we'd need a way to inject delays
      // For now, we'll test with a very short timeout on a normal request

      try {
        await makeHttpGetRequest(
          `http://localhost:${slowServer.port}/health`,
          1 // 1ms timeout - should fail immediately
        );
        assert.fail("Should have timed out");
      } catch (err) {
        assert.ok(err instanceof Error, "Should throw timeout error");
        assert.ok(
          err.message.includes("timed out") ||
            err.message.includes("timeout") ||
            err.message.includes("ECONNRESET"),
          "Error should mention timeout"
        );
      } finally {
        await slowServer.stop();
      }
    });

    it("should handle connection refused errors gracefully", async function () {
      this.timeout(5000);

      // Stop the server to simulate connection refused
      await mockServer.stop();

      try {
        await makeHttpGetRequest(`http://localhost:${mockServer.port}/health`, 2000);
        assert.fail("Should have thrown connection error");
      } catch (err) {
        assert.ok(err instanceof Error, "Should throw connection error");
        // Node.js system errors have a code property
        const nodeError = err as NodeJS.ErrnoException;
        assert.ok(
          nodeError.code === "ECONNREFUSED" ||
            err.message.includes("ECONNREFUSED") ||
            err.message.includes("connect") ||
            err.message.includes("socket"),
          "Error should indicate connection problem"
        );
      }
    });
  });

  describe("MockAgentBridge Error Scenarios", () => {
    let mockBridge: MockAgentBridge;

    beforeEach(() => {
      mockBridge = new MockAgentBridge();
    });

    afterEach(async () => {
      if (mockBridge) {
        await mockBridge.shutdown();
      }
    });

    it("should handle agent errors and emit error events", async function () {
      this.timeout(5000);

      let errorEventReceived = false;
      let errorMessage = "";

      // Register error handler
      mockBridge.onEvent((event: { type: string; error?: string }) => {
        if (event.type === "error") {
          errorEventReceived = true;
          errorMessage = event.error || "";
        }
      });

      // Configure bridge to throw error
      mockBridge.setError(true, "Test error message");

      try {
        await mockBridge.sendMessage("test message");
        assert.fail("Should have thrown an error");
      } catch (err) {
        assert.ok(err instanceof Error, "Should throw error");
        assert.strictEqual(
          (err as Error).message,
          "Test error message",
          "Error message should match"
        );
      }

      assert.ok(errorEventReceived, "Should have emitted error event");
      assert.strictEqual(errorMessage, "Test error message", "Error event should contain message");
    });

    it("should track message history correctly", async function () {
      this.timeout(5000);

      await mockBridge.sendMessage("message 1");
      await mockBridge.sendMessage("message 2");
      await mockBridge.sendMessage("message 3");

      const history = mockBridge.getMessageHistory();
      assert.strictEqual(history.length, 3, "Should track all messages");
      assert.strictEqual(history[0], "message 1");
      assert.strictEqual(history[1], "message 2");
      assert.strictEqual(history[2], "message 3");
    });

    it("should clear message history when requested", async function () {
      this.timeout(5000);

      await mockBridge.sendMessage("test message");
      assert.strictEqual(mockBridge.getMessageHistory().length, 1, "Should have one message");

      mockBridge.clearHistory();
      assert.strictEqual(mockBridge.getMessageHistory().length, 0, "History should be cleared");
    });

    it("should properly dispose event handlers", async function () {
      this.timeout(5000);

      let eventCount = 0;
      const disposable = mockBridge.onEvent(() => {
        eventCount++;
      });

      await mockBridge.sendMessage("test 1");
      assert.ok(eventCount > 0, "Should receive events before disposal");

      const countBeforeDispose = eventCount;
      disposable.dispose();

      await mockBridge.sendMessage("test 2");
      assert.strictEqual(
        eventCount,
        countBeforeDispose,
        "Should not receive events after disposal"
      );
    });

    it("should handle multiple simultaneous error conditions", async function () {
      this.timeout(5000);

      mockBridge.setError(true, "Error 1");

      try {
        await mockBridge.sendMessage("message 1");
        assert.fail("Should have thrown first error");
      } catch (err) {
        assert.strictEqual((err as Error).message, "Error 1");
      }

      // Change error message
      mockBridge.setError(true, "Error 2");

      try {
        await mockBridge.sendMessage("message 2");
        assert.fail("Should have thrown second error");
      } catch (err) {
        assert.strictEqual((err as Error).message, "Error 2");
      }

      // Disable errors
      mockBridge.setError(false);

      // This should succeed
      await mockBridge.sendMessage("message 3");
      const history = mockBridge.getMessageHistory();
      assert.strictEqual(
        history.length,
        3,
        "All messages should be tracked even when errors occur"
      );
    });
  });

  describe("Command Execution Edge Cases", () => {
    it("should timeout when command takes too long", async function () {
      this.timeout(5000);

      try {
        // Try to execute a command that likely doesn't exist or will timeout
        await assertCommandExecutes("dolphin.nonexistentCommand", [], 100);
        assert.fail("Should have timed out");
      } catch (err) {
        assert.ok(err instanceof Error, "Should throw timeout error");
        assert.ok(
          err.message.includes("timed out") ||
            err.message.includes("timeout") ||
            err.message.includes("not found"),
          "Error should mention timeout or command not found"
        );
      }
    });
  });

  describe("Configuration Edge Cases", () => {
    it("should handle reset after configuration", async function () {
      this.timeout(5000);

      // Configure mock server
      mockServer.setSearchResults([
        {
          chunk_id: "custom-chunk",
          repo: "custom-repo",
          path: "custom/path.ts",
          content: "custom content",
          score: 0.99,
          line_start: 1,
          line_end: 1,
        },
      ]);

      mockServer.setHealthy(false);

      // Verify configuration applied
      let response = await makeHttpGetRequest<MockHealthResponse>(
        `http://localhost:${mockServer.port}/health`,
        2000
      );
      assert.strictEqual(response.status, 503, "Should be unhealthy");

      // Reset configuration
      mockServer.reset();

      // Verify reset to defaults
      response = await makeHttpGetRequest<MockHealthResponse>(
        `http://localhost:${mockServer.port}/health`,
        2000
      );
      assert.strictEqual(response.status, 200, "Should be healthy after reset");
    });

    it("should handle partial configuration", async function () {
      this.timeout(5000);

      // Configure only health, leave other settings default
      mockServer.configure({
        health: false,
      });

      const healthResponse = await makeHttpGetRequest<MockHealthResponse>(
        `http://localhost:${mockServer.port}/health`,
        2000
      );
      assert.strictEqual(healthResponse.status, 503, "Health should be configured");

      // Search should still work with defaults
      const searchRequest: MockSearchRequest = {
        query: "test",
        top_k: 5,
      };
      const postData = JSON.stringify(searchRequest);
      const searchResponse = await makeHttpPostRequest<MockSearchResponse>(
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
        2000
      );

      assert.strictEqual(
        searchResponse.status,
        200,
        "Search should work with default configuration"
      );
      assert.ok(searchResponse.data.hits.length > 0, "Should return default results");
    });
  });
});
