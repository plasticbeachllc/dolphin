import type { Tool, CallToolResult, TextContent } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { restSearch, type SearchResponse } from "../../rest/client.js";
import { CONFIG } from "../../util/config.js";
import { mimeFromLangOrPath } from "../../util/mime.js";
import { jsonSizeBytes } from "../../util/payloadCap.js";
import { logInfo, logWarn, logError } from "../../util/logger.js";

// Interface for the actual API response
interface ApiSearchHit {
  chunk_id: string;
  repo: string;
  path: string;
  start_line: number;
  end_line: number;
  language?: string;
  symbol_kind?: string | null;
  symbol_name?: string | null;
  symbol_path?: string | null;
  score: number;
  commit?: string;
  branch?: string;
}

interface _ApiSearchResponse {
  hits: ApiSearchHit[];
  meta: {
    top_k?: number;
    model?: string;
    latency_ms?: number;
    timing?: { embedding_ms?: number; search_ms?: number; processing_ms?: number };
    cursor?: string;
    estimated_total?: number;
    complete?: boolean;
    warnings?: string[];
  };
}

const INPUT_SHAPE = {
  query: z.string().min(1),
  repos: z.array(z.string()).optional(),
  path_prefix: z.array(z.string()).optional(),
  exclude_paths: z.array(z.string()).optional(),
  exclude_patterns: z.array(z.string()).optional(),
  top_k: z.number().int().min(1).max(CONFIG.MCP_LIMITS.TOP_K_MAX).optional(),
  max_snippets: z.number().int().min(1).optional(),
  deadline_ms: z.number().int().min(50).optional(),
  embed_model: z.enum(["small", "large"]).optional().default("large"),
  score_cutoff: z.number().optional(),
  mmr_enabled: z.boolean().optional(),
  mmr_lambda: z.number().min(0).max(1).optional(),
  cursor: z.string().optional(),
  ann_strategy: z.enum(["speed", "accuracy", "adaptive", "custom"]).optional(),
  ann_nprobes: z.number().int().min(1).max(50).optional(),
  ann_refine_factor: z.number().int().min(1).max(100).optional(),
  include_graph_context: z.boolean().optional(),
  context_lines_before: z.number().int().min(0).max(10).optional(),
  context_lines_after: z.number().int().min(0).max(10).optional(),
  output_mode: z.enum(["prompt_ready", "resources", "both"]).optional(),
  include_prompt_ready: z.boolean().optional(),
  include_resource_text: z.boolean().optional(),
};

const INPUT = z.object(INPUT_SHAPE);

const SEARCH_KNOWLEDGE_JSON_SCHEMA: Tool["inputSchema"] = {
  type: "object",
  properties: {
    query: { type: "string", minLength: 1 },
    repos: { type: "array", items: { type: "string" } },
    path_prefix: { type: "array", items: { type: "string" } },
    exclude_paths: { type: "array", items: { type: "string" } },
    exclude_patterns: { type: "array", items: { type: "string" } },
    top_k: { type: "integer", minimum: 1, maximum: CONFIG.MCP_LIMITS.TOP_K_MAX },
    max_snippets: { type: "integer", minimum: 1 },
    deadline_ms: { type: "integer", minimum: 50 },
    embed_model: { type: "string", enum: ["small", "large"] },
    score_cutoff: { type: "number" },
    mmr_enabled: { type: "boolean" },
    mmr_lambda: { type: "number", minimum: 0, maximum: 1 },
    cursor: { type: "string" },
    ann_strategy: {
      type: "string",
      enum: ["speed", "accuracy", "adaptive", "custom"],
    },
    ann_nprobes: { type: "integer", minimum: 1, maximum: 50 },
    ann_refine_factor: { type: "integer", minimum: 1, maximum: 100 },
    include_graph_context: { type: "boolean" },
    context_lines_before: { type: "integer", minimum: 0, maximum: 10 },
    context_lines_after: { type: "integer", minimum: 0, maximum: 10 },
    output_mode: { type: "string", enum: ["prompt_ready", "resources", "both"] },
    include_prompt_ready: { type: "boolean" },
    include_resource_text: { type: "boolean" },
  },
  required: ["query"],
};

type _Input = z.infer<typeof INPUT>;

const CAP_BYTES = CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES;
const _PER_SNIPPET_CHAR_CAP = CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP;
const SHRUNK_SNIPPET_CHAR_CAP = CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP;
const MIN_SNIPPET_CHAR_FLOOR = CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR;

import { fenceLang } from "../../util/language.js";

interface GraphRelationship {
  type: string;
  direction: string;
  target?: { qualified_name: string };
  source?: { qualified_name: string };
  line_number?: number;
}

interface GraphContext {
  nodes?: Array<{
    type: string;
    qualified_name: string;
    signature?: string;
    line_range: [number, number];
  }>;
  relationships?: GraphRelationship[];
}

function formatGraphContext(graphContext: unknown): string {
  const ctx = graphContext as GraphContext;
  if (!ctx || !ctx.nodes || ctx.nodes.length === 0) {
    return "";
  }

  const lines: string[] = ["", "### Code Graph Context", ""];

  // Format nodes
  if (ctx.nodes && ctx.nodes.length > 0) {
    lines.push("**Entities:**");
    for (const node of ctx.nodes) {
      const sig = node.signature ? ` - ${node.signature}` : "";
      lines.push(
        `- **${node.type}** \`${node.qualified_name}\`${sig} (lines ${node.line_range[0]}-${node.line_range[1]})`
      );
    }
    lines.push("");
  }

  // Format relationships grouped by type
  const relationships = ctx.relationships || [];
  if (relationships.length > 0) {
    const callsTo = relationships.filter((r) => r.type === "calls" && r.direction === "outgoing");
    const calledBy = relationships.filter((r) => r.type === "calls" && r.direction === "incoming");
    const inherits = relationships.filter(
      (r) => r.type === "inherits" && r.direction === "outgoing"
    );
    const implementations = relationships.filter((r) => r.type === "implements");
    const imports = relationships.filter((r) => r.type === "imports" && r.direction === "outgoing");

    if (callsTo.length > 0) {
      lines.push("**Calls:**");
      for (const rel of callsTo.slice(0, 5)) {
        const lineInfo = rel.line_number ? ` (line ${rel.line_number})` : "";
        lines.push(`- → \`${rel.target?.qualified_name}\`${lineInfo}`);
      }
      lines.push("");
    }

    if (calledBy.length > 0) {
      lines.push("**Called by:**");
      for (const rel of calledBy.slice(0, 5)) {
        const lineInfo = rel.line_number ? ` (line ${rel.line_number})` : "";
        lines.push(`- ← \`${rel.source?.qualified_name}\`${lineInfo}`);
      }
      lines.push("");
    }

    if (inherits.length > 0) {
      lines.push("**Inherits from:**");
      for (const rel of inherits) {
        lines.push(`- \`${rel.target?.qualified_name}\``);
      }
      lines.push("");
    }

    if (implementations.length > 0) {
      lines.push("**Implementations:**");
      for (const rel of implementations) {
        if (rel.direction === "outgoing") {
          lines.push(`- Implements \`${rel.target?.qualified_name}\``);
        } else {
          lines.push(`- Implemented by \`${rel.source?.qualified_name}\``);
        }
      }
      lines.push("");
    }

    if (imports.length > 0) {
      lines.push("**Dependencies:**");
      for (const rel of imports.slice(0, 5)) {
        lines.push(`- \`${rel.target?.qualified_name}\``);
      }
      lines.push("");
    }
  }

  return lines.join("\n");
}

interface ExtendedSearchHit {
  chunk_id: string;
  repo: string;
  path: string;
  start_line: number;
  end_line: number;
  lang?: string;
  snippet?: string;
  score: number;
  resource_link: string;
  graph_context?: unknown;
  _context_start_line?: number;
  _context_end_line?: number;
  _chunk_start_line?: number;
  _chunk_end_line?: number;
}

function buildPromptReady(res: SearchResponse): string {
  const parts: string[] = [];
  for (const h of res.hits) {
    const hit = h as unknown as ExtendedSearchHit;

    // Show expanded line range if context was included
    const hasContext = hit._context_start_line && hit._context_start_line !== hit.start_line;
    const lineRange = hasContext
      ? `L${hit._context_start_line}-L${hit._context_end_line}`
      : `L${h.start_line}-L${h.end_line}`;
    parts.push(`[${h.repo}] ${h.path}#${lineRange}`);

    // Add graph context if available
    if (hit.graph_context) {
      const graphText = formatGraphContext(hit.graph_context);
      if (graphText) {
        parts.push(graphText);
      }
    }

    const lang = fenceLang(h.lang, h.path);
    let code = h.snippet ?? "";

    // Format code with context markers if context lines are present
    if (hasContext && code) {
      const lines = code.split("\n");
      const chunkStart = hit._chunk_start_line;
      const chunkEnd = hit._chunk_end_line;
      const contextStart = hit._context_start_line;

      const formattedLines: string[] = [];
      lines.forEach((line, idx) => {
        const lineNum = (contextStart ?? hit.start_line) + idx;

        // Mark context vs chunk boundaries
        if (lineNum === chunkStart && (contextStart ?? hit.start_line) < chunkStart) {
          formattedLines.push("# --- Result starts (line " + chunkStart + ") ---");
        }

        formattedLines.push(line);

        if (lineNum === chunkEnd && chunkEnd < (hit._context_end_line ?? hit.end_line)) {
          formattedLines.push("# --- Result ends (line " + chunkEnd + ") ---");
        }
      });
      code = formattedLines.join("\n");
    }

    if (lang) {
      parts.push("```" + lang);
      parts.push(code);
      parts.push("```");
    } else {
      parts.push("```");
      parts.push(code);
      parts.push("```");
    }
  }
  return parts.join("\n") + (parts.length ? "\n" : "");
}

export function makeSearchKnowledge(): {
  definition: Tool;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: any;
  inputSchema: typeof INPUT_SHAPE;
} {
  const definition: Tool = {
    name: "search_knowledge",
    description:
      "Semantically query code and docs across indexed repositories and return ranked snippets with citations.",
    inputSchema: SEARCH_KNOWLEDGE_JSON_SCHEMA,
    annotations: {
      title: "Search Knowledge Base",
      readOnlyHint: true,
      openWorldHint: false,
    },
  };

  const handler = async (args: unknown, signal?: AbortSignal): Promise<CallToolResult> => {
    const started = Date.now();
    try {
      const argsObj = args as { input?: unknown } | undefined;
      const input = INPUT.parse(argsObj?.input ?? args);

      // Trim repo names only
      const repos = input.repos?.map((r) => r.trim());

      let includePromptReady = input.include_prompt_ready ?? CONFIG.SEARCH_DEFAULTS.INCLUDE_PROMPT_READY;
      let includeResourceText =
        input.include_resource_text ?? CONFIG.SEARCH_DEFAULTS.INCLUDE_RESOURCE_TEXT;

      if (input.output_mode) {
        includePromptReady = input.output_mode === "prompt_ready" || input.output_mode === "both";
        includeResourceText = input.output_mode === "resources" || input.output_mode === "both";
      }

      const includeSnippets = includePromptReady || includeResourceText;

      const body = {
        query: input.query,
        repos,
        path_prefix: input.path_prefix,
        exclude_paths: input.exclude_paths,
        exclude_patterns: input.exclude_patterns,
        top_k: input.top_k,
        max_snippets: input.max_snippets,
        deadline_ms: input.deadline_ms,
        embed_model: input.embed_model,
        score_cutoff: input.score_cutoff,
        mmr_enabled: input.mmr_enabled,
        mmr_lambda: input.mmr_lambda,
        cursor: input.cursor,
        include_prompt_ready: false,
        ann_strategy: input.ann_strategy,
        ann_nprobes: input.ann_nprobes,
        ann_refine_factor: input.ann_refine_factor,
        include_graph_context:
          input.include_graph_context ?? CONFIG.SEARCH_DEFAULTS.INCLUDE_GRAPH_CONTEXT,
        include_snippets: includeSnippets,
        context_lines_before:
          input.context_lines_before ?? CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_BEFORE,
        context_lines_after:
          input.context_lines_after ?? CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_AFTER,
      };

      const res: SearchResponse = await restSearch(body, signal);

      // Transform API response to match expected format
      interface ApiHit {
        repo: string;
        path: string;
        start_line: number;
        end_line: number;
        language?: string;
        lang?: string;
        chunk_id: string;
        score: number;
        graph_context?: unknown;
        snippet?: string;
        snippet_start_line?: number;
        snippet_end_line?: number;
      }
      const hits = res.hits as unknown as ApiHit[];
      const transformedHits = hits.map((hit) => {
        const snippetStart = hit.snippet_start_line ?? hit.start_line;
        const snippetEnd = hit.snippet_end_line ?? hit.end_line;
        return {
          ...hit,
          lang: hit.language || hit.lang,
          snippet: hit.snippet ?? "",
          resource_link: `kb://${hit.repo}/${hit.path}#L${hit.start_line}-L${hit.end_line}`,
          graph_context: hit.graph_context, // Preserve graph context if present
          // Context metadata for visual formatting
          _context_start_line: snippetStart,
          _context_end_line: snippetEnd,
          _chunk_start_line: hit.start_line,
          _chunk_end_line: hit.end_line,
        };
      });

      // Replace hits with transformed version
      const transformedRes = {
        ...res,
        hits: transformedHits,
      };

      // Build summary
      const k = transformedRes.hits.length;
      const reposSet = new Set(transformedRes.hits.map((h) => h.repo));
      const rcount = reposSet.size;
      const est = transformedRes.meta.estimated_total;
      const more = transformedRes.meta.complete === false && transformedRes.meta.cursor;
      const summaryParts = [
        `Found ${k} result${k === 1 ? "" : "s"}${rcount > 0 ? ` across ${rcount} repo${rcount === 1 ? "" : "s"}` : ""}.`,
      ];
      if (typeof est === "number") summaryParts.push(`~${est} estimated results.`);
      if (more) summaryParts.push("More available — call search_knowledge again with cursor.");
      const summary = summaryParts.join(" ");

      // Build prompt-ready text
      let promptReady = includePromptReady ? buildPromptReady(transformedRes) : "";

      // Build content blocks: one text summary + prompt-ready + resource blocks for each hit
      const content: CallToolResult["content"] = [];
      content.push({ type: "text", text: summary } as TextContent);
      if (promptReady.length > 0) {
        content.push({ type: "text", text: promptReady } as TextContent);
      }

      for (const hit of transformedRes.hits) {
        const resourceBlock = {
          type: "resource" as const,
          resource: {
            uri: hit.resource_link,
            mimeType: mimeFromLangOrPath(hit.lang, hit.path),
            // Always include snippet text initially - payload trimming logic will reduce if needed
            text: includeResourceText ? (hit.snippet ?? "").slice(0, _PER_SNIPPET_CHAR_CAP) : "",
          },
        };
        content.push(resourceBlock);
      }

      // _meta compact hits list
      const metaHits = transformedRes.hits.map((h) => ({
        chunk_id: h.chunk_id,
        repo: h.repo,
        path: h.path,
        start_line: h.start_line,
        end_line: h.end_line,
        score: h.score,
      }));

      const result: CallToolResult = {
        content,
        isError: false,
        _meta: {
          hits: metaHits,
          cursor: transformedRes.meta.cursor,
          estimated_total: transformedRes.meta.estimated_total,
          complete: transformedRes.meta.complete,
          warnings: transformedRes.meta.warnings,
          model: transformedRes.meta.model,
          top_k: transformedRes.meta.top_k,
          mcp_latency_ms: Date.now() - started,
        },
      };

      // Enforce ~70KB total cap by trimming in specified order
      let size = jsonSizeBytes(result);

      // Step 1: Trim prompt_ready text to fit budget
      if (size > CAP_BYTES) {
        const prIndex = content.length > 1 && content[1]?.type === "text" ? 1 : -1;
        if (prIndex === 1) {
          let prText: string = (content[1] as TextContent).text;
          // Iteratively trim promptReady by 10% until under cap or floor
          while (prText.length > 0 && size > CAP_BYTES) {
            const cut = Math.max(Math.floor(prText.length * 0.9), 0);
            prText = prText.slice(0, cut);
            (content[1] as TextContent).text = prText;
            size = jsonSizeBytes(result);
          }
        }
      }

      // Step 2: Shrink per-snippet windows (reduce text length) toward a floor
      if (size > CAP_BYTES) {
        // First pass: cap each resource text to SHRUNK_SNIPPET_CHAR_CAP
        for (let i = 0; i < content.length && size > CAP_BYTES; i++) {
          const block = content[i];
          if (
            block.type === "resource" &&
            "resource" in block &&
            block.resource &&
            "text" in block.resource
          ) {
            const txt = block.resource.text as string;
            if (txt.length > SHRUNK_SNIPPET_CHAR_CAP) {
              block.resource.text = txt.slice(0, SHRUNK_SNIPPET_CHAR_CAP);
              size = jsonSizeBytes(result);
            }
          }
        }
        // Second pass: cap further to MIN_SNIPPET_CHAR_FLOOR if still too big
        for (let i = 0; i < content.length && size > CAP_BYTES; i++) {
          const block = content[i];
          if (
            block.type === "resource" &&
            "resource" in block &&
            block.resource &&
            "text" in block.resource
          ) {
            const txt = block.resource.text as string;
            if (txt.length > MIN_SNIPPET_CHAR_FLOOR) {
              block.resource.text = txt.slice(0, MIN_SNIPPET_CHAR_FLOOR);
              size = jsonSizeBytes(result);
            }
          }
        }
      }

      const resourceOffset = promptReady.length > 0 ? 2 : 1;

      // Step 3: Minimize snippet text from lowest-scoring hits first (keep citations present)
      if (size > CAP_BYTES) {
        for (let i = transformedRes.hits.length - 1; i >= 0 && size > CAP_BYTES; i--) {
          const blockIdx = i + resourceOffset;
          const block = result.content[blockIdx];
          if (
            block?.type === "resource" &&
            "resource" in block &&
            block.resource &&
            "text" in block.resource
          ) {
            // Replace with empty string to satisfy SDK schema while trimming payload
            block.resource.text = "";
            size = jsonSizeBytes(result);
          }
        }
      }

      // Step 4: Drop lowest-scoring citations entirely
      if (size > CAP_BYTES) {
        while (result.content.length > 1 && size > CAP_BYTES) {
          // Keep summary at index 0; attempt to keep promptReady at index 1 if present
          const _dropIndex = result.content.length - 1;
          // pop content and its meta hit
          result.content.pop();
          metaHits.pop();
          size = jsonSizeBytes(result);
        }
        // Mark as partial page when trimming occurred
        result._meta = { ...result._meta, complete: false };
        await logWarn("search", "trimmed content to respect 70KB cap", { trimmed: true });
      }

      await logInfo("search", "search_knowledge success", {
        hits_count: transformedRes.hits.length,
        warnings: transformedRes.meta.warnings,
        latency_ms: transformedRes.meta.latency_ms,
        mcp_latency_ms: Date.now() - started,
        include_prompt_ready: includePromptReady,
        include_resource_text: includeResourceText,
      });

      return result;
    } catch (e: unknown) {
      const error = e instanceof Error ? e : new Error(String(e));
      const err = (e as { error?: { code: string; message: string; remediation?: string } })?.error
        ? (e as { error: { code: string; message: string; remediation?: string } })
        : { error: { code: "unexpected_error", message: error.message } };
      await logError("search", "search_knowledge error", {
        error_code: err.error.code,
        message: err.error.message,
      });
      const remediation =
        err.error?.remediation ??
        (err.error?.code === "invalid_json"
          ? 'Upstream returned non-JSON (e.g., "Internal Server Error"). Inspect server logs, verify endpoints and filters, or increase deadline_ms/top_k.'
          : "Check repo names with /v1/repos, adjust filters, or increase deadline_ms/top_k.");
      const message = `${err.error.message}${remediation ? " Remediation: " + remediation : ""}`;
      const content: CallToolResult["content"] = [{ type: "text", text: message }];
      return { content, isError: true, _meta: { upstream: err } };
    }
  };

  return { definition, handler, inputSchema: INPUT_SHAPE };
}
