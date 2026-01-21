import type { Tool, CallToolResult, TextContent } from "@modelcontextprotocol/sdk/types.js";
import { restListRepos } from "../../rest/client.js";
import { logInfo, logError } from "../../util/logger.js";

export function makeListRepos(): {
  definition: Tool;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
} {
  const definition: Tool = {
    name: "list_repos",
    description:
      "List indexed repositories with their absolute root paths and approximate file/chunk counts.",
    inputSchema: { type: "object", properties: {} },
    annotations: { title: "List Repositories", readOnlyHint: true, idempotentHint: true },
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

      await logInfo("list_repos", "list_repos success", { latency_ms: Date.now() - started });
      return { content, isError: false, data: { repos } };
    } catch (e: unknown) {
      const error = e instanceof Error ? e : new Error(String(e));
      const err = (e as { error?: { code: string; message: string } })?.error
        ? (e as { error: { code: string; message: string } })
        : { error: { code: "unexpected_error", message: error.message } };
      await logError("list_repos", "list_repos error", {
        error_code: err.error.code,
        message: err.error.message,
      });
      const content: CallToolResult["content"] = [
        {
          type: "text",
          text: `${err.error.message} Remediation: ensure REST service is running and the KB API key is configured.`,
        },
      ];
      return { content, isError: true, _meta: { upstream: err } };
    }
  };

  return { definition, handler };
}
