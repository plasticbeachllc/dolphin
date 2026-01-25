import type { Tool, CallToolResult, TextContent } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { restHealthV1, KBClient } from "../../rest/client.js";
import { logInfo, logError } from "../../util/logger.js";
import { buildToolInputSchema } from "./schema.js";
import { TOOL_VERSION } from "./version.js";
import { normalizeToolError, formatToolErrorText } from "./error.js";

const INPUT_SHAPE = {
  check: z.enum(["shallow", "deep"]).optional(),
};
const INPUT = z.object(INPUT_SHAPE);
const INPUT_SCHEMA = buildToolInputSchema(INPUT);

export function makeKbHealth(client?: KBClient): {
  definition: Tool;
  inputSchema: typeof INPUT;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
} {
  const definition: Tool = {
    name: "health",
    description: "Check Knowledge Base REST API health (/v1/health).",
    inputSchema: INPUT_SCHEMA,
    annotations: {
      title: "KB Health",
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

      const health = await (client ? client.healthV1(input.check, signal) : restHealthV1(input.check, signal));
      const content: CallToolResult["content"] = [
        { type: "text", text: "KB health ready." } as TextContent,
        { type: "text", text: "```json\n" + JSON.stringify(health) + "\n```" } as TextContent,
      ];

      await logInfo("health", "health success", { latency_ms: Date.now() - started });
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
        "Ensure REST service is running on 127.0.0.1:7777 and the KB API key is configured."
      );
      await logError("health", "health error", {
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
