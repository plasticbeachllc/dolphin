import type { Tool, CallToolResult, TextContent } from "@modelcontextprotocol/sdk/types.js";
import { CONFIG } from "../../util/config.js";
import { mimeFromLangOrPath } from "../../util/mime.js";
import { logInfo, logError } from "../../util/logger.js";
import type { RepoInfo } from "../../rest/client.js";
import { parseSearchInput, resolveSearchOptions, SEARCH_INPUT_SCHEMA } from "../search/input.js";
import { buildSearchRequestBody, executeSearch } from "../search/rest.js";
import { fetchSnippetsForHits } from "../search/snippets.js";
import { getReposByName, transformHits } from "../search/transform.js";
import {
  buildPromptReady,
  buildWarnings,
  buildSummary,
  buildHitsJsonObject,
  buildHitsJsonText,
} from "../search/format.js";
import { applyPayloadTrimming } from "../search/trim.js";
import type { ApiHit } from "../search/contracts.js";
import { TOOL_VERSION } from "./version.js";
import { normalizeToolError, formatToolErrorText } from "./error.js";

export function makeSearchKnowledge(): {
  definition: Tool;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
} {
  const definition: Tool = {
    name: "search",
    description:
      "Semantically query code and docs across indexed repositories and return many ranked candidates with follow-up-ready identifiers and citations.",
    inputSchema: SEARCH_INPUT_SCHEMA,
    annotations: {
      title: "Search Knowledge Base",
      readOnlyHint: true,
      idempotentHint: true,
      openWorldHint: false,
    },
  };

  const handler = async (args: unknown, signal?: AbortSignal): Promise<CallToolResult> => {
    const started = Date.now();
    try {
      const input = parseSearchInput(args);
      const options = resolveSearchOptions(input);

      const body = buildSearchRequestBody(input, options);
      const res = await executeSearch(body, signal);

      let reposByName: Map<string, RepoInfo> | undefined;
      if ((options.includeAbsPaths || options.includeVscodeUris) && options.includeHitsJson) {
        reposByName = await getReposByName(signal);
      }

      const hits = res.hits as unknown as ApiHit[];

      const { snippetsByHitIndex, snippetFailures } = await fetchSnippetsForHits({
        hits,
        includeSnippets: options.includeSnippets,
        snippetsTopN: options.snippetsTopN,
        topContextN: options.topContextN,
        contextLinesBefore: options.contextLinesBefore,
        contextLinesAfter: options.contextLinesAfter,
        signal,
      });

      const { hits: transformedHits, escapedPathCount } = transformHits({
        hits,
        snippetsByHitIndex,
        includeAbsPaths: options.includeAbsPaths,
        includeVscodeUris: options.includeVscodeUris,
        reposByName,
      });

      const transformedRes = {
        ...res,
        hits: transformedHits,
      };

      const { warnings, warningEntries } = buildWarnings({
        metaWarnings: transformedRes.meta.warnings,
        snippetFailures,
        escapedPathCount,
      });

      const summary = buildSummary({
        hits: transformedRes.hits,
        snippetsIncluded: snippetsByHitIndex.size,
        estimatedTotal: transformedRes.meta.estimated_total,
        moreAvailable: transformedRes.meta.complete === false && Boolean(transformedRes.meta.cursor),
        includeWarningsInText: options.includeWarningsInText,
        warningEntries,
      });

      const promptReady = options.includePromptReady
        ? buildPromptReady(transformedRes, options.snippetsTopN)
        : "";

      const hitsJsonObj = buildHitsJsonObject({
        query: input.query,
        hits: transformedRes.hits,
        meta: transformedRes.meta,
        topK: options.topK,
        warningEntries,
      });

      const hitsJsonText = buildHitsJsonText(hitsJsonObj);

      const content: CallToolResult["content"] = [];
      content.push({ type: "text", text: summary } as TextContent);
      if (options.includeHitsJson) {
        content.push({ type: "text", text: hitsJsonText } as TextContent);
      }
      if (promptReady.length > 0) {
        content.push({ type: "text", text: promptReady } as TextContent);
      }

      if (options.includeResourceText) {
        for (const hit of transformedRes.hits) {
          if (!hit.snippet) continue;
          const resourceBlock = {
            type: "resource" as const,
            resource: {
              uri: hit.resource_link,
              mimeType: mimeFromLangOrPath(hit.lang, hit.path),
              text: (hit.snippet ?? "").slice(0, CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP),
            },
          };
          content.push(resourceBlock);
        }
      }

      const result: CallToolResult = {
        content,
        isError: false,
        _meta: {
          cursor: transformedRes.meta.cursor,
          estimated_total: transformedRes.meta.estimated_total,
          complete: transformedRes.meta.complete,
          warnings,
          model: transformedRes.meta.model,
          top_k: transformedRes.meta.top_k ?? options.topK,
          tool_version: TOOL_VERSION,
          latency_ms: Date.now() - started,
        },
      };

      await applyPayloadTrimming({
        result,
        hitsJson: hitsJsonObj,
        includeHitsJson: options.includeHitsJson,
        promptReady,
        warningEntries,
        includeWarningsInText: options.includeWarningsInText,
        capBytes: CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES,
        shrunkSnippetCharCap: CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP,
        minSnippetCharFloor: CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR,
        totalHits: transformedRes.hits.length,
      });

      await logInfo("search", "search success", {
        hits_count: transformedRes.hits.length,
        warnings,
        latency_ms: transformedRes.meta.latency_ms,
        mcp_latency_ms: Date.now() - started,
        include_prompt_ready: options.includePromptReady,
        include_resource_text: options.includeResourceText,
      });

      return result;
    } catch (e: unknown) {
      const { error: toolError, upstream } = normalizeToolError(
        e,
        "Check repo names with /v1/repos, adjust filters, or increase deadline_ms/top_k."
      );
      await logError("search", "search error", {
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
