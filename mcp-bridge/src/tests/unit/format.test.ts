/**
 * Unit tests for search/format.ts functions
 *
 * Tests buildPromptReady, buildWarnings, buildSummary, buildHitsJsonObject, buildHitsJsonText
 */

import { describe, it, expect } from "bun:test";
import {
  buildPromptReady,
  buildWarnings,
  buildSummary,
  buildHitsJsonObject,
  buildHitsJsonText,
} from "../../mcp/search/format.js";
import type { ExtendedSearchHit, SnippetFailure } from "../../mcp/search/contracts.js";

describe("buildPromptReady", () => {
  const createMockHit = (overrides: Partial<ExtendedSearchHit> = {}): ExtendedSearchHit => ({
    chunk_id: "chunk-1",
    repo: "test-repo",
    path: "src/example.ts",
    start_line: 10,
    end_line: 20,
    score: 0.85,
    snippet: "function example() { return 42; }",
    resource_link: "file:///src/example.ts#L10-L20",
    ...overrides,
  });

  it("returns empty string for empty hits array", () => {
    const result = buildPromptReady({ hits: [], meta: {} }, 10);
    expect(result).toBe("");
  });

  it("formats basic hit with snippet", () => {
    const hit = createMockHit();
    const result = buildPromptReady({ hits: [hit as any], meta: {} }, 10);

    expect(result).toContain("[test-repo]");
    expect(result).toContain("src/example.ts");
    expect(result).toContain("L10-L20");
    expect(result).toContain("chunk_id=chunk-1");
    expect(result).toContain("function example()");
  });

  it("includes score in output", () => {
    const hit = createMockHit({ score: 0.9542 });
    const result = buildPromptReady({ hits: [hit as any], meta: {} }, 10);

    expect(result).toContain("score=0.954");
  });

  it("respects maxHits limit", () => {
    const hits = [
      createMockHit({ chunk_id: "chunk-1" }),
      createMockHit({ chunk_id: "chunk-2" }),
      createMockHit({ chunk_id: "chunk-3" }),
    ];
    const result = buildPromptReady({ hits: hits as any, meta: {} }, 2);

    expect(result).toContain("chunk-1");
    expect(result).toContain("chunk-2");
    expect(result).not.toContain("chunk-3");
  });

  it("shows followup hint when no snippet", () => {
    const hit = createMockHit({ snippet: undefined });
    const result = buildPromptReady({ hits: [hit as any], meta: {} }, 10);

    expect(result).toContain("No snippet included");
    expect(result).toContain("chunk_get");
    expect(result).toContain("file_lines");
  });

  it("uses fenced code block with language", () => {
    const hit = createMockHit({ lang: "typescript" });
    const result = buildPromptReady({ hits: [hit as any], meta: {} }, 10);

    // fenceLang returns short names like "ts" for typescript
    expect(result).toContain("```ts");
    expect(result).toContain("```");
  });

  it("handles context lines correctly", () => {
    const hit = createMockHit({
      _context_start_line: 5,
      _context_end_line: 25,
      _chunk_start_line: 10,
      _chunk_end_line: 20,
    });
    const result = buildPromptReady({ hits: [hit as any], meta: {} }, 10);

    expect(result).toContain("L5-L25");
  });
});

describe("buildWarnings", () => {
  it("returns empty arrays for no warnings", () => {
    const result = buildWarnings({
      metaWarnings: [],
      snippetFailures: [],
      escapedPathCount: 0,
    });

    expect(result.warnings).toEqual([]);
    expect(result.warningEntries).toEqual([]);
  });

  it("includes meta warnings", () => {
    const result = buildWarnings({
      metaWarnings: ["low_confidence", "truncated"],
      snippetFailures: [],
      escapedPathCount: 0,
    });

    expect(result.warnings).toContain("low_confidence");
    expect(result.warnings).toContain("truncated");
    expect(result.warningEntries).toHaveLength(2);
  });

  it("reports snippet fetch failures", () => {
    const failures: SnippetFailure[] = [
      { repo: "r1", path: "p1.ts", start: 1, end: 10 },
      { repo: "r2", path: "p2.ts", start: 5, end: 15 },
    ];
    const result = buildWarnings({
      snippetFailures: failures,
      escapedPathCount: 0,
    });

    expect(result.warnings).toContain("snippet_fetch_failed");
    expect(result.warningEntries[0].detail).toContain("2 snippet(s)");
  });

  it("reports escaped path count", () => {
    const result = buildWarnings({
      snippetFailures: [],
      escapedPathCount: 3,
    });

    expect(result.warnings).toContain("path_escaped_repo_root");
    expect(result.warningEntries[0].detail).toContain("3 path(s)");
  });

  it("combines multiple warning types", () => {
    const result = buildWarnings({
      metaWarnings: ["rate_limited"],
      snippetFailures: [{ repo: "r", path: "p", start: 1, end: 2 }],
      escapedPathCount: 1,
    });

    expect(result.warnings).toHaveLength(3);
    expect(result.warningEntries).toHaveLength(3);
  });
});

describe("buildSummary", () => {
  const createMockHits = (count: number): ExtendedSearchHit[] => {
    return Array.from({ length: count }, (_, i) => ({
      chunk_id: `chunk-${i}`,
      repo: i % 2 === 0 ? "repo-a" : "repo-b",
      path: `file-${i}.ts`,
      start_line: 1,
      end_line: 10,
      score: 0.9 - i * 0.1,
      resource_link: `file:///file-${i}.ts#L1-L10`,
    }));
  };

  it("formats result count correctly", () => {
    const result = buildSummary({
      hits: createMockHits(5),
      snippetsIncluded: 3,
      includeWarningsInText: false,
      warningEntries: [],
    });

    expect(result).toContain("Found 5 results");
    expect(result).toContain("across 2 repos");
  });

  it("uses singular form for 1 result", () => {
    const result = buildSummary({
      hits: createMockHits(1),
      snippetsIncluded: 1,
      includeWarningsInText: false,
      warningEntries: [],
    });

    expect(result).toContain("Found 1 result");
    expect(result).toContain("1 repo");
  });

  it("shows snippets included count", () => {
    const result = buildSummary({
      hits: createMockHits(10),
      snippetsIncluded: 5,
      includeWarningsInText: false,
      warningEntries: [],
    });

    expect(result).toContain("top 5/10");
  });

  it("includes estimated total when provided", () => {
    const result = buildSummary({
      hits: createMockHits(5),
      snippetsIncluded: 5,
      estimatedTotal: 100,
      includeWarningsInText: false,
      warningEntries: [],
    });

    expect(result).toContain("~100 estimated");
  });

  it("includes warnings in text when requested", () => {
    const result = buildSummary({
      hits: createMockHits(1),
      snippetsIncluded: 1,
      includeWarningsInText: true,
      warningEntries: [{ code: "low_confidence" }, { code: "snippet_failed", detail: "timeout" }],
    });

    expect(result).toContain("Warnings:");
    expect(result).toContain("low_confidence");
    expect(result).toContain("snippet_failed(timeout)");
  });

  it("omits warnings when includeWarningsInText is false", () => {
    const result = buildSummary({
      hits: createMockHits(1),
      snippetsIncluded: 1,
      includeWarningsInText: false,
      warningEntries: [{ code: "test_warning" }],
    });

    expect(result).not.toContain("Warnings:");
    expect(result).not.toContain("test_warning");
  });

  it("indicates when snippets are not shown", () => {
    const result = buildSummary({
      hits: createMockHits(1),
      snippetsIncluded: 0,
      includeWarningsInText: false,
      warningEntries: [],
    });
    expect(result).toContain("Snippets disabled or none found");
  });

  it("indicates when snippets are shown", () => {
    const result = buildSummary({
      hits: createMockHits(1),
      snippetsIncluded: 1,
      includeWarningsInText: false,
      warningEntries: [],
    });
    expect(result).toContain("Showing snippets for top 1/1 results");
  });
});

describe("buildHitsJsonObject", () => {
  const createMockHit = (): ExtendedSearchHit => ({
    chunk_id: "chunk-123",
    repo: "test-repo",
    path: "src/test.ts",
    start_line: 10,
    end_line: 20,
    score: 0.85,
    lang: "typescript",
    snippet: "const x = 1;",
    resource_link: "file:///src/test.ts#L10-L20",
  });

  it("creates valid HitsJson structure", () => {
    const result = buildHitsJsonObject({
      query: "test query",
      hits: [createMockHit()],
      meta: { estimated_total: 100, max_snippets: 1 },
      topK: 20,
      warningEntries: [],
    });

    expect(result.schema_version).toBeDefined();
    expect(result.query).toBe("test query");
    expect(result.hits).toHaveLength(1);
    expect(result.meta).toBeDefined();
  });

  it("assigns ranks starting from 1", () => {
    const result = buildHitsJsonObject({
      query: "query",
      hits: [createMockHit(), createMockHit()],
      meta: {},
      topK: 10,
      warningEntries: [],
    });

    expect(result.hits[0].rank).toBe(1);
    expect(result.hits[1].rank).toBe(2);
  });

  it("includes chunk and snippet ranges", () => {
    const hit = createMockHit();
    hit._chunk_start_line = 12;
    hit._chunk_end_line = 18;
    hit._context_start_line = 8;
    hit._context_end_line = 22;

    const result = buildHitsJsonObject({
      query: "query",
      hits: [hit],
      meta: {},
      topK: 10,
      warningEntries: [],
    });

    expect(result.hits[0].chunk_range!.start_line).toBe(12);
    expect(result.hits[0].chunk_range!.end_line).toBe(18);
    expect(result.hits[0].snippet_range!.start_line).toBe(8);
    expect(result.hits[0].snippet_range!.end_line).toBe(22);
  });

  it("includes followup hints for each hit", () => {
    const result = buildHitsJsonObject({
      query: "query",
      hits: [createMockHit()],
      meta: {},
      topK: 10,
      warningEntries: [],
    });

    const hit = result.hits[0];
    expect(hit.followups!.chunk_get.chunk_id).toBe("chunk-123");
    expect(hit.followups!.file_lines.repo).toBe("test-repo");
    expect(hit.followups!.file_lines.path).toBe("src/test.ts");
  });

  it("includes URIs", () => {
    const hit = createMockHit();
    hit.vscode_uri = "vscode://file/src/test.ts:10";
    hit.abs_path = "/home/user/src/test.ts";
    hit.repo_root = "/home/user";

    const result = buildHitsJsonObject({
      query: "query",
      hits: [hit],
      meta: {},
      topK: 10,
      warningEntries: [],
    });

    expect(result.hits[0].uris!.vscode).toBe("vscode://file/src/test.ts:10");
    expect(result.hits[0].uris!.abs_path).toBe("/home/user/src/test.ts");
    expect(result.hits[0].uris!.repo_root).toBe("/home/user");
  });

  it("includes meta with warnings", () => {
    const result = buildHitsJsonObject({
      query: "query",
      hits: [],
      meta: { estimated_total: 50, model: "large", top_k: 20, max_snippets: 0 },
      topK: 20,
      warningEntries: [{ code: "test_warning" }],
    });

    expect(result.meta.estimated_total).toBe(50);
    expect(result.meta.model).toBe("large");
    expect(result.meta.warnings).toHaveLength(1);
  });

  it("returns simplified object when compact is true", () => {
    const hits = [createMockHit()];
    const meta = { top_k: 10, estimated_total: 100 };
    const result = buildHitsJsonObject({
      query: "test",
      hits: hits,
      meta: meta as any,
      topK: 10,
      warningEntries: [],
      compact: true,
    });

    const hit = result.hits[0];
    // Essential fields
    expect(hit.chunk_id).toBe("chunk-123");
    expect(hit.repo).toBe("test-repo");
    expect(hit.path).toBe("src/test.ts");
    expect(hit.score).toBe(0.85);

    // Omitted fields
    expect((hit as any).uris).toBeUndefined();
    expect((hit as any).followups).toBeUndefined();
    expect((hit as any).lang).toBeUndefined();
    expect((hit as any).chunk_range).toBeUndefined();
    expect((hit as any).snippet_range).toBeUndefined();
  });
});

describe("buildHitsJsonText", () => {
  it("wraps JSON in markdown code block", () => {
    const hitsJson = {
      schema_version: "1.0",
      query: "test",
      hits: [],
      meta: {
        estimated_total: null,
        warnings: [],
        model: null,
        top_k: 20,
        max_snippets: null,
      },
    };

    const result = buildHitsJsonText(hitsJson);

    expect(result).toStartWith("```json\n");
    expect(result).toEndWith("\n```");
  });

  it("contains valid JSON", () => {
    const hitsJson = {
      schema_version: "1.0",
      query: "search term",
      hits: [],
      meta: {
        estimated_total: 10,
        warnings: [],
        model: "small",
        top_k: 5,
        max_snippets: 0,
      },
    };

    const result = buildHitsJsonText(hitsJson);
    const jsonPart = result.replace(/^```json\n/, "").replace(/\n```$/, "");

    expect(() => JSON.parse(jsonPart)).not.toThrow();
    const parsed = JSON.parse(jsonPart);
    expect(parsed.query).toBe("search term");
  });
});
