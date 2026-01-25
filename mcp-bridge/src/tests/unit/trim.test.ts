/**
 * Unit tests for search/trim.ts payload trimming
 *
 * Tests applyPayloadTrimming function for size reduction strategies
 */

import { describe, it, expect, beforeEach } from "bun:test";
import { applyPayloadTrimming } from "../../mcp/search/trim.js";
import type { CallToolResult, TextContent } from "@modelcontextprotocol/sdk/types.js";
import type { HitsJson } from "../../mcp/search/format.js";

describe("applyPayloadTrimming", () => {
  const createMockResult = (textContent: string): CallToolResult => ({
    content: [
      {
        type: "text",
        text: textContent,
      } as TextContent,
    ],
  });

  const createMockHitsJson = (hitCount: number): HitsJson => ({
    schema_version: "1.0",
    query: "test",
    hits: Array.from({ length: hitCount }, (_, i) => ({
      rank: i + 1,
      chunk_id: `chunk-${i}`,
      score: 0.9,
      repo: "repo",
      path: "path.ts",
      chunk_range: { start_line: 1, end_line: 10 },
      snippet_range: { start_line: 1, end_line: 10, included: true },
      uris: {
        chunk: "file:///chunk",
        snippet: "file:///snippet",
        vscode: "vscode://file",
        abs_path: "/abs/path",
        repo_root: "/repo",
      },
      followups: {
        chunk_get: { chunk_id: `chunk-${i}` },
        file_lines: { repo: "repo", path: "path.ts", start: 1, end: 10 },
      },
    })),
    meta: {
      estimated_total: null,
      warnings: [],
      model: null,
      top_k: 20,
      max_snippets: null,
    },
  });

  it("does not trim if size is under cap", async () => {
    const result = createMockResult("small text");
    const hitsJson = createMockHitsJson(1);

    await applyPayloadTrimming({
      result,
      hitsJson,
      includeHitsJson: false,
      promptReady: "",
      warningEntries: [],
      includeWarningsInText: false,
      capBytes: 100000, // Large cap
      shrunkSnippetCharCap: 1000,
      minSnippetCharFloor: 100,
      totalHits: 1,
    });

    // Should not modify content
    expect(result.content).toHaveLength(1);
    expect((result.content[0] as TextContent).text).toBe("small text");
  });

  it("trims prompt ready text when over cap", async () => {
    const largeText = "a".repeat(50000);
    const result: CallToolResult = {
      content: [
        { type: "text", text: "summary" } as TextContent,
        { type: "text", text: largeText } as TextContent, // This is promptReady
      ],
    };
    const hitsJson = createMockHitsJson(1);

    await applyPayloadTrimming({
      result,
      hitsJson,
      includeHitsJson: false,
      promptReady: largeText,
      warningEntries: [],
      includeWarningsInText: false,
      capBytes: 10000, // Small cap to force trimming
      shrunkSnippetCharCap: 1000,
      minSnippetCharFloor: 100,
      totalHits: 1,
    });

    // Prompt ready text should be trimmed
    expect((result.content[1] as TextContent).text.length).toBeLessThan(largeText.length);
  });

  it("removes hits from hitsJson when over cap", async () => {
    const result: CallToolResult = {
      content: [
        { type: "text", text: "summary" } as TextContent,
        { type: "text", text: "{}".repeat(20000) } as TextContent, // Large hitsJson
      ],
    };
    const hitsJson = createMockHitsJson(10);

    await applyPayloadTrimming({
      result,
      hitsJson,
      includeHitsJson: true,
      promptReady: "",
      warningEntries: [],
      includeWarningsInText: false,
      capBytes: 15000,
      shrunkSnippetCharCap: 1000,
      minSnippetCharFloor: 100,
      totalHits: 10,
    });

    // Should have removed some hits
    expect(hitsJson.hits.length).toBeLessThan(10);
  });

  it("nullifies URIs in last hit when still over cap", async () => {
    const result: CallToolResult = {
      content: [
        { type: "text", text: "summary" } as TextContent,
        { type: "text", text: JSON.stringify(createMockHitsJson(1)) } as TextContent,
      ],
    };
    const hitsJson = createMockHitsJson(1);

    await applyPayloadTrimming({
      result,
      hitsJson,
      includeHitsJson: true,
      promptReady: "",
      warningEntries: [],
      includeWarningsInText: false,
      capBytes: 500, // Very small cap
      shrunkSnippetCharCap: 1000,
      minSnippetCharFloor: 100,
      totalHits: 1,
    });

    // URIs should be nullified
    expect(hitsJson.hits[0].uris.vscode).toBe(null);
    expect(hitsJson.hits[0].uris.abs_path).toBe(null);
    expect(hitsJson.hits[0].uris.repo_root).toBe(null);
  });

  it("adds payload_trimmed warning when content is removed", async () => {
    const result = createMockResult("x".repeat(100000));
    const hitsJson = createMockHitsJson(1);
    const warningEntries: any[] = [];

    await applyPayloadTrimming({
      result,
      hitsJson,
      includeHitsJson: false,
      promptReady: "",
      warningEntries,
      includeWarningsInText: false,
      capBytes: 500,
      shrunkSnippetCharCap: 100,
      minSnippetCharFloor: 50,
      totalHits: 1,
    });

    // Should have added warning
    expect(warningEntries.some((w) => w.code === "payload_trimmed")).toBe(true);
  });

  it("sets complete to false when trimmed", async () => {
    const result = createMockResult("x".repeat(100000));
    const hitsJson = createMockHitsJson(5);

    await applyPayloadTrimming({
      result,
      hitsJson,
      includeHitsJson: false,
      promptReady: "",
      warningEntries: [],
      includeWarningsInText: false,
      capBytes: 500,
      shrunkSnippetCharCap: 100,
      minSnippetCharFloor: 50,
      totalHits: 5,
    });

    // Should mark as incomplete
    expect(result._meta?.complete).toBe(false);
  });

  it("includes warnings in text when requested", async () => {
    const result = createMockResult("summary text");
    const hitsJson = createMockHitsJson(1);
    const warningEntries: any[] = [];

    // Add lots of content to force trimming
    for (let i = 0; i < 100; i++) {
      result.content.push({ type: "text", text: "x".repeat(1000) } as TextContent);
    }

    await applyPayloadTrimming({
      result,
      hitsJson,
      includeHitsJson: false,
      promptReady: "",
      warningEntries,
      includeWarningsInText: true,
      capBytes: 1000,
      shrunkSnippetCharCap: 100,
      minSnippetCharFloor: 50,
      totalHits: 1,
    });

    // First content block should include warnings
    const firstBlock = result.content[0] as TextContent;
    expect(firstBlock.text).toContain("Warnings:");
  });

  it("trims resource blocks to shrunkSnippetCharCap", async () => {
    const result: CallToolResult = {
      content: [
        { type: "text", text: "summary" } as TextContent,
        {
          type: "resource",
          resource: {
            uri: "file:///test",
            mimeType: "text/plain",
            text: "a".repeat(5000),
          },
        },
      ],
    };
    const hitsJson = createMockHitsJson(1);

    await applyPayloadTrimming({
      result,
      hitsJson,
      includeHitsJson: false,
      promptReady: "",
      warningEntries: [],
      includeWarningsInText: false,
      capBytes: 2000,
      shrunkSnippetCharCap: 1000,
      minSnippetCharFloor: 100,
      totalHits: 1,
    });

    // Resource text should be trimmed
    const resource = result.content[1];
    if (resource.type === "resource" && "resource" in resource && resource.resource) {
      expect((resource.resource.text as string).length).toBeLessThanOrEqual(1000);
    }
  });
});
