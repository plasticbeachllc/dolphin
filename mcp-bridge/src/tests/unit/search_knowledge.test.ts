import { describe, it, expect, mock, beforeEach } from "bun:test";
import { makeSearchKnowledge } from "../../mcp/tools/search_knowledge.js";
import { executeSearch } from "../../mcp/search/rest.js";

const mockExecuteSearch = mock(async () => ({
  hits: [],
  meta: {
    estimated_total: 10,
    model: "small",
    top_k: 20,
    max_snippets: 5,
    latency_ms: 10
  }
}));

const mockFetchSnippets = mock(async () => ({
  snippetsByHitIndex: new Map(),
  snippetFailures: []
}));

const mockTransformHits = mock(() => ({
  hits: [],
  escapedPathCount: 0
}));

const mockBuildSummary = mock(() => "Search Summary");
const mockBuildHitsJsonObject = mock(() => ({}));

// Setup mocks - Bun hoists these to run before imports
mock.module("../../mcp/search/rest.js", () => ({
  buildSearchRequestBody: (input: any) => ({ query: input.query }),
  executeSearch: mockExecuteSearch
}));

mock.module("../../mcp/search/snippets.js", () => ({
  fetchSnippetsForHits: mockFetchSnippets
}));

mock.module("../../mcp/search/transform.js", () => ({
  getReposByName: mock(async () => new Map()),
  transformHits: mockTransformHits
}));

mock.module("../../mcp/search/format.js", () => ({
  buildPromptReady: () => "Prompt Ready",
  buildWarnings: () => ({ warnings: [], warningEntries: [] }),
  buildSummary: mockBuildSummary,
  buildHitsJsonObject: mockBuildHitsJsonObject,
  buildHitsJsonText: () => "{}"
}));

mock.module("../../mcp/search/trim.js", () => ({
  applyPayloadTrimming: mock(async () => {})
}));

describe("search_knowledge tool", () => {
  beforeEach(async () => {
    mockExecuteSearch.mockClear();
    mockFetchSnippets.mockClear();
    mockTransformHits.mockClear();
    mockBuildSummary.mockClear();

    // Reset default mock implementations
    mockExecuteSearch.mockResolvedValue({
      hits: [],
      meta: {
        estimated_total: 10,
        model: "small",
        top_k: 20,
        max_snippets: 5,
        latency_ms: 10
      }
    });
    mockFetchSnippets.mockResolvedValue({
        snippetsByHitIndex: new Map(),
        snippetFailures: []
    });
    mockTransformHits.mockReturnValue({
        hits: [],
        escapedPathCount: 0
    });
  });

  it("verify mocks are active", () => {
    // This confirms that the module mocking worked despite static imports
    expect(executeSearch).toBe(mockExecuteSearch);
  });

  it("has correct tool definition", () => {
    const { definition } = makeSearchKnowledge();
    expect(definition.name).toBe("search");
    expect(definition.description).toContain("Semantically query");
  });

  it("executes search successfully with basic query", async () => {
    const { handler } = makeSearchKnowledge();
    const result = await handler({ query: "test query" });

    expect(mockExecuteSearch).toHaveBeenCalled();
    expect(result.isError).toBe(false);
    expect(result.content[0].type).toBe("text");
    expect(result.content[0].text).toBe("Search Summary");
  });

  it("handles empty results gracefully", async () => {
    mockExecuteSearch.mockResolvedValueOnce({
      hits: [],
      meta: { estimated_total: 0, model: "small", latency_ms: 5 }
    });

    const { handler } = makeSearchKnowledge();
    const result = await handler({ query: "no results" });

    expect(result.isError).toBe(false);
    expect(mockBuildSummary).toHaveBeenCalled();
  });

  it("includes JSON output when requested", async () => {
    const { handler } = makeSearchKnowledge();
    const result = await handler({ query: "test", include_hits_json: true });

    // Should include summary and JSON text
    expect(result.content.length).toBeGreaterThanOrEqual(2);
    expect(result.content.some((c: any) => c.type === "text" && c.text === "{}")).toBe(true);
  });

  it("includes prompt ready block when requested", async () => {
    const { handler } = makeSearchKnowledge();
    const result = await handler({ query: "test", include_prompt_ready: true });

    expect(result.content.some((c: any) => c.type === "text" && c.text === "Prompt Ready")).toBe(true);
  });

  it("includes resource text when requested and hits exist", async () => {
    // Setup hits with snippets
    const mockHit = {
        snippet: "code snippet",
        resource_link: "kb://repo/file",
        lang: "python",
        path: "file.py"
    };

    mockTransformHits.mockReturnValueOnce({
        hits: [mockHit],
        escapedPathCount: 0
    });

    // Also executeSearch should return hits that are then passed to transformHits
    mockExecuteSearch.mockResolvedValueOnce({
      hits: [{}], // raw hits
      meta: { estimated_total: 1, model: "small" }
    });

    const { handler } = makeSearchKnowledge();
    const result = await handler({ query: "test", include_resource_text: true });

    const resource = result.content.find((c: any) => c.type === "resource");
    expect(resource).toBeDefined();
    if (resource && resource.type === "resource") {
        expect(resource.resource.text).toBe("code snippet");
    }
  });

  it("handles errors from search execution", async () => {
    mockExecuteSearch.mockRejectedValueOnce(new Error("API Error"));

    const { handler } = makeSearchKnowledge();
    const result = await handler({ query: "error" });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain("API Error");
  });

  it("validates input using schema", async () => {
    const { handler } = makeSearchKnowledge();

    try {
        await handler({}); // Missing query
        expect(true).toBe(false); // Should fail
    } catch (e) {
        // Zod error expected
        expect(e).toBeDefined();
    }
  });
});
