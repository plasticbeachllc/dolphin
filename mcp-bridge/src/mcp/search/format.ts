import type { SearchResponse } from "../../rest/client.js";
import { fenceLang } from "../../util/language.js";
import type {
  ExtendedSearchHit,
  WarningEntry,
  SnippetFailure,
  SearchResultWithHits,
} from "./contracts.js";
import { HITS_JSON_SCHEMA_VERSION } from "./contracts.js";

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

export function buildPromptReady(res: SearchResponse, maxHits: number): string {
  const parts: string[] = [];
  for (const h of res.hits.slice(0, maxHits)) {
    const hit = h as unknown as ExtendedSearchHit;

    const hasContext = hit._context_start_line && hit._context_start_line !== hit.start_line;
    const lineRange = hasContext
      ? `L${hit._context_start_line}-L${hit._context_end_line}`
      : `L${h.start_line}-L${h.end_line}`;
    const scoreText =
      typeof h.score === "number"
        ? ` score=${Number.isFinite(h.score) ? h.score.toFixed(3) : h.score}`
        : "";
    parts.push(`[${h.repo}] ${h.path}#${lineRange} (chunk_id=${h.chunk_id})${scoreText}`);

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
        `No snippet included for this result. Follow up with chunk_get({chunk_id: "${h.chunk_id}"}) or file_lines({repo:"${h.repo}", path:"${h.path}", start:${h.start_line}, end:${h.end_line}}).`
      );
      continue;
    }

    if (hasContext && code) {
      const lines = code.split("\n");
      const chunkStart = hit._chunk_start_line;
      const chunkEnd = hit._chunk_end_line;
      const contextStart = hit._context_start_line;

      const formattedLines: string[] = [];
      lines.forEach((line, idx) => {
        const lineNum = (contextStart ?? hit.start_line) + idx;

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

export function buildWarnings(params: {
  metaWarnings?: string[];
  snippetFailures: SnippetFailure[];
  escapedPathCount: number;
}): { warnings: string[]; warningEntries: WarningEntry[] } {
  const warnings: string[] = [];
  const warningEntries: WarningEntry[] = [];

  if (Array.isArray(params.metaWarnings)) {
    for (const warning of params.metaWarnings) {
      warnings.push(warning);
      warningEntries.push({ code: warning });
    }
  }

  if (params.snippetFailures.length > 0) {
    const code = "snippet_fetch_failed";
    warnings.push(code);
    warningEntries.push({ code, detail: `${params.snippetFailures.length} snippet(s) failed` });
  }

  if (params.escapedPathCount > 0) {
    const code = "path_escaped_repo_root";
    warnings.push(code);
    warningEntries.push({ code, detail: `${params.escapedPathCount} path(s) escaped repo root` });
  }

  return { warnings, warningEntries };
}

export function buildSummary(params: {
  hits: ExtendedSearchHit[];
  snippetsIncluded: number;
  estimatedTotal?: number;
  includeWarningsInText: boolean;
  warningEntries: WarningEntry[];
}): string {
  const k = params.hits.length;
  const reposSet = new Set(params.hits.map((h) => h.repo));
  const rcount = reposSet.size;

  const summaryParts = [
    `Found ${k} result${k === 1 ? "" : "s"}${rcount > 0 ? ` across ${rcount} repo${rcount === 1 ? "" : "s"}` : ""}.`,
    `Showing snippets for top ${params.snippetsIncluded}/${k} results.`,
  ];
  if (typeof params.estimatedTotal === "number")
    summaryParts.push(`~${params.estimatedTotal} estimated results.`);

  if (params.includeWarningsInText && params.warningEntries.length > 0) {
    const warningText = params.warningEntries
      .map((entry) => (entry.detail ? `${entry.code}(${entry.detail})` : entry.code))
      .join(", ");
    summaryParts.push(`Warnings: ${warningText}`);
  }
  return summaryParts.join(" ");
}

export type HitsJson = {
  schema_version: string;
  query: string;
  hits: Array<{
    rank: number;
    chunk_id: string;
    score: number;
    repo: string;
    path: string;
    lang?: string;
    chunk_range: { start_line: number | undefined; end_line: number | undefined };
    snippet_range: { start_line: number; end_line: number; included: boolean };
    uris: {
      chunk: string;
      snippet: string;
      vscode: string | null;
      abs_path: string | null;
      repo_root: string | null;
    };
    followups: {
      chunk_get: { chunk_id: string };
      file_lines: { repo: string; path: string; start: number; end: number };
    };
  }>;
  meta: {
    estimated_total: number | null;
    warnings: WarningEntry[];
    model: string | null;
    top_k: number;
    max_snippets: number | null;
  };
};

export function buildHitsJsonObject(params: {
  query: string;
  hits: ExtendedSearchHit[];
  meta: SearchResultWithHits["meta"];
  topK: number;
  warningEntries: WarningEntry[];
}): HitsJson {
  return {
    schema_version: HITS_JSON_SCHEMA_VERSION,
    query: params.query,
    hits: params.hits.map((h, i) => {
      const hit = h as ExtendedSearchHit;
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
        snippet_range: {
          start_line: snippetStart,
          end_line: snippetEnd,
          included: Boolean(hit.snippet),
        },
        uris: {
          chunk: hit.chunk_resource_link ?? hit.resource_link,
          snippet: hit.resource_link,
          vscode: hit.vscode_uri ?? null,
          abs_path: hit.abs_path ?? null,
          repo_root: hit.repo_root ?? null,
        },
        followups: {
          chunk_get: { chunk_id: hit.chunk_id },
          file_lines: defaultFetchLines,
        },
      };
    }),
    meta: {
      estimated_total: params.meta.estimated_total ?? null,
      warnings: params.warningEntries,
      model: params.meta.model ?? null,
      top_k: params.meta.top_k ?? params.topK,
      max_snippets: params.meta.max_snippets ?? null,
    },
  };
}

export function buildHitsJsonText(hitsJson: HitsJson): string {
  return "```json\n" + JSON.stringify(hitsJson) + "\n```";
}
