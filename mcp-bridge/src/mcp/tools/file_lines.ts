import type { Tool, CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { restGetFileSlice, KBClient } from "../../rest/client.js";
import { mimeFromLangOrPath } from "../../util/mime.js";
import { logInfo, logError } from "../../util/logger.js";
import { buildToolInputSchema } from "./schema.js";
import { TOOL_VERSION } from "./version.js";
import { normalizeToolError, formatToolErrorText } from "./error.js";

/**
 * file_lines tool analysis:
 * - Single request tool: fetches one file slice by repo/path/line range
 * - No parallelization needed: only makes one restGetFileSlice() call
 * - Performance is optimal: one request = one response
 * - No changes required for parallel snippet fetching implementation
 */

const INPUT_SHAPE = {
  repo: z.string(),
  path: z.string(),
  start: z.number().int().min(1),
  end: z.number().int().min(1),
};

const INPUT = z.object(INPUT_SHAPE);
const INPUT_SCHEMA = buildToolInputSchema(INPUT);

export function makeFileLines(client?: KBClient): {
  definition: Tool;
  inputSchema: typeof INPUT;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
} {
  const definition: Tool = {
    name: "file_lines",
    description:
      "Fetch a file slice [start, end] inclusive from disk and return fenced code with citation.",
    inputSchema: INPUT_SCHEMA,
    annotations: {
      title: "Get File Lines",
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
      const res = await (client
        ? client.getFileSlice(input.repo.trim(), input.path, input.start, input.end, signal)
        : restGetFileSlice(input.repo.trim(), input.path, input.start, input.end, signal));
      const mime = mimeFromLangOrPath(res.lang, res.path);

      const content: CallToolResult["content"] = [
        { type: "text", text: `${res.repo}/${res.path}#L${res.start_line}-L${res.end_line}` },
        {
          type: "resource",
          resource: {
            uri: `kb://${res.repo}/${res.path}#L${res.start_line}-L${res.end_line}`,
            mimeType: mime,
            text: res.content,
          },
        },
      ];

      await logInfo("file_lines", "file_lines success", { latency_ms: Date.now() - started });
      return {
        content,
        isError: false,
        _meta: {
          tool_version: TOOL_VERSION,
          latency_ms: Date.now() - started,
          warnings: res._meta?.warnings ?? [],
        },
      };
    } catch (e: unknown) {
      const { error: toolError, upstream } = normalizeToolError(
        e,
        "Verify repo/path and line range."
      );
      await logError("file_lines", "file_lines error", {
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
