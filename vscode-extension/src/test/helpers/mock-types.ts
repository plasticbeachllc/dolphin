/**
 * TypeScript interfaces for mock data types used in testing
 * Improves type safety by replacing 'any' types throughout test code
 */

/**
 * Mock search result item returned by the KB API
 */
export interface MockSearchResult {
  chunk_id: string;
  repo: string;
  path: string;
  content: string;
  score: number;
  line_start: number;
  line_end: number;
}

/**
 * Mock search response from the KB API /search endpoint
 */
export interface MockSearchResponse {
  hits: MockSearchResult[];
  total: number;
  cursor: string | null;
  complete: boolean;
  warnings: string[];
}

/**
 * Mock search request payload
 */
export interface MockSearchRequest {
  query: string;
  top_k?: number;
  repos?: string[];
  cursor?: string | null;
}

/**
 * Repository metadata in the KB
 */
export interface MockRepoMetadata {
  name: string;
  path: string;
  files: number;
  chunks: number;
}

/**
 * Mock metadata response from the KB API /metadata endpoint
 */
export interface MockMetadataResponse {
  repos: MockRepoMetadata[];
  total_chunks: number;
  total_files: number;
}

/**
 * Mock chunk response from the KB API /chunks endpoint
 */
export interface MockChunkResponse {
  chunk_id: string;
  repo: string;
  path: string;
  content: string;
  line_start: number;
  line_end: number;
  metadata: {
    language: string;
    size: number;
  };
}

/**
 * Mock health check response
 */
export interface MockHealthResponse {
  status: 'ok' | 'error';
  mock: boolean;
  error?: string;
}

/**
 * HTTP response wrapper for tests
 */
export interface HttpTestResponse<T = any> {
  status: number;
  data: T;
  headers?: Record<string, string>;
}

/**
 * Configuration for MockKBServer
 */
export interface MockKBConfig {
  searchResults?: MockSearchResult[];
  metadata?: MockMetadataResponse;
  health?: boolean;
  chunkData?: MockChunkResponse;
}

/**
 * Agent bridge event types
 */
export type AgentEventType =
  | 'content_delta'
  | 'task_completed'
  | 'tool_call'
  | 'error';

/**
 * Agent bridge event structure
 */
export interface AgentEvent {
  type: AgentEventType;
  delta?: string;
  success?: boolean;
  error?: string;
  toolName?: string;
  toolArgs?: any;
}

/**
 * Event handler disposable
 */
export interface EventHandlerDisposable {
  dispose: () => void;
}
