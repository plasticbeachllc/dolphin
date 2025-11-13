/**
 * JSON-RPC Communication Layer for Dolphin v2
 * 
 * Handles framed JSON-RPC message parsing and serialization for
 * stdio-based communication with the VSCode extension.
 * 
 * Based on: docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md
 */

import type { JSONRPCMessage } from '../types/index.js';

/**
 * JSON-RPC handler callback type
 */
export type MessageHandler = (message: JSONRPCMessage) => void | Promise<void>;

/**
 * JSON-RPC message parser with Content-Length framing
 */
export class JSONRPCParser {
  private buffer: Buffer = Buffer.alloc(0);
  private onMessage: MessageHandler;

  constructor(onMessage: MessageHandler) {
    this.onMessage = onMessage;
  }

  /**
   * Process incoming data chunks
   */
  async processChunk(chunk: Buffer): Promise<void> {
    this.buffer = Buffer.concat([this.buffer, chunk]);

    while (true) {
      const crlfDelimiterIndex = this.buffer.indexOf('\r\n\r\n');
      const lfDelimiterIndex = this.buffer.indexOf('\n\n');

      let headerEndIndex = -1;
      let delimiterLength = 0;

      // Handle both CRLF and LF line endings
      if (crlfDelimiterIndex !== -1 && (lfDelimiterIndex === -1 || crlfDelimiterIndex <= lfDelimiterIndex)) {
        headerEndIndex = crlfDelimiterIndex;
        delimiterLength = 4;
      } else if (lfDelimiterIndex !== -1) {
        headerEndIndex = lfDelimiterIndex;
        delimiterLength = 2;
      }

      if (headerEndIndex === -1) {
        // Need more data
        break;
      }

      // Parse Content-Length header
      const header = this.buffer.slice(0, headerEndIndex).toString('utf-8');
      const headers = header.split(/\r?\n/);
      let contentLength: number | undefined;

      for (const line of headers) {
        const match = line.match(/^Content-Length:\s*(\d+)/i);
        if (match) {
          contentLength = Number.parseInt(match[1], 10);
          break;
        }
      }

      if (contentLength === undefined || Number.isNaN(contentLength)) {
        console.error(`[JSON-RPC] Missing or invalid Content-Length header: ${header}`);
        this.buffer = this.buffer.slice(headerEndIndex + delimiterLength);
        continue;
      }

      const messageStartIndex = headerEndIndex + delimiterLength;
      const messageEndIndex = messageStartIndex + contentLength;

      if (this.buffer.length < messageEndIndex) {
        // Wait for the rest of the message
        break;
      }

      // Extract message
      const messageBuffer = this.buffer.slice(messageStartIndex, messageEndIndex);
      this.buffer = this.buffer.slice(messageEndIndex);

      if (messageBuffer.length > 0) {
        try {
          const message: JSONRPCMessage = JSON.parse(messageBuffer.toString('utf-8'));
          await this.onMessage(message);
        } catch (error) {
          console.error('[JSON-RPC] Failed to parse message:', error);
        }
      }
    }
  }

  /**
   * Clear the internal buffer
   */
  clear(): void {
    this.buffer = Buffer.alloc(0);
  }
}

/**
 * JSON-RPC message serializer with Content-Length framing
 */
export class JSONRPCSerializer {
  private writeQueue: Promise<void> = Promise.resolve();

  /**
   * Serialize and send a JSON-RPC message
   */
  async send(message: JSONRPCMessage, output: NodeJS.WritableStream): Promise<void> {
    // Queue writes to prevent message interleaving
    this.writeQueue = this.writeQueue.then(() => {
      return new Promise<void>((resolve) => {
        const payload = JSON.stringify(message);
        const contentLength = Buffer.byteLength(payload, 'utf-8');
        const header = `Content-Length: ${contentLength}\r\n\r\n`;
        const framedMessage = header + payload;

        output.write(framedMessage, () => {
          resolve();
        });
      });
    });

    await this.writeQueue;
  }

  /**
   * Send a request and wait for response
   */
  async request(
    method: string,
    params: any,
    output: NodeJS.WritableStream,
    timeout: number = 30000
  ): Promise<any> {
    const id = this.generateId();
    
    const message: JSONRPCMessage = {
      jsonrpc: '2.0',
      id,
      method,
      params,
    };

    await this.send(message, output);

    // Note: In production, this would need a response handler
    // For now, this is a placeholder for the request pattern
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`Request timeout: ${method}`));
      }, timeout);

      // Response handling would be implemented with an event emitter
      // that matches request IDs to response promises
    });
  }

  /**
   * Send a notification (no response expected)
   */
  async notify(method: string, params: any, output: NodeJS.WritableStream): Promise<void> {
    const message: JSONRPCMessage = {
      jsonrpc: '2.0',
      method,
      params,
    };

    await this.send(message, output);
  }

  /**
   * Send a response to a request
   */
  async respond(id: string | number, result: any, output: NodeJS.WritableStream): Promise<void> {
    const message: JSONRPCMessage = {
      jsonrpc: '2.0',
      id,
      result,
    };

    await this.send(message, output);
  }

  /**
   * Send an error response
   */
  async respondError(
    id: string | number,
    code: number,
    message: string,
    data?: any,
    output: NodeJS.WritableStream = process.stdout
  ): Promise<void> {
    const response: JSONRPCMessage = {
      jsonrpc: '2.0',
      id,
      error: {
        code,
        message,
        data,
      },
    };

    await this.send(response, output);
  }

  /**
   * Generate unique message ID
   */
  private generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  }
}

/**
 * JSON-RPC server that handles method routing
 */
export class JSONRPCServer {
  private parser: JSONRPCParser;
  private serializer: JSONRPCSerializer;
  private methods: Map<string, (params: any) => Promise<any>> = new Map();
  private output: NodeJS.WritableStream;

  constructor(
    input: NodeJS.ReadableStream,
    output: NodeJS.WritableStream
  ) {
    this.output = output;
    this.serializer = new JSONRPCSerializer();
    this.parser = new JSONRPCParser(this.handleMessage.bind(this));

    // Set up input stream
    input.on('data', (chunk: Buffer) => {
      this.parser.processChunk(chunk);
    });
  }

  /**
   * Register a method handler
   */
  registerMethod(method: string, handler: (params: any) => Promise<any>): void {
    this.methods.set(method, handler);
  }

  /**
   * Unregister a method handler
   */
  unregisterMethod(method: string): void {
    this.methods.delete(method);
  }

  /**
   * Send a notification to the client
   */
  async sendNotification(method: string, params: any): Promise<void> {
    await this.serializer.notify(method, params, this.output);
  }

  /**
   * Handle incoming messages
   */
  private async handleMessage(message: JSONRPCMessage): Promise<void> {
    // Handle requests
    if (message.method && message.id !== undefined) {
      const handler = this.methods.get(message.method);

      if (!handler) {
        await this.serializer.respondError(
          message.id,
          -32601,
          `Method not found: ${message.method}`,
          undefined,
          this.output
        );
        return;
      }

      try {
        const result = await handler(message.params);
        await this.serializer.respond(message.id, result, this.output);
      } catch (error) {
        await this.serializer.respondError(
          message.id,
          -32603,
          error instanceof Error ? error.message : 'Internal error',
          error,
          this.output
        );
      }
    }
    // Handle notifications (no response needed)
    else if (message.method && message.id === undefined) {
      const handler = this.methods.get(message.method);
      
      if (handler) {
        try {
          await handler(message.params);
        } catch (error) {
          console.error(`[JSON-RPC] Error handling notification ${message.method}:`, error);
        }
      }
    }
    // Handle responses (for outgoing requests)
    else if (message.id !== undefined && (message.result !== undefined || message.error !== undefined)) {
      // Response handling would be implemented here
      // This would typically involve resolving a pending promise
      console.error('[JSON-RPC] Received response:', message);
    }
  }
}

/**
 * Standard JSON-RPC error codes
 */
export const JSONRPCErrorCode = {
  PARSE_ERROR: -32700,
  INVALID_REQUEST: -32600,
  METHOD_NOT_FOUND: -32601,
  INVALID_PARAMS: -32602,
  INTERNAL_ERROR: -32603,
} as const;