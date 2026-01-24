import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import type { ZodTypeAny } from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";

export function buildToolInputSchema(schema: ZodTypeAny): Tool["inputSchema"] {
  return zodToJsonSchema(schema) as Tool["inputSchema"];
}
