/**
 * Unit tests for search/transform.ts hit transformation
 *
 * Tests transformHits, getReposByName, and helper functions
 */

import { describe, it, expect, mock } from "bun:test";
import { transformHits, getReposByName } from "../../mcp/search/transform.js";
import type { ApiHit, SnippetInfo } from "../../mcp/search/contracts.js";
import type { RepoInfo } from "../../rest/client.js";

import { type KBClient } from "../../rest/client.js";

// Mock the rest client
const mockListRepos = mock(async () => ({
  repos: [
    { name: "repo1", path: "/path/to/repo1" },
    { name: "repo2", path: "/path/to/repo2" },
  ] as RepoInfo[],
}));

const mockClient = { listRepos: mockListRepos } as unknown as KBClient;

describe("transformHits", () => {
  const createMockHit = (overrides: Partial<ApiHit> = {}): ApiHit => ({
    repo: "test-repo",
    path: "src/test.ts",
    start_line: 10,
    end_line: 20,
    score: 0.9,
    snippet: "code snippet",
    chunk_id: "chunk-123",
    ...overrides,
  });

  it("transforms basic hits correctly", () => {
    const hits: ApiHit[] = [createMockHit()];
    const snippetsByHitIndex = new Map<number, SnippetInfo>();

    const result = transformHits({
      hits,
      snippetsByHitIndex,
      includeAbsPaths: false,
      includeVscodeUris: false,
    });

    expect(result.hits).toHaveLength(1);
    expect(result.hits[0].repo).toBe("test-repo");
    expect(result.hits[0].resource_link).toContain("kb://");
  });

  it("creates kb:// URIs with line numbers", () => {
    const hits: ApiHit[] = [createMockHit({ start_line: 5, end_line: 15 })];

    const result = transformHits({
      hits,
      snippetsByHitIndex: new Map(),
      includeAbsPaths: false,
      includeVscodeUris: false,
    });

    expect(result.hits[0].resource_link).toContain("L5-L15");
    expect(result.hits[0].chunk_resource_link).toContain("L5-L15");
  });

  it("uses snippet info when provided", () => {
    const hits: ApiHit[] = [createMockHit()];
    const snippetInfo: SnippetInfo = {
      snippet: "custom snippet",
      start: 1,
      end: 30,
    };
    const snippetsByHitIndex = new Map([[0, snippetInfo]]);

    const result = transformHits({
      hits,
      snippetsByHitIndex,
      includeAbsPaths: false,
      includeVscodeUris: false,
    });

    expect(result.hits[0].snippet).toBe("custom snippet");
    expect(result.hits[0]._context_start_line).toBe(1);
    expect(result.hits[0]._context_end_line).toBe(30);
  });

  it("creates absolute paths when repo info provided", () => {
    const hits: ApiHit[] = [createMockHit({ repo: "repo1", path: "src/file.ts" })];
    const reposByName = new Map<string, RepoInfo>([
      ["repo1", { name: "repo1", path: "/home/user/repo1" }],
    ]);

    const result = transformHits({
      hits,
      snippetsByHitIndex: new Map(),
      includeAbsPaths: true,
      includeVscodeUris: false,
      reposByName,
    });

    expect(result.hits[0].abs_path).toBeDefined();
    expect(result.hits[0].repo_root).toBe("/home/user/repo1");
  });

  it("creates vscode URIs when requested", () => {
    const hits: ApiHit[] = [createMockHit({ repo: "repo1", path: "src/file.ts", start_line: 10 })];
    const reposByName = new Map<string, RepoInfo>([
      ["repo1", { name: "repo1", path: "/home/user/repo1" }],
    ]);

    const result = transformHits({
      hits,
      snippetsByHitIndex: new Map(),
      includeAbsPaths: true,
      includeVscodeUris: true,
      reposByName,
    });

    expect(result.hits[0].vscode_uri).toBeDefined();
    expect(result.hits[0].vscode_uri).toContain("vscode://file/");
  });

  it("tracks escaped path count", () => {
    const hits: ApiHit[] = [createMockHit({ repo: "repo1", path: "../../../etc/passwd" })];
    const reposByName = new Map<string, RepoInfo>([
      ["repo1", { name: "repo1", path: "/home/user/repo1" }],
    ]);

    const result = transformHits({
      hits,
      snippetsByHitIndex: new Map(),
      includeAbsPaths: true,
      includeVscodeUris: false,
      reposByName,
    });

    // Should detect path escape attempt
    expect(result.escapedPathCount).toBeGreaterThan(0);
  });

  it("handles missing snippet info gracefully", () => {
    const hits: ApiHit[] = [createMockHit({ snippet: undefined })];

    const result = transformHits({
      hits,
      snippetsByHitIndex: new Map(),
      includeAbsPaths: false,
      includeVscodeUris: false,
    });

    expect(result.hits[0].snippet).toBe("");
  });

  it("preserves language field", () => {
    const hits: ApiHit[] = [createMockHit({ language: "typescript" })];

    const result = transformHits({
      hits,
      snippetsByHitIndex: new Map(),
      includeAbsPaths: false,
      includeVscodeUris: false,
    });

    expect(result.hits[0].lang).toBe("typescript");
  });

  it("handles hits without line numbers", () => {
    const hits: ApiHit[] = [createMockHit({ start_line: undefined, end_line: undefined })];

    const result = transformHits({
      hits,
      snippetsByHitIndex: new Map(),
      includeAbsPaths: false,
      includeVscodeUris: false,
    });

    // Should not crash and create valid URIs
    expect(result.hits[0].resource_link).toContain("kb://");
    expect(result.hits[0].resource_link).not.toContain("L");
  });

  it("transforms multiple hits", () => {
    const hits: ApiHit[] = [
      createMockHit({ chunk_id: "chunk1" }),
      createMockHit({ chunk_id: "chunk2" }),
      createMockHit({ chunk_id: "chunk3" }),
    ];

    const result = transformHits({
      hits,
      snippetsByHitIndex: new Map(),
      includeAbsPaths: false,
      includeVscodeUris: false,
    });

    expect(result.hits).toHaveLength(3);
    expect(result.hits[0].chunk_id).toBe("chunk1");
    expect(result.hits[1].chunk_id).toBe("chunk2");
    expect(result.hits[2].chunk_id).toBe("chunk3");
  });
});

describe("getReposByName", () => {
  it("fetches and caches repo list", async () => {
    mockListRepos.mockImplementation(async () => ({
      repos: [
        { name: "repo1", path: "/path1" },
        { name: "repo2", path: "/path2" },
      ],
    }));

    const result = await getReposByName(undefined, mockClient);

    expect(result.size).toBe(2);
    expect(result.get("repo1")?.path).toBe("/path1");
    expect(result.get("repo2")?.path).toBe("/path2");
  });

  it("does not pollute cache when client provided", async () => {
    // Reset any previous cache state (though we can't easily reset the module-level variable without reloading)
    // We rely on the fact that if the bug exists, the cache is global.

    // First call with Client A
    const mockClientA = {
      listRepos: mock(async () => ({
        repos: [{ name: "repo1", path: "/clientA/path1" }] as RepoInfo[],
      })),
    } as unknown as KBClient;

    const resultA = await getReposByName(undefined, mockClientA);
    expect(resultA.get("repo1")?.path).toBe("/clientA/path1");

    // Second call with Client B
    const mockClientB = {
      listRepos: mock(async () => ({
        repos: [{ name: "repo1", path: "/clientB/path1" }] as RepoInfo[],
      })),
    } as unknown as KBClient;

    const resultB = await getReposByName(undefined, mockClientB);
    
    // With the bug, this would be /clientA/path1 because cache was hit
    // With the fix, this should be /clientB/path1 because cache is bypassed
    expect(resultB.get("repo1")?.path).toBe("/clientB/path1");
  });
});
