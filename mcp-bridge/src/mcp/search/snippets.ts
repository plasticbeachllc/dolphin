import { fetchSnippetsInParallel } from "../tools/snippet_fetcher.js";
import { CONFIG } from "../../util/config.js";
import type { ApiHit, SnippetFailure, SnippetInfo } from "./contracts.js";

export async function fetchSnippetsForHits(params: {
  hits: ApiHit[];
  includeSnippets: boolean;
  snippetsTopN: number;
  topContextN: number;
  contextLinesBefore: number;
  contextLinesAfter: number;
  signal?: AbortSignal;
}): Promise<{
  snippetsByHitIndex: Map<number, SnippetInfo>;
  snippetFailures: SnippetFailure[];
}> {
  const {
    hits,
    includeSnippets,
    snippetsTopN,
    topContextN,
    contextLinesBefore,
    contextLinesAfter,
    signal,
  } = params;

  const snippetFailures: SnippetFailure[] = [];
  const snippetsByHitIndex: Map<number, SnippetInfo> = new Map();

  if (!includeSnippets) {
    return { snippetsByHitIndex, snippetFailures };
  }

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

  if (requests.length === 0) {
    return { snippetsByHitIndex, snippetFailures };
  }

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

  return { snippetsByHitIndex, snippetFailures };
}
