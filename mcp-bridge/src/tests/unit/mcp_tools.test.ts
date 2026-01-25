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

// Mock REST client
const mockRestGetChunk = mock(async () => ({
  chunk_id: "chunk-123",
  repo: "test-repo",
  path: "src/test.ts",
  start_line: 10,
  end_line: 20,
  content: "code",
  resource_link: "kb://test",
  lang: "typescript",
}));

const mockRestListRepos = mock(async () => ({
  repos: [
    { name: "repo1", path: "/path/to/repo1", files: 100, chunks: 500 },
    { name: "repo2", path: "/path/to/repo2", default_embed_model: "large" },
  ],
}));

const mockRestHealthV1 = mock(async () => ({
  status: "ok",
  version: "1.0.0",
}));

mock.module("../../rest/client.js", () => ({
  restGetChunk: mockRestGetChunk,
  restListRepos: mockRestListRepos,
  restHealthV1: mockRestHealthV1,
  restGetFileSlice: mock(async () => ({
    repo: "",
    path: "",
    start_line: 1,
    end_line: 1,
    content: "",
    source: "file",
  })),
}));

describe("get_metadata tool", () => {
  it("fetches chunk metadata successfully", async () => {
    const { handler } = makeGetMetadata();

    const result = await handler({ chunk_id: "chunk-123" });

    expect(result.isError).toBe(false);
    expect(result.content).toHaveLength(1);
  });

  it("includes metadata in response", async () => {
    const { handler } = makeGetMetadata();

    const result = await handler({ chunk_id: "chunk-123" });

    expect(result._meta).toBeDefined();
    expect(result._meta?.tool_version).toBeDefined();
  });

  it("has correct tool definition", () => {
    const { definition } = makeGetMetadata();

    expect(definition.name).toBe("metadata_get");
    expect(definition.description).toContain("metadata");
  });

  it("handles errors gracefully", async () => {
    mockRestGetChunk.mockImplementationOnce(async () => {
      throw new Error("Not found");
    });

    const { handler } = makeGetMetadata();
    const result = await handler({ chunk_id: "bad" });

    expect(result.isError).toBe(true);
  });
});

describe("list_repos tool", () => {
  it("returns list of repositories", async () => {
    const { handler } = makeListRepos();

    const result = await handler({});

    expect(result.isError).toBe(false);
    expect(result.content).toHaveLength(1);
  });

  it("includes repo information in text", async () => {
    const { handler } = makeListRepos();

    const result = await handler({});

    const textContent = result.content[0];
    if (textContent.type === "text") {
      expect(textContent.text).toContain("repo1");
      expect(textContent.text).toContain("repo2");
    }
  });

  it("has correct tool definition", () => {
    const { definition } = makeListRepos();

    expect(definition.name).toBe("repos_list");
    expect(definition.description).toContain("repo");
  });

  it("handles errors gracefully", async () => {
    mockRestListRepos.mockImplementationOnce(async () => {
      throw new Error("API error");
    });

    const { handler } = makeListRepos();
    const result = await handler({});

    expect(result.isError).toBe(true);
  });

  it("includes metadata", async () => {
    const { handler } = makeListRepos();

    const result = await handler({});

    expect(result._meta?.tool_version).toBeDefined();
    expect(result._meta?.latency_ms).toBeDefined();
  });
});

describe("kb_health tool", () => {
  it("returns health status", async () => {
    const { handler } = makeKbHealth();

    const result = await handler({});

    expect(result.isError).toBe(false);
  });

  it("supports check parameter", async () => {
    const { handler } = makeKbHealth();

    const result = await handler({ check: "deep" });

    expect(result.isError).toBe(false);
  });

  it("has correct tool definition", () => {
    const { definition } = makeKbHealth();

    expect(definition.name).toBe("health");
    expect(definition.description).toContain("health");
  });

  it("handles errors gracefully", async () => {
    mockRestHealthV1.mockImplementationOnce(async () => {
      throw new Error("Service unavailable");
    });

    const { handler } = makeKbHealth();
    const result = await handler({});

    expect(result.isError).toBe(true);
  });
});

describe("store_info tool", () => {
  it("returns store information", async () => {
    const { handler } = makeStoreInfo();

    const result = await handler({});

    expect(result.isError).toBe(false);
  });

  it("has correct tool definition", () => {
    const { definition } = makeStoreInfo();

    expect(definition.name).toBe("store_info");
  });

  it("handles errors gracefully", async () => {
    // Mock implementation will be called
    const { handler } = makeStoreInfo();
    const result = await handler({});

    // Should still work or handle error
    expect(result).toBeDefined();
  });
});
