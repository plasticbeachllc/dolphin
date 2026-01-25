import path from "node:path";
import type { RepoInfo, KBClient } from "../../rest/client.js";
import { restListRepos } from "../../rest/client.js";
import type { ApiHit, ExtendedSearchHit, SnippetInfo } from "./contracts.js";

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

export async function getReposByName(
  signal?: AbortSignal,
  client?: KBClient
): Promise<Map<string, RepoInfo>> {
  if (repoCache && !isRepoCacheExpired(repoCache)) {
    return repoCache.reposByName;
  }
  const repoList = await (client ? client.listRepos(signal) : restListRepos(signal));
  const reposByName = new Map(repoList.repos.map((r) => [r.name, r]));
  repoCache = { ts: Date.now(), reposByName };
  return reposByName;
}

export function transformHits(params: {
  hits: ApiHit[];
  snippetsByHitIndex: Map<number, SnippetInfo>;
  includeAbsPaths: boolean;
  includeVscodeUris: boolean;
  reposByName?: Map<string, RepoInfo>;
}): { hits: ExtendedSearchHit[]; escapedPathCount: number } {
  const { hits, snippetsByHitIndex, includeAbsPaths, includeVscodeUris, reposByName } = params;
  let escapedPathCount = 0;

  const transformedHits = hits.map((hit, idx) => {
    const chunkStart = hit.start_line;
    const chunkEnd = hit.end_line;
    const snippetInfo = snippetsByHitIndex.get(idx);
    const snippetStart =
      snippetInfo?.start ??
      hit.snippet_start_line ??
      (typeof chunkStart === "number" ? chunkStart : undefined);
    const snippetEnd =
      snippetInfo?.end ??
      hit.snippet_end_line ??
      (typeof chunkEnd === "number" ? chunkEnd : snippetStart);

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
    const absPath = includeAbsPaths && repoRoot ? safeResolveWithin(repoRoot, hit.path) : undefined;
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
    } as ExtendedSearchHit;
  });

  return { hits: transformedHits, escapedPathCount };
}
