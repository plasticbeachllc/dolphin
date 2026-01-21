import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import type { ZodRawShape } from "zod";
import { makeSearchKnowledge } from "./search_knowledge.js";
import { makeFetchChunk } from "./fetch_chunk.js";
import { makeFetchLines } from "./fetch_lines.js";
import { makeGetVectorStoreInfo } from "./get_vector_store_info.js";
import { makeGetMetadata } from "./get_metadata.js";
import { makeListRepos } from "./list_repos.js";
import { makeKbHealth } from "./kb_health.js";

export interface ToolRegistration {
  definition: Tool;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
  inputSchema?: ZodRawShape;
}

export const tools: ToolRegistration[] = [
  makeSearchKnowledge(),
  makeFetchChunk(),
  makeFetchLines(),
  makeListRepos(),
  makeKbHealth(),
  makeGetVectorStoreInfo(),
  makeGetMetadata(),
];
