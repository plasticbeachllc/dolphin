import { describe, test, expect, mock } from "bun:test";
import { makeOpenRef } from "../../mcp/tools/open_ref.js";
import { z } from "zod";

describe("open_ref tool", () => {
  test("handles kb:// URI (file slice)", async () => {
    const mockClient = {
      getFileSlice: mock(() =>
        Promise.resolve({
          repo: "my-repo",
          path: "src/main.py",
          start_line: 10,
          end_line: 20,
          content: "print('hello')",
          lang: "python",
        })
      ),
      getChunk: mock(() => Promise.resolve({})),
    };

    const { handler } = makeOpenRef(mockClient as any);
    const result = await handler({ ref: "kb://my-repo/src/main.py#L10-L20" });

    expect(mockClient.getFileSlice).toHaveBeenCalledWith(
      "my-repo",
      "src/main.py",
      10,
      20,
      undefined
    );
    expect(result.isError).toBe(false);
    expect(result.content[0].text).toBe("my-repo/src/main.py#L10-L20");
    expect(result.content[1].resource.uri).toBe("kb://my-repo/src/main.py#L10-L20");
    expect(result.content[1].resource.text).toBe("print('hello')");
  });

  test("handles chunk_id (chunk get)", async () => {
    const mockClient = {
      getFileSlice: mock(() => Promise.resolve({})),
      getChunk: mock(() =>
        Promise.resolve({
          chunk_id: "chunk-123",
          repo: "my-repo",
          path: "src/utils.ts",
          start_line: 5,
          end_line: 15,
          content: "export function foo() {}",
          lang: "typescript",
          resource_link: "kb://my-repo/src/utils.ts#L5-L15",
        })
      ),
    };

    const { handler } = makeOpenRef(mockClient as any);
    const result = await handler({ ref: "chunk-123" });

    expect(mockClient.getChunk).toHaveBeenCalledWith("chunk-123", undefined);
    expect(result.isError).toBe(false);
    expect(result.content[0].text).toContain("Chunk chunk-123");
    expect(result.content[1].resource.uri).toBe("kb://my-repo/src/utils.ts#L5-L15");
    expect(result.content[1].resource.text).toBe("export function foo() {}");
  });

  test("handles errors gracefully", async () => {
    const mockClient = {
      getFileSlice: mock(() => Promise.reject(new Error("File not found"))),
      getChunk: mock(() => Promise.resolve({})),
    };

    const { handler } = makeOpenRef(mockClient as any);
    const result = await handler({ ref: "kb://repo/missing#L1-L2" });

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain("File not found");
  });

  test("handles malformed kb:// URI as chunk_id", async () => {
    // A URI without line numbers should fall through to chunk_get logic
    const mockClient = {
      getFileSlice: mock(() => Promise.resolve({})),
      getChunk: mock(() =>
        Promise.resolve({
          chunk_id: "kb://my-repo/file.txt", // weird chunk ID but valid string
          repo: "my-repo",
          path: "file.txt",
          start_line: 1,
          end_line: 10,
          content: "content",
          lang: "text",
          resource_link: "kb://my-repo/file.txt#L1-L10",
        })
      ),
    };

    const { handler } = makeOpenRef(mockClient as any);
    // This looks like a URI but doesn't match the REGEX (missing #L...-L...)
    // So it should be treated as a chunk ID
    const result = await handler({ ref: "kb://my-repo/file.txt" });

    expect(mockClient.getChunk).toHaveBeenCalledWith("kb://my-repo/file.txt", undefined);
    expect(mockClient.getFileSlice).not.toHaveBeenCalled();
    expect(result.isError).toBe(false);
  });

  test("handles empty string", async () => {
    const mockClient = {
      getFileSlice: mock(() => Promise.resolve({})),
      getChunk: mock(() => Promise.reject(new Error("Chunk not found"))),
    };
    const { handler } = makeOpenRef(mockClient as any);
    const result = await handler({ ref: "" });

    // Empty string matches nothing, goes to chunk_get, returns error
    expect(result.isError).toBe(true);
  });
});
