import { describe, it, expect, beforeAll, afterAll } from "bun:test";
import { startMockRest } from "./mockServer.js";
import { makeListRepos } from "../mcp/tools/list_repos.js";
import { initLogger } from "../util/logger.js";

let stop: () => Promise<void>;

beforeAll(async () => {
  await initLogger();
  stop = await startMockRest(7777);
});
afterAll(async () => {
  await stop?.();
});

describe("list_repos", () => {
  it("returns repos list with paths and a JSON text block", async () => {
    const { handler } = makeListRepos();
    const res = await handler({ input: {} });

    expect(res.isError).toBe(false);
    expect(Array.isArray(res.content)).toBe(true);
    expect(res.content[0].type).toBe("text");
    expect(String(res.content[1].text)).toContain("```json");
    expect(res.data.repos.length).toBe(2);
    expect(res.data.repos[0].path).toContain("/abs/");
  });
});

