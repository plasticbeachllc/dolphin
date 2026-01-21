import type { Tool, CallToolResult, TextContent } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { restListRepos, restSearch, type SearchResponse, type RepoInfo } from "../../rest/client.js";
import { CONFIG } from "../../util/config.js";
import { mimeFromLangOrPath } from "../../util/mime.js";
import { jsonSizeBytes } from "../../util/payloadCap.js";
import { logInfo, logWarn, logError } from "../../util/logger.js";
import { fetchSnippetsInParallel } from "./snippet_fetcher.js";
import path from "node:path";

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
  top_context_n: z.number().int().min(0).optional(),
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
  include_hits_json: z.boolean().optional(),
  include_warnings_in_text: z.boolean().optional(),
  include_abs_paths: z.boolean().optional(),
  include_vscode_uris: z.boolean().optional(),
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
    top_context_n: { type: "integer", minimum: 0 },
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
    include_hits_json: { type: "boolean" },
    include_warnings_in_text: { type: "boolean" },
    include_abs_paths: { type: "boolean" },
    include_vscode_uris: { type: "boolean" },
  },
  required: ["query"],
};

type _Input = z.infer<typeof INPUT>;

const CAP_BYTES = CONFIG.MCP_LIMITS.PAYLOAD_CAP_BYTES;
const _PER_SNIPPET_CHAR_CAP = CONFIG.MCP_LIMITS.SNIPPET_CHAR_CAP;
const SHRUNK_SNIPPET_CHAR_CAP = CONFIG.RESPONSE_LIMITS.SHRUNK_SNIPPET_CHAR_CAP;
const MIN_SNIPPET_CHAR_FLOOR = CONFIG.RESPONSE_LIMITS.MIN_SNIPPET_CHAR_FLOOR;

import { fenceLang } from "../../util/language.js";

function safeResolveWithin(baseDir: string, relPath: string): string | null {
  const resolvedBase = path.resolve(baseDir);
  const resolved = path.resolve(resolvedBase, relPath);
  const relative = path.relative(resolvedBase, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    return null;
  }
  return resolved;
}

function buildVscodeFileUri(absPath: string, line?: number, column?: number): string {
  const encodedPath = encodeURI(absPath);
  const col = column ?? (line != null ? 1 : undefined);
  const suffix = line != null ? `:${line}${col != null ? `:${col}` : ""}` : "";
  return `vscode://file/${encodedPath}${suffix}`;
}

type RepoCacheEntry = { ts: number; reposByName: Map<string, RepoInfo> };
let repoCache: RepoCacheEntry | null = null;
const REPO_CACHE_TTL_MS = 5 * 60 * 1000;

function isRepoCacheExpired(entry: RepoCacheEntry): boolean {
  return Date.now() - entry.ts > REPO_CACHE_TTL_MS;
}

async function getReposByName(signal?: AbortSignal): Promise<Map<string, RepoInfo>> {
  if (repoCache && !isRepoCacheExpired(repoCache)) {
    return repoCache.reposByName;
  }
  const repoList = await restListRepos(signal);
  const reposByName = new Map(repoList.repos.map((r) => [r.name, r]));
  repoCache = { ts: Date.now(), reposByName };
  return reposByName;
}

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
  chunk_resource_link?: string;
  abs_path?: string;
  vscode_uri?: string;
  repo_root?: string;
  graph_context?: unknown;
  _context_start_line?: number;
  _context_end_line?: number;
  _chunk_start_line?: number;
  _chunk_end_line?: number;
}

type WarningEntry = { code: string; detail?: string };

function buildPromptReady(res: SearchResponse, maxHits: number): string {
  const parts: string[] = [];
  for (const h of res.hits.slice(0, maxHits)) {
    const hit = h as unknown as ExtendedSearchHit;

    // Show expanded line range if context was included
    const hasContext = hit._context_start_line && hit._context_start_line !== hit.start_line;
    const lineRange = hasContext
      ? `L${hit._context_start_line}-L${hit._context_end_line}`
      : `L${h.start_line}-L${h.end_line}`;
    const scoreText =
      typeof h.score === "number" ? ` score=${Number.isFinite(h.score) ? h.score.toFixed(3) : h.score}` : "";
    parts.push(`[${h.repo}] ${h.path}#${lineRange} (chunk_id=${h.chunk_id})${scoreText}`);

    // Add graph context if available
    if (hit.graph_context) {
      const graphText = formatGraphContext(hit.graph_context);
      if (graphText) {
        parts.push(graphText);
      }
    }

    const lang = fenceLang(h.lang, h.path);
    let code = h.snippet ?? "";

    if (!code) {
      parts.push(
        `No snippet included for this result. Follow up with fetch_chunk({chunk_id: "${h.chunk_id}"}) or fetch_lines({repo:"${h.repo}", path:"${h.path}", start:${h.start_line}, end:${h.end_line}}).`
      );
      continue;
    }

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
      "Semantically query code and docs across indexed repositories and return many ranked candidates with follow-up-ready identifiers and citations.",
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

      const topK = input.top_k ?? CONFIG.SEARCH_DEFAULTS.TOP_K;
      const snippetsTopNRequested =
        input.max_snippets ?? CONFIG.SEARCH_DEFAULTS.SNIPPETS_TOP_N;
      const snippetsTopN = Math.max(0, Math.min(topK, snippetsTopNRequested));
      const topContextNRequested = input.top_context_n ?? CONFIG.SEARCH_DEFAULTS.TOP_CONTEXT_N;
      const topContextN = Math.max(0, Math.min(snippetsTopN, topContextNRequested));

      let includePromptReady = input.include_prompt_ready ?? CONFIG.SEARCH_DEFAULTS.INCLUDE_PROMPT_READY;
      let includeResourceText =
        input.include_resource_text ?? CONFIG.SEARCH_DEFAULTS.INCLUDE_RESOURCE_TEXT;
      const includeHitsJson = input.include_hits_json ?? CONFIG.SEARCH_DEFAULTS.INCLUDE_HITS_JSON;
      const includeWarningsInText =
        input.include_warnings_in_text ?? CONFIG.SEARCH_DEFAULTS.INCLUDE_WARNINGS_IN_TEXT;
      const includeAbsPaths = input.include_abs_paths ?? CONFIG.SEARCH_DEFAULTS.INCLUDE_ABS_PATHS;
      const includeVscodeUris = input.include_vscode_uris ?? CONFIG.SEARCH_DEFAULTS.INCLUDE_VSCODE_URIS;

      if (input.output_mode) {
        includePromptReady = input.output_mode === "prompt_ready" || input.output_mode === "both";
        includeResourceText = input.output_mode === "resources" || input.output_mode === "both";
      }

      const includeSnippets = (includePromptReady || includeResourceText) && snippetsTopN > 0;

      const body = {
        query: input.query,
        repos,
        path_prefix: input.path_prefix,
        exclude_paths: input.exclude_paths,
        exclude_patterns: input.exclude_patterns,
        top_k: topK,
        max_snippets: snippetsTopN,
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
        // Prefer lightweight candidate lists; fetch snippets separately for top results.
        include_snippets: false,
        context_lines_before: 0,
        context_lines_after: 0,
      };

      const res: SearchResponse = await restSearch(body, signal);

      let reposByName: Map<string, RepoInfo> | undefined;
      if ((includeAbsPaths || includeVscodeUris) && includeHitsJson) {
        reposByName = await getReposByName(signal);
      }

      const contextLinesBefore = input.context_lines_before ?? CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_BEFORE;
      const contextLinesAfter = input.context_lines_after ?? CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_AFTER;

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

      // Fetch top snippets in parallel to keep search lightweight but follow-up friendly.
      const snippetFailures: Array<{ repo: string; path: string; start: number; end: number }> = [];
      const snippetsByHitIndex: Map<number, { snippet: string; start: number; end: number }> = new Map();
      if (includeSnippets) {
        const requests: Array<{
          repo: string;
          path: string;
          startLine: number;
          endLine: number;
          contextLinesBefore?: number;
          contextLinesAfter?: number;
        }> = [];
        const requestHitIndices: number[] = [];

        for (let i = 0; i < hits.length && requests.length < snippetsTopN; i++) {
          const h = hits[i];
          if (!h?.repo || !h?.path) continue;
          if (typeof h.start_line !== "number" || typeof h.end_line !== "number") continue;
          const includeContext = requests.length < topContextN;
          requests.push({
            repo: h.repo,
            path: h.path,
            startLine: h.start_line,
            endLine: h.end_line,
            contextLinesBefore: includeContext ? contextLinesBefore : 0,
            contextLinesAfter: includeContext ? contextLinesAfter : 0,
          });
          requestHitIndices.push(i);
        }

        if (requests.length > 0) {
          const snippetMap = await fetchSnippetsInParallel(requests, {
            maxConcurrent: CONFIG.MAX_CONCURRENT_SNIPPET_FETCH,
            requestTimeoutMs: CONFIG.SNIPPET_FETCH_TIMEOUT_MS,
            retryAttempts: CONFIG.SNIPPET_FETCH_RETRY_ATTEMPTS,
            signal,
          });

          for (let reqIdx = 0; reqIdx < requests.length; reqIdx++) {
            const hitIdx = requestHitIndices[reqIdx];
            const result = snippetMap[reqIdx];
            const req = requests[reqIdx];
            if (result && result.content) {
              snippetsByHitIndex.set(hitIdx, {
                snippet: result.content,
                start: result.actualStartLine ?? req.startLine,
                end: result.actualEndLine ?? req.endLine,
              });
            } else {
              snippetFailures.push({
                repo: req.repo,
                path: req.path,
                start: req.startLine,
                end: req.endLine,
              });
            }
          }
        }
      }

      let escapedPathCount = 0;
      const transformedHits = hits.map((hit, idx) => {
        const chunkStart = hit.start_line;
        const chunkEnd = hit.end_line;
        const snippetInfo = snippetsByHitIndex.get(idx);
        const snippetStart =
          snippetInfo?.start ?? hit.snippet_start_line ?? (typeof chunkStart === "number" ? chunkStart : 1);
        const snippetEnd =
          snippetInfo?.end ?? hit.snippet_end_line ?? (typeof chunkEnd === "number" ? chunkEnd : snippetStart);

        const lang = hit.language || hit.lang;
        const chunkUri =
          typeof chunkStart === "number" && typeof chunkEnd === "number"
            ? `kb://${hit.repo}/${hit.path}#L${chunkStart}-L${chunkEnd}`
            : `kb://${hit.repo}/${hit.path}`;
        const snippetUri =
          typeof snippetStart === "number" && typeof snippetEnd === "number"
            ? `kb://${hit.repo}/${hit.path}#L${snippetStart}-L${snippetEnd}`
            : chunkUri;

        const repoInfo = reposByName?.get(hit.repo);
        const repoRoot = repoInfo?.path;
        const absPath =
          includeAbsPaths && repoRoot ? safeResolveWithin(repoRoot, hit.path) : undefined;
        if (includeAbsPaths && repoRoot && absPath == null) {
          escapedPathCount++;
        }

        const vscodeUri =
          includeVscodeUris && absPath
            ? buildVscodeFileUri(absPath, snippetStart ?? chunkStart, 1)
            : undefined;

        return {
          ...hit,
          lang,
          snippet: snippetInfo?.snippet ?? hit.snippet ?? "",
          resource_link: snippetUri,
          chunk_resource_link: chunkUri,
          repo_root: repoRoot,
          abs_path: absPath ?? undefined,
          vscode_uri: vscodeUri ?? undefined,
          graph_context: hit.graph_context,
          _context_start_line: snippetStart,
          _context_end_line: snippetEnd,
          _chunk_start_line: typeof chunkStart === "number" ? chunkStart : undefined,
          _chunk_end_line: typeof chunkEnd === "number" ? chunkEnd : undefined,
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
      const warnings: string[] = [];
      const warningEntries: WarningEntry[] = [];
      if (Array.isArray(transformedRes.meta.warnings)) {
        for (const warning of transformedRes.meta.warnings) {
          warnings.push(warning);
          warningEntries.push({ code: warning });
        }
      }
      if (snippetFailures.length > 0) {
        const code = "snippet_fetch_failed";
        warnings.push(code);
        warningEntries.push({ code, detail: `${snippetFailures.length} snippet(s) failed` });
      }
      if (escapedPathCount > 0) {
        const code = "path_escaped_repo_root";
        warnings.push(code);
        warningEntries.push({ code, detail: `${escapedPathCount} path(s) escaped repo root` });
      }

      const summaryParts = [
        `Found ${k} result${k === 1 ? "" : "s"}${rcount > 0 ? ` across ${rcount} repo${rcount === 1 ? "" : "s"}` : ""}.`,
        `Showing snippets for top ${snippetsByHitIndex.size}/${k} results.`,
      ];
      if (typeof est === "number") summaryParts.push(`~${est} estimated results.`);
      if (more) summaryParts.push("More available — call search_knowledge again with cursor.");
      if (includeWarningsInText && warningEntries.length > 0) {
        const warningText = warningEntries
          .map((entry) => (entry.detail ? `${entry.code}(${entry.detail})` : entry.code))
          .join(", ");
        summaryParts.push(`Warnings: ${warningText}`);
      }
      const summary = summaryParts.join(" ");

      // Build prompt-ready text
      let promptReady = includePromptReady ? buildPromptReady(transformedRes, snippetsTopN) : "";

      // Build a follow-up friendly, machine-readable list of candidates.
      const hitsJsonObj = {
        schema_version: "2025-01-18",
        query: input.query,
        hits: transformedRes.hits.map((h, i) => {
          const hit = h as unknown as ExtendedSearchHit;
          const chunkStart = hit._chunk_start_line ?? hit.start_line;
          const chunkEnd = hit._chunk_end_line ?? hit.end_line;
          const snippetStart = hit._context_start_line ?? hit.start_line;
          const snippetEnd = hit._context_end_line ?? hit.end_line;
          const defaultFetchLines = {
            repo: hit.repo,
            path: hit.path,
            start: snippetStart,
            end: snippetEnd,
          };
          return {
            rank: i + 1,
            chunk_id: hit.chunk_id,
            score: hit.score,
            repo: hit.repo,
            path: hit.path,
            lang: hit.lang,
            chunk_range: { start_line: chunkStart, end_line: chunkEnd },
            snippet_range: { start_line: snippetStart, end_line: snippetEnd, included: Boolean(hit.snippet) },
            uris: {
              chunk: hit.chunk_resource_link ?? hit.resource_link,
              snippet: hit.resource_link,
              vscode: hit.vscode_uri ?? null,
              abs_path: hit.abs_path ?? null,
              repo_root: hit.repo_root ?? null,
            },
            followups: {
              fetch_chunk: { chunk_id: hit.chunk_id },
              fetch_lines: defaultFetchLines,
            },
          };
        }),
        meta: {
          cursor: transformedRes.meta.cursor ?? null,
          estimated_total: transformedRes.meta.estimated_total ?? null,
          complete: transformedRes.meta.complete ?? null,
          warnings: warningEntries,
          model: transformedRes.meta.model ?? null,
          top_k: transformedRes.meta.top_k ?? topK,
        },
      };

      const hitsJsonText = "```json\n" + JSON.stringify(hitsJsonObj) + "\n```";

      // Build content blocks: one text summary + prompt-ready + resource blocks for each hit
      const content: CallToolResult["content"] = [];
      content.push({ type: "text", text: summary } as TextContent);
      if (includeHitsJson) {
        content.push({ type: "text", text: hitsJsonText } as TextContent);
      }
      if (promptReady.length > 0) {
        content.push({ type: "text", text: promptReady } as TextContent);
      }

      if (includeResourceText) {
        for (const hit of transformedRes.hits) {
          if (!hit.snippet) continue;
          const resourceBlock = {
            type: "resource" as const,
            resource: {
              uri: hit.resource_link,
              mimeType: mimeFromLangOrPath(hit.lang, hit.path),
              text: (hit.snippet ?? "").slice(0, _PER_SNIPPET_CHAR_CAP),
            },
          };
          content.push(resourceBlock);
        }
      }

      // _meta compact hits list
      const metaHits = transformedRes.hits.map((h) => ({
        chunk_id: h.chunk_id,
        repo: h.repo,
        path: h.path,
        start_line: h.start_line,
        end_line: h.end_line,
        score: h.score,
        snippet_start_line: (h as unknown as ExtendedSearchHit)._context_start_line,
        snippet_end_line: (h as unknown as ExtendedSearchHit)._context_end_line,
      }));

      const result: CallToolResult = {
        content,
        isError: false,
        _meta: {
          hits: metaHits,
          cursor: transformedRes.meta.cursor,
          estimated_total: transformedRes.meta.estimated_total,
          complete: transformedRes.meta.complete,
          warnings,
          model: transformedRes.meta.model,
          top_k: transformedRes.meta.top_k ?? topK,
          mcp_latency_ms: Date.now() - started,
        },
      };

      // Enforce ~70KB total cap by trimming in specified order
      let size = jsonSizeBytes(result);

      const hitsJsonIndex = includeHitsJson ? 1 : -1;
      const promptReadyIndex =
        promptReady.length > 0 ? (includeHitsJson ? 2 : 1) : -1;

      // Step 1: Trim prompt_ready text to fit budget
      if (size > CAP_BYTES) {
        if (promptReadyIndex >= 0 && content[promptReadyIndex]?.type === "text") {
          let prText: string = (content[promptReadyIndex] as TextContent).text;
          // Iteratively trim promptReady by 10% until under cap or floor
          while (prText.length > 0 && size > CAP_BYTES) {
            const cut = Math.max(Math.floor(prText.length * 0.9), 0);
            prText = prText.slice(0, cut);
            (content[promptReadyIndex] as TextContent).text = prText;
            size = jsonSizeBytes(result);
          }
        }
      }

      // Step 1b: Reduce hits_json size by dropping lowest-scoring hits (from the end).
      if (size > CAP_BYTES && hitsJsonIndex >= 0 && content[hitsJsonIndex]?.type === "text") {
        // Keep at least 1 hit if any exist.
        while (hitsJsonObj.hits.length > 1 && size > CAP_BYTES) {
          hitsJsonObj.hits.pop();
          metaHits.pop();
          (content[hitsJsonIndex] as TextContent).text =
            "```json\n" + JSON.stringify(hitsJsonObj) + "\n```";
          size = jsonSizeBytes(result);
        }
        if (size > CAP_BYTES && hitsJsonObj.hits.length === 1) {
          // As a last resort, drop optional URI fields.
          (hitsJsonObj.hits[0] as any).uris = {
            chunk: (hitsJsonObj.hits[0] as any).uris.chunk,
            snippet: (hitsJsonObj.hits[0] as any).uris.snippet,
          };
          (content[hitsJsonIndex] as TextContent).text =
            "```json\n" + JSON.stringify(hitsJsonObj) + "\n```";
          size = jsonSizeBytes(result);
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

      const resourceOffset = (() => {
        let offset = 1; // summary
        if (includeHitsJson) offset += 1;
        if (promptReady.length > 0) offset += 1;
        return offset;
      })();

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
        result._meta = {
          ...result._meta,
          complete: false,
          warnings: Array.isArray(result._meta?.warnings)
            ? [...(result._meta?.warnings as string[]), "payload_trimmed"]
            : ["payload_trimmed"],
        };
        warningEntries.push({ code: "payload_trimmed" });
        if (includeHitsJson && hitsJsonIndex >= 0 && result.content[hitsJsonIndex]?.type === "text") {
          (hitsJsonObj.meta as { warnings: WarningEntry[] }).warnings = warningEntries;
          (result.content[hitsJsonIndex] as TextContent).text =
            "```json\n" + JSON.stringify(hitsJsonObj) + "\n```";
          size = jsonSizeBytes(result);
        }
        if (includeWarningsInText) {
          // Keep summary at index 0; append trimming warning if possible.
          const txt = (result.content[0] as TextContent).text;
          const warningText = warningEntries
            .map((entry) => (entry.detail ? `${entry.code}(${entry.detail})` : entry.code))
            .join(", ");
          (result.content[0] as TextContent).text = txt.includes("payload_trimmed")
            ? txt
            : `${txt} Warnings: ${warningText}`;
        }
        await logWarn("search", "trimmed content to respect 70KB cap", { trimmed: true });
      }

      await logInfo("search", "search_knowledge success", {
        hits_count: transformedRes.hits.length,
        warnings,
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
