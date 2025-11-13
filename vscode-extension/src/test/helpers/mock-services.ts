import * as http from 'http';
import { AddressInfo } from 'net';

/**
 * Mock KB API server for testing
 */
export class MockKBServer {
  private server: http.Server | null = null;
  public port = 0;
  private mockSearchResults: any[] | null = null;
  private mockMetadata: any | null = null;
  private isHealthy: boolean = true;
  private requestHistory: any[] = [];

  /**
   * Start the mock server
   */
  async start(port = 0): Promise<number> {
    return new Promise((resolve, reject) => {
      this.server = http.createServer(this.handleRequest.bind(this));

      this.server.on('error', reject);

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
          console.log('Mock KB API server stopped');
          resolve();
        });
      } else {
        resolve();
      }
    });
  }

  /**
   * Set custom search results
   */
  setSearchResults(results: any[]): void {
    this.mockSearchResults = results;
  }

  /**
   * Set custom metadata
   */
  setMetadata(metadata: any): void {
    this.mockMetadata = metadata;
  }

  /**
   * Set health status
   */
  setHealthy(healthy: boolean): void {
    this.isHealthy = healthy;
  }

  /**
   * Get request history
   */
  getRequestHistory(): any[] {
    return [...this.requestHistory];
  }

  /**
   * Reset mock state
   */
  reset(): void {
    this.mockSearchResults = null;
    this.mockMetadata = null;
    this.isHealthy = true;
    this.requestHistory = [];
  }

  /**
   * Handle HTTP requests
   */
  private handleRequest(
    req: http.IncomingMessage,
    res: http.ServerResponse
  ): void {
    const url = req.url || '';

    // Log request
    this.requestHistory.push({
      method: req.method,
      url,
      timestamp: Date.now(),
    });

    // CORS headers for testing
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
      res.writeHead(200);
      res.end();
      return;
    }

    // Health check
    if (url === '/health' || url === '/') {
      if (this.isHealthy) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'ok', mock: true }));
      } else {
        res.writeHead(503, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'error', mock: true }));
      }
      return;
    }

    // Search endpoint
    if (url.startsWith('/search') && req.method === 'POST') {
      let body = '';
      req.on('data', (chunk) => {
        body += chunk;
      });

      req.on('end', () => {
        try {
          const searchRequest = JSON.parse(body);
          const response = this.generateMockSearchResponse(searchRequest);

          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(response));
        } catch (err) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid request' }));
        }
      });
      return;
    }

    // Get metadata endpoint
    if (url.startsWith('/metadata/') && req.method === 'GET') {
      const response = this.generateMockMetadata();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(response));
      return;
    }

    // Fetch chunk endpoint
    if (url.startsWith('/chunks/') && req.method === 'GET') {
      const response = this.generateMockChunk();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(response));
      return;
    }

    // Not found
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
  }

  /**
   * Generate mock search response
   */
  private generateMockSearchResponse(request: any): any {
    // Use custom results if set
    if (this.mockSearchResults !== null) {
      return {
        hits: this.mockSearchResults,
        total: this.mockSearchResults.length,
        cursor: null,
        complete: true,
        warnings: [],
      };
    }

    // Default mock response
    return {
      hits: [
        {
          chunk_id: 'mock-chunk-1',
          repo: 'test-repo',
          path: 'src/test.ts',
          content: 'function testFunction() { return true; }',
          score: 0.95,
          line_start: 1,
          line_end: 3,
        },
        {
          chunk_id: 'mock-chunk-2',
          repo: 'test-repo',
          path: 'src/utils.ts',
          content: 'export const helper = () => {}',
          score: 0.85,
          line_start: 5,
          line_end: 7,
        },
      ],
      total: 2,
      cursor: null,
      complete: true,
      warnings: [],
    };
  }

  /**
   * Generate mock metadata
   */
  private generateMockMetadata(): any {
    // Use custom metadata if set
    if (this.mockMetadata !== null) {
      return this.mockMetadata;
    }

    // Default mock metadata
    return {
      repos: [
        {
          name: 'test-repo',
          path: '/test/repo',
          files: 10,
          chunks: 50,
        },
      ],
      total_chunks: 50,
      total_files: 10,
    };
  }

  /**
   * Generate mock chunk
   */
  private generateMockChunk(): any {
    return {
      chunk_id: 'mock-chunk-1',
      repo: 'test-repo',
      path: 'src/test.ts',
      content: 'function testFunction() {\n  return true;\n}',
      line_start: 1,
      line_end: 3,
      metadata: {
        language: 'typescript',
        size: 45,
      },
    };
  }
}

/**
 * Enhanced MockAgentBridge with full feature support.
 */
export class MockAgentBridge {
  private messageHandlers: Map<string, Function> = new Map();
  private eventHandlers: Map<string, Function[]> = new Map();
  private messageHistory: any[] = [];
  private responseQueue: string[] = [];
  private toolCallQueue: any[] = [];
  private shouldError: Error | null = null;

  /**
   * Send a message (simulates user sending message to agent).
   */
  async sendMessage(message: string): Promise<void> {
    this.messageHistory.push({ type: 'user_message', content: message, timestamp: Date.now() });

    // Simulate processing delay
    await new Promise(resolve => setTimeout(resolve, 50));

    if (this.shouldError) {
      this.emit('error', this.shouldError);
      throw this.shouldError;
    }

    // Emit tool calls if configured
    for (const toolCall of this.toolCallQueue) {
      this.emit('tool_call_started', toolCall);
      await new Promise(resolve => setTimeout(resolve, 20));
      this.emit('tool_call_completed', { ...toolCall, result: 'mock result' });
    }

    // Emit response
    const response = this.responseQueue.shift() || 'Mock agent response';
    this.emit('message_chunk', { content: response });
    this.emit('content_delta', { delta: response }); // Legacy compatibility
    this.messageHistory.push({ type: 'assistant_message', content: response, timestamp: Date.now() });

    await new Promise(resolve => setTimeout(resolve, 20));
    this.emit('task_completed', { success: true, message: response });
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
  onEvent(handler: (event: any) => void): { dispose: () => void } {
    const id = Math.random().toString(36);
    this.messageHandlers.set(id, handler);

    return {
      dispose: () => this.messageHandlers.delete(id),
    };
  }

  /**
   * Emit event to listeners.
   */
  private emit(event: string, data: any): void {
    // Emit to specific event handlers
    const handlers = this.eventHandlers.get(event) || [];
    for (const handler of handlers) {
      handler(data);
    }

    // Also emit to onEvent handlers
    const eventData = { type: event, ...data };
    this.messageHandlers.forEach((handler) => handler(eventData));
  }

  /**
   * Get message history.
   */
  getMessageHistory(): any[] {
    return [...this.messageHistory];
  }

  /**
   * Get event history.
   */
  getEventHistory(): any[] {
    return [...this.messageHistory];
  }

  /**
   * Set next response.
   */
  setResponse(response: string): void {
    this.responseQueue.push(response);
  }

  /**
   * Set tool calls to emit.
   */
  setToolCalls(toolCalls: any[]): void {
    this.toolCallQueue = toolCalls;
  }

  /**
   * Set error to throw.
   */
  setError(error: Error): void {
    this.shouldError = error;
  }

  /**
   * Reset all state.
   */
  reset(): void {
    this.messageHistory = [];
    this.responseQueue = [];
    this.toolCallQueue = [];
    this.shouldError = null;
    this.eventHandlers.clear();
  }

  /**
   * Get KB status (mock).
   */
  async getKBStatus(): Promise<any> {
    return {
      running: true,
      port: 7778,
      totalChunks: 1000,
      repositories: ['test-repo'],
    };
  }

  /**
   * Shutdown
   */
  shutdown(): void {
    this.reset();
    this.messageHandlers.clear();
  }
}
