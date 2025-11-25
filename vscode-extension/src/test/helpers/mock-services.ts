import * as http from "http";
import { AddressInfo } from "net";
import {
  MockSearchRequest,
  MockSearchResponse,
  MockSearchResult,
  MockMetadataResponse,
  MockChunkResponse,
  MockHealthResponse,
  MockKBConfig,
  AgentEvent,
  EventHandlerDisposable,
  HttpRequestLog,
  ToolCall,
} from "./mock-types";

/**
 * Mock KB API server for testing
 */
export class MockKBServer {
  private searchResults: MockSearchResult[] | null = null;
  private metadata: MockMetadataResponse | null = null;
  private isHealthy: boolean = true;
  private chunkData: MockChunkResponse | null = null;
  private server: http.Server | null = null;
  public port = 0;
  private requestHistory: HttpRequestLog[] = [];

  /**
   * Start the mock server
   */
  async start(port = 0): Promise<number> {
    return new Promise((resolve, reject) => {
      this.server = http.createServer(this.handleRequest.bind(this));

      this.server.on("error", reject);

      this.server.listen(port, () => {
        const addr = this.server!.address() as AddressInfo;
        this.port = addr.port;
        console.log(`Mock KB API server started on port ${this.port}`);
        resolve(this.port);
      });
    });
  }

  /**
   * Stop the mock server
   */
  async stop(): Promise<void> {
    return new Promise((resolve) => {
      if (this.server) {
        this.server.close(() => {
          console.log("Mock KB API server stopped");
          resolve();
        });
      } else {
        resolve();
      }
    });
  }

  /**
   * Configure mock search results
   */
  setSearchResults(results: MockSearchResult[]): void {
    this.searchResults = results;
  }

  /**
   * Configure mock metadata
   */
  setMetadata(metadata: MockMetadataResponse): void {
    this.metadata = metadata;
  }

  /**
   * Configure mock health status
   */
  setHealthy(healthy: boolean): void {
    this.isHealthy = healthy;
  }

  /**
   * Configure mock chunk data
   */
  setChunkData(chunk: MockChunkResponse): void {
    this.chunkData = chunk;
  }

  /**
   * Configure all mock settings at once
   */
  configure(config: MockKBConfig): void {
    if (config.searchResults !== undefined) {
      this.searchResults = config.searchResults;
    }
    if (config.metadata !== undefined) {
      this.metadata = config.metadata;
    }
    if (config.health !== undefined) {
      this.isHealthy = config.health;
    }
    if (config.chunkData !== undefined) {
      this.chunkData = config.chunkData;
    }
  }

  /**
   * Reset all mock configuration to defaults
   */
  reset(): void {
    this.searchResults = null;
    this.metadata = null;
    this.isHealthy = true;
    this.chunkData = null;
    this.requestHistory = [];
  }

  /**
   * Get request history for testing
   */
  getRequestHistory(): HttpRequestLog[] {
    return [...this.requestHistory];
  }

  /**
   * Handle HTTP requests
   */
  private handleRequest(req: http.IncomingMessage, res: http.ServerResponse): void {
    const url = req.url || "";

    // Log request
    this.requestHistory.push({
      method: req.method,
      url,
      timestamp: Date.now(),
    });

    // CORS headers for testing
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");

    if (req.method === "OPTIONS") {
      res.writeHead(200);
      res.end();
      return;
    }

    // Health check
    if (url === "/health" || url === "/") {
      const healthResponse: MockHealthResponse = {
        status: this.isHealthy ? "ok" : "error",
        mock: true,
        ...(this.isHealthy ? {} : { error: "Mock server is unhealthy" }),
      };
      res.writeHead(this.isHealthy ? 200 : 503, {
        "Content-Type": "application/json",
      });
      res.end(JSON.stringify(healthResponse));
      return;
    }

    // Search endpoint
    if (url.startsWith("/search") && req.method === "POST") {
      let body = "";
      req.on("data", (chunk) => {
        body += chunk;
      });

      req.on("end", () => {
        try {
          const searchRequest = JSON.parse(body);
          const response = this.generateMockSearchResponse(searchRequest);

          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify(response));
        } catch {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Invalid request" }));
        }
      });
      return;
    }

    // Get metadata endpoint
    if (url.startsWith("/metadata/") && req.method === "GET") {
      const response = this.generateMockMetadata();
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(response));
      return;
    }

    // Fetch chunk endpoint
    if (url.startsWith("/chunks/") && req.method === "GET") {
      const response = this.generateMockChunk();
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(response));
      return;
    }

    // Not found
    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "Not found" }));
  }

  /**
   * Generate mock search response
   */
  private generateMockSearchResponse(_request: MockSearchRequest): MockSearchResponse {
    // Use configured search results if available, otherwise use defaults
    const hits: MockSearchResult[] = this.searchResults || [
      {
        chunk_id: "mock-chunk-1",
        repo: "test-repo",
        path: "src/test.ts",
        content: "function testFunction() { return true; }",
        score: 0.95,
        line_start: 1,
        line_end: 3,
      },
      {
        chunk_id: "mock-chunk-2",
        repo: "test-repo",
        path: "src/utils.ts",
        content: "export const helper = () => {}",
        score: 0.85,
        line_start: 5,
        line_end: 7,
      },
    ];

    return {
      hits,
      total: hits.length,
      cursor: null,
      complete: true,
      warnings: [],
    };
  }

  /**
   * Generate mock metadata
   */
  private generateMockMetadata(): MockMetadataResponse {
    // Use configured metadata if available, otherwise use defaults
    return (
      this.metadata || {
        repos: [
          {
            name: "test-repo",
            path: "/test/repo",
            files: 10,
            chunks: 50,
          },
        ],
        total_chunks: 50,
        total_files: 10,
      }
    );
  }

  /**
   * Generate mock chunk
   */
  private generateMockChunk(): MockChunkResponse {
    // Use configured chunk data if available, otherwise use defaults
    return (
      this.chunkData || {
        chunk_id: "mock-chunk-1",
        repo: "test-repo",
        path: "src/test.ts",
        content: "function testFunction() {\n  return true;\n}",
        line_start: 1,
        line_end: 3,
        metadata: {
          language: "typescript",
          size: 45,
        },
      }
    );
  }
}

/**
 * Enhanced MockAgentBridge with full feature support.
 */
export class MockAgentBridge {
  private handlers: Map<string, (data: AgentEvent) => void> = new Map();
  private messageHistory: string[] = [];
  private shouldThrowError: boolean = false;
  private errorMessage: string = "Mock error";
  private shouldError: Error | null = null;
  private toolCallQueue: ToolCall[] = [];
  private responseQueue: string[] = [];
  private eventHandlers: Map<string, Function[]> = new Map();
  private messageHandlers: Map<string, (event: AgentEvent) => void> = new Map();
  public mockResponse: string | null = null;
  public mockToolCalls: ToolCall[] = [];
  public mockError: Error | null = null;
  public mockConnected: boolean = true;

  /**
   * Send a message (simulates user sending message to agent).
   */
  async sendMessage(content: string, _mode?: string): Promise<void> {
    this.messageHistory.push(content);

    if (this.shouldThrowError) {
      const errorEvent = {
        type: "error" as const,
        error: this.errorMessage,
      };
      // Emit to both onEvent and on handlers
      this.emitEvent(errorEvent);
      this.messageHandlers.forEach((handler) => handler(errorEvent));
      throw new Error(this.errorMessage);
    }

    // Simulate async processing
    await new Promise((resolve) => setTimeout(resolve, 100));

    // Simulate processing delay
    await new Promise((resolve) => setTimeout(resolve, 50));

    if (this.shouldError) {
      this.emitToHandlers("error", { error: this.shouldError.message });
      throw this.shouldError;
    }

    // Emit tool calls if configured
    for (const toolCall of this.toolCallQueue) {
      this.emitToHandlers("tool_call_started", toolCall as unknown as Record<string, unknown>);
      await new Promise((resolve) => setTimeout(resolve, 20));
      this.emitToHandlers("tool_call_completed", {
        ...(toolCall as unknown as Record<string, unknown>),
        result: "mock result",
      });
    }

    // Emit response
    const response = this.responseQueue.shift() || "Mock agent response";
    this.emitToHandlers("message_chunk", { content: response });
    this.emitToHandlers("content_delta", { delta: response }); // Legacy compatibility

    await new Promise((resolve) => setTimeout(resolve, 20));
    this.emitToHandlers("task_completed", { success: true, message: response });
  }

  /**
   * Register event listener.
   */
  on(event: string, handler: Function): void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, []);
    }
    this.eventHandlers.get(event)!.push(handler);
  }

  /**
   * Register event handler (alternative syntax for compatibility)
   */
  onEvent(handler: (event: AgentEvent) => void): EventHandlerDisposable {
    const id = Math.random().toString(36);
    this.messageHandlers.set(id, handler);

    return {
      dispose: () => this.messageHandlers.delete(id),
    };
  }

  /**
   * Configure error injection for testing error paths
   */
  setError(shouldThrow: boolean, message: string = "Mock error"): void {
    this.shouldThrowError = shouldThrow;
    this.errorMessage = message;
  }

  /**
   * Get message history for test verification
   */
  getMessageHistory(): string[] {
    return [...this.messageHistory];
  }

  /**
   * Emit to registered event handlers
   */
  private emitToHandlers(event: string, data: Record<string, unknown>): void {
    const handlers = this.eventHandlers.get(event);
    if (handlers) {
      handlers.forEach((handler) => handler(data));
    }
    // Also emit to onEvent handlers
    const eventData = { type: event, ...data };
    this.messageHandlers.forEach((handler) => handler(eventData as AgentEvent));
  }

  /**
   * Clear message history
   */
  clearHistory(): void {
    this.messageHistory = [];
  }

  /**
   * Simulate a tool call event
   */
  simulateToolCall(toolName: string, toolArgs: Record<string, unknown>): void {
    this.emitEvent({
      type: "tool_call",
      toolName,
      toolArgs,
    });
  }

  /**
   * Emit an event to all handlers
   */
  private emitEvent(event: AgentEvent): void {
    this.handlers.forEach((handler) => handler(event));
  }

  /**
   * Reset mock state between tests
   */
  reset(): void {
    this.handlers.clear();
    this.messageHistory = [];
    this.shouldThrowError = false;
    this.errorMessage = "Mock error";
    this.shouldError = null;
    this.toolCallQueue = [];
    this.responseQueue = [];
    this.eventHandlers.clear();
    this.messageHandlers.clear();
    this.mockResponse = null;
    this.mockToolCalls = [];
    this.mockError = null;
    this.mockConnected = true;
  }

  /**
   * Set mock response for tests
   */
  setResponse(response: string): void {
    this.mockResponse = response;
    if (typeof response === "string") {
      this.responseQueue.push(response);
    }
  }

  /**
   * Set mock tool calls for tests
   */
  setToolCalls(toolCalls: ToolCall[]): void {
    this.mockToolCalls = toolCalls;
    this.toolCallQueue = [...toolCalls];
  }

  /**
   * Wait for agent to be ready (mock implementation for tests)
   */
  async waitForReady(_timeout = 60000): Promise<void> {
    // Mock always ready
    return Promise.resolve();
  }

  /**
   * Shutdown
   */
  shutdown(): void {
    this.handlers.clear();
    this.messageHistory = [];
  }

  /**
   * Emit a raw AgentEvent to all registered handlers (utility for tests).
   */
  emit(event: Record<string, unknown>): void {
    const { type, ...rest } = event as Record<string, unknown>;
    const eventType = type ? String(type) : "";
    if (!eventType) return;
    this.emitToHandlers(eventType, rest);
  }
}
