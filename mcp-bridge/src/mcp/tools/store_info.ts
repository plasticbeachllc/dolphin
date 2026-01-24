import type { Tool, CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { restListRepos } from "../../rest/client.js";
import { logInfo, logError } from "../../util/logger.js";
import { CONFIG } from "../../util/config.js";
import { buildToolInputSchema } from "./schema.js";
import { TOOL_VERSION } from "./version.js";
import { normalizeToolError, formatToolErrorText } from "./error.js";

const INPUT = z.object({});
const INPUT_SCHEMA = buildToolInputSchema(INPUT);

export function makeStoreInfo(): {
  definition: Tool;
  inputSchema: typeof INPUT;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
} {
  const definition: Tool = {
    name: "store_info",
    description: "Report vector store dims, namespaces, and counts.",
    inputSchema: INPUT_SCHEMA,
    annotations: {
      title: "Get Vector Store Info",
      readOnlyHint: true,
      idempotentHint: true,
      openWorldHint: false,
    },
  };

  const handler = async (_args: unknown, signal?: AbortSignal): Promise<CallToolResult> => {
    const started = Date.now();
    try {
      const repos = await restListRepos(signal);
      const totalChunks = repos.repos.reduce((sum, r) => sum + (r.chunks ?? 0), 0);

      const data = {
        namespaces: ["chunks_small", "chunks_large"],
        dims: { chunks_small: 1536, chunks_large: 3072 },
        limits: {
          top_k_max: CONFIG.MCP_LIMITS.TOP_K_MAX,
          snippet_char_cap: CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP,
          payload_cap_bytes: CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES,
        },
        counts: { approx_chunks_total: totalChunks },
        latency: { search_p50_ms: null as number | null, search_p95_ms: null as number | null },
      };

      const infoJson = "```json\n" + JSON.stringify(data) + "\n```";
      await logInfo("store_info", "store_info success", {
        latency_ms: Date.now() - started,
      });
      return {
        content: [
          { type: "text", text: "Vector store info ready." },
          { type: "text", text: infoJson },
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
        "Ensure REST service is running on 127.0.0.1:7777."
      );
      await logError("store_info", "store_info error", {
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
