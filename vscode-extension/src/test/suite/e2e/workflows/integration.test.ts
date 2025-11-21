import * as assert from "assert";
import * as vscode from "vscode";
import {
  activateExtension,
  assertCommandsExist,
  waitForCondition,
} from "../../../helpers/shared-fixtures";
import {
  configureMockKB,
  getMockEnvironment,
  resetMocks,
  setupMockEnvironment,
  teardownMockEnvironment,
} from "../../../helpers/mock-manager";
import { TEST_COMMANDS, TEST_TIMEOUTS } from "../../../helpers/test-constants";
import {
  MockHealthResponse,
  MockSearchRequest,
  MockSearchResponse,
  MockSearchResult,
} from "../../../helpers/mock-types";
import { makeHttpGetRequest, makeHttpPostRequest } from "../../../helpers/test-utils";

/**
 * Integration tests that exercise the extension against the mock KB server.
 */
describe("Integration Tests", function () {
  this.timeout(20000);

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

  it("Starts mock KB server and responds to health checks", async () => {
    const { kbServer } = getMockEnvironment();
    configureMockKB({ health: true });

    const response = await makeHttpGetRequest<MockHealthResponse>(
      `http://localhost:${kbServer.port}/health`,
      3000
    );

    assert.strictEqual(response.status, 200, "Health check should succeed");
    assert.strictEqual(response.data.status, "ok", "Health status should be ok");
    assert.strictEqual(response.data.mock, true, "Mock flag should be present");
  });

  it("Serves configured search results", async () => {
    const { kbServer } = getMockEnvironment();

    const mockResults: MockSearchResult[] = [
      {
        chunk_id: "search-1",
        repo: "test-repo",
        path: "file.ts",
        content: "console.log('hello')",
        score: 0.99,
        line_start: 1,
        line_end: 3,
      },
    ];

    configureMockKB({ searchResults: mockResults });

    const request: MockSearchRequest = { query: "hello", top_k: 5 };
    const response = await makeHttpPostRequest<MockSearchResponse>(
      {
        hostname: "localhost",
        port: kbServer.port,
        path: "/search",
        headers: {
          "Content-Type": "application/json",
        },
      },
      JSON.stringify(request),
      3000
    );

    assert.strictEqual(response.status, 200, "Search should return success");
    assert.strictEqual(response.data.complete, true, "Search should mark completion");
    assert.deepStrictEqual(
      response.data.hits,
      mockResults,
      "Results should match configured mocks"
    );
  });

  it("Registers extension commands before invoking KB", async () => {
    await assertCommandsExist([TEST_COMMANDS.KB_SHOW_STATUS, TEST_COMMANDS.KB_RESTART]);

    await assertCommandsExist([TEST_COMMANDS.FOCUS_INPUT, TEST_COMMANDS.NEW_CONVERSATION]);
  });

  it("Logs KB requests when commands interact with the API", async () => {
    const { kbServer } = getMockEnvironment();
    const initialHistoryLength = kbServer.getRequestHistory().length;

    await vscode.commands.executeCommand(TEST_COMMANDS.KB_SHOW_STATUS);

    await waitForCondition(() => kbServer.getRequestHistory().length > initialHistoryLength, {
      timeout: TEST_TIMEOUTS.KB_STARTUP,
      timeoutMessage: "KB commands did not trigger HTTP traffic",
    });

    const history = kbServer.getRequestHistory();
    assert.ok(history.length > initialHistoryLength, "Requests should be recorded");
    assert.ok(
      history.every((entry) => entry.url),
      "Each request should have URL metadata"
    );
  });
});
