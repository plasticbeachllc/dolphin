import { z } from "zod";
import { CONFIG } from "../../util/config.js";
import { buildToolInputSchema } from "../tools/schema.js";
import { SearchRequestSchema } from "../../rest/schemas.js";

export const SEARCH_INPUT = SearchRequestSchema.omit({
  include_snippets: true,
}).extend({
  top_k: z.number().int().min(1).max(CONFIG.MCP_LIMITS.TOP_K_MAX).optional(),
  max_snippets: z.number().int().min(0).optional(),
  top_context_n: z.number().int().min(0).optional(),
  embed_model: z.enum(["small", "large"]).optional().default("large"),
  score_cutoff: z.number().optional(),
  mmr_enabled: z.boolean().optional(),
  mmr_lambda: z.number().min(0).max(1).optional(),
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
});

export const SEARCH_INPUT_SCHEMA = buildToolInputSchema(SEARCH_INPUT);

export type SearchInput = z.infer<typeof SEARCH_INPUT>;

export type SearchOptions = {
  repos?: string[];
  topK: number;
  snippetsTopN: number;
  topContextN: number;
  includePromptReady: boolean;
  includeResourceText: boolean;
  includeHitsJson: boolean;
  includeWarningsInText: boolean;
  includeAbsPaths: boolean;
  includeVscodeUris: boolean;
  includeSnippets: boolean;
  includeGraphContext: boolean;
  contextLinesBefore: number;
  contextLinesAfter: number;
};

export function parseSearchInput(args: unknown): SearchInput {
  const argsObj = args as { input?: unknown } | undefined;
  return SEARCH_INPUT.parse(argsObj?.input ?? args);
}

export function resolveSearchOptions(input: SearchInput): SearchOptions {
  const repos = input.repos?.map((r) => r.trim());
  const topK = input.top_k ?? CONFIG.SEARCH_DEFAULTS.TOP_K;
  const snippetsTopNRequested = input.max_snippets ?? CONFIG.SEARCH_DEFAULTS.SNIPPETS_TOP_N;
  const snippetsTopN = Math.max(0, Math.min(topK, snippetsTopNRequested));
  const topContextNRequested = input.top_context_n ?? CONFIG.SEARCH_DEFAULTS.TOP_CONTEXT_N;
  const topContextN = Math.max(0, Math.min(snippetsTopN, topContextNRequested));

  let includePromptReady =
    input.include_prompt_ready ?? CONFIG.SEARCH_DEFAULTS.INCLUDE_PROMPT_READY;
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
  const includeGraphContext =
    input.include_graph_context ?? CONFIG.SEARCH_DEFAULTS.INCLUDE_GRAPH_CONTEXT;

  const contextLinesBefore =
    input.context_lines_before ?? CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_BEFORE;
  const contextLinesAfter = input.context_lines_after ?? CONFIG.SEARCH_DEFAULTS.CONTEXT_LINES_AFTER;

  return {
    repos,
    topK,
    snippetsTopN,
    topContextN,
    includePromptReady,
    includeResourceText,
    includeHitsJson,
    includeWarningsInText,
    includeAbsPaths,
    includeVscodeUris,
    includeSnippets,
    includeGraphContext,
    contextLinesBefore,
    contextLinesAfter,
  };
}
