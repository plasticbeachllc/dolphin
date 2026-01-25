import { CONFIG } from "../util/config.js";
import { resolveKbApiKey } from "../../../shared/kb-auth";

export interface RestError {
  error: {
    code: string;
    message: string;
    details?: unknown;
    remediation?: string;
  };
}

export interface SearchRequestBody {
  query: string;
  repos?: string[];
  path_prefix?: string[];
  exclude_paths?: string[];
  exclude_patterns?: string[];
  top_k?: number;
  max_snippets?: number;
  embed_model?: "small" | "large";
  score_cutoff?: number;
  mmr_enabled?: boolean;
  mmr_lambda?: number;
  include_snippets?: boolean;
  ann_strategy?: "speed" | "accuracy" | "adaptive" | "custom";
  ann_nprobes?: number;
  ann_refine_factor?: number;
  include_graph_context?: boolean;
  context_lines_before?: number;
  context_lines_after?: number;
}

export interface SearchHit {
  repo: string;
  path: string;
  lang?: string;
  symbol?: { kind?: string; name?: string; path?: string };
  start_line: number;
  end_line: number;
  score: number;
  snippet: string;
  snippet_fenced?: string;
  chunk_id: string;
  resource_link: string;
}

export interface SearchResponse {
  hits: SearchHit[];
  meta: {
    top_k?: number;
    model?: string;
    latency_ms?: number;
    timing?: { embedding_ms?: number; search_ms?: number; processing_ms?: number };
    estimated_total?: number;
    max_snippets?: number;
    warnings?: string[];
  };
  prompt_ready?: string;
}

export interface ChunkResponse {
  chunk_id: string;
  repo: string;
  path: string;
  lang?: string;
  symbol?: { kind?: string; name?: string; path?: string };
  start_line: number;
  end_line: number;
  content: string;
  resource_link: string;
}

export interface FileSliceResponse {
  repo: string;
  path: string;
  start_line: number;
  end_line: number;
  content: string;
  lang?: string;
  source: string;
  symbol_context?: Array<{ kind?: string; name?: string; path?: string }>;
  _meta?: { warnings?: string[] };
}

let KB_API_KEY: string | undefined;

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class KBClient {
  private readonly _fetch?: FetchLike;
  private readonly _baseUrl?: string;

  constructor(options?: { fetch?: FetchLike; baseUrl?: string }) {
    this._fetch = options?.fetch;
    this._baseUrl = options?.baseUrl;
  }

  private _getBaseUrl(): string {
    if (this._baseUrl) return this._baseUrl;
    // Read env vars dynamically to support test mock server
    // Mock server sets KB_REST_BASE_URL after module load
    return process.env.KB_REST_BASE_URL || process.env.DOLPHIN_API_URL || CONFIG.DOLPHIN_API_URL;
  }

  private _getKbApiKey(): string | undefined {
    if (KB_API_KEY !== undefined) {
      return KB_API_KEY;
    }
    const envKey =
      process.env.DOLPHIN_API_KEY?.trim() || process.env.DOLPHIN_KB_API_KEY?.trim() || "";
    if (envKey) {
      KB_API_KEY = envKey;
      return KB_API_KEY;
    }

    KB_API_KEY = resolveKbApiKey({ readOnly: true });
    return KB_API_KEY;
  }

  private async _doFetch<T>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
    const headers = new Headers(init?.headers);
    headers.set("Content-Type", "application/json");
    headers.set("Accept", "application/json");
    headers.set("X-Client", "mcp");

    const kbKey = this._getKbApiKey();
    if (kbKey) {
      headers.set("X-API-Key", kbKey);
    }

    const baseUrl = this._getBaseUrl();
    const fetchFn = this._fetch ?? globalThis.fetch.bind(globalThis);
    const res = await fetchFn(baseUrl + path, { ...init, headers, signal });
    const text = await res.text();

    // Be robust to non-JSON upstream responses (e.g., "Internal Server Error")
    let json: unknown = {};
    try {
      json = text ? JSON.parse(text) : {};
    } catch (parseErr: unknown) {
      const snippet = text?.slice(0, 200) ?? "";
      const error = parseErr instanceof Error ? parseErr : new Error(String(parseErr));
      const rawMsg = error.message;
      const normalizedMsg =
        typeof rawMsg === "string" ? rawMsg.replace(/^JSON Parse error:\s*/i, "") : String(rawMsg);
      const err: RestError = {
        error: {
          code: "invalid_json",
          message: `JSON parse error: ${normalizedMsg}`,
          remediation:
            "Upstream returned non-JSON. Inspect server logs, verify endpoints/filters, or reduce response size (top_k/max_snippets).",
          details: { status: res.status, statusText: res.statusText, body_snippet: snippet },
        },
      };
      throw err;
    }

    if (!res.ok) {
      // Ensure a structured error even if upstream returned plain text
      if (!(json as { error?: unknown })?.error) {
        const err: RestError = {
          error: {
            code: "upstream_error",
            message: `HTTP ${res.status} ${res.statusText}`,
            remediation:
              "Check repo names with /v1/repos, adjust filters, or reduce response size (top_k/max_snippets). See server logs.",
            details: { body_snippet: (text || "").slice(0, 200) },
          },
        };
        throw err;
      }
      throw json as RestError;
    }

    return json as T;
  }

  async search(body: SearchRequestBody, signal?: AbortSignal): Promise<SearchResponse> {
    return await this._doFetch<SearchResponse>(
      "/v1/search",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
      signal
    );
  }

  async getChunk(id: string, signal?: AbortSignal): Promise<ChunkResponse> {
    return await this._doFetch<ChunkResponse>(
      `/v1/chunks/${encodeURIComponent(id)}`,
      { method: "GET" },
      signal
    );
  }

  async getFileSlice(
    repo: string,
    path: string,
    start: number,
    end: number,
    signal?: AbortSignal
  ): Promise<FileSliceResponse> {
    const q = new URLSearchParams({ repo, path, start: String(start), end: String(end) });
    return await this._doFetch<FileSliceResponse>(
      `/v1/file?${q.toString()}`,
      { method: "GET" },
      signal
    );
  }

  async listRepos(signal?: AbortSignal): Promise<{ repos: RepoInfo[] }> {
    return await this._doFetch<{ repos: RepoInfo[] }>("/v1/repos", { method: "GET" }, signal);
  }

  async healthV1(check?: "shallow" | "deep", signal?: AbortSignal): Promise<HealthResponse> {
    const q = new URLSearchParams();
    if (check) q.set("check", check);
    const suffix = q.toString();
    return await this._doFetch<HealthResponse>(
      `/v1/health${suffix ? `?${suffix}` : ""}`,
      { method: "GET" },
      signal
    );
  }
}

export interface RepoInfo {
  name: string;
  path: string;
  default_embed_model?: string;
  files?: number;
  chunks?: number;
}

export interface HealthResponse {
  status?: string;
  version?: string;
  [key: string]: unknown;
}

// Global instance for backward compatibility
const globalClient = new KBClient();

export async function restSearch(
  body: SearchRequestBody,
  signal?: AbortSignal
): Promise<SearchResponse> {
  return globalClient.search(body, signal);
}

export async function restGetChunk(id: string, signal?: AbortSignal): Promise<ChunkResponse> {
  return globalClient.getChunk(id, signal);
}

export async function restGetFileSlice(
  repo: string,
  path: string,
  start: number,
  end: number,
  signal?: AbortSignal
): Promise<FileSliceResponse> {
  return globalClient.getFileSlice(repo, path, start, end, signal);
}

export async function restListRepos(signal?: AbortSignal): Promise<{ repos: RepoInfo[] }> {
  return globalClient.listRepos(signal);
}

export async function restHealthV1(
  check?: "shallow" | "deep",
  signal?: AbortSignal
): Promise<HealthResponse> {
  return globalClient.healthV1(check, signal);
}
