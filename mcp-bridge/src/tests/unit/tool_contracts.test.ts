import { describe, it, expect } from "bun:test";
import { tools } from "../../mcp/tools/registry.js";

describe("tool contracts", () => {
  it("all registered tools expose required metadata", () => {
    tools.forEach((tool) => {
      expect(tool.definition.name).toBeDefined();
      expect(tool.definition.description).toBeDefined();
      expect(tool.definition.description?.length).toBeGreaterThan(0);
      expect(tool.definition.inputSchema).toBeDefined();
      expect(tool.definition.annotations?.title).toBeDefined();
      expect(tool.definition.annotations?.readOnlyHint).toBe(true);
      expect(tool.definition.annotations?.idempotentHint).toBe(true);
      expect(tool.definition.annotations?.openWorldHint).toBe(false);
    });
  });
});
