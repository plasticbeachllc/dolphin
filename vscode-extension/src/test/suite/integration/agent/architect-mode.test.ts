import * as assert from "assert";
import {
  configureMockAgent,
  getMockEnvironment,
  resetMocks,
  setupMockEnvironment,
  teardownMockEnvironment,
} from "../../../helpers/mock-manager";
import { waitForCondition } from "../../../helpers/shared-fixtures";
import { AgentEvent } from "../../../helpers/mock-types";

/**
 * Architect mode tests using the mock agent bridge.
 */
describe("Architect Mode E2E Tests", function () {
  this.timeout(30000);

  before(async () => {
    await setupMockEnvironment();
  });

  after(async () => {
    await teardownMockEnvironment();
  });

  beforeEach(() => {
    resetMocks();
  });

  it("Emits discovery results for architect prompts", async () => {
    const { agentBridge } = getMockEnvironment();
    const received: AgentEvent[] = [];

    configureMockAgent({ response: "Discovery Results: authentication" });
    agentBridge.onEvent((event) => received.push(event));

    await agentBridge.sendMessage("How is auth implemented?", "architect");

    await waitForCondition(() => received.some((e) => e.type === "task_completed"), {
      timeout: 10000,
      timeoutMessage: "Architect mode did not complete",
    });

    const content = received
      .filter((e) => e.type === "content_delta" || e.type === "message_chunk")
      .map((e) => (e as AgentEvent & { content?: string; delta?: string }).content ?? e.delta)
      .join(" ");

    assert.ok(content.includes("Discovery Results"), "Should surface discovery output");
  });

  it("Includes tool call events during architect runs", async () => {
    const { agentBridge } = getMockEnvironment();
    const toolEvents: AgentEvent[] = [];

    configureMockAgent({
      toolCalls: [{ name: "kb.search", args: { query: "architecture" } }],
    });

    agentBridge.onEvent((event) => toolEvents.push(event));

    await agentBridge.sendMessage("Show architecture context", "architect");

    await waitForCondition(
      () =>
        toolEvents.some((e) => e.type === "tool_call_started") &&
        toolEvents.some((e) => e.type === "tool_call_completed"),
      { timeout: 10000, timeoutMessage: "Tool call lifecycle not emitted" }
    );

    const started = toolEvents.find((e) => e.type === "tool_call_started");
    const completed = toolEvents.find((e) => e.type === "tool_call_completed");

    assert.ok(started, "Should emit tool_call_started");
    assert.ok(completed, "Should emit tool_call_completed");
  });
});
