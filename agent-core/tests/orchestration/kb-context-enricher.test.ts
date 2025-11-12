// tests/orchestration/kb-context-enricher.test.ts

/**
 * Unit tests for KBContextEnricher
 */

import { describe, test, expect } from "bun:test";
import { KBContextEnricher } from "../../src/kb/kb-context-enricher";
import type { EnrichedChunk, GraphContext, GraphNode, GraphRelationship } from "../../src/orchestration/types";

describe("KBContextEnricher", () => {
  const createMockNode = (name: string): GraphNode => ({
    type: "function",
    qualified_name: name,
    signature: `function ${name}()`,
    line_range: [1, 10]
  });

  const createMockRelationship = (from: string, to: string, type: GraphRelationship["type"]): GraphRelationship => ({
    type,
    direction: "outgoing",
    source: createMockNode(from),
    target: createMockNode(to),
    line_number: 5
  });

  test("should return null when no graph context in chunks", async () => {
    const enricher = new KBContextEnricher();

    const chunks: EnrichedChunk[] = [
      {
        chunk_id: "1",
        repo: "test",
        path: "test.ts",
        start_line: 1,
        end_line: 10,
        score: 0.9,
        snippet: "code",
        graph_context: undefined
      }
    ];

    const result = await enricher.enrichWithGraph(chunks, "test-repo");

    expect(result).toBeNull();
  });

  test("should aggregate graph context from multiple chunks", async () => {
    const enricher = new KBContextEnricher();

    const chunks: EnrichedChunk[] = [
      {
        chunk_id: "1",
        repo: "test",
        path: "test.ts",
        start_line: 1,
        end_line: 10,
        score: 0.9,
        snippet: "code",
        graph_context: {
          nodes: [createMockNode("funcA")],
          relationships: [createMockRelationship("funcA", "funcB", "calls")]
        }
      },
      {
        chunk_id: "2",
        repo: "test",
        path: "test2.ts",
        start_line: 1,
        end_line: 10,
        score: 0.8,
        snippet: "code",
        graph_context: {
          nodes: [createMockNode("funcB")],
          relationships: [createMockRelationship("funcB", "funcC", "calls")]
        }
      }
    ];

    const result = await enricher.enrichWithGraph(chunks, "test-repo");

    expect(result).not.toBeNull();
    expect(result!.nodes).toHaveLength(2);
    expect(result!.relationships).toHaveLength(2);
  });

  test("should deduplicate nodes by qualified name", async () => {
    const enricher = new KBContextEnricher();

    const chunks: EnrichedChunk[] = [
      {
        chunk_id: "1",
        repo: "test",
        path: "test.ts",
        start_line: 1,
        end_line: 10,
        score: 0.9,
        snippet: "code",
        graph_context: {
          nodes: [createMockNode("funcA"), createMockNode("funcB")],
          relationships: []
        }
      },
      {
        chunk_id: "2",
        repo: "test",
        path: "test2.ts",
        start_line: 1,
        end_line: 10,
        score: 0.8,
        snippet: "code",
        graph_context: {
          nodes: [createMockNode("funcA"), createMockNode("funcC")], // funcA is duplicate
          relationships: []
        }
      }
    ];

    const result = await enricher.enrichWithGraph(chunks, "test-repo");

    expect(result).not.toBeNull();
    expect(result!.nodes).toHaveLength(3); // funcA, funcB, funcC (deduplicated)
    expect(result!.nodes.map(n => n.qualified_name).sort()).toEqual(["funcA", "funcB", "funcC"]);
  });

  test("should deduplicate relationships", async () => {
    const enricher = new KBContextEnricher();

    const chunks: EnrichedChunk[] = [
      {
        chunk_id: "1",
        repo: "test",
        path: "test.ts",
        start_line: 1,
        end_line: 10,
        score: 0.9,
        snippet: "code",
        graph_context: {
          nodes: [],
          relationships: [
            createMockRelationship("funcA", "funcB", "calls"),
            createMockRelationship("funcA", "funcC", "calls")
          ]
        }
      },
      {
        chunk_id: "2",
        repo: "test",
        path: "test2.ts",
        start_line: 1,
        end_line: 10,
        score: 0.8,
        snippet: "code",
        graph_context: {
          nodes: [],
          relationships: [
            createMockRelationship("funcA", "funcB", "calls"), // Duplicate
            createMockRelationship("funcB", "funcD", "calls")
          ]
        }
      }
    ];

    const result = await enricher.enrichWithGraph(chunks, "test-repo");

    expect(result).not.toBeNull();
    expect(result!.relationships).toHaveLength(3); // Deduplicated
  });

  test("should format graph summary correctly", () => {
    const enricher = new KBContextEnricher();

    const graph: GraphContext = {
      nodes: [
        createMockNode("funcA"),
        createMockNode("funcB"),
        { ...createMockNode("ClassA"), type: "class" }
      ],
      relationships: [
        createMockRelationship("funcA", "funcB", "calls"),
        createMockRelationship("funcA", "ClassA", "imports")
      ]
    };

    const summary = enricher.formatGraphSummary(graph);

    expect(summary).toContain("3 total");
    expect(summary).toContain("2 functions");
    expect(summary).toContain("1 class");
    expect(summary).toContain("1 calls");
    expect(summary).toContain("1 imports");
  });

  test("should handle null graph context in summary", () => {
    const enricher = new KBContextEnricher();
    const summary = enricher.formatGraphSummary(null);

    expect(summary).toBe("No graph context available");
  });
});
