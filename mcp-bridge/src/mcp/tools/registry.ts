import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import type { ZodTypeAny } from "zod";
import { makeSearchKnowledge } from "./search_knowledge.js";
import { makeChunkGet } from "./chunk_get.js";
import { makeFileLines } from "./file_lines.js";
import { makeStoreInfo } from "./store_info.js";
import { makeGetMetadata } from "./get_metadata.js";
import { makeListRepos } from "./list_repos.js";
import { makeOpenRef } from "./open_ref.js";
import { makeKbHealth } from "./kb_health.js";
import { TOOL_VERSION } from "./version.js";

export interface ToolRegistration {
  definition: Tool;
  inputSchema: ZodTypeAny;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
  version: string;
}

export function validateTools(tools: ToolRegistration[]): ToolRegistration[] {
  const seen = new Set<string>();

  for (const tool of tools) {
    const name = tool.definition.name?.trim();
    if (!name) {
      throw new Error("Tool registry error: tool missing name");
    }
    if (seen.has(name)) {
      throw new Error(`Tool registry error: duplicate tool name "${name}"`);
    }
    seen.add(name);

    if (!tool.definition.description) {
      throw new Error(`Tool registry error: "${name}" missing description`);
    }
    if (!tool.definition.inputSchema) {
      throw new Error(`Tool registry error: "${name}" missing input schema`);
    }
    if (!tool.inputSchema) {
      throw new Error(`Tool registry error: "${name}" missing zod input schema`);
    }
    if (!tool.definition.annotations?.title) {
      throw new Error(`Tool registry error: "${name}" missing annotations.title`);
    }
    if (!tool.version) {
      throw new Error(`Tool registry error: "${name}" missing version`);
    }
    if (typeof tool.handler !== "function") {
      throw new Error(`Tool registry error: "${name}" missing handler`);
    }
  }

  return tools;
}

export const tools: ToolRegistration[] = validateTools([
  { ...makeSearchKnowledge(), version: TOOL_VERSION },
  { ...makeChunkGet(), version: TOOL_VERSION },
  { ...makeFileLines(), version: TOOL_VERSION },
  { ...makeOpenRef(), version: TOOL_VERSION },
  { ...makeListRepos(), version: TOOL_VERSION },
  { ...makeKbHealth(), version: TOOL_VERSION },
  { ...makeStoreInfo(), version: TOOL_VERSION },
  { ...makeGetMetadata(), version: TOOL_VERSION },
]);
