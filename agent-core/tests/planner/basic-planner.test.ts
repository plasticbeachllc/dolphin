// agent-core/tests/planner/basic-planner.test.ts
import { describe, it, expect, beforeAll } from "bun:test";
import { BasicPlanner } from "../../src/planner/basic-planner";
import { ClaudeClient } from "../../src/llm/claude-client";
import type { AgentEvent } from "../../../shared/types/events";

describe("BasicPlanner Integration Tests", () => {
  let client: ClaudeClient;
  let planner: BasicPlanner;

  beforeAll(() => {
    client = new ClaudeClient({
      authMode: "auto",
      model: "claude-sonnet-4-20250514",
      maxTokens: 1000, // Lower for faster tests
      temperature: 1.0,
    });

    planner = new BasicPlanner(client, {
      enableStreaming: true,
      maxTokens: 1000,
    });
  });

  it(
    "should process a simple message and emit events",
    async () => {
      const events: AgentEvent[] = [];

      try {
        await planner.processMessage(
        {
          userMessage: "What is the Dolphin project?",
        },
        (event) => {
          events.push(event);
          console.log(`Event: ${event.type}`);
          if (event.type === "content_delta") {
            process.stdout.write(event.delta);
          }
        }
        );

        console.log("\n\n✅ Test completed");
        console.log(`📊 Total events emitted: ${events.length}`);

        // Verify we got content deltas
        const contentDeltas = events.filter((e) => e.type === "content_delta");
        expect(contentDeltas.length).toBeGreaterThan(0);

        // Verify we got task completed
        const taskCompleted = events.find((e) => e.type === "task_completed");
        expect(taskCompleted).toBeDefined();
        expect((taskCompleted as any).success).toBe(true);

        console.log("✅ All assertions passed");
      } catch (error: any) {
        if (error.message.includes("No authentication configured")) {
          console.log("⚠️  Test skipped: No authentication configured");
          console.log("   This is expected if you haven't set up Claude CLI or API key");
          return;
        }
        throw error;
      }
    },
    { timeout: 10000 } // Increased from default 5000ms to 10000ms for API calls
  );

  it(
    "should handle KB context in prompt",
    async () => {
      const events: AgentEvent[] = [];
      const kbContext = `
# Knowledge Bank Results

## kb/api/app.py (lines 45-60)
\`\`\`python
def search_endpoint(query: str):
    results = kb.search(query)
    return results
\`\`\`
`;

    try {
      await planner.processMessage(
        {
          userMessage: "How does the KB search work?",
          kbResults: kbContext,
        },
        (event) => {
          events.push(event);
          if (event.type === "content_delta") {
            process.stdout.write(event.delta);
          }
        }
        );

        console.log("\n\n✅ KB context test completed");

        const contentDeltas = events.filter((e) => e.type === "content_delta");
        expect(contentDeltas.length).toBeGreaterThan(0);

        const taskCompleted = events.find((e) => e.type === "task_completed");
        expect(taskCompleted).toBeDefined();

        console.log("✅ KB context test passed");
      } catch (error: any) {
        if (error.message.includes("No authentication configured")) {
          console.log("⚠️  Test skipped: No authentication configured");
          return;
        }
        throw error;
      }
    },
    { timeout: 30000 } // Increased to 30s for API calls that may take longer
  );

  it("should handle errors gracefully", async () => {
    // Create a planner with invalid config to trigger error
    const badClient = new ClaudeClient({
      authMode: "api_key",
      apiKey: "invalid-key",
      model: "claude-sonnet-4-20250514",
      maxTokens: 100,
    });

    const badPlanner = new BasicPlanner(badClient);
    const events: AgentEvent[] = [];

    await badPlanner.processMessage(
      {
        userMessage: "Test error handling",
      },
      (event) => {
        events.push(event);
      }
    );

    // Should emit an error event
    const errorEvent = events.find((e) => e.type === "error");
    expect(errorEvent).toBeDefined();
    expect((errorEvent as any).error.recoverable).toBe(true);

    console.log("✅ Error handling test passed");
  });
});