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
  status: "ok" | "error";
  mock: boolean;
  error?: string;
}

/**
 * HTTP response wrapper for tests
 */
export interface HttpTestResponse<T = unknown> {
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
export type AgentEventType = "content_delta" | "task_completed" | "tool_call" | "error";

/**
 * Agent bridge event structure
 */
export interface AgentEvent {
  type: AgentEventType;
  delta?: string;
  success?: boolean;
  error?: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
}

/**
 * Event handler disposable
 */
export interface EventHandlerDisposable {
  dispose: () => void;
}

/**
 * HTTP request log entry for testing
 */
export interface HttpRequestLog {
  method: string | undefined;
  url: string;
  timestamp: number;
}

/**
 * Tool call structure for agent testing
 */
export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
}

/**
 * Generic extension exports type
 */
export interface ExtensionExports {
  isReady?: boolean;
  webviewProvider?: unknown;
  [key: string]: unknown;
}

/**
 * Mock JSON-RPC connection for testing
 */
export interface MockConnection {
  sendNotification: (method: string, params?: Record<string, unknown>) => void | Promise<void>;
  sendRequest: (method: string, params?: Record<string, unknown>) => Promise<unknown>;
  dispose: () => void;
}

/**
 * Generic record with string keys for test data
 */
export type TestRecord = Record<string, unknown>;
