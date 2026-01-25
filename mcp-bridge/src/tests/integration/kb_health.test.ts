import { describe, it, expect, beforeAll, afterAll } from "bun:test";
import { startMockRest } from "./mockServer.js";
import { makeKbHealth } from "../../mcp/tools/kb_health.js";
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

describe("health", () => {
  it("returns health JSON", async () => {
    const { handler } = makeKbHealth();
    const res = await handler({ input: { check: "shallow" } });

    expect(res.isError).toBe(false);
    expect(Array.isArray(res.content)).toBe(true);
    expect(res.content[0].type).toBe("text");
    const jsonText = String(res.content[1].text);
    expect(jsonText).toContain("```json");
    const data = parseJsonBlock(jsonText) as { status?: string };
    expect(data.status).toBe("healthy");
  });
});
