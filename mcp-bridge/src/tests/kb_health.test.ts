import { describe, it, expect, beforeAll, afterAll } from "bun:test";
import { startMockRest } from "./mockServer.js";
import { makeKbHealth } from "../mcp/tools/kb_health.js";
import { initLogger } from "../util/logger.js";

let stop: () => Promise<void>;

beforeAll(async () => {
  await initLogger();
  stop = await startMockRest(7777);
});
afterAll(async () => {
  await stop?.();
});

describe("kb_health", () => {
  it("returns health JSON", async () => {
    const { handler } = makeKbHealth();
    const res = await handler({ input: { check: "shallow" } });

    expect(res.isError).toBe(false);
    expect(Array.isArray(res.content)).toBe(true);
    expect(res.content[0].type).toBe("text");
    expect(String(res.content[1].text)).toContain("```json");
    expect(res.data.status).toBe("healthy");
  });
});

