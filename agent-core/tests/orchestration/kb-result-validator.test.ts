// tests/orchestration/kb-result-validator.test.ts

/**
 * Unit tests for KBResultValidator
 */

import { describe, test, expect } from "bun:test";
import { KBResultValidator } from "../../src/kb/kb-result-validator";
import type { EnrichedChunk, GraphContext } from "../../src/orchestration/types";

describe("KBResultValidator", () => {
  const createMockChunk = (overrides: Partial<EnrichedChunk> = {}): EnrichedChunk => ({
    chunk_id: "test-chunk",
    repo: "test-repo",
    path: "src/test.ts",
    start_line: 1,
    end_line: 10,
    score: 0.8,
    snippet: "test code",
    ...overrides
  });

  test("should filter chunks below confidence threshold", async () => {
    const validator = new KBResultValidator(0.7);

    const chunks: EnrichedChunk[] = [
      createMockChunk({ chunk_id: "1", score: 0.9 }),
      createMockChunk({ chunk_id: "2", score: 0.6 }), // Below threshold
      createMockChunk({ chunk_id: "3", score: 0.8 })
    ];

    const result = await validator.validate({
      chunks,
      userQuery: "test",
      graphContext: null
    });

    expect(result.chunks).toHaveLength(2);
    expect(result.chunks.map(c => c.chunk_id)).toEqual(["1", "3"]);
  });

  test("should calculate overall confidence correctly", async () => {
    const validator = new KBResultValidator(0.6);

    const chunks: EnrichedChunk[] = [
      createMockChunk({ chunk_id: "1", path: "src/a.ts", score: 0.9 }),
      createMockChunk({ chunk_id: "2", path: "src/b.ts", score: 0.8 }),
      createMockChunk({ chunk_id: "3", path: "src/c.ts", score: 0.85 })
    ];

    const result = await validator.validate({
      chunks,
      userQuery: "test",
      graphContext: null
    });

    expect(result.overallConfidence).toBeGreaterThan(0.6);
    expect(result.overallConfidence).toBeLessThanOrEqual(1.0);
  });

  test("should calculate quality metrics", async () => {
    const validator = new KBResultValidator(0.6);

    const chunks: EnrichedChunk[] = [
      createMockChunk({ chunk_id: "1", path: "src/a.ts", score: 0.9 }),
      createMockChunk({ chunk_id: "2", path: "src/a.ts", score: 0.8 }),
      createMockChunk({ chunk_id: "3", path: "src/b.ts", score: 0.7 })
    ];

    const result = await validator.validate({
      chunks,
      userQuery: "test",
      graphContext: null
    });

    expect(result.qualityMetrics.avgScore).toBeCloseTo(0.8, 1);
    expect(result.qualityMetrics.minScore).toBe(0.7);
    expect(result.qualityMetrics.maxScore).toBe(0.9);
    expect(result.qualityMetrics.uniqueFiles).toBe(2);
  });

  test("should identify gaps when no results found", () => {
    const validator = new KBResultValidator(0.6);
    const gaps = validator.identifyGaps([], "test query");

    expect(gaps).toContain("No relevant code found in knowledge base");
  });

  test("should identify gaps for low-scoring results", () => {
    const validator = new KBResultValidator(0.6);

    const chunks: EnrichedChunk[] = [
      createMockChunk({ score: 0.5 }),
      createMockChunk({ score: 0.4 })
    ];

    const gaps = validator.identifyGaps(chunks, "test query");

    expect(gaps.some(g => g.includes("low relevance scores"))).toBe(true);
  });

  test("should identify gap for single-file results", () => {
    const validator = new KBResultValidator(0.6);

    const chunks: EnrichedChunk[] = [
      createMockChunk({ chunk_id: "1", path: "src/same.ts", score: 0.9 }),
      createMockChunk({ chunk_id: "2", path: "src/same.ts", score: 0.8 }),
      createMockChunk({ chunk_id: "3", path: "src/same.ts", score: 0.7 })
    ];

    const gaps = validator.identifyGaps(chunks, "test query");

    expect(gaps.some(g => g.includes("single file"))).toBe(true);
  });

  test("should identify gap for missing graph context", () => {
    const validator = new KBResultValidator(0.6);

    const chunks: EnrichedChunk[] = [
      createMockChunk({ chunk_id: "1", score: 0.9, graph_context: undefined })
    ];

    const gaps = validator.identifyGaps(chunks, "test query");

    expect(gaps.some(g => g.includes("No graph context"))).toBe(true);
  });

  test("should handle graph context in confidence calculation", async () => {
    const validator = new KBResultValidator(0.6);

    const chunks: EnrichedChunk[] = [
      createMockChunk({ score: 0.8 })
    ];

    const graphContext: GraphContext = {
      nodes: [
        {
          type: "function",
          qualified_name: "test.function",
          line_range: [1, 10]
        }
      ],
      relationships: []
    };

    const resultWithGraph = await validator.validate({
      chunks,
      userQuery: "test",
      graphContext
    });

    const resultWithoutGraph = await validator.validate({
      chunks,
      userQuery: "test",
      graphContext: null
    });

    // Confidence should be higher with graph context
    expect(resultWithGraph.overallConfidence).toBeGreaterThan(resultWithoutGraph.overallConfidence);
  });
});
