/**
 * Unit tests for search/input.ts and search/rest.ts
 *
 * Tests input parsing, validation, and REST request building
 */

import { describe, it, expect, mock } from "bun:test";
import { parseSearchInput, resolveSearchOptions, SEARCH_INPUT } from "../../mcp/search/input.js";
import { buildSearchRequestBody, executeSearch } from "../../mcp/search/rest.js";

// Mock REST client
const mockRestSearch = mock(async () => ({
  hits: [],
  meta: { top_k: 20 },
}));

mock.module("../../rest/client.js", () => ({
  restSearch: mockRestSearch,
  restGetChunk: mock(async () => ({
    chunk_id: "",
    repo: "",
    path: "",
    start_line: 1,
    end_line: 1,
    content: "",
    resource_link: "",
  })),
  restListRepos: mock(async () => ({ repos: [] })),
}));

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

  it("parses embed_model parameter", () => {
    const result = parseSearchInput({
      query: "test",
      embed_model: "large",
    });

    expect(result.embed_model).toBe("large");
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

  it("includes embed_model", () => {
    const input = parseSearchInput({ query: "test", embed_model: "large" });
    const options = resolveSearchOptions(input);
    const body = buildSearchRequestBody(input, options);

    expect(body.embed_model).toBe("large");
  });
});

describe("executeSearch", () => {
  it("calls REST search with body", async () => {
    const body = { query: "test", top_k: 20 };

    const result = await executeSearch(body);

    expect(result).toBeDefined();
    expect(mockRestSearch).toHaveBeenCalled();
  });

  it("passes abort signal", async () => {
    const body = { query: "test" };
    const abortController = new AbortController();

    await executeSearch(body, abortController.signal);

    expect(mockRestSearch).toHaveBeenCalled();
  });

  it("returns hits and metadata", async () => {
    mockRestSearch.mockImplementationOnce(async () => ({
      hits: [
        {
          repo: "r",
          path: "p",
          start_line: 1,
          end_line: 10,
          score: 0.9,
          snippet: "code",
          chunk_id: "c",
        },
      ],
      meta: { top_k: 20, model: "small" },
    }));

    const body = { query: "test" };
    const result = await executeSearch(body);

    expect(result.hits).toHaveLength(1);
    expect(result.meta.top_k).toBe(20);
  });
});
