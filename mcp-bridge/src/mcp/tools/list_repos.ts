import type { Tool, CallToolResult, TextContent } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { restListRepos } from "../../rest/client.js";
import { logInfo, logError } from "../../util/logger.js";
import { buildToolInputSchema } from "./schema.js";
import { TOOL_VERSION } from "./version.js";
import { normalizeToolError, formatToolErrorText } from "./error.js";

const INPUT = z.object({});
const INPUT_SCHEMA = buildToolInputSchema(INPUT);

export function makeListRepos(): {
  definition: Tool;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
} {
  const definition: Tool = {
    name: "repos.list",
    description:
      "List indexed repositories with their absolute root paths and approximate file/chunk counts.",
    inputSchema: INPUT_SCHEMA,
    annotations: {
      title: "List Repositories",
      readOnlyHint: true,
      idempotentHint: true,
      openWorldHint: false,
    },
  };

  const handler = async (_args: unknown, signal?: AbortSignal): Promise<CallToolResult> => {
    const started = Date.now();
    try {
      const res = await restListRepos(signal);
      const repos = res.repos ?? [];

      const content: CallToolResult["content"] = [
        { type: "text", text: `Found ${repos.length} repos.` } as TextContent,
        { type: "text", text: "```json\n" + JSON.stringify({ repos }) + "\n```" } as TextContent,
      ];

      await logInfo("repos.list", "repos.list success", { latency_ms: Date.now() - started });
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
        "Ensure REST service is running and the KB API key is configured."
      );
      await logError("repos.list", "repos.list error", {
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
