// tests/orchestration/kb-query-planner.test.ts

/**
 * Unit tests for KBQueryPlanner
 */

import { describe, test, expect, mock } from "bun:test";
import { KBQueryPlanner } from "../../src/kb/kb-query-planner";
import type { ClaudeClient } from "../../src/llm/claude-client";

describe("KBQueryPlanner", () => {
  test("should generate queries using Claude", async () => {
    const mockClaudeClient = {
      complete: mock(async () => ({
        content: JSON.stringify([
          {
            text: "authentication middleware",
            strategy: "broad",
            priority: 1,
            expectedResultType: "any"
          },
          {
            text: "JWT token validation",
            strategy: "specific",
            priority: 2,
            expectedResultType: "function"
          }
        ])
      }))
    } as unknown as ClaudeClient;

    const planner = new KBQueryPlanner(mockClaudeClient, {
      maxQueries: 5,
      temperature: 0.7
    });

    const queries = await planner.generateQueries({
      userQuery: "Add authentication to the API",
      conversationHistory: [],
      maxQueries: 5
    });

    expect(queries).toHaveLength(2);
    expect(queries[0].text).toBe("authentication middleware");
    expect(queries[0].strategy).toBe("broad");
    expect(queries[1].text).toBe("JWT token validation");
    expect(queries[1].strategy).toBe("specific");
  });

  test("should handle JSON in markdown code blocks", async () => {
    const mockClaudeClient = {
      complete: mock(async () => ({
        content: `Here are the queries:

\`\`\`json
[
  {
    "text": "test query",
    "strategy": "broad",
    "priority": 1,
    "expectedResultType": "any"
  }
]
\`\`\`

That's it!`
      }))
    } as unknown as ClaudeClient;

    const planner = new KBQueryPlanner(mockClaudeClient, {
      maxQueries: 5,
      temperature: 0.7
    });

    const queries = await planner.generateQueries({
      userQuery: "test",
      conversationHistory: [],
      maxQueries: 5
    });

    expect(queries).toHaveLength(1);
    expect(queries[0].text).toBe("test query");
  });

  test("should use fallback on Claude failure", async () => {
    const mockClaudeClient = {
      complete: mock(async () => {
        throw new Error("API error");
      })
    } as unknown as ClaudeClient;

    const planner = new KBQueryPlanner(mockClaudeClient, {
      maxQueries: 3,
      temperature: 0.7
    });

    const queries = await planner.generateQueries({
      userQuery: "Add REST API endpoints",
      conversationHistory: [],
      maxQueries: 3
    });

    // Should return fallback queries
    expect(queries.length).toBeGreaterThan(0);
    expect(queries[0].text).toBe("Add REST API endpoints");
  });

  test("should limit queries to maxQueries", async () => {
    const mockClaudeClient = {
      complete: mock(async () => ({
        content: JSON.stringify([
          { text: "query 1", strategy: "broad", priority: 1, expectedResultType: "any" },
          { text: "query 2", strategy: "specific", priority: 2, expectedResultType: "any" },
          { text: "query 3", strategy: "pattern", priority: 3, expectedResultType: "any" },
          { text: "query 4", strategy: "dependency", priority: 4, expectedResultType: "any" },
          { text: "query 5", strategy: "broad", priority: 5, expectedResultType: "any" },
          { text: "query 6", strategy: "broad", priority: 6, expectedResultType: "any" }
        ])
      }))
    } as unknown as ClaudeClient;

    const planner = new KBQueryPlanner(mockClaudeClient, {
      maxQueries: 3,
      temperature: 0.7
    });

    const queries = await planner.generateQueries({
      userQuery: "test",
      conversationHistory: [],
      maxQueries: 3
    });

    expect(queries).toHaveLength(3);
  });
});
