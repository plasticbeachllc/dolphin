import type { SearchRequestBody, SearchResponse, KBClient } from "../../rest/client.js";
import { restSearch } from "../../rest/client.js";
import type { SearchInput, SearchOptions } from "./input.js";

export function buildSearchRequestBody(
  input: SearchInput,
  options: SearchOptions
): SearchRequestBody {
  return {
    query: input.query,
    repos: options.repos,
    path_prefix: input.path_prefix,
    exclude_paths: input.exclude_paths,
    exclude_patterns: input.exclude_patterns,
    top_k: options.topK,
    max_snippets: options.snippetsTopN,
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
    include_graph_context: options.includeGraphContext,
    // Prefer lightweight candidate lists; fetch snippets separately for top results.
    include_snippets: false,
    context_lines_before: 0,
    context_lines_after: 0,
  };
}

export async function executeSearch(
  body: SearchRequestBody,
  signal?: AbortSignal,
  client?: KBClient
): Promise<SearchResponse> {
  return await (client ? client.search(body, signal) : restSearch(body, signal));
}
