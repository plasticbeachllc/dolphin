import { describe, it, expect } from "bun:test";
import { runBridgeSmokeSuite, type BridgeSmokeDeps } from "./bridge_smoke_suite.js";

function createDeps(overrides: Partial<BridgeSmokeDeps> = {}): BridgeSmokeDeps {
  const baseHit = {
    chunk_id: "chunk-1",
    repo: "repoa",
    path: "src/app.ts",
    start_line: 10,
    end_line: 20,
  };
  const hitsJson = "```json\n" + JSON.stringify({ hits: [baseHit] }) + "\n```";

  const defaultDeps: BridgeSmokeDeps = {
    listRepos: async () => ({
      repos: [{ name: "repoa", path: "/tmp/repo", chunks: 5, files: 2 }],
    }),
    makeSearchKnowledge: () => ({
      definition: {
        name: "search",
        description: "",
        inputSchema: { type: "object", properties: {} },
      },
      handler: async () => ({
        isError: false,
        content: [
          { type: "text", text: "summary" },
          { type: "text", text: hitsJson },
        ],
      }),
    }),
    makeFetchChunk: () => ({
      definition: {
        name: "chunk.get",
        description: "",
        inputSchema: { type: "object", properties: {} },
      },
      handler: async () => ({
        isError: false,
        content: [
          { type: "text", text: "Chunk chunk-1" },
          {
            type: "resource",
            resource: { uri: "kb://chunk-1", mimeType: "text/plain", text: "code" },
          },
        ],
      }),
    }),
    makeFetchLines: () => ({
      definition: {
        name: "file.lines",
        description: "",
        inputSchema: { type: "object", properties: {} },
      },
      handler: async () => ({
        isError: false,
        content: [{ type: "text", text: "Lines" }],
      }),
    }),
    makeGetVectorStoreInfo: () => ({
      definition: {
        name: "store.info",
        description: "",
        inputSchema: { type: "object", properties: {} },
      },
      handler: async () => ({
        isError: false,
        content: [{ type: "text", text: "info" }],
      }),
    }),
  };

  return { ...defaultDeps, ...overrides };
}

describe("runBridgeSmokeSuite", () => {
  it("reports success across all smoke steps when dependencies resolve", async () => {
    const report = await runBridgeSmokeSuite(createDeps());

    expect(report.failed).toBe(0);
    expect(report.passed).toBe(5);
    expect(report.entries).toHaveLength(5);
    report.entries.forEach((entry) => expect(entry.status).toBe("passed"));
  });

  it("stops after the failing step and reports the error message", async () => {
    const failingDeps = createDeps({
      listRepos: async () => {
        throw new Error("REST offline");
      },
    });

    const report = await runBridgeSmokeSuite(failingDeps);
    expect(report.failed).toBe(1);
    expect(report.entries).toHaveLength(1);
    expect(report.entries[0].status).toBe("failed");
    expect(report.entries[0].error).toContain("REST offline");
  });

  it("surfaces tool-level errors such as search failures", async () => {
    const deps = createDeps({
      makeSearchKnowledge: () => ({
        definition: {
          name: "search",
          description: "",
          inputSchema: { type: "object", properties: {} },
        },
        handler: async () => ({
          isError: true,
          content: [{ type: "text", text: "Search failed" }],
        }),
      }),
    });

    const report = await runBridgeSmokeSuite(deps);
    expect(report.failed).toBe(1);
    expect(report.entries).toHaveLength(3);
    expect(report.entries.at(-1)?.name).toBe("search");
    expect(report.entries.at(-1)?.status).toBe("failed");
    expect(report.entries.at(-1)?.error).toContain("Search failed");
  });
});
