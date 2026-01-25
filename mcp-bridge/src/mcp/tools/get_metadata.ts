import type { Tool, CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { restGetChunk, KBClient } from "../../rest/client.js";
import { logInfo, logError } from "../../util/logger.js";
import { buildToolInputSchema } from "./schema.js";
import { TOOL_VERSION } from "./version.js";
import { normalizeToolError, formatToolErrorText } from "./error.js";

/**
 * metadata_get tool analysis:
 * - Single request tool: fetches metadata for one chunk by chunk_id
 * - No parallelization needed: only makes one restGetChunk() call
 * - Performance is optimal: one request = one response
 * - No changes required for parallel snippet fetching implementation
 */

const INPUT_SHAPE = { chunk_id: z.string() };
const INPUT = z.object(INPUT_SHAPE);
const INPUT_SCHEMA = buildToolInputSchema(INPUT);

export function makeGetMetadata(client?: KBClient): {
  definition: Tool;
  inputSchema: typeof INPUT;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
} {
  const definition: Tool = {
    name: "metadata_get",
    description: "Fetch chunk metadata without content.",
    inputSchema: INPUT_SCHEMA,
    annotations: {
      title: "Get Chunk Metadata",
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
      const chunk = await (client
        ? client.getChunk(input.chunk_id, signal)
        : restGetChunk(input.chunk_id, signal));
      // Drop content to keep response small
      const { content: _content, ...meta } = chunk;
      const metaJson = "```json\n" + JSON.stringify(meta) + "\n```";
      await logInfo("metadata_get", "metadata_get success", { latency_ms: Date.now() - started });
      return {
        content: [
          { type: "text", text: "Metadata ready." },
          { type: "text", text: metaJson },
        ],
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
      await logError("metadata_get", "metadata_get error", {
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

  return { definition, inputSchema: INPUT, handler };
}
