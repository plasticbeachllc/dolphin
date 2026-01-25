/**
 * Unit tests for rest/client.ts API functions
 *
 * Tests restSearch, restGetChunk, restGetFileSlice, restListRepos, restHealthV1
 * Uses fetch mocking to test API clients without external dependencies
 */

import { describe, it, expect, beforeEach, afterEach, mock, spyOn } from "bun:test";
import {
  KBClient,
  type SearchRequestBody,
  type SearchResponse,
  type ChunkResponse,
  type FileSliceResponse,
  type RepoInfo,
  type HealthResponse,
  type RestError,
} from "../../rest/client.js";

describe("rest/client", () => {
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
      const mockFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        console.log("DEBUG: Mock fetch called");
        console.log("DEBUG: Mock Returning:", JSON.stringify(mockResponse));
        capturedRequest = new Request(input, init);
        return new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });
      const body: SearchRequestBody = { query: "test query", repos: ["repo1"] };
      const result = await client.search(body);

      expect(result.hits).toHaveLength(1);
      expect(result.hits[0].repo).toBe("test-repo");
      expect(capturedRequest).toBeDefined();
      expect(capturedRequest!.method).toBe("POST");
    });

    it("includes request body correctly", async () => {
      let capturedBody: string | undefined;
      const mockFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.body) {
          capturedBody = init.body as string;
        }
        return new Response(JSON.stringify({ hits: [], meta: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });
      const body: SearchRequestBody = {
        query: "findme",
        repos: ["r1", "r2"],
        top_k: 50,
        embed_model: "small",
      };
      await client.search(body);

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

      const mockFetch = async () => {
        return new Response(JSON.stringify(errorResponse), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });

      try {
        await client.search({ query: "x" });
        expect(true).toBe(false); // Should not reach here
      } catch (err) {
        const restError = err as RestError;
        expect(restError.error.code).toBe("invalid_query");
      }
    });

    it("handles non-JSON error response", async () => {
      const mockFetch = async () => {
        return new Response("Internal Server Error", {
          status: 500,
          headers: { "Content-Type": "text/plain" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });

      try {
        await client.search({ query: "test" });
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
      const mockFetch = async (input: RequestInfo | URL) => {
        capturedUrl = input.toString();
        return new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });
      const result = await client.getChunk("chunk-abc");

      expect(result.chunk_id).toBe("chunk-abc");
      expect(result.content).toBe("const x = 1;");
      expect(capturedUrl).toContain("/v1/chunks/chunk-abc");
    });

    it("URL-encodes chunk ID", async () => {
      let capturedUrl: string | undefined;
      const mockFetch = async (input: RequestInfo | URL) => {
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

      const client = new KBClient({ fetch: mockFetch });
      await client.getChunk("chunk/with/slashes");

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
        lang: "typescript",
      };

      let capturedUrl: string | undefined;
      const mockFetch = async (input: RequestInfo | URL) => {
        capturedUrl = input.toString();
        return new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });
      const result = await client.getFileSlice("myrepo", "path/to/file.ts", 10, 20);

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

      const mockFetch = async () => {
        return new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });
      const result = await client.listRepos();

      expect(result.repos).toHaveLength(2);
      expect(result.repos[0].name).toBe("repo1");
      expect(result.repos[1].default_embed_model).toBe("large");
    });

    it("sends GET to /v1/repos", async () => {
      let capturedRequest: Request | undefined;
      const mockFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        capturedRequest = new Request(input, init);
        return new Response(JSON.stringify({ repos: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });
      await client.listRepos();

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

      const mockFetch = async () => {
        return new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });
      const result = await client.healthV1();

      expect(result.status).toBe("ok");
      expect(result.version).toBe("1.0.0");
    });

    it("supports shallow check parameter", async () => {
      let capturedUrl: string | undefined;
      const mockFetch = async (input: RequestInfo | URL) => {
        capturedUrl = input.toString();
        return new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });
      await client.healthV1("shallow");

      expect(capturedUrl).toContain("check=shallow");
    });

    it("supports deep check parameter", async () => {
      let capturedUrl: string | undefined;
      const mockFetch = async (input: RequestInfo | URL) => {
        capturedUrl = input.toString();
        return new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });
      await client.healthV1("deep");

      expect(capturedUrl).toContain("check=deep");
    });

    it("omits check param when not specified", async () => {
      let capturedUrl: string | undefined;
      const mockFetch = async (input: RequestInfo | URL) => {
        capturedUrl = input.toString();
        return new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });
      await client.healthV1();

      expect(capturedUrl).toContain("/v1/health");
      expect(capturedUrl).not.toContain("check=");
    });
  });

  describe("error handling", () => {
    it("throws structured error for HTTP errors without JSON body", async () => {
      const mockFetch = async () => {
        return new Response("Gateway Timeout", {
          status: 504,
          statusText: "Gateway Timeout",
          headers: { "Content-Type": "text/plain" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });

      try {
        await client.listRepos();
        expect(true).toBe(false);
      } catch (err) {
        const restError = err as RestError;
        expect(restError.error.code).toBe("invalid_json");
      }
    });

    it("throws structured error for HTTP errors with plain text body", async () => {
      const mockFetch = async () => {
        return new Response("Not Found", {
          status: 404,
          statusText: "Not Found",
          headers: { "Content-Type": "text/html" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });

      try {
        await client.getChunk("nonexistent");
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
      const mockFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        capturedHeaders = new Headers(init?.headers);
        return new Response(JSON.stringify({ repos: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      const client = new KBClient({ fetch: mockFetch });
      await client.listRepos();

      expect(capturedHeaders!.get("Content-Type")).toBe("application/json");
      expect(capturedHeaders!.get("Accept")).toBe("application/json");
      expect(capturedHeaders!.get("X-Client")).toBe("mcp");
    });
  });
});
