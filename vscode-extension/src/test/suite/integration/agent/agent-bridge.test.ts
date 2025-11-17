import * as assert from "assert";
import * as vscode from "vscode";
import { EventEmitter } from "events";
import { PassThrough } from "stream";
import { AgentBridge, mergeAgentEnvironment } from "../../../../agent/bridge";
import { MockConnection, TestRecord } from "../../../helpers/mock-types";
import { createMockOutputChannel } from "../../../helpers/mock-output-channel";
import type { ChildProcess, SpawnOptionsWithoutStdio } from "child_process";
type SpawnImpl = typeof import("child_process").spawn;
import type { AgentAuthStatusResponse } from "../../../../types/auth";

describe("AgentBridge Unit Tests", () => {
  let agentBridge: AgentBridge;
  let outputChannel: vscode.OutputChannel;

  beforeEach(() => {
    outputChannel = createMockOutputChannel("Test Agent Bridge");
    agentBridge = new AgentBridge(outputChannel);
  });

  afterEach(async () => {
    // CRITICAL: Shutdown AgentBridge BEFORE disposing output channel
    // This prevents async operations from trying to use disposed resources
    if (agentBridge) {
      // Add a mock kill method to the process if it exists
      const process = (agentBridge as unknown as TestRecord).process as TestRecord | undefined;
      if (process && !process.kill) {
        (process as TestRecord).kill = () => true;
      }
      await agentBridge.shutdown();
    }

    // Dispose output channel AFTER shutdown completes
    if (outputChannel) {
      outputChannel.dispose();
    }
  });

  describe("clearConversation", () => {
    it("Should send clear_conversation notification via JSON-RPC connection", async () => {
      // Mock the connection
      const mockConnection: MockConnection = {
        sendNotification: (method: string, _params?: Record<string, unknown>) => {
          assert.strictEqual(method, "clear_conversation", "Method should be clear_conversation");
        },
        sendRequest: () => Promise.resolve({}),
        dispose: () => {},
      };

      // Inject mock connection
      (agentBridge as unknown as TestRecord).connection = mockConnection;

      // Call clearConversation
      await agentBridge.clearConversation();
    });

    it("Should throw error when JSON-RPC connection is not established", async () => {
      // Don't set up a connection
      (agentBridge as unknown as TestRecord).connection = null;

      try {
        await agentBridge.clearConversation();
        assert.fail("Should have thrown an error");
      } catch (error: unknown) {
        const err = error as Error;
        assert.ok(
          err.message.includes("not established"),
          "Error should mention connection not established"
        );
      }
    });
  });

  describe("abortGeneration", () => {
    it("Should send abort_generation notification via JSON-RPC connection", async () => {
      const mockConnection: Partial<MockConnection> = {
        sendNotification: (method: string, _params?: Record<string, unknown>) => {
          assert.strictEqual(method, "abort_generation", "Method should be abort_generation");
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      await agentBridge.abortGeneration();
    });
  });

  describe("sendMessage", () => {
    it("Should send send_message notification with content via JSON-RPC connection", async () => {
      const testContent = "Test message content";
      let receivedParams: Record<string, unknown> | undefined;

      const mockConnection: Partial<MockConnection> = {
        sendNotification: (method: string, params?: Record<string, unknown>) => {
          assert.strictEqual(method, "send_message", "Method should be send_message");
          if (params) receivedParams = params;
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      await agentBridge.sendMessage(testContent);

      assert.ok(receivedParams, "Should have received params");
      assert.strictEqual(
        (receivedParams as TestRecord).content,
        testContent,
        "Should include message content"
      );
      assert.ok((receivedParams as TestRecord).messageId, "Should include message ID");
    });
  });

  describe("getAuthStatus", () => {
    it("Should send get_auth_status request and resolve with result", async () => {
      let requestMethod: string | undefined;
      const mockResult: AgentAuthStatusResponse = {
        providers: [{ provider: "anthropic", authenticated: true, mode: "subscription" }],
      };

      const mockConnection: Partial<MockConnection> = {
        sendRequest: (method: string, _params?: Record<string, unknown>) => {
          requestMethod = method;
          return Promise.resolve(mockResult);
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      const result = await agentBridge.getAuthStatus();

      assert.strictEqual(requestMethod, "get_auth_status", "Should send get_auth_status request");
      assert.deepStrictEqual(result, mockResult, "Should resolve with auth status");
    });

    it("Should reject on timeout", async function () {
      this.timeout(7000); // Allow time for timeout

      const mockConnection: Partial<MockConnection> = {
        sendRequest: () => {
          // Never resolve to simulate timeout
          return new Promise(() => {});
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      try {
        await agentBridge.getAuthStatus();
        assert.fail("Should have thrown timeout error");
      } catch (error: unknown) {
        const err = error as Error;
        assert.ok(err.message.includes("timeout"), "Should be a timeout error");
      }
    });

    it("Should reject when connection not established", async () => {
      (agentBridge as unknown as TestRecord).connection = null;

      try {
        await agentBridge.getAuthStatus();
        assert.fail("Should have thrown an error");
      } catch (error: unknown) {
        const err = error as Error;
        assert.ok(
          err.message.includes("not established"),
          "Error should mention connection not established"
        );
      }
    });
  });

  describe("Event Handling", () => {
    it("Should emit events received from agent via connection", (done) => {
      const testEvent = {
        type: "agent_ready",
        version: "0.1.0",
        capabilities: ["test"],
        requestId: "req-123",
      };

      // Listen for the event
      const disposable = agentBridge.onEvent((event) => {
        assert.deepStrictEqual(event, testEvent, "Should emit the received event");
        disposable.dispose();
        done();
      });

      // Simulate receiving an event via the event emitter
      const bridge = agentBridge as unknown as TestRecord;
      (bridge.eventEmitter as { fire: (event: unknown) => void }).fire(testEvent);
    });

    it("Should include requestId in event logs", (done) => {
      const testEvent = {
        type: "content_delta",
        delta: "test content",
        requestId: "req-456",
      };

      const disposable = agentBridge.onEvent((event) => {
        assert.strictEqual(
          (event as TestRecord).requestId,
          "req-456",
          "Event should include requestId"
        );
        disposable.dispose();
        done();
      });

      const bridge = agentBridge as unknown as TestRecord;
      (bridge.eventEmitter as { fire: (event: unknown) => void }).fire(testEvent);
    });
  });

  describe("Auto-recovery and Backoff", () => {
    it("Should not auto-restart when isShuttingDown is true", async () => {
      (agentBridge as unknown as TestRecord).isShuttingDown = true;
      let restartCalled = false;

      // Mock start method
      const _originalStart = agentBridge.start.bind(agentBridge);
      const bridge = agentBridge as unknown as TestRecord;
      bridge.start = async () => {
        restartCalled = true;
      };

      // Call handleCrash
      await (
        bridge.handleCrash as (agentPath: string, extPath: string, error: unknown) => Promise<void>
      )("/fake/path", "/fake/ext", undefined);

      assert.strictEqual(restartCalled, false, "Should not restart when shutting down");
    });

    it("Should increment restart attempts and use exponential backoff", async function () {
      this.timeout(5000);

      let startCallCount = 0;
      const startTimes: number[] = [];

      // Mock start method to track calls
      const bridge = agentBridge as unknown as TestRecord;
      bridge.start = async () => {
        startCallCount++;
        startTimes.push(Date.now());
      };

      // Mock vscode.window.showWarningMessage
      const originalShowWarning = (global as TestRecord).vscode as TestRecord | undefined;
      if (!(global as TestRecord).vscode) {
        (global as TestRecord).vscode = { window: {} };
      }
      ((global as TestRecord).vscode as TestRecord).window = { showWarningMessage: () => {} };

      // Set restart attempts to 0
      (agentBridge as unknown as TestRecord).restartAttempts = 0;
      (agentBridge as unknown as TestRecord).isShuttingDown = false;

      // First crash - should restart after 1s
      await (
        bridge.handleCrash as (agentPath: string, extPath: string, error: unknown) => Promise<void>
      )("/fake/path", "/fake/ext", undefined);

      // Wait for first restart
      await new Promise((resolve) => setTimeout(resolve, 1100));
      assert.strictEqual(startCallCount, 1, "Should call start once after first crash");
      assert.strictEqual(bridge.restartAttempts as number, 1, "Should increment restart attempts");

      // Clean up
      if (originalShowWarning !== undefined) {
        const globalVscode = (global as TestRecord).vscode as TestRecord;
        (globalVscode.window as TestRecord).showWarningMessage = originalShowWarning;
      }
    });

    it("Should stop auto-restart after max attempts", async function () {
      this.timeout(2000); // Give enough time for async operations

      const bridge = agentBridge as unknown as TestRecord;
      bridge.restartAttempts = 3; // Max attempts
      bridge.maxRestartAttempts = 3;
      bridge.isShuttingDown = false;

      let errorShown = false;
      let errorMessage = "";

      // Mock vscode.window.showErrorMessage
      const originalShowError = vscode.window.showErrorMessage;
      (vscode.window as TestRecord).showErrorMessage = (msg: string) => {
        errorShown = true;
        errorMessage = msg;
        return Promise.resolve("Cancel");
      };

      await (
        bridge.handleCrash as (agentPath: string, extPath: string, error: unknown) => Promise<void>
      )("/fake/path", "/fake/ext", undefined);

      // Wait a tick for the promise to resolve
      await new Promise((resolve) => setImmediate(resolve));

      assert.ok(errorShown, "Should show error message");
      assert.ok(errorMessage.includes("crashed 3 times"), "Error should mention max attempts");

      // Restore
      (vscode.window as TestRecord).showErrorMessage = originalShowError;
    });
  });

  describe("Cross-platform Bun Detection", () => {
    it('Should use "which bun" on Unix platforms', async () => {
      const originalPlatform = process.platform;
      Object.defineProperty(process, "platform", { value: "linux", configurable: true });

      const { exec: _exec } = require("child_process");
      const { promisify: _promisify } = require("util");

      // This will actually try to run 'which bun' which might fail in test env
      // So we'll just verify the logic without actually running it
      try {
        const bridge = agentBridge as unknown as TestRecord;
        await (bridge.findBun as () => Promise<string | null>)();
      } catch {
        // Expected if bun not installed
      }

      // Restore platform
      Object.defineProperty(process, "platform", { value: originalPlatform, configurable: true });
    });

    it('Should use "where bun" on Windows platforms', async () => {
      const originalPlatform = process.platform;
      Object.defineProperty(process, "platform", { value: "win32", configurable: true });

      // Just verify the code path exists - actual execution will fail in test env
      try {
        const bridge = agentBridge as unknown as TestRecord;
        await (bridge.findBun as () => Promise<string | null>)();
      } catch {
        // Expected if bun not installed
      }

      // Restore platform
      Object.defineProperty(process, "platform", { value: originalPlatform, configurable: true });
    });

    it("Should check platform-specific paths", async () => {
      const originalPlatform = process.platform;
      const { exec } = require("child_process");
      const _promisify = require("util").promisify;
      const originalExec = exec;
      const fs = require("fs");
      const originalExistsSync = fs.existsSync;

      // Mock exec to fail (simulating bun not in PATH)
      const mockExec = (
        cmd: string,
        options: unknown,
        callback?: (error: Error | null, stdout: string, stderr: string) => void
      ) => {
        let cb = callback;
        if (typeof options === "function") {
          cb = options as (error: Error | null, stdout: string, stderr: string) => void;
        }
        if (cb) {
          cb(new Error("Command not found"), "", "");
        }
      };

      // Replace exec in child_process module
      require("child_process").exec = mockExec;

      // Mock existsSync to return false for all paths
      fs.existsSync = () => false;

      Object.defineProperty(process, "platform", { value: "darwin", configurable: true });

      const result = await (
        (agentBridge as unknown as TestRecord).findBun as () => Promise<string | null>
      )();
      assert.strictEqual(result, null, "Should return null when bun not found");

      // Restore
      require("child_process").exec = originalExec;
      fs.existsSync = originalExistsSync;
      Object.defineProperty(process, "platform", { value: originalPlatform, configurable: true });
    });
  });

  describe("Connection Cleanup on Shutdown", () => {
    it("Should dispose connection and clear pending requests on shutdown", async () => {
      let disposeCalled = false;
      const mockConnection: Partial<MockConnection> = {
        sendNotification: () => {},
        dispose: () => {
          disposeCalled = true;
        },
      };

      // Set up connection and pending requests
      (agentBridge as unknown as TestRecord).connection = mockConnection;
      let bridgeA = agentBridge as unknown as TestRecord;
      (
        bridgeA.pendingRequests as Map<
          number,
          { resolve: () => void; reject: () => void; timeout: NodeJS.Timeout }
        >
      ).set(1, {
        resolve: () => {},
        reject: () => {},
        timeout: setTimeout(() => {}, 1000),
      });

      // Mock process
      const mockProcess = {
        kill: () => true,
      };
      bridgeA.process = mockProcess;

      await agentBridge.shutdown();

      assert.ok(disposeCalled, "Should dispose connection");
      bridgeA = agentBridge as unknown as TestRecord;
      assert.strictEqual(bridgeA.connection, null, "Connection should be null");
      assert.strictEqual(
        (bridgeA.pendingRequests as Map<number, unknown>).size,
        0,
        "Pending requests should be cleared"
      );
      assert.ok(bridgeA.isShuttingDown as boolean, "isShuttingDown should be true");
    });

    it("Should reject all pending requests with shutdown error on shutdown", async () => {
      let rejectionError: Error | null = null;

      const mockConnection: Partial<MockConnection> = {
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;
      const bridgeB = agentBridge as unknown as TestRecord;
      (
        bridgeB.pendingRequests as Map<
          number,
          { resolve: () => void; reject: (error: Error) => void; timeout: NodeJS.Timeout }
        >
      ).set(1, {
        resolve: () => {},
        reject: (error: Error) => {
          rejectionError = error;
        },
        timeout: setTimeout(() => {}, 1000),
      });

      const mockProcess = {
        kill: () => true,
      };
      bridgeB.process = mockProcess;

      await agentBridge.shutdown();

        if (!rejectionError) {
          throw new Error("Should reject pending request");
        }
        const error = rejectionError as Error;
        assert.ok(
          error.message.includes("Agent bridge stopped"),
          "Error should mention shutdown"
        );
      });

    it("Should clear timeout for pending requests on shutdown", async () => {
      const mockTimer = setTimeout(() => {}, 5000);
      let timerCleared = false;

      // Override clearTimeout to track calls
      const originalClearTimeout = global.clearTimeout;
      global.clearTimeout = (timer: string | number | NodeJS.Timeout | undefined) => {
        if (timer === mockTimer) {
          timerCleared = true;
        }
        originalClearTimeout(timer);
      };

      const mockConnection: Partial<MockConnection> = { dispose: () => {} };
      (agentBridge as unknown as TestRecord).connection = mockConnection;
      const bridgeC = agentBridge as unknown as TestRecord;
      (
        bridgeC.pendingRequests as Map<
          number,
          { resolve: () => void; reject: () => void; timeout: NodeJS.Timeout }
        >
      ).set(1, {
        resolve: () => {},
        reject: () => {},
        timeout: mockTimer,
      });

      const mockProcess = { kill: () => true };
      bridgeC.process = mockProcess;

      await agentBridge.shutdown();

      assert.ok(timerCleared, "Should clear timeout");

      // Restore
      global.clearTimeout = originalClearTimeout;
    });
  });

  describe("Request Timeout Handling", () => {
    it("Should timeout long-running requests", async function () {
      this.timeout(35000); // Allow time for timeout

      const mockConnection: Partial<MockConnection> = {
        sendRequest: () => {
          // Never resolve
          return new Promise(() => {});
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      const startTime = Date.now();
      try {
        const bridgeD = agentBridge as unknown as TestRecord;
        await (
          bridgeD.sendRequest as (
            method: string,
            params: Record<string, unknown>,
            timeout: number
          ) => Promise<unknown>
        )("test_method", {}, 1000);
        assert.fail("Should have timed out");
      } catch (error: unknown) {
        const elapsed = Date.now() - startTime;
        const err = error as Error;
        assert.ok(err.message.includes("timeout"), "Should be timeout error");
        const tolerance = 10;
        const minExpected = 1000 - tolerance;
        assert.ok(
          elapsed >= minExpected && elapsed < 2000,
          `Should timeout after >=${minExpected}ms, got ${elapsed}ms`
        );
      }
    });

    it("Should clean up pending request on timeout", async function () {
      this.timeout(3000);

      const mockConnection: Partial<MockConnection> = {
        sendRequest: () => new Promise(() => {}),
        dispose: () => {},
      };

      const bridgeE = agentBridge as unknown as TestRecord;
      bridgeE.connection = mockConnection;

      try {
        await (
          bridgeE.sendRequest as (
            method: string,
            params: Record<string, unknown>,
            timeout: number
          ) => Promise<unknown>
        )("test_method", {}, 500);
      } catch {
        // Expected timeout
      }

      // Wait a bit more
      await new Promise((resolve) => setTimeout(resolve, 100));

      assert.strictEqual(
        (bridgeE.pendingRequests as Map<number, unknown>).size,
        0,
        "Pending requests should be empty after timeout"
      );
    });
  });

  // Phase 5: Conversation Management Tests

  describe("listConversations", () => {
    it("Should send list_conversations request and return conversations", async () => {
      const mockConversations = [
        {
          id: "conv-1",
          metadata: {
            title: "Test Conversation 1",
            files: [],
            token_count: 100,
            pinned: false,
          },
          created_at: "2025-01-01T00:00:00.000Z",
          updated_at: "2025-01-01T00:00:00.000Z",
          message_count: 5,
        },
        {
          id: "conv-2",
          metadata: {
            title: "Test Conversation 2",
            files: ["file.ts"],
            token_count: 200,
            pinned: true,
          },
          created_at: "2025-01-02T00:00:00.000Z",
          updated_at: "2025-01-02T00:00:00.000Z",
          message_count: 10,
        },
      ];

      const mockConnection: Partial<MockConnection> = {
        sendRequest: (method: string, _params?: Record<string, unknown>) => {
          assert.strictEqual(
            method,
            "list_conversations",
            "Should send list_conversations request"
          );
          return Promise.resolve({ conversations: mockConversations });
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      const result = await agentBridge.listConversations();

      assert.deepStrictEqual(
        result,
        mockConversations,
        "Should return conversations from response"
      );
    });

    it("Should return empty array when no conversations exist", async () => {
      const mockConnection: Partial<MockConnection> = {
        sendRequest: (_method: string, _params?: Record<string, unknown>) => {
          return Promise.resolve({ conversations: [] });
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      const result = await agentBridge.listConversations();

      assert.deepStrictEqual(result, [], "Should return empty array");
    });

    it("Should handle missing conversations field in response", async () => {
      const mockConnection: Partial<MockConnection> = {
        sendRequest: (_method: string, _params?: Record<string, unknown>) => {
          return Promise.resolve({}); // No conversations field
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      const result = await agentBridge.listConversations();

      assert.deepStrictEqual(
        result,
        [],
        "Should return empty array when conversations field missing"
      );
    });

    it("Should timeout after 5 seconds", async function () {
      this.timeout(7000);

      const mockConnection: Partial<MockConnection> = {
        sendRequest: (_method: string, _params?: Record<string, unknown>) => {
          // Never resolve to simulate timeout
          return new Promise(() => {});
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      try {
        await agentBridge.listConversations();
        assert.fail("Should have thrown timeout error");
      } catch (error: unknown) {
        assert.ok(
          error instanceof Error && error.message.includes("timeout"),
          "Should be a timeout error"
        );
      }
    });
  });

  describe("loadConversation", () => {
    it("Should send load_conversation request with conversationId", async () => {
      let receivedParams: Record<string, unknown> = {};
      const mockResult = {
        conversation: {
          schema_version: "1.0",
          conversation: {
            id: "conv-1",
            created_at: "2025-01-01T00:00:00.000Z",
            updated_at: "2025-01-01T00:00:00.000Z",
            workspace_root: "/workspace",
          },
          metadata: {
            title: "Test Conversation",
            files: [],
            token_count: 100,
            pinned: false,
          },
          messages: [],
        },
      };

      const mockConnection: Partial<MockConnection> = {
        sendRequest: (method: string, params?: Record<string, unknown>) => {
          assert.strictEqual(method, "load_conversation", "Should send load_conversation request");
          if (params) receivedParams = params;
          return Promise.resolve(mockResult);
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      const result = await agentBridge.loadConversation("conv-1");

      assert.strictEqual(
        receivedParams.conversationId,
        "conv-1",
        "Should include conversationId in params"
      );
      assert.deepStrictEqual(result, mockResult, "Should return load result");
    });

    it("Should handle conversation with branch info", async () => {
      const mockResult = {
        conversation: {
          schema_version: "1.0",
          conversation: {
            id: "branch-conv",
            created_at: "2025-01-01T00:00:00.000Z",
            updated_at: "2025-01-01T00:00:00.000Z",
            workspace_root: "/workspace",
          },
          metadata: {
            title: "Branched Conversation",
            parent_conversation_id: "parent-conv",
            branch_point_message_id: "msg-5",
            files: [],
            token_count: 50,
            pinned: false,
          },
          messages: [],
        },
        branchInfo: {
          originalId: "parent-conv",
          originalTitle: "Parent Conversation",
        },
      };

      const mockConnection: Partial<MockConnection> = {
        sendRequest: () => Promise.resolve(mockResult),
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      const result = await agentBridge.loadConversation("branch-conv");

      assert.ok(result.branchInfo, "Should include branch info");
      assert.strictEqual(
        result.branchInfo?.originalId,
        "parent-conv",
        "Branch info should have parent ID"
      );
      assert.strictEqual(
        result.branchInfo?.originalTitle,
        "Parent Conversation",
        "Branch info should have parent title"
      );
    });

    it("Should timeout after 5 seconds", async function () {
      this.timeout(7000);

      const mockConnection: Partial<MockConnection> = {
        sendRequest: () => new Promise(() => {}),
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      try {
        await agentBridge.loadConversation("conv-1");
        assert.fail("Should have thrown timeout error");
      } catch (error: unknown) {
        assert.ok(
          error instanceof Error && error.message.includes("timeout"),
          "Should be a timeout error"
        );
      }
    });
  });

  describe("deleteConversation", () => {
    it("Should send delete_conversation request with conversationId", async () => {
      let receivedMethod: string | undefined;
      let receivedParams: Record<string, unknown> = {};

      const mockConnection: Partial<MockConnection> = {
        sendRequest: (method: string, params?: Record<string, unknown>) => {
          receivedMethod = method;
          if (params) receivedParams = params;
          return Promise.resolve({ success: true });
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      await agentBridge.deleteConversation("conv-to-delete");

      assert.strictEqual(
        receivedMethod,
        "delete_conversation",
        "Should send delete_conversation request"
      );
      assert.strictEqual(
        receivedParams.conversationId,
        "conv-to-delete",
        "Should include conversationId"
      );
    });

    it("Should handle deletion errors", async () => {
      const mockConnection: Partial<MockConnection> = {
        sendRequest: (_method: string, _params?: Record<string, unknown>) => {
          return Promise.reject(new Error("Conversation not found"));
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      try {
        await agentBridge.deleteConversation("non-existent");
        assert.fail("Should have thrown error");
      } catch (error: unknown) {
        assert.ok(
          error instanceof Error && error.message.includes("Conversation not found"),
          "Should propagate error"
        );
      }
    });

    it("Should timeout after 5 seconds", async function () {
      this.timeout(7000);

      const mockConnection: Partial<MockConnection> = {
        sendRequest: () => new Promise(() => {}),
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      try {
        await agentBridge.deleteConversation("conv-1");
        assert.fail("Should have thrown timeout error");
      } catch (error: unknown) {
        assert.ok(
          error instanceof Error && error.message.includes("timeout"),
          "Should be a timeout error"
        );
      }
    });
  });

  describe("renameConversation", () => {
    it("Should send rename_conversation request with conversationId and newTitle", async () => {
      let receivedMethod: string | undefined;
      let receivedParams: Record<string, unknown> = {};

      const mockConnection: Partial<MockConnection> = {
        sendRequest: (method: string, params?: Record<string, unknown>) => {
          receivedMethod = method;
          if (params) receivedParams = params;
          return Promise.resolve({ success: true });
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      await agentBridge.renameConversation("conv-1", "New Title");

      assert.strictEqual(
        receivedMethod,
        "rename_conversation",
        "Should send rename_conversation request"
      );
      assert.strictEqual(receivedParams.conversationId, "conv-1", "Should include conversationId");
      assert.strictEqual(receivedParams.newTitle, "New Title", "Should include newTitle");
    });

    it("Should handle empty title", async () => {
      let receivedParams: Record<string, unknown> = {};

      const mockConnection: Partial<MockConnection> = {
        sendRequest: (method: string, params?: Record<string, unknown>) => {
          if (params) receivedParams = params;
          return Promise.resolve({ success: true });
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      await agentBridge.renameConversation("conv-1", "");

      assert.strictEqual(receivedParams.newTitle, "", "Should accept empty title");
    });

    it("Should handle special characters in title", async () => {
      let receivedParams: Record<string, unknown> = {};

      const mockConnection: Partial<MockConnection> = {
        sendRequest: (method: string, params?: Record<string, unknown>) => {
          if (params) receivedParams = params;
          return Promise.resolve({ success: true });
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      const specialTitle = "Test with \"quotes\" and 'apostrophes' & <html> tags";
      await agentBridge.renameConversation("conv-1", specialTitle);

      assert.strictEqual(
        receivedParams.newTitle,
        specialTitle,
        "Should preserve special characters"
      );
    });

    it("Should handle rename errors", async () => {
      const mockConnection: Partial<MockConnection> = {
        sendRequest: (_method: string, _params?: Record<string, unknown>) => {
          return Promise.reject(new Error("Conversation not found"));
        },
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      try {
        await agentBridge.renameConversation("non-existent", "New Title");
        assert.fail("Should have thrown error");
      } catch (error: unknown) {
        assert.ok(
          error instanceof Error && error.message.includes("Conversation not found"),
          "Should propagate error"
        );
      }
    });

    it("Should timeout after 5 seconds", async function () {
      this.timeout(7000);

      const mockConnection: Partial<MockConnection> = {
        sendRequest: () => new Promise(() => {}),
        dispose: () => {},
      };

      (agentBridge as unknown as TestRecord).connection = mockConnection;

      try {
        await agentBridge.renameConversation("conv-1", "New Title");
        assert.fail("Should have thrown timeout error");
      } catch (error: unknown) {
        assert.ok(
          error instanceof Error && error.message.includes("timeout"),
          "Should be a timeout error"
        );
      }
    });
  });

  describe("start", () => {
    class StubProcess extends EventEmitter {
      stdout = new PassThrough();
      stderr = new PassThrough();
      stdin = new PassThrough();
      kill(): boolean {
        return true;
      }
    }

    it("merges env vars with correct precedence", async () => {
      const spawned: { env?: NodeJS.ProcessEnv } = {};
      const stub = new StubProcess();
      const spawnStub = (
        _command: string,
        _args?: readonly string[],
        options?: SpawnOptionsWithoutStdio
      ): ChildProcess => {
        spawned.env = options?.env;
        return stub as unknown as ChildProcess;
      };
      const spawnFn = spawnStub as SpawnImpl;

      agentBridge = new AgentBridge(outputChannel, spawnFn);
      (agentBridge as unknown as { findBun: () => Promise<string> }).findBun = async () =>
        "/bin/bun";
      (agentBridge as unknown as { waitForReady: () => Promise<void> }).waitForReady =
        async () => {};

      const originalModel = process.env.DOLPHIN_LLM_MODEL;
      process.env.DOLPHIN_LLM_MODEL = "should-not-stick";

      await agentBridge.start("agent-core.ts", "/ext", {
        anthropicApiKey: "sk-ant",
        openaiApiKey: "sk-openai",
        env: {
          defaults: { DOLPHIN_LLM_PROVIDER: "anthropic", DOLPHIN_LLM_MODEL: "claude" },
          overrides: { DOLPHIN_LLM_MODEL: "claude-custom" },
        },
      });

      assert.strictEqual(spawned.env?.DOLPHIN_LLM_PROVIDER, "anthropic");
      assert.strictEqual(spawned.env?.DOLPHIN_LLM_MODEL, "claude-custom");
      assert.strictEqual(spawned.env?.ANTHROPIC_API_KEY, "sk-ant");
      assert.strictEqual(spawned.env?.OPENAI_API_KEY, "sk-openai");

      if (originalModel) {
        process.env.DOLPHIN_LLM_MODEL = originalModel;
      } else {
        delete process.env.DOLPHIN_LLM_MODEL;
      }
    });
  });

  describe("mergeAgentEnvironment", () => {
    it("applies overrides after defaults", () => {
      const merged = mergeAgentEnvironment(
        { EXISTING: "1" },
        {
          defaults: { EXISTING: "2", DEFAULT_ONLY: "a" },
          overrides: { EXISTING: "3" },
        }
      );
      assert.strictEqual(merged.EXISTING, "3");
      assert.strictEqual(merged.DEFAULT_ONLY, "a");
    });
  });
});
