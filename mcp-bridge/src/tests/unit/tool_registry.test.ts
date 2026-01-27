import { describe, it, expect } from "bun:test";
import { z } from "zod";
import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { validateTools, type ToolRegistration } from "../../mcp/tools/registry.js";

function makeTool(overrides?: Partial<Tool>): Tool {
  return {
    name: "example",
    description: "example tool",
    inputSchema: { type: "object", properties: {} },
    annotations: {
      title: "Example",
      readOnlyHint: true,
      idempotentHint: true,
      openWorldHint: false,
    },
    ...overrides,
  };
}

function makeRegistration(overrides?: Partial<ToolRegistration>): ToolRegistration {
  return {
    definition: makeTool(),
    inputSchema: z.object({}),
    handler: async () => undefined,
    version: "1.0",
    ...overrides,
  };
}

describe("tool registry validation", () => {
  it("rejects duplicate tool names", () => {
    const first = makeRegistration();
    const second = makeRegistration({ definition: makeTool({ name: "example" }) });

    expect(() => validateTools([first, second])).toThrow(/duplicate tool name/i);
  });

  it("rejects missing annotations.title", () => {
    const broken = makeRegistration({
      definition: makeTool({ annotations: { readOnlyHint: true } }),
    });

    expect(() => validateTools([broken])).toThrow(/missing annotations\.title/i);
  });

  it("rejects missing description", () => {
    const broken = makeRegistration({
      definition: makeTool({ description: "" }),
    });

    expect(() => validateTools([broken])).toThrow(/missing description/i);
  });

  it("exports valid default tools including open_ref", async () => {
    // Dynamic import to avoid side-effects during other tests if any
    const { tools } = await import("../../mcp/tools/registry.js");
    
    expect(tools.length).toBeGreaterThan(0);
    const openRef = tools.find(t => t.definition.name === "open_ref");
    expect(openRef).toBeDefined();
    expect(openRef?.definition.inputSchema).toBeDefined();
    
    // Ensure all exported tools are valid (validateTools calls this internally, but good to double check)
    expect(() => validateTools(tools)).not.toThrow();
  });
});
