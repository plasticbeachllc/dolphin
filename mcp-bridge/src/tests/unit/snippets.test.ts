/**
 * Unit tests for search/snippets.ts
 *
 * Tests snippet fetching coordination for search results
 */

import { describe, it, expect, mock } from "bun:test";
import { fetchSnippetsForHits } from "../../mcp/search/snippets.js";
import type { ApiHit } from "../../mcp/search/contracts.js";

// Mock snippet fetcher
const mockFetchSnippetsInParallel = mock(async () => ({}));

describe("fetchSnippetsForHits", () => {
  it("returns empty when snippets disabled", async () => {
    const hits: ApiHit[] = [
      {
        repo: "r",
        path: "p",
        start_line: 1,
        end_line: 10,
        score: 0.9,
        snippet: "code",
        chunk_id: "c",
      },
    ];

    const result = await fetchSnippetsForHits({
      hits,
      includeSnippets: false,
      snippetsTopN: 10,
      topContextN: 5,
      contextLinesBefore: 3,
      contextLinesAfter: 3,
    });

    expect(result.snippetsByHitIndex.size).toBe(0);
    expect(result.snippetFailures).toHaveLength(0);
  });

  it("fetches snippets for valid hits", async () => {
    mockFetchSnippetsInParallel.mockImplementationOnce(async () => ({
      0: { content: "fetched code", actualStartLine: 1, actualEndLine: 10 },
    }));

    const hits: ApiHit[] = [
      {
        repo: "r",
        path: "p",
        start_line: 1,
        end_line: 10,
        score: 0.9,
        snippet: "code",
        chunk_id: "c",
      },
    ];

    const result = await fetchSnippetsForHits({
      hits,
      includeSnippets: true,
      snippetsTopN: 10,
      topContextN: 5,
      contextLinesBefore: 3,
      contextLinesAfter: 3,
      fetcher: mockFetchSnippetsInParallel,
    });

    expect(result.snippetsByHitIndex.size).toBe(1);
    expect(result.snippetsByHitIndex.get(0)?.snippet).toBe("fetched code");
  });

  it("respects snippetsTopN limit", async () => {
    const hits: ApiHit[] = Array.from({ length: 20 }, (_, i) => ({
      repo: "r",
      path: `file${i}.ts`,
      start_line: 1,
      end_line: 10,
      score: 0.9,
      snippet: "code",
      chunk_id: `c${i}`,
    }));

    await fetchSnippetsForHits({
      hits,
      includeSnippets: true,
      snippetsTopN: 5,
      topContextN: 2,
      contextLinesBefore: 3,
      contextLinesAfter: 3,
      fetcher: mockFetchSnippetsInParallel,
    });

    // Should only request 5 snippets
    expect(mockFetchSnippetsInParallel).toHaveBeenCalled();
    const calls = mockFetchSnippetsInParallel.mock.calls as any;
    const requests = calls[calls.length - 1][0];
    expect(requests.length).toBe(5);
  });

  it("handles snippet fetch failures", async () => {
    mockFetchSnippetsInParallel.mockImplementationOnce(async () => ({
      0: null, // Failed fetch
    }));

    const hits: ApiHit[] = [
      {
        repo: "r",
        path: "p",
        start_line: 1,
        end_line: 10,
        score: 0.9,
        snippet: "code",
        chunk_id: "c",
      },
    ];

    const result = await fetchSnippetsForHits({
      hits,
      includeSnippets: true,
      snippetsTopN: 10,
      topContextN: 5,
      contextLinesBefore: 3,
      contextLinesAfter: 3,
      fetcher: mockFetchSnippetsInParallel,
    });

    expect(result.snippetsByHitIndex.size).toBe(0);
    expect(result.snippetFailures).toHaveLength(1);
    expect(result.snippetFailures[0].repo).toBe("r");
  });

  it("skips hits with missing required fields", async () => {
    const hits: ApiHit[] = [
      {
        repo: "r",
        path: "p",
        start_line: 1,
        end_line: 10,
        score: 0.9,
        snippet: "code",
        chunk_id: "c",
      },
      {
        repo: "",
        path: "p",
        start_line: 1,
        end_line: 10,
        score: 0.9,
        snippet: "code",
        chunk_id: "c2",
      } as ApiHit,
      {
        repo: "r",
        path: "",
        start_line: 1,
        end_line: 10,
        score: 0.9,
        snippet: "code",
        chunk_id: "c3",
      } as ApiHit,
    ];

    await fetchSnippetsForHits({
      hits,
      includeSnippets: true,
      snippetsTopN: 10,
      topContextN: 5,
      contextLinesBefore: 3,
      contextLinesAfter: 3,
      fetcher: mockFetchSnippetsInParallel,
    });

    const calls = mockFetchSnippetsInParallel.mock.calls as any;
    const requests = calls[calls.length - 1][0];
    // Should only request for the valid hit
    expect(requests.length).toBe(1);
  });

  it("applies context lines for top hits", async () => {
    mockFetchSnippetsInParallel.mockImplementationOnce(async () => ({}));

    const hits: ApiHit[] = Array.from({ length: 10 }, (_, i) => ({
      repo: "r",
      path: `file${i}.ts`,
      start_line: 1,
      end_line: 10,
      score: 0.9,
      snippet: "code",
      chunk_id: `c${i}`,
    }));

    await fetchSnippetsForHits({
      hits,
      includeSnippets: true,
      snippetsTopN: 10,
      topContextN: 3,
      contextLinesBefore: 5,
      contextLinesAfter: 5,
      fetcher: mockFetchSnippetsInParallel,
    });

    const calls = mockFetchSnippetsInParallel.mock.calls as any;
    const requests = calls[calls.length - 1][0];

    // First 3 should have context
    expect(requests[0].contextLinesBefore).toBe(5);
    expect(requests[0].contextLinesAfter).toBe(5);
    expect(requests[1].contextLinesBefore).toBe(5);
    expect(requests[2].contextLinesBefore).toBe(5);

    // Rest should have no context
    if (requests[3]) {
      expect(requests[3].contextLinesBefore).toBe(0);
      expect(requests[3].contextLinesAfter).toBe(0);
    }
  });

  it("passes abort signal through", async () => {
    const abortController = new AbortController();
    const hits: ApiHit[] = [
      {
        repo: "r",
        path: "p",
        start_line: 1,
        end_line: 10,
        score: 0.9,
        snippet: "code",
        chunk_id: "c",
      },
    ];

    await fetchSnippetsForHits({
      hits,
      includeSnippets: true,
      snippetsTopN: 10,
      topContextN: 5,
      contextLinesBefore: 3,
      contextLinesAfter: 3,
      signal: abortController.signal,
      fetcher: mockFetchSnippetsInParallel,
    });

    // Verify signal was passed
    expect(mockFetchSnippetsInParallel).toHaveBeenCalled();
  });
});
