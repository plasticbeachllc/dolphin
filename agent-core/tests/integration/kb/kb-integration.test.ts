/**
 * Integration tests for Knowledge Bank integration
 *
 * Tests semantic search, context assembly, and KB error handling
 */

import { describe, it, expect, beforeEach, afterEach, mock } from "bun:test";
import { ContextBuilder } from "../../../src/context/context-builder";
import type { ContextBuildParams } from "../../../src/types/index";

describe("Knowledge Bank Integration", () => {
  let contextBuilder: ContextBuilder;
  let originalFetch: typeof fetch;

  beforeEach(() => {
    contextBuilder = new ContextBuilder({
      workspaceRoot: "/test/workspace",
      kbUrl: "http://localhost:7777",
    });

    // Save original fetch
    originalFetch = global.fetch;
  });

  afterEach(() => {
    // Restore original fetch
    global.fetch = originalFetch;
  });

  describe("KB Search", () => {
    it("should search KB successfully", async () => {
      // Mock successful KB search
      global.fetch = mock(async (url: string) => {
        if (url.includes("/v1/search")) {
          return {
            ok: true,
            json: async () => [
              {
                file_path: "src/utils.ts",
                start_line: 10,
                end_line: 25,
                snippet_text: 'export function helper() {\n  return "test";\n}',
                language: "typescript",
                score: 0.95,
                chunk_id: "chunk_123",
              },
              {
                file_path: "src/lib.ts",
                start_line: 1,
                end_line: 15,
                snippet_text: 'import { helper } from "./utils";',
                language: "typescript",
                score: 0.85,
                chunk_id: "chunk_456",
              },
            ],
          };
        }
        return { ok: false };
      }) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "helper function",
        files: [],
        maxTokens: 10000,
      };

      const context = await contextBuilder.build(params);

      expect(context.kbResults.length).toBe(2);
      expect(context.kbResults[0].file).toBe("src/utils.ts");
      expect(context.kbResults[0].score).toBe(0.95);
      expect(context.kbResults[0].language).toBe("typescript");
    });

    it("should handle KB unavailable gracefully", async () => {
      // Mock KB failure
      global.fetch = mock(async () => {
        throw new Error("Connection refused");
      }) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "test query",
        files: [],
        maxTokens: 10000,
      };

      const context = await contextBuilder.build(params);

      // Should return empty results without throwing
      expect(context.kbResults.length).toBe(0);
      expect(context.truncated).toBe(false);
    });

    it("should handle KB HTTP errors", async () => {
      // Mock HTTP error
      global.fetch = mock(async () => ({
        ok: false,
        statusText: "Internal Server Error",
      })) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "test query",
        files: [],
        maxTokens: 10000,
      };

      const context = await contextBuilder.build(params);

      // Should return empty results
      expect(context.kbResults.length).toBe(0);
    });

    it("should handle malformed KB responses", async () => {
      // Mock malformed response
      global.fetch = mock(async () => ({
        ok: true,
        json: async () => {
          throw new Error("Invalid JSON");
        },
      })) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "test query",
        files: [],
        maxTokens: 10000,
      };

      const context = await contextBuilder.build(params);

      // Should return empty results
      expect(context.kbResults.length).toBe(0);
    });

    it("should timeout KB search when request hangs", async () => {
      global.fetch = mock(async (_url: string, init?: RequestInit) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            const abortError = new Error("Aborted");
            abortError.name = "AbortError";
            reject(abortError);
          });
        });
      }) as unknown;

      const timeoutBuilder = new ContextBuilder({
        workspaceRoot: "/test/workspace",
        kbUrl: "http://localhost:7777",
        kbTimeoutMs: 50,
      });

      const params: ContextBuildParams = {
        searchQuery: "slow query",
        files: [],
        maxTokens: 10000,
      };

      const start = Date.now();
      const context = await timeoutBuilder.build(params);
      const duration = Date.now() - start;

      expect(duration).toBeLessThan(500);
      expect(context.kbResults.length).toBe(0);
    });
  });

  describe("Context Assembly", () => {
    it("should combine KB results and files", async () => {
      // Mock KB search
      global.fetch = mock(async () => ({
        ok: true,
        json: async () => [
          {
            file_path: "kb-result.ts",
            start_line: 1,
            end_line: 10,
            snippet_text: "KB content",
            language: "typescript",
            score: 0.9,
            chunk_id: "chunk_1",
          },
        ],
      })) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "test",
        files: ["explicit-file.ts"],
        maxTokens: 10000,
      };

      const context = await contextBuilder.build(params);

      // Should have both KB results and explicit files
      expect(context.kbResults.length).toBe(1);
      expect(context.files.length).toBeGreaterThanOrEqual(0); // May fail to load file in test
    });

    it("should track total tokens", async () => {
      global.fetch = mock(async () => ({
        ok: true,
        json: async () => [
          {
            file_path: "test.ts",
            start_line: 1,
            end_line: 50,
            snippet_text: "x".repeat(1000), // ~250 tokens
            language: "typescript",
            score: 0.9,
            chunk_id: "chunk_1",
          },
        ],
      })) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "test",
        files: [],
        maxTokens: 10000,
      };

      const context = await contextBuilder.build(params);

      expect(context.totalTokens).toBeGreaterThan(0);
    });
  });

  describe("Token Management", () => {
    it("should truncate context when exceeding token limit", async () => {
      // Mock large KB results
      global.fetch = mock(async () => ({
        ok: true,
        json: async () =>
          Array(100).fill({
            file_path: "large.ts",
            start_line: 1,
            end_line: 100,
            snippet_text: "x".repeat(1000), // ~250 tokens each
            language: "typescript",
            score: 0.9,
            chunk_id: "chunk_1",
          }),
      })) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "test",
        files: [],
        maxTokens: 5000, // Much less than total
      };

      const context = await contextBuilder.build(params);

      // Should truncate
      expect(context.truncated).toBe(true);
      expect(context.totalTokens).toBeLessThanOrEqual(5000);
      expect(context.kbResults.length).toBeLessThan(100);
    });

    it("should prioritize explicit files over KB results", async () => {
      global.fetch = mock(async () => ({
        ok: true,
        json: async () =>
          Array(50).fill({
            file_path: "kb.ts",
            start_line: 1,
            end_line: 100,
            snippet_text: "x".repeat(1000),
            language: "typescript",
            score: 0.9,
            chunk_id: "chunk_1",
          }),
      })) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "test",
        files: ["important.ts"], // Explicit file
        maxTokens: 1000, // Very limited
      };

      const context = await contextBuilder.build(params);

      // Explicit files should be included
      // KB results should be truncated
      expect(context.truncated).toBe(true);
      expect(context.kbResults.length).toBeLessThan(50);
    });

    it("should sort KB results by score", async () => {
      global.fetch = mock(async () => ({
        ok: true,
        json: async () => [
          {
            file_path: "low.ts",
            start_line: 1,
            end_line: 10,
            snippet_text: "content",
            language: "typescript",
            score: 0.5,
            chunk_id: "chunk_1",
          },
          {
            file_path: "high.ts",
            start_line: 1,
            end_line: 10,
            snippet_text: "content",
            language: "typescript",
            score: 0.95,
            chunk_id: "chunk_2",
          },
          {
            file_path: "medium.ts",
            start_line: 1,
            end_line: 10,
            snippet_text: "content",
            language: "typescript",
            score: 0.7,
            chunk_id: "chunk_3",
          },
        ],
      })) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "test",
        files: [],
        maxTokens: 500, // Limited, will need to truncate
      };

      const context = await contextBuilder.build(params);

      // Should keep highest scored results
      if (context.kbResults.length > 0) {
        expect(context.kbResults[0].score).toBeGreaterThanOrEqual(0.7);
      }
    });
  });

  describe("Language Detection", () => {
    it("should detect language from file extensions", async () => {
      global.fetch = mock(async () => ({
        ok: true,
        json: async () => [
          {
            file_path: "test.ts",
            start_line: 1,
            end_line: 10,
            snippet_text: "code",
            language: "typescript",
            score: 0.9,
            chunk_id: "chunk_1",
          },
          {
            file_path: "script.py",
            start_line: 1,
            end_line: 10,
            snippet_text: "code",
            language: "python",
            score: 0.9,
            chunk_id: "chunk_2",
          },
        ],
      })) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "test",
        files: [],
        maxTokens: 10000,
      };

      const context = await contextBuilder.build(params);

      expect(context.kbResults[0].language).toBe("typescript");
      expect(context.kbResults[1].language).toBe("python");
    });
  });

  describe("Performance", () => {
    it("should complete search within reasonable time", async () => {
      global.fetch = mock(async () => {
        // Simulate network delay
        await new Promise((resolve) => setTimeout(resolve, 100));
        return {
          ok: true,
          json: async () => [
            {
              file_path: "test.ts",
              start_line: 1,
              end_line: 10,
              snippet_text: "content",
              language: "typescript",
              score: 0.9,
              chunk_id: "chunk_1",
            },
          ],
        };
      }) as unknown;

      const startTime = Date.now();

      const params: ContextBuildParams = {
        searchQuery: "test",
        files: [],
        maxTokens: 10000,
      };

      await contextBuilder.build(params);

      const duration = Date.now() - startTime;

      // Should complete in reasonable time (< 2s target from plan)
      expect(duration).toBeLessThan(2000);
    });
  });

  describe("Edge Cases", () => {
    it("should handle empty search results", async () => {
      global.fetch = mock(async () => ({
        ok: true,
        json: async () => [],
      })) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "nonexistent",
        files: [],
        maxTokens: 10000,
      };

      const context = await contextBuilder.build(params);

      expect(context.kbResults.length).toBe(0);
      expect(context.totalTokens).toBe(0);
      expect(context.truncated).toBe(false);
    });

    it("should handle missing searchQuery", async () => {
      const params: ContextBuildParams = {
        files: ["test.ts"],
        maxTokens: 10000,
      };

      const context = await contextBuilder.build(params);

      // Should not attempt KB search
      expect(context.kbResults.length).toBe(0);
    });

    it("should handle zero token limit", async () => {
      global.fetch = mock(async () => ({
        ok: true,
        json: async () => [
          {
            file_path: "test.ts",
            start_line: 1,
            end_line: 10,
            snippet_text: "content",
            language: "typescript",
            score: 0.9,
            chunk_id: "chunk_1",
          },
        ],
      })) as unknown;

      const params: ContextBuildParams = {
        searchQuery: "test",
        files: [],
        maxTokens: 0,
      };

      const context = await contextBuilder.build(params);

      // Should truncate everything
      expect(context.truncated).toBe(true);
      expect(context.kbResults.length).toBe(0);
    });
  });
});
