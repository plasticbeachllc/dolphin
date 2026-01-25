import type { SearchRequestBody, SearchResponse, KBClient } from "../../rest/client.js";
import { restSearch } from "../../rest/client.js";
import type { SearchInput, SearchOptions } from "./input.js";

export function buildSearchRequestBody(
  input: SearchInput,
  options: SearchOptions
): SearchRequestBody {
  const maxSnippets = options.includeSnippets ? options.snippetsTopN : 0;
  const includeContextInKb = maxSnippets > 0 && options.topContextN >= maxSnippets;
  const contextLinesBefore = includeContextInKb ? options.contextLinesBefore : 0;
  const contextLinesAfter = includeContextInKb ? options.contextLinesAfter : 0;
  return {
    query: input.query,
    repos: options.repos,
    path_prefix: input.path_prefix,
    exclude_paths: input.exclude_paths,
    exclude_patterns: input.exclude_patterns,
    top_k: options.topK,
    max_snippets: maxSnippets,
    embed_model: input.embed_model,
    score_cutoff: input.score_cutoff,
    mmr_enabled: input.mmr_enabled,
    mmr_lambda: input.mmr_lambda,
    ann_strategy: input.ann_strategy,
    ann_nprobes: input.ann_nprobes,
    ann_refine_factor: input.ann_refine_factor,
    include_graph_context: options.includeGraphContext,
    // Ask the KB to include snippets for up to `max_snippets` hits. When the caller only wants
    // expanded context for the top N, we fetch that via follow-up `file_lines` calls.
    context_lines_before: contextLinesBefore,
    context_lines_after: contextLinesAfter,
  };
}

export async function executeSearch(
  body: SearchRequestBody,
  signal?: AbortSignal,
  client?: KBClient
): Promise<SearchResponse> {
  return await (client ? client.search(body, signal) : restSearch(body, signal));
}
