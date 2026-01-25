import { describe, it, expect, beforeAll, afterAll } from "bun:test";
import { startMockRest } from "./mockServer.js";
import { makeGetMetadata } from "../../mcp/tools/get_metadata.js";
import { initLogger } from "../../util/logger.js";

let stop: () => Promise<void>;

function parseJsonBlock(text: string): Record<string, unknown> {
  const match = text.match(/```json\n([\s\S]*?)\n```/);
  if (!match) {
    throw new Error("JSON block not found");
  }
  return JSON.parse(match[1]);
}

beforeAll(async () => {
  await initLogger();
  stop = await startMockRest(7777);
});
afterAll(async () => {
  await stop?.();
});

describe("metadata.get", () => {
  it("returns metadata subset without content", async () => {
    const { handler } = makeGetMetadata();
    const res = await handler({ input: { chunk_id: "1" } });

    expect(res.isError).toBe(false);
    const jsonText = String(res.content[1]?.type === "text" ? res.content[1].text : "");
    const metadata = parseJsonBlock(jsonText);
    expect(metadata.chunk_id).toBe("1");
    expect(metadata.content).toBeUndefined();
    // Should include other metadata fields
    expect(metadata.repo).toBeDefined();
    expect(metadata.path).toBeDefined();
    expect(metadata.start_line).toBeDefined();
    expect(metadata.end_line).toBeDefined();
    expect(metadata.lang).toBeDefined();
  });

  it("chunk_not_found → isError=true with remediation", async () => {
    const { handler } = makeGetMetadata();
    const res = await handler({ input: { chunk_id: "not-found" } });

    expect(res.isError).toBe(true);
    expect(res.content[0].text).toMatch(/remediation/i);
    expect(res.content[0].text).toMatch(/chunk/i);
  });

  it("tool definition includes valid JSON Schema", async () => {
    const { definition } = makeGetMetadata();

    expect(definition.inputSchema).toBeDefined();
    expect(definition.inputSchema.type).toBe("object");
    expect(definition.inputSchema.required).toContain("chunk_id");
    expect(definition.inputSchema.properties).toBeDefined();
    expect(definition.inputSchema.properties.chunk_id).toBeDefined();
  });
});
