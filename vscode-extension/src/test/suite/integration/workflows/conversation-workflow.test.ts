import * as assert from "assert";
import {
  activateExtension,
  assertCommandsExist,
  waitForCondition,
} from "../../../helpers/shared-fixtures";
import {
  configureMockAgent,
  getMockEnvironment,
  resetMocks,
  setupMockEnvironment,
  teardownMockEnvironment,
} from "../../../helpers/mock-manager";
import { TEST_COMMANDS, TEST_TIMEOUTS } from "../../../helpers/test-constants";
import { AgentEvent } from "../../../helpers/mock-types";

/**
 * Conversation flows using mock agent bridge.
 * Runs in the integration suite (no real services or VS Code UI required).
 */
describe("Conversation Workflow (integration)", function () {
  this.timeout(40000);

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

  it("Registers conversation commands", async () => {
    await assertCommandsExist([
      TEST_COMMANDS.FOCUS_INPUT,
      TEST_COMMANDS.NEW_CONVERSATION,
      TEST_COMMANDS.ASK_ABOUT_SELECTION,
      TEST_COMMANDS.ASK_ABOUT_FILE,
      TEST_COMMANDS.ASK_ABOUT_FOLDER,
    ]);
  });

  it("Streams mock agent responses", async () => {
    const { agentBridge } = getMockEnvironment();
    const receivedEvents: AgentEvent[] = [];

    configureMockAgent({ response: "Hello from mock agent" });

    agentBridge.onEvent((event) => {
      receivedEvents.push(event);
    });

    await agentBridge.sendMessage("Hi", "code");

    await waitForCondition(() => receivedEvents.some((e) => e.type === "task_completed"), {
      timeout: TEST_TIMEOUTS.AGENT_RESPONSE,
      timeoutMessage: "Mock agent did not complete task",
    });

    const chunks = receivedEvents.filter((e) => e.type === "message_chunk");
    assert.ok(chunks.length > 0, "Should receive streamed message chunks");
    assert.ok(
      chunks.some((chunk) => String(chunk.content).includes("mock agent")),
      "Mock response should be surfaced"
    );
  });

  it("Emits tool call lifecycle events", async () => {
    const { agentBridge } = getMockEnvironment();
    const toolEvents: AgentEvent[] = [];

    configureMockAgent({
      toolCalls: [
        {
          name: "kb.search",
          args: { query: "test" },
        },
      ],
    });

    agentBridge.onEvent((event) => toolEvents.push(event));

    await agentBridge.sendMessage("Search for context", "code");

    await waitForCondition(
      () =>
        toolEvents.some((e) => e.type === "tool_call_started") &&
        toolEvents.some((e) => e.type === "tool_call_completed"),
      {
        timeout: TEST_TIMEOUTS.AGENT_RESPONSE,
        timeoutMessage: "Tool call events were not emitted",
      }
    );

    const completed = toolEvents.find((e) => e.type === "tool_call_completed");
    assert.ok(completed, "Tool call completion event should be present");
    assert.strictEqual((completed as AgentEvent & { name?: string }).name, "kb.search");
  });

  it("Surfaces agent errors to callers", async () => {
    const { agentBridge } = getMockEnvironment();

    configureMockAgent({ shouldError: true, error: new Error("planned failure") });

    await assert.rejects(agentBridge.sendMessage("boom", "code"), /planned failure/);
    assert.deepStrictEqual(agentBridge.getMessageHistory(), ["boom"], "Message history tracked");
  });
});
