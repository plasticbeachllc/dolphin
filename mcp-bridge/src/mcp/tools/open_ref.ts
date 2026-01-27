import type { Tool, CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { restGetChunk, restGetFileSlice, KBClient } from "../../rest/client.js";
import { mimeFromLangOrPath } from "../../util/mime.js";
import { logInfo, logError } from "../../util/logger.js";
import { buildToolInputSchema } from "./schema.js";
import { TOOL_VERSION } from "./version.js";
import { normalizeToolError, formatToolErrorText } from "./error.js";

/**
 * open_ref tool analysis:
 * - Unified entry point for resolving references (URIs or IDs)
 * - Parses `kb://` URIs to call file_lines logic
 * - Treats non-URI strings as chunk_ids to call chunk_get logic
 */

const INPUT_SHAPE = {
  ref: z.string().describe("The URI (kb://...) or chunk_id to open"),
};

const INPUT = z.object(INPUT_SHAPE);
const INPUT_SCHEMA = buildToolInputSchema(INPUT);

// Regex for parsing kb:// URIs
// Example: kb://repo/path/to/file.py#L10-L20
const KB_URI_REGEX = /^kb:\/\/([^/]+)\/(.+)#L(\d+)-L(\d+)$/;

export function makeOpenRef(client?: KBClient): {
  definition: Tool;
  inputSchema: typeof INPUT;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
} {
  const definition: Tool = {
    name: "open_ref",
    description:
      "Open a reference (kb:// URI or chunk_id) and return the content. Use this to follow up on search results.",
    inputSchema: INPUT_SCHEMA,
    annotations: {
      title: "Open Reference",
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
      const ref = input.ref.trim();

      let content: CallToolResult["content"];
      let warnings: string[] = [];

      const uriMatch = ref.match(KB_URI_REGEX);

      if (uriMatch) {
        // Handle as File Slice (kb:// URI)
        const [, repo, path, startStr, endStr] = uriMatch;
        const start = parseInt(startStr, 10);
        const end = parseInt(endStr, 10);

        const res = await (client
          ? client.getFileSlice(repo, path, start, end, signal)
          : restGetFileSlice(repo, path, start, end, signal));

        const mime = mimeFromLangOrPath(res.lang, res.path);
        warnings = res._meta?.warnings ?? [];

        content = [
          { type: "text", text: `${res.repo}/${res.path}#L${res.start_line}-L${res.end_line}` },
          {
            type: "resource",
            resource: {
              uri: ref, // Echo back the canonical URI
              mimeType: mime,
              text: res.content,
            },
          },
        ];
      } else {
        // Handle as Chunk ID
        const chunk = await (client ? client.getChunk(ref, signal) : restGetChunk(ref, signal));

        const mime = mimeFromLangOrPath(chunk.lang, chunk.path);

        content = [
          {
            type: "text",
            text: `Chunk ${chunk.chunk_id} — ${chunk.repo}/${chunk.path}#L${chunk.start_line}-L${chunk.end_line}`,
          },
          {
            type: "resource",
            resource: {
              uri: chunk.resource_link,
              mimeType: mime,
              text: chunk.content,
            },
          },
        ];
      }

      await logInfo("open_ref", "open_ref success", { latency_ms: Date.now() - started, ref });
      return {
        content,
        isError: false,
        _meta: {
          tool_version: TOOL_VERSION,
          latency_ms: Date.now() - started,
          warnings,
        },
      };
    } catch (e: unknown) {
      const { error: toolError, upstream } = normalizeToolError(
        e,
        "Verify the reference format (kb://... or chunk_id)."
      );
      await logError("open_ref", "open_ref error", {
        error_code: toolError.code,
        message: toolError.message,
        ref: (args as { ref?: string })?.ref,
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
