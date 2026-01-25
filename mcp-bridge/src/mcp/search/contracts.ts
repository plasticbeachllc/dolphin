import type { SearchResponse } from "../../rest/client.js";

export interface ApiSearchHit {
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

export interface ApiSearchResponse {
  hits: ApiSearchHit[];
  meta: {
    top_k?: number;
    model?: string;
    latency_ms?: number;
    timing?: { embedding_ms?: number; search_ms?: number; processing_ms?: number };
    estimated_total?: number;
    max_snippets?: number;
    warnings?: string[];
  };
}

export interface ApiHit {
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

export interface ExtendedSearchHit {
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

export type WarningEntry = { code: string; detail?: string };

export type SnippetFailure = { repo: string; path: string; start: number; end: number };

export type SnippetInfo = { snippet: string; start: number; end: number };

export type SearchResultWithHits = SearchResponse & { hits: ExtendedSearchHit[] };

export const HITS_JSON_SCHEMA_VERSION = "2026-01-25.1";
