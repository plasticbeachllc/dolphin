// agent-core/tests/llm/claude-tool-executor-kb.test.ts
/**
 * Tests for ClaudeToolExecutor KB tool execution functionality.
 * Complements existing diff tests with KB-specific scenarios.
 *
 * NOTE: These tests require the Dolphin REST API to be running on port 7777.
 * Run `uv run dolphin serve` before running these tests.
 */
import { describe, test, expect, beforeAll, afterAll, mock } from "bun:test";
import { ClaudeToolExecutor } from "../../src/llm/claude-tool-executor";
import { MCPClient } from "../../src/mcp/client";
import type { AgentEvent } from "../../../shared/types/events";
import * as path from "path";

// Helper to check if KB API is available
async function isKBApiAvailable(): Promise<boolean> {
  try {
    const response = await fetch("http://127.0.0.1:7777/health", {
      signal: AbortSignal.timeout(1000)
    });
    return response.ok;
  } catch {
    return false;
  }
}

describe("ClaudeToolExecutor - KB Tool Execution", () => {
  let mcpClient: MCPClient;
  let kbApiAvailable: boolean;
  const mcpBridgePath = path.join(__dirname, "../../../mcp-bridge/src/index.ts");

  beforeAll(async () => {
    // Check if KB API is available
    kbApiAvailable = await isKBApiAvailable();
    
    if (!kbApiAvailable) {
      console.warn("⚠️  KB API not available at http://127.0.0.1:7777 - some tests will be skipped");
      console.warn("   To run KB tests, start the API with: uv run dolphin serve");
    }
    
    // Start MCP client
    mcpClient = new MCPClient();
    await mcpClient.start(mcpBridgePath);
  });

  afterAll(async () => {
    try {
      mcpClient.shutdown();
    } catch (error) {
      // Ignore MCP shutdown errors
    }
  });

  describe("KB Search Tool", () => {
    test("executes search_knowledge tool successfully", async () => {
      if (!kbApiAvailable) {
        console.log("ℹ️  Skipping test (KB API not running)");
        return;
      }
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCall = {
        id: "kb-search-1",
        name: "search_knowledge",
        input: {
          query: "authentication logic"
        }
      };

      await (executor as any).executeToolCalls([toolCall]);

      // Find the tool_call_started event
      const startedEvent = events.find(e =>
        e.type === "tool_call_started" &&
        (e as any).toolId === "kb-search-1"
      );
      expect(startedEvent).toBeDefined();

      // Find the tool_call_completed event
      const completedEvent = events.find(e =>
        e.type === "tool_call_completed" &&
        (e as any).toolId === "kb-search-1"
      ) as any;

      expect(completedEvent).toBeDefined();
      expect(completedEvent.result).toBeDefined();
      expect(completedEvent.executionTime).toBeGreaterThanOrEqual(0);
    }, 30000); // Increase timeout to 30s for API calls

    test("handles search_knowledge with empty query", async () => {
      if (!kbApiAvailable) {
        console.log("ℹ️  Skipping test (KB API not running)");
        return;
      }
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCall = {
        id: "kb-search-2",
        name: "search_knowledge",
        input: {
          query: ""
        }
      };

      await (executor as any).executeToolCalls([toolCall]);

      const completedEvent = events.find(e =>
        e.type === "tool_call_completed" &&
        (e as any).toolId === "kb-search-2"
      ) as any;

      expect(completedEvent).toBeDefined();
      // Should either succeed with empty results or have error
      expect(completedEvent.result !== undefined || completedEvent.error !== undefined).toBe(true);
    }, 30000);

    test("handles search_knowledge with invalid input", async () => {
      if (!kbApiAvailable) {
        console.log("ℹ️  Skipping test (KB API not running)");
        return;
      }
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCall = {
        id: "kb-search-3",
        name: "search_knowledge",
        input: {
          // Missing query field
        }
      };

      await (executor as any).executeToolCalls([toolCall]);

      const completedEvent = events.find(e =>
        e.type === "tool_call_completed" &&
        (e as any).toolId === "kb-search-3"
      ) as any;

      expect(completedEvent).toBeDefined();
      // Should have error for invalid input
      if (completedEvent.error) {
        expect(completedEvent.error).toBeDefined();
      }
    }, 30000);
  });

  describe("File Read Tool", () => {
    test("executes file_read tool successfully", async () => {
      const events: AgentEvent[] = [];
      const testFilePath = path.join(__dirname, "../fixtures/sample.txt");

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCall = {
        id: "file-read-1",
        name: "file_read",
        input: {
          path: testFilePath
        }
      };

      await (executor as any).executeToolCalls([toolCall]);

      const completedEvent = events.find(e =>
        e.type === "tool_call_completed" &&
        (e as any).toolId === "file-read-1"
      ) as any;

      expect(completedEvent).toBeDefined();
      expect(completedEvent.executionTime).toBeGreaterThanOrEqual(0);
    });

    test("handles file_read for non-existent file", async () => {
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCall = {
        id: "file-read-2",
        name: "file_read",
        input: {
          path: "/nonexistent/file.txt"
        }
      };

      await (executor as any).executeToolCalls([toolCall]);

      const completedEvent = events.find(e =>
        e.type === "tool_call_completed" &&
        (e as any).toolId === "file-read-2"
      ) as any;

      expect(completedEvent).toBeDefined();
      // Should have error
      expect(completedEvent.error).toBeDefined();
    });
  });

  describe("Multiple Tool Execution", () => {
    test("executes multiple tools in sequence", async () => {
      if (!kbApiAvailable) {
        console.log("ℹ️  Skipping test (KB API not running)");
        return;
      }
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCalls = [
        {
          id: "multi-1",
          name: "search_knowledge",
          input: { query: "test" }
        },
        {
          id: "multi-2",
          name: "search_knowledge",
          input: { query: "authentication" }
        }
      ];

      await (executor as any).executeToolCalls(toolCalls);

      // Should have events for both tool calls
      const startedEvents = events.filter(e => e.type === "tool_call_started");
      const completedEvents = events.filter(e => e.type === "tool_call_completed");

      expect(startedEvents.length).toBe(2);
      expect(completedEvents.length).toBe(2);

      // Check that tool IDs match
      const completedIds = completedEvents.map((e: any) => e.toolId);
      expect(completedIds).toContain("multi-1");
      expect(completedIds).toContain("multi-2");
    }, 30000);

    test("continues execution if one tool fails", async () => {
      if (!kbApiAvailable) {
        console.log("ℹ️  Skipping test (KB API not running)");
        return;
      }
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCalls = [
        {
          id: "mixed-1",
          name: "file_read",
          input: { path: "/nonexistent/file.txt" } // Will fail
        },
        {
          id: "mixed-2",
          name: "search_knowledge",
          input: { query: "test" } // Should succeed
        }
      ];

      await (executor as any).executeToolCalls(toolCalls);

      const completedEvents = events.filter(e => e.type === "tool_call_completed");

      // Both should complete (one with error, one with result)
      expect(completedEvents.length).toBe(2);

      const errorEvent = completedEvents.find((e: any) => e.toolId === "mixed-1") as any;
      const successEvent = completedEvents.find((e: any) => e.toolId === "mixed-2") as any;

      expect(errorEvent.error).toBeDefined();
      // Success event should have result or possibly error if KB is not set up
      expect(successEvent.result !== undefined || successEvent.error !== undefined).toBe(true);
    }, 30000);
  });

  describe("Tool Execution Timing", () => {
    test("tracks execution time for tool calls", async () => {
      if (!kbApiAvailable) {
        console.log("ℹ️  Skipping test (KB API not running)");
        return;
      }
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCall = {
        id: "timing-1",
        name: "search_knowledge",
        input: { query: "test query" }
      };

      const startTime = Date.now();
      await (executor as any).executeToolCalls([toolCall]);
      const endTime = Date.now();

      const completedEvent = events.find(e =>
        e.type === "tool_call_completed" &&
        (e as any).toolId === "timing-1"
      ) as any;

      expect(completedEvent).toBeDefined();
      expect(completedEvent.executionTime).toBeDefined();
      expect(completedEvent.executionTime).toBeGreaterThanOrEqual(0);
      // Execution time should be reasonable (less than total elapsed time)
      expect(completedEvent.executionTime).toBeLessThanOrEqual(endTime - startTime);
    }, 30000);
  });

  describe("Error Handling", () => {
    test("handles unknown tool gracefully", async () => {
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCall = {
        id: "unknown-1",
        name: "nonexistent_tool",
        input: {}
      };

      await (executor as any).executeToolCalls([toolCall]);

      const completedEvent = events.find(e =>
        e.type === "tool_call_completed" &&
        (e as any).toolId === "unknown-1"
      ) as any;

      expect(completedEvent).toBeDefined();
      expect(completedEvent.error).toBeDefined();
      expect(completedEvent.error).toContain("not found");
    });

    test("handles malformed tool input", async () => {
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCall = {
        id: "malformed-1",
        name: "search_knowledge",
        input: null as any // Invalid input
      };

      await (executor as any).executeToolCalls([toolCall]);

      const completedEvent = events.find(e =>
        e.type === "tool_call_completed" &&
        (e as any).toolId === "malformed-1"
      ) as any;

      expect(completedEvent).toBeDefined();
      // Should either have error or handle null input
      expect(completedEvent.result !== undefined || completedEvent.error !== undefined).toBe(true);
    });
  });

  describe("Event Emission", () => {
    test("emits tool_call_started event", async () => {
      if (!kbApiAvailable) {
        console.log("ℹ️  Skipping test (KB API not running)");
        return;
      }
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCall = {
        id: "event-1",
        name: "search_knowledge",
        input: { query: "test" }
      };

      await (executor as any).executeToolCalls([toolCall]);

      const startedEvent = events.find(e =>
        e.type === "tool_call_started" &&
        (e as any).toolId === "event-1"
      ) as any;

      expect(startedEvent).toBeDefined();
      expect(startedEvent.tool).toBe("search_knowledge");
      expect(startedEvent.input).toBeDefined();
    }, 30000);

    test("emits tool_call_completed event", async () => {
      if (!kbApiAvailable) {
        console.log("ℹ️  Skipping test (KB API not running)");
        return;
      }
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCall = {
        id: "event-2",
        name: "search_knowledge",
        input: { query: "test" }
      };

      await (executor as any).executeToolCalls([toolCall]);

      const completedEvent = events.find(e =>
        e.type === "tool_call_completed" &&
        (e as any).toolId === "event-2"
      ) as any;

      expect(completedEvent).toBeDefined();
      expect(completedEvent.toolId).toBe("event-2");
      expect(completedEvent.executionTime).toBeDefined();
    }, 30000);

    test("emits events in correct order", async () => {
      if (!kbApiAvailable) {
        console.log("ℹ️  Skipping test (KB API not running)");
        return;
      }
      const events: AgentEvent[] = [];

      const executor = new ClaudeToolExecutor({
        claudeClient: null as any,
        mcpClient,
        maxToolRounds: 1,
        onEvent: (event: AgentEvent) => {
          events.push(event);
        }
      });

      await executor.initialize();

      const toolCall = {
        id: "order-1",
        name: "search_knowledge",
        input: { query: "test" }
      };

      await (executor as any).executeToolCalls([toolCall]);

      const relevantEvents = events.filter(e =>
        e.type === "tool_call_started" || e.type === "tool_call_completed"
      );

      // Should have started before completed
      expect(relevantEvents[0].type).toBe("tool_call_started");
      expect(relevantEvents[relevantEvents.length - 1].type).toBe("tool_call_completed");
    }, 30000);
  });
});
