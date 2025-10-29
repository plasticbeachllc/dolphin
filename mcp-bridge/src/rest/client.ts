export interface RestError {
  error: {
    code: string
    message: string
    details?: any
    remediation?: string
  }
}

export interface SearchRequestBody {
  query: string
  repos?: string[]
  path_prefix?: string[]
  top_k?: number
  max_snippets?: number
  deadline_ms?: number
  embed_model?: 'small' | 'large'
  score_cutoff?: number
  cursor?: string
  include_prompt_ready?: boolean
}

export interface SearchHit {
  repo: string
  path: string
  lang?: string
  symbol?: { kind?: string, name?: string, path?: string }
  start_line: number
  end_line: number
  score: number
  snippet: string
  snippet_fenced?: string
  chunk_id: string
  resource_link: string
}

export interface SearchResponse {
  hits: SearchHit[]
  meta: {
    top_k?: number
    model?: string
    latency_ms?: number
    timing?: { embedding_ms?: number, search_ms?: number, processing_ms?: number }
    cursor?: string
    estimated_total?: number
    complete?: boolean
    warnings?: string[]
  }
  prompt_ready?: string
}

export interface ChunkResponse {
  chunk_id: string
  repo: string
  path: string
  lang?: string
  symbol?: { kind?: string, name?: string, path?: string }
  start_line: number
  end_line: number
  content: string
  resource_link: string
}

export interface FileSliceResponse {
  repo: string
  path: string
  start_line: number
  end_line: number
  content: string
  lang?: string
  source: string
  symbol_context?: Array<{ kind?: string, name?: string, path?: string }>
  _meta?: { warnings?: string[] }
}

const BASE_URL = 'http://127.0.0.1:7777'

async function doFetch<T> (path: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('Content-Type', 'application/json')
  headers.set('X-Client', 'mcp')

  const res = await fetch(BASE_URL + path, { ...init, headers, signal })
  const text = await res.text()
  const json = text ? JSON.parse(text) : {}
  if (!res.ok) {
    throw json as RestError
  }
  return json as T
}

export async function restSearch (body: SearchRequestBody, signal?: AbortSignal): Promise<SearchResponse> {
  return await doFetch<SearchResponse>('/v1/search', {
    method: 'POST',
    body: JSON.stringify(body)
  }, signal)
}

export async function restGetChunk (id: string, signal?: AbortSignal): Promise<ChunkResponse> {
  return await doFetch<ChunkResponse>(`/v1/chunks/${encodeURIComponent(id)}`, { method: 'GET' }, signal)
}

export async function restGetFileSlice (repo: string, path: string, start: number, end: number, signal?: AbortSignal): Promise<FileSliceResponse> {
  const q = new URLSearchParams({ repo, path, start: String(start), end: String(end) })
  return await doFetch<FileSliceResponse>(`/v1/file?${q.toString()}`, { method: 'GET' }, signal)
}

export interface RepoInfo { name: string, path: string, default_embed_model?: string, files?: number, chunks?: number }
export async function restListRepos (signal?: AbortSignal): Promise<{ repos: RepoInfo[] }> {
  return await doFetch<{ repos: RepoInfo[] }>('/v1/repos', { method: 'GET' }, signal)
}
