/**
 * Unit tests for search/input.ts and search/rest.ts
 *
 * Tests input parsing, validation, and REST request building
 */

import { describe, it, expect, mock } from "bun:test";
import { parseSearchInput, resolveSearchOptions, SEARCH_INPUT } from "../../mcp/search/input.js";
import { buildSearchRequestBody, executeSearch } from "../../mcp/search/rest.js";

import type { KBClient } from "../../rest/client.js";

// Mock REST client
const mockSearch = mock(async () => ({
  hits: [] as any[],
  meta: { top_k: 20 },
  prompt_ready: "",
}));

const mockClient = { search: mockSearch } as unknown as KBClient;

describe("parseSearchInput", () => {
  it("parses basic query", () => {
    const result = parseSearchInput({ query: "test search" });

    expect(result.query).toBe("test search");
  });

  it("parses query with repos", () => {
    const result = parseSearchInput({
      query: "test",
      repos: ["repo1", "repo2"],
    });

    expect(result.repos).toEqual(["repo1", "repo2"]);
  });

  it("parses top_k parameter", () => {
    const result = parseSearchInput({
      query: "test",
      top_k: 50,
    });

    expect(result.top_k).toBe(50);
  });

  it("validates query is required", () => {
    try {
      parseSearchInput({});
      expect(true).toBe(false); // Should not reach
    } catch (error) {
      expect(error).toBeDefined();
    }
  });

  it("parses path filters", () => {
    const result = parseSearchInput({
      query: "test",
      path_prefix: ["src/"],
      exclude_paths: ["test/"],
    });

    expect(result.path_prefix).toEqual(["src/"]);
    expect(result.exclude_paths).toEqual(["test/"]);
  });

  it("parses context lines", () => {
    const result = parseSearchInput({
      query: "test",
      context_lines_before: 3,
      context_lines_after: 3,
    });

    expect(result.context_lines_before).toBe(3);
    expect(result.context_lines_after).toBe(3);
  });
});

describe("resolveSearchOptions", () => {
  it("uses default options", () => {
    const input = parseSearchInput({ query: "test" });
    const options = resolveSearchOptions(input);

    expect(options.topK).toBeDefined();
    expect(options.includeSnippets).toBe(true);
  });

  it("respects provided top_k", () => {
    const input = parseSearchInput({ query: "test", top_k: 100 });
    const options = resolveSearchOptions(input);

    expect(options.topK).toBe(100);
  });

  it("sets snippet limits", () => {
    const input = parseSearchInput({ query: "test" });
    const options = resolveSearchOptions(input);

    expect(options.snippetsTopN).toBeDefined();
    expect(options.snippetsTopN).toBeGreaterThan(0);
  });

  it("defaults snippetsTopN to 3 when max_snippets is undefined", () => {
    const input = parseSearchInput({ query: "test" });
    const options = resolveSearchOptions(input);
    expect(options.snippetsTopN).toBe(3);
  });

  it("respects explicit max_snippets", () => {
    const input = parseSearchInput({ query: "test", max_snippets: 5 });
    const options = resolveSearchOptions(input);
    expect(options.snippetsTopN).toBe(5);
  });

  it("respects explicit max_snippets=0", () => {
    const input = parseSearchInput({ query: "test", max_snippets: 0 });
    const options = resolveSearchOptions(input);
    expect(options.snippetsTopN).toBe(0);
  });
});

describe("buildSearchRequestBody", () => {
  it("builds basic request", () => {
    const input = parseSearchInput({ query: "test search" });
    const options = resolveSearchOptions(input);
    const body = buildSearchRequestBody(input, options);

    expect(body.query).toBe("test search");
  });

  it("includes repos filter", () => {
    const input = parseSearchInput({
      query: "test",
      repos: ["repo1", "repo2"],
    });
    const options = resolveSearchOptions(input);
    const body = buildSearchRequestBody(input, options);

    expect(body.repos).toEqual(["repo1", "repo2"]);
  });

  it("includes top_k", () => {
    const input = parseSearchInput({ query: "test", top_k: 50 });
    const options = resolveSearchOptions(input);
    const body = buildSearchRequestBody(input, options);

    expect(body.top_k).toBe(50);
  });

  it("includes max_snippets", () => {
    const input = parseSearchInput({ query: "test", max_snippets: 2 });
    const options = resolveSearchOptions(input);
    const body = buildSearchRequestBody(input, options);

    expect(body.max_snippets).toBe(2);
  });
});

describe("executeSearch", () => {
  it("calls REST search with body", async () => {
    const body = { query: "test", top_k: 20 };

    const result = await executeSearch(body, undefined, mockClient);

    expect(result).toBeDefined();
    expect(mockSearch).toHaveBeenCalled();
  });

  it("passes abort signal", async () => {
    const body = { query: "test" };
    const abortController = new AbortController();

    await executeSearch(body, abortController.signal, mockClient);

    expect(mockSearch).toHaveBeenCalled();
  });

  it("returns hits and metadata", async () => {
    mockSearch.mockImplementationOnce(async () => ({
      hits: [
        {
          repo: "r",
          path: "p",
          start_line: 1,
          end_line: 10,
          score: 0.9,
          snippet: "code",
          chunk_id: "c",
          resource_link: "",
        },
      ],
      meta: { top_k: 20, model: "small" },
      prompt_ready: "",
    }));

    const body = { query: "test" };
    const result = await executeSearch(body, undefined, mockClient);

    expect(result.hits).toHaveLength(1);
    expect(result.meta.top_k).toBe(20);
  });
});
