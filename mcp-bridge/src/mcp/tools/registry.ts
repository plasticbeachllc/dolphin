import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { makeSearchKnowledge } from "./search_knowledge.js";
import { makeFetchChunk } from "./fetch_chunk.js";
import { makeFetchLines } from "./fetch_lines.js";
import { makeGetVectorStoreInfo } from "./get_vector_store_info.js";
import { makeGetMetadata } from "./get_metadata.js";
import { makeListRepos } from "./list_repos.js";
import { makeKbHealth } from "./kb_health.js";
import { TOOL_VERSION } from "./version.js";

export interface ToolRegistration {
  definition: Tool;
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
  { ...makeFetchChunk(), version: TOOL_VERSION },
  { ...makeFetchLines(), version: TOOL_VERSION },
  { ...makeListRepos(), version: TOOL_VERSION },
  { ...makeKbHealth(), version: TOOL_VERSION },
  { ...makeGetVectorStoreInfo(), version: TOOL_VERSION },
  { ...makeGetMetadata(), version: TOOL_VERSION },
]);
