import type { Tool, CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { restGetChunk } from "../../rest/client.js";
import { mimeFromLangOrPath } from "../../util/mime.js";
import { logInfo, logError } from "../../util/logger.js";
import { buildToolInputSchema } from "./schema.js";
import { TOOL_VERSION } from "./version.js";
import { normalizeToolError, formatToolErrorText } from "./error.js";

/**
 * chunk.get tool analysis:
 * - Single request tool: fetches one chunk by chunk_id
 * - No parallelization needed: only makes one restGetChunk() call
 * - Performance is optimal: one request = one response
 * - No changes required for parallel snippet fetching implementation
 */

const INPUT_SHAPE = { chunk_id: z.string() };
const INPUT = z.object(INPUT_SHAPE);
const INPUT_SCHEMA = buildToolInputSchema(INPUT);

export function makeChunkGet(): {
  definition: Tool;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
} {
  const definition: Tool = {
    name: "chunk.get",
    description: "Fetch a chunk by chunk_id and return fenced code with citation.",
    inputSchema: INPUT_SCHEMA,
    annotations: {
      title: "Get Chunk",
      readOnlyHint: true,
      idempotentHint: true,
      openWorldHint: false,
    },
  };

  const handler = async (args: unknown, signal?: AbortSignal): Promise<CallToolResult> => {
    const started = Date.now();
    try {
      const argsObj = args as { input?: unknown } | undefined;
      const input = INPUT.parse(argsObj?.input ?? args);
      const chunk = await restGetChunk(input.chunk_id, signal);
      const lang = chunk.lang;
      const code = chunk.content;
      const mime = mimeFromLangOrPath(lang, chunk.path);

      const content: CallToolResult["content"] = [
        {
          type: "text",
          text: `Chunk ${chunk.chunk_id} — ${chunk.repo}/${chunk.path}#L${chunk.start_line}-L${chunk.end_line}`,
        },
        { type: "resource", resource: { uri: chunk.resource_link, mimeType: mime, text: code } },
      ];

      await logInfo("chunk.get", "chunk.get success", { latency_ms: Date.now() - started });
      return {
        content,
        isError: false,
        _meta: {
          tool_version: TOOL_VERSION,
          latency_ms: Date.now() - started,
          warnings: [],
        },
      };
    } catch (e: unknown) {
      const { error: toolError, upstream } = normalizeToolError(
        e,
        "Verify chunk_id or re-run search."
      );
      await logError("chunk.get", "chunk.get error", {
        error_code: toolError.code,
        message: toolError.message,
      });
      const content: CallToolResult["content"] = [
        {
          type: "text",
          text: formatToolErrorText(toolError),
        },
      ];
      return {
        content,
        isError: true,
        _meta: {
          error: toolError,
          upstream,
          tool_version: TOOL_VERSION,
          latency_ms: Date.now() - started,
          warnings: [],
        },
      };
    }
  };

  return { definition, handler };
}
