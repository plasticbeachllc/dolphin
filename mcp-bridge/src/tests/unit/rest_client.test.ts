/**
 * Unit tests for rest/client.ts API functions
 *
 * Tests restSearch, restGetChunk, restGetFileSlice, restListRepos, restHealthV1
 * Uses fetch mocking to test API clients without external dependencies
 */

import { describe, it, expect, beforeEach, afterEach, mock, spyOn } from "bun:test";
import {
  restSearch,
  restGetChunk,
  restGetFileSlice,
  restListRepos,
  restHealthV1,
  type SearchRequestBody,
  type SearchResponse,
  type ChunkResponse,
  type FileSliceResponse,
  type RepoInfo,
  type HealthResponse,
  type RestError,
} from "../../rest/client.js";

// Store original fetch
const originalFetch = globalThis.fetch;

describe("rest/client", () => {
  // Reset fetch after each test
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe("restSearch", () => {
    it("sends correct request to /v1/search", async () => {
      const mockResponse: SearchResponse = {
        hits: [
          {
            repo: "test-repo",
            path: "src/test.ts",
            start_line: 1,
            end_line: 10,
            score: 0.95,
            snippet: "test code",
            chunk_id: "chunk-123",
            resource_link: "file:///test.ts",
          },
        ],
        meta: { top_k: 20, model: "large" },
      };

      let capturedRequest: Request | undefined;
      globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        capturedRequest = new Request(input, init);
        return new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const body: SearchRequestBody = { query: "test query", repos: ["repo1"] };
      const result = await restSearch(body);

      expect(result.hits).toHaveLength(1);
      expect(result.hits[0].repo).toBe("test-repo");
      expect(capturedRequest).toBeDefined();
      expect(capturedRequest!.method).toBe("POST");
    });

    it("includes request body correctly", async () => {
      let capturedBody: string | undefined;
      globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.body) {
          capturedBody = init.body as string;
        }
        return new Response(JSON.stringify({ hits: [], meta: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const body: SearchRequestBody = {
        query: "findme",
        repos: ["r1", "r2"],
        top_k: 50,
        embed_model: "small",
      };
      await restSearch(body);

      expect(capturedBody).toBeDefined();
      const parsed = JSON.parse(capturedBody!);
      expect(parsed.query).toBe("findme");
      expect(parsed.repos).toEqual(["r1", "r2"]);
      expect(parsed.top_k).toBe(50);
    });

    it("handles error response", async () => {
      const errorResponse: RestError = {
        error: {
          code: "invalid_query",
          message: "Query is too short",
        },
      };

      globalThis.fetch = async () => {
        return new Response(JSON.stringify(errorResponse), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        });
      };

      try {
        await restSearch({ query: "x" });
        expect(true).toBe(false); // Should not reach here
      } catch (err) {
        const restError = err as RestError;
        expect(restError.error.code).toBe("invalid_query");
      }
    });

    it("handles non-JSON error response", async () => {
      globalThis.fetch = async () => {
        return new Response("Internal Server Error", {
          status: 500,
          headers: { "Content-Type": "text/plain" },
        });
      };

      try {
        await restSearch({ query: "test" });
        expect(true).toBe(false);
      } catch (err) {
        const restError = err as RestError;
        expect(restError.error.code).toBe("invalid_json");
      }
    });
  });

  describe("restGetChunk", () => {
    it("sends GET request to correct endpoint", async () => {
      const mockResponse: ChunkResponse = {
        chunk_id: "chunk-abc",
        repo: "test-repo",
        path: "src/file.ts",
        start_line: 1,
        end_line: 20,
        content: "const x = 1;",
        resource_link: "file:///file.ts",
      };

      let capturedUrl: string | undefined;
      globalThis.fetch = async (input: RequestInfo | URL) => {
        capturedUrl = input.toString();
        return new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const result = await restGetChunk("chunk-abc");

      expect(result.chunk_id).toBe("chunk-abc");
      expect(result.content).toBe("const x = 1;");
      expect(capturedUrl).toContain("/v1/chunks/chunk-abc");
    });

    it("URL-encodes chunk ID", async () => {
      let capturedUrl: string | undefined;
      globalThis.fetch = async (input: RequestInfo | URL) => {
        capturedUrl = input.toString();
        return new Response(
          JSON.stringify({
            chunk_id: "test",
            repo: "r",
            path: "p",
            start_line: 1,
            end_line: 1,
            content: "",
            resource_link: "",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      await restGetChunk("chunk/with/slashes");

      expect(capturedUrl).toContain(encodeURIComponent("chunk/with/slashes"));
    });
  });

  describe("restGetFileSlice", () => {
    it("sends GET request with correct query params", async () => {
      const mockResponse: FileSliceResponse = {
        repo: "test-repo",
        path: "src/file.ts",
        start_line: 10,
        end_line: 20,
        content: "function fn() {}",
        source: "file",
      };

      let capturedUrl: string | undefined;
      globalThis.fetch = async (input: RequestInfo | URL) => {
        capturedUrl = input.toString();
        return new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const result = await restGetFileSlice("myrepo", "path/to/file.ts", 10, 20);

      expect(result.content).toBe("function fn() {}");
      expect(capturedUrl).toContain("/v1/file");
      expect(capturedUrl).toContain("repo=myrepo");
      expect(capturedUrl).toContain("start=10");
      expect(capturedUrl).toContain("end=20");
    });
  });

  describe("restListRepos", () => {
    it("returns list of repos", async () => {
      const mockResponse = {
        repos: [
          { name: "repo1", path: "/path/to/repo1" },
          { name: "repo2", path: "/path/to/repo2", default_embed_model: "large" },
        ] as RepoInfo[],
      };

      globalThis.fetch = async () => {
        return new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const result = await restListRepos();

      expect(result.repos).toHaveLength(2);
      expect(result.repos[0].name).toBe("repo1");
      expect(result.repos[1].default_embed_model).toBe("large");
    });

    it("sends GET to /v1/repos", async () => {
      let capturedRequest: Request | undefined;
      globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        capturedRequest = new Request(input, init);
        return new Response(JSON.stringify({ repos: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      await restListRepos();

      expect(capturedRequest!.method).toBe("GET");
      expect(capturedRequest!.url).toContain("/v1/repos");
    });
  });

  describe("restHealthV1", () => {
    it("returns health status", async () => {
      const mockResponse: HealthResponse = {
        status: "ok",
        version: "1.0.0",
      };

      globalThis.fetch = async () => {
        return new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const result = await restHealthV1();

      expect(result.status).toBe("ok");
      expect(result.version).toBe("1.0.0");
    });

    it("supports shallow check parameter", async () => {
      let capturedUrl: string | undefined;
      globalThis.fetch = async (input: RequestInfo | URL) => {
        capturedUrl = input.toString();
        return new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      await restHealthV1("shallow");

      expect(capturedUrl).toContain("check=shallow");
    });

    it("supports deep check parameter", async () => {
      let capturedUrl: string | undefined;
      globalThis.fetch = async (input: RequestInfo | URL) => {
        capturedUrl = input.toString();
        return new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      await restHealthV1("deep");

      expect(capturedUrl).toContain("check=deep");
    });

    it("omits check param when not specified", async () => {
      let capturedUrl: string | undefined;
      globalThis.fetch = async (input: RequestInfo | URL) => {
        capturedUrl = input.toString();
        return new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      await restHealthV1();

      expect(capturedUrl).toContain("/v1/health");
      expect(capturedUrl).not.toContain("check=");
    });
  });

  describe("error handling", () => {
    it("throws structured error for HTTP errors without JSON body", async () => {
      globalThis.fetch = async () => {
        return new Response("Gateway Timeout", {
          status: 504,
          statusText: "Gateway Timeout",
          headers: { "Content-Type": "text/plain" },
        });
      };

      try {
        await restListRepos();
        expect(true).toBe(false);
      } catch (err) {
        const restError = err as RestError;
        expect(restError.error.code).toBe("invalid_json");
      }
    });

    it("throws structured error for HTTP errors with plain text body", async () => {
      globalThis.fetch = async () => {
        return new Response("Not Found", {
          status: 404,
          statusText: "Not Found",
          headers: { "Content-Type": "text/html" },
        });
      };

      try {
        await restGetChunk("nonexistent");
        expect(true).toBe(false);
      } catch (err) {
        const restError = err as RestError;
        expect(restError.error).toBeDefined();
      }
    });
  });

  describe("request headers", () => {
    it("sets required headers", async () => {
      let capturedHeaders: Headers | undefined;
      globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        capturedHeaders = new Headers(init?.headers);
        return new Response(JSON.stringify({ repos: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      await restListRepos();

      expect(capturedHeaders!.get("Content-Type")).toBe("application/json");
      expect(capturedHeaders!.get("Accept")).toBe("application/json");
      expect(capturedHeaders!.get("X-Client")).toBe("mcp");
    });
  });
});
