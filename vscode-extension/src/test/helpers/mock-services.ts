import * as http from 'http';
import { AddressInfo } from 'net';

/**
 * Mock KB API server for testing
 */
export class MockKBServer {
  private server: http.Server | null = null;
  public port = 0;

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
   * Handle HTTP requests
   */
  private handleRequest(
    req: http.IncomingMessage,
    res: http.ServerResponse
  ): void {
    const url = req.url || '';

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
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'ok', mock: true }));
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
 * Create a mock agent bridge for testing
 */
export class MockAgentBridge {
  private handlers: Map<string, (data: any) => void> = new Map();

  /**
   * Simulate sending a message
   */
  async sendMessage(content: string): Promise<void> {
    // Simulate async processing
    await new Promise((resolve) => setTimeout(resolve, 100));

    // Emit mock events
    this.emitEvent({
      type: 'content_delta',
      delta: `Mock response to: ${content}`,
    });

    this.emitEvent({
      type: 'task_completed',
      success: true,
    });
  }

  /**
   * Register event handler
   */
  onEvent(handler: (event: any) => void): { dispose: () => void } {
    const id = Math.random().toString(36);
    this.handlers.set(id, handler);

    return {
      dispose: () => this.handlers.delete(id),
    };
  }

  /**
   * Emit an event to all handlers
   */
  private emitEvent(event: any): void {
    this.handlers.forEach((handler) => handler(event));
  }

  /**
   * Shutdown
   */
  shutdown(): void {
    this.handlers.clear();
  }
}
