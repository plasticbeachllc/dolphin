import type { Tool, CallToolResult, TextContent } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { restHealthV1 } from "../../rest/client.js";
import { logInfo, logError } from "../../util/logger.js";

const INPUT_SHAPE = {
  check: z.enum(["shallow", "deep"]).optional(),
};
const INPUT = z.object(INPUT_SHAPE);

const KB_HEALTH_JSON_SCHEMA: Tool["inputSchema"] = {
  type: "object",
  properties: {
    check: { type: "string", enum: ["shallow", "deep"] },
  },
};

export function makeKbHealth(): {
  definition: Tool;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
  inputSchema: typeof INPUT_SHAPE;
} {
  const definition: Tool = {
    name: "kb_health",
    description: "Check Knowledge Base REST API health (/v1/health).",
    inputSchema: KB_HEALTH_JSON_SCHEMA,
    annotations: { title: "KB Health", readOnlyHint: true, idempotentHint: true },
  };

  const handler = async (args: unknown, signal?: AbortSignal): Promise<CallToolResult> => {
    const started = Date.now();
    try {
      const argsObj = args as { input?: unknown } | undefined;
      const input = INPUT.parse(argsObj?.input ?? args);

      const health = await restHealthV1(input.check, signal);
      const content: CallToolResult["content"] = [
        { type: "text", text: "KB health ready." } as TextContent,
        { type: "text", text: "```json\n" + JSON.stringify(health) + "\n```" } as TextContent,
      ];

      await logInfo("kb_health", "kb_health success", { latency_ms: Date.now() - started });
      return { content, isError: false, data: health };
    } catch (e: unknown) {
      const error = e instanceof Error ? e : new Error(String(e));
      const err = (e as { error?: { code: string; message: string } })?.error
        ? (e as { error: { code: string; message: string } })
        : { error: { code: "unexpected_error", message: error.message } };
      await logError("kb_health", "kb_health error", {
        error_code: err.error.code,
        message: err.error.message,
      });
      const content: CallToolResult["content"] = [
        {
          type: "text",
          text: `${err.error.message} Remediation: ensure REST service is running on 127.0.0.1:7777 and the KB API key is configured.`,
        },
      ];
      return { content, isError: true, _meta: { upstream: err } };
    }
  };

  return { definition, handler, inputSchema: INPUT_SHAPE };
}

