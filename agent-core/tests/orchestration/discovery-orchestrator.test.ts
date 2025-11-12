// tests/orchestration/discovery-orchestrator.test.ts

/**
 * Integration test for DiscoveryOrchestrator
 * Tests the full discovery phase workflow
 */

import { describe, test, expect, mock } from "bun:test";
import { DiscoveryOrchestrator } from "../../src/orchestration/discovery-phase";
import type { MCPClient } from "../../src/mcp/client";
import type { ClaudeClient } from "../../src/llm/claude-client";
import type { DiscoveryConfig } from "../../src/orchestration/types";

describe("DiscoveryOrchestrator Integration", () => {
  const createMockMCPClient = (mockResults: any[] = []): MCPClient => {
    let callIndex = 0;

    return {
      callTool: mock(async (toolName: string, params: any) => {
        const result = mockResults[callIndex % mockResults.length];
        callIndex++;
        return result;
      })
    } as unknown as MCPClient;
  };

  const createMockClaudeClient = (queries: any[] = []): ClaudeClient => {
    return {
      complete: mock(async () => ({
        content: JSON.stringify(queries)
      }))
    } as unknown as ClaudeClient;
  };

  const defaultConfig: DiscoveryConfig = {
    maxQueries: 3,
    maxResultsPerQuery: 5,
    includeGraphContext: true,
    confidenceThreshold: 0.05,
    timeoutMs: 5000
  };

  test("should execute full discovery workflow", async () => {
    const mockQueries = [
      {
        text: "authentication middleware",
        strategy: "broad",
        priority: 1,
        expectedResultType: "any"
      },
      {
        text: "JWT validation",
        strategy: "specific",
        priority: 2,
        expectedResultType: "function"
      }
    ];

    const mockKBResults = [
      {
        _meta: {
          hits: [
            {
              chunk_id: "chunk1",
              repo: "test-repo",
              path: "src/auth.ts",
              start_line: 10,
              end_line: 30,
              score: 0.9,
              symbol_name: "authenticate",
              symbol_kind: "function"
            }
          ]
        },
        content: [
          {
            type: "resource",
            resource: {
              uri: "kb://test-repo/src/auth.ts#chunk1",
              text: "export function authenticate() { /* ... */ }"
            }
          }
        ]
      },
      {
        _meta: {
          hits: [
            {
              chunk_id: "chunk2",
              repo: "test-repo",
              path: "src/jwt.ts",
              start_line: 5,
              end_line: 20,
              score: 0.85,
              symbol_name: "validateJWT",
              symbol_kind: "function"
            }
          ]
        },
        content: [
          {
            type: "resource",
            resource: {
              uri: "kb://test-repo/src/jwt.ts#chunk2",
              text: "export function validateJWT(token: string) { /* ... */ }"
            }
          }
        ]
      }
    ];

    const mcpClient = createMockMCPClient(mockKBResults);
    const claudeClient = createMockClaudeClient(mockQueries);

    const orchestrator = new DiscoveryOrchestrator(
      mcpClient,
      claudeClient,
      defaultConfig
    );

    const result = await orchestrator.execute({
      userQuery: "Add authentication to the API",
      workspaceRoot: "/test/workspace",
      repoName: "test-repo",
      conversationHistory: []
    });

    // Verify queries were generated
    expect(result.queries).toHaveLength(2);
    expect(result.queries[0].text).toBe("authentication middleware");

    // Verify chunks were retrieved and aggregated
    expect(result.retrievedChunks.length).toBeGreaterThan(0);
    expect(result.retrievedChunks[0].chunk_id).toBe("chunk1");

    // Verify confidence score
    expect(result.confidence).toBeGreaterThan(0);
    expect(result.confidence).toBeLessThanOrEqual(1.0);

    // Verify summary
    expect(result.summary).toContain("Found");

    // Verify execution time
    expect(result.executionTimeMs).toBeGreaterThan(0);
  });

  test("should deduplicate results from multiple queries", async () => {
    const mockQueries = [
      { text: "auth", strategy: "broad", priority: 1, expectedResultType: "any" },
      { text: "authentication", strategy: "specific", priority: 2, expectedResultType: "any" }
    ];

    // Both queries return the same chunk
    const sameChunk = {
      _meta: {
        hits: [
          {
            chunk_id: "duplicate-chunk",
            repo: "test-repo",
            path: "src/auth.ts",
            start_line: 10,
            end_line: 30,
            score: 0.9
          }
        ]
      },
      content: [
        {
          type: "resource",
          resource: {
            uri: "kb://test-repo/src/auth.ts#duplicate-chunk",
            text: "auth code"
          }
        }
      ]
    };

    const mcpClient = createMockMCPClient([sameChunk, sameChunk]);
    const claudeClient = createMockClaudeClient(mockQueries);

    const orchestrator = new DiscoveryOrchestrator(
      mcpClient,
      claudeClient,
      defaultConfig
    );

    const result = await orchestrator.execute({
      userQuery: "test",
      workspaceRoot: "/test",
      repoName: "test-repo",
      conversationHistory: []
    });

    // Should have only 1 chunk (deduplicated)
    expect(result.retrievedChunks).toHaveLength(1);
    expect(result.retrievedChunks[0].chunk_id).toBe("duplicate-chunk");
  });

  test("should handle KB query failures gracefully", async () => {
    const mockQueries = [
      { text: "test", strategy: "broad", priority: 1, expectedResultType: "any" }
    ];

    const mcpClient = {
      callTool: mock(async () => {
        throw new Error("KB service unavailable");
      })
    } as unknown as MCPClient;

    const claudeClient = createMockClaudeClient(mockQueries);

    const orchestrator = new DiscoveryOrchestrator(
      mcpClient,
      claudeClient,
      defaultConfig
    );

    const result = await orchestrator.execute({
      userQuery: "test",
      workspaceRoot: "/test",
      repoName: "test-repo",
      conversationHistory: []
    });

    // Should complete without crashing
    expect(result.retrievedChunks).toHaveLength(0);
    expect(result.gaps.length).toBeGreaterThan(0);
    expect(result.gaps).toContain("No relevant code found in knowledge base");
  });

  test("should sort results by score descending", async () => {
    const mockQueries = [
      { text: "test", strategy: "broad", priority: 1, expectedResultType: "any" }
    ];

    const mockKBResults = {
      _meta: {
        hits: [
          { chunk_id: "low", repo: "test", path: "a.ts", start_line: 1, end_line: 10, score: 0.6 },
          { chunk_id: "high", repo: "test", path: "b.ts", start_line: 1, end_line: 10, score: 0.9 },
          { chunk_id: "medium", repo: "test", path: "c.ts", start_line: 1, end_line: 10, score: 0.75 }
        ]
      },
      content: [
        { type: "resource", resource: { uri: "kb://test/a.ts#low", text: "code" } },
        { type: "resource", resource: { uri: "kb://test/b.ts#high", text: "code" } },
        { type: "resource", resource: { uri: "kb://test/c.ts#medium", text: "code" } }
      ]
    };

    const mcpClient = createMockMCPClient([mockKBResults]);
    const claudeClient = createMockClaudeClient(mockQueries);

    const orchestrator = new DiscoveryOrchestrator(
      mcpClient,
      claudeClient,
      defaultConfig
    );

    const result = await orchestrator.execute({
      userQuery: "test",
      workspaceRoot: "/test",
      repoName: "test",
      conversationHistory: []
    });

    // Results should be sorted by score descending
    expect(result.retrievedChunks[0].chunk_id).toBe("high");
    expect(result.retrievedChunks[1].chunk_id).toBe("medium");
    expect(result.retrievedChunks[2].chunk_id).toBe("low");
  });

  test("should include graph context when enabled", async () => {
    const mockQueries = [
      { text: "test", strategy: "broad", priority: 1, expectedResultType: "any" }
    ];

    const mockKBResults = {
      _meta: {
        hits: [
          {
            chunk_id: "chunk1",
            repo: "test",
            path: "test.ts",
            start_line: 1,
            end_line: 10,
            score: 0.9,
            graph_context: {
              nodes: [
                {
                  type: "function",
                  qualified_name: "test.myFunction",
                  signature: "function myFunction()",
                  line_range: [1, 10]
                }
              ],
              relationships: [
                {
                  type: "calls",
                  direction: "outgoing",
                  source: { type: "function", qualified_name: "test.myFunction", line_range: [1, 10] },
                  target: { type: "function", qualified_name: "test.otherFunction", line_range: [20, 30] },
                  line_number: 5
                }
              ]
            }
          }
        ]
      },
      content: [
        { type: "resource", resource: { uri: "kb://test/test.ts#chunk1", text: "code" } }
      ]
    };

    const mcpClient = createMockMCPClient([mockKBResults]);
    const claudeClient = createMockClaudeClient(mockQueries);

    const config = { ...defaultConfig, includeGraphContext: true };

    const orchestrator = new DiscoveryOrchestrator(
      mcpClient,
      claudeClient,
      config
    );

    const result = await orchestrator.execute({
      userQuery: "test",
      workspaceRoot: "/test",
      repoName: "test",
      conversationHistory: []
    });

    expect(result.graphContext).not.toBeNull();
    expect(result.graphContext!.nodes.length).toBeGreaterThan(0);
    expect(result.graphContext!.relationships.length).toBeGreaterThan(0);
  });
});
