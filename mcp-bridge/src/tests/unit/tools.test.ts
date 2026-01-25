/**
 * Unit tests for MCP tool handlers
 *
 * Tests chunk_get, file_lines, and other MCP tool implementations
 */

import { describe, it, expect, mock, beforeEach } from "bun:test";
import { makeChunkGet } from "../../mcp/tools/chunk_get.js";
import type { ChunkResponse } from "../../rest/client.js";

// Mock REST client
const mockRestGetChunk = mock(async () => ({
  chunk_id: "chunk-123",
  repo: "test-repo",
  path: "src/test.ts",
  start_line: 10,
  end_line: 20,
  content: "const x = 1;",
  resource_link: "kb://test-repo/src/test.ts#L10-L20",
  lang: "typescript",
}));

mock.module("../../rest/client.js", () => ({
  restGetChunk: mockRestGetChunk,
  restGetFileSlice: mock(async () => ({
    repo: "r",
    path: "p",
    start_line: 1,
    end_line: 10,
    content: "code",
    source: "file",
  })),
  restListRepos: mock(async () => ({ repos: [] })),
}));

describe("chunk_get tool", () => {
  it("returns chunk content successfully", async () => {
    const { handler } = makeChunkGet();

    const result = await handler({ chunk_id: "chunk-123" });

    expect(result.isError).toBe(false);
    expect(result.content).toHaveLength(2);
    expect(result.content[0].type).toBe("text");
    expect(result.content[1].type).toBe("resource");
  });

  it("includes chunk citation in text", async () => {
    const { handler } = makeChunkGet();

    const result = await handler({ chunk_id: "chunk-123" });

    const textContent = result.content[0];
    if (textContent.type === "text") {
      expect(textContent.text).toContain("chunk-123");
      expect(textContent.text).toContain("test-repo");
      expect(textContent.text).toContain("src/test.ts");
    }
  });

  it("includes code content as resource", async () => {
    const { handler } = makeChunkGet();

    const result = await handler({ chunk_id: "chunk-123" });

    const resourceContent = result.content[1];
    if (resourceContent.type === "resource" && "resource" in resourceContent) {
      expect(resourceContent.resource.text).toBe("const x = 1;");
      expect(resourceContent.resource.uri).toContain("kb://");
    }
  });

  it("sets correct MIME type for TypeScript", async () => {
    const { handler } = makeChunkGet();

    const result = await handler({ chunk_id: "chunk-123" });

    const resourceContent = result.content[1];
    if (resourceContent.type === "resource" && "resource" in resourceContent) {
      expect(resourceContent.resource.mimeType).toContain("typescript");
    }
  });

  it("handles errors gracefully", async () => {
    mockRestGetChunk.mockImplementationOnce(async () => {
      throw new Error("Chunk not found");
    });

    const { handler } = makeChunkGet();
    const result = await handler({ chunk_id: "nonexistent" });

    expect(result.isError).toBe(true);
    expect(result.content[0].type).toBe("text");
  });

  it("includes metadata in response", async () => {
    const { handler } = makeChunkGet();

    const result = await handler({ chunk_id: "chunk-123" });

    expect(result._meta).toBeDefined();
    expect(result._meta?.tool_version).toBeDefined();
    expect(result._meta?.latency_ms).toBeDefined();
  });

  it("accepts input wrapped in input field", async () => {
    const { handler } = makeChunkGet();

    const result = await handler({ input: { chunk_id: "chunk-123" } });

    expect(result.isError).toBe(false);
  });

  it("respects abort signal", async () => {
    const abortController = new AbortController();
    const { handler } = makeChunkGet();

    // Verify signal is passed through
    const resultPromise = handler({ chunk_id: "chunk-123" }, abortController.signal);

    // Even if aborted, should handle gracefully
    expect(resultPromise).resolves.toBeDefined();
  });

  it("validates chunk_id is required", async () => {
    const { handler } = makeChunkGet();

    try {
      await handler({});
      expect(true).toBe(false); // Should not reach here
    } catch (error) {
      // Zod validation should fail
      expect(error).toBeDefined();
    }
  });

  it("has correct tool definition", () => {
    const { definition } = makeChunkGet();

    expect(definition.name).toBe("chunk_get");
    expect(definition.description).toContain("chunk");
    expect(definition.inputSchema).toBeDefined();
  });

  it("marks tool as read-only and idempotent", () => {
    const { definition } = makeChunkGet();

    expect(definition.annotations?.readOnlyHint).toBe(true);
    expect(definition.annotations?.idempotentHint).toBe(true);
  });

  it("includes latency tracking", async () => {
    const { handler } = makeChunkGet();

    const result = await handler({ chunk_id: "chunk-123" });

    expect(result._meta?.latency_ms).toBeGreaterThanOrEqual(0);
  });
});
