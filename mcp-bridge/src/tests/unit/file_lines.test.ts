/**
 * Unit tests for file_lines MCP tool
 *
 * Tests file_lines tool handler for fetching file slices
 */

import { describe, it, expect, mock } from "bun:test";
import { makeFileLines } from "../../mcp/tools/file_lines.js";

// Mock REST client
const mockRestGetFileSlice = mock(async () => ({
  repo: "test-repo",
  path: "src/test.ts",
  start_line: 1,
  end_line: 10,
  content: "function test() {\n  return 42;\n}",
  lang: "typescript",
  source: "file",
}));

mock.module("../../rest/client.js", () => ({
  restGetFileSlice: mockRestGetFileSlice,
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

describe("file_lines tool", () => {
  it("fetches file slice successfully", async () => {
    const { handler } = makeFileLines();

    const result = await handler({
      repo: "test-repo",
      path: "src/test.ts",
      start: 1,
      end: 10,
    });

    expect(result.isError).toBe(false);
    expect(result.content).toHaveLength(2);
  });

  it("includes file citation", async () => {
    const { handler } = makeFileLines();

    const result = await handler({
      repo: "test-repo",
      path: "src/test.ts",
      start: 1,
      end: 10,
    });

    const textContent = result.content[0];
    if (textContent.type === "text") {
      expect(textContent.text).toContain("test-repo");
      expect(textContent.text).toContain("src/test.ts");
      expect(textContent.text).toContain("L1-L10");
    }
  });

  it("returns code as resource", async () => {
    const { handler } = makeFileLines();

    const result = await handler({
      repo: "test-repo",
      path: "src/test.ts",
      start: 1,
      end: 10,
    });

    const resourceContent = result.content[1];
    if (resourceContent.type === "resource" && "resource" in resourceContent) {
      expect(resourceContent.resource.text).toContain("function test()");
    }
  });

  it("validates required fields", async () => {
    const { handler } = makeFileLines();

    try {
      await handler({ repo: "test-repo" }); // Missing path, start, end
      expect(true).toBe(false);
    } catch (error) {
      expect(error).toBeDefined();
    }
  });

  it("has correct tool definition", () => {
    const { definition } = makeFileLines();

    expect(definition.name).toBe("file_lines");
    expect(definition.description).toContain("file");
  });

  it("handles errors gracefully", async () => {
    mockRestGetFileSlice.mockImplementationOnce(async () => {
      throw new Error("File not found");
    });

    const { handler } = makeFileLines();
    const result = await handler({
      repo: "test-repo",
      path: "nonexistent.ts",
      start: 1,
      end: 10,
    });

    expect(result.isError).toBe(true);
  });

  it("accepts input wrapped in input field", async () => {
    const { handler } = makeFileLines();

    const result = await handler({
      input: {
        repo: "test-repo",
        path: "src/test.ts",
        start: 1,
        end: 10,
      },
    });

    expect(result.isError).toBe(false);
  });

  it("includes metadata", async () => {
    const { handler } = makeFileLines();

    const result = await handler({
      repo: "test-repo",
      path: "src/test.ts",
      start: 1,
      end: 10,
    });

    expect(result._meta).toBeDefined();
    expect(result._meta?.latency_ms).toBeDefined();
  });
});
