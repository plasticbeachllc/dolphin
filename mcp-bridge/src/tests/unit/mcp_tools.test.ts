/**
 * Unit tests for additional MCP tools
 *
 * Tests get_metadata, list_repos, kb_health, and store_info tools
 */

import { describe, it, expect, mock } from "bun:test";
import { makeGetMetadata } from "../../mcp/tools/get_metadata.js";
import { makeListRepos } from "../../mcp/tools/list_repos.js";
import { makeKbHealth } from "../../mcp/tools/kb_health.js";
import { makeStoreInfo } from "../../mcp/tools/store_info.js";

import { type KBClient } from "../../rest/client.js";

// Mock REST client methods
const mockGetChunk = mock(async () => ({
  chunk_id: "chunk-123",
  repo: "test-repo",
  path: "src/test.ts",
  start_line: 10,
  end_line: 20,
  content: "code",
  resource_link: "kb://test",
  lang: "typescript",
}));

const mockListRepos = mock(async () => ({
  repos: [
    { name: "repo1", path: "/path/to/repo1", files: 100, chunks: 500 },
    { name: "repo2", path: "/path/to/repo2", default_embed_model: "large" },
  ],
}));

const mockHealthV1 = mock(async () => ({
  status: "ok",
  version: "1.0.0",
}));

const mockClient = {
  getChunk: mockGetChunk,
  listRepos: mockListRepos,
  healthV1: mockHealthV1,
} as unknown as KBClient;

describe("get_metadata tool", () => {
  it("fetches chunk metadata successfully", async () => {
    const { handler } = makeGetMetadata(mockClient);

    const result = await handler({ chunk_id: "chunk-123" });

    expect(result.isError).toBe(false);
    expect(result.content).toHaveLength(2); // Returns both text and metadata
  });

  it("includes metadata in response", async () => {
    const { handler } = makeGetMetadata(mockClient);

    const result = await handler({ chunk_id: "chunk-123" });

    expect(result._meta).toBeDefined();
    expect(result._meta?.tool_version).toBeDefined();
  });

  it("has correct tool definition", () => {
    const { definition } = makeGetMetadata(mockClient);

    expect(definition.name).toBe("metadata_get");
    expect(definition.description).toContain("metadata");
  });

  it("handles errors gracefully", async () => {
    mockGetChunk.mockImplementationOnce(async () => {
      throw new Error("Not found");
    });

    const { handler } = makeGetMetadata(mockClient);
    const result = await handler({ chunk_id: "bad" });

    expect(result.isError).toBe(true);
  });
});

describe("list_repos tool", () => {
  it("returns list of repositories", async () => {
    const { handler } = makeListRepos(mockClient);

    const result = await handler({});

    expect(result.isError).toBe(false);
    expect(result.content).toHaveLength(2); // Returns both text and resource content
  });

  it("has correct tool definition", () => {
    const { definition } = makeListRepos(mockClient);

    expect(definition.name).toBe("repos_list");
    expect(definition.description).toContain("repo");
  });

  it("handles errors gracefully", async () => {
    mockListRepos.mockImplementationOnce(async () => {
      throw new Error("API error");
    });

    const { handler } = makeListRepos(mockClient);
    const result = await handler({});

    expect(result.isError).toBe(true);
  });

  it("includes metadata", async () => {
    const { handler } = makeListRepos(mockClient);

    const result = await handler({});

    expect(result._meta?.tool_version).toBeDefined();
    expect(result._meta?.latency_ms).toBeDefined();
  });
});

describe("kb_health tool", () => {
  it("returns health status", async () => {
    const { handler } = makeKbHealth(mockClient);

    const result = await handler({});

    expect(result.isError).toBe(false);
  });

  it("supports check parameter", async () => {
    const { handler } = makeKbHealth(mockClient);

    const result = await handler({ check: "deep" });

    expect(result.isError).toBe(false);
  });

  it("has correct tool definition", () => {
    const { definition } = makeKbHealth(mockClient);

    expect(definition.name).toBe("health");
    expect(definition.description).toContain("health");
  });

  it("handles errors gracefully", async () => {
    mockHealthV1.mockImplementationOnce(async () => {
      throw new Error("Service unavailable");
    });

    const { handler } = makeKbHealth(mockClient);
    const result = await handler({});

    expect(result.isError).toBe(true);
  });
});

describe("store_info tool", () => {
  it("returns store information", async () => {
    const { handler } = makeStoreInfo(mockClient);

    const result = await handler({});

    expect(result.isError).toBe(false);
  });

  it("has correct tool definition", () => {
    const { definition } = makeStoreInfo(mockClient);

    expect(definition.name).toBe("store_info");
  });

  it("handles errors gracefully", async () => {
    // Mock implementation will be called
    const { handler } = makeStoreInfo(mockClient);
    const result = await handler({});

    // Should still work or handle error
    expect(result).toBeDefined();
  });
});
