import { describe, it, expect, beforeAll, afterAll } from "bun:test";
import { startMockRest } from "./mockServer.js";
import { makeListRepos } from "../../mcp/tools/list_repos.js";
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

describe("repos.list", () => {
  it("returns repos list with paths and a JSON text block", async () => {
    const { handler } = makeListRepos();
    const res = await handler({ input: {} });

    expect(res.isError).toBe(false);
    expect(Array.isArray(res.content)).toBe(true);
    expect(res.content[0].type).toBe("text");
    const jsonText = String(res.content[1].text);
    expect(jsonText).toContain("```json");
    const data = parseJsonBlock(jsonText) as { repos: Array<{ path?: string }> };
    expect(data.repos.length).toBe(2);
    expect(data.repos[0].path).toContain("/abs/");
  });
});
