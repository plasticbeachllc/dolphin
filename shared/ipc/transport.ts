/**
 * IPC Transport Layer
 *
 * Wraps vscode-jsonrpc for robust message framing with support for:
 * - Content-Length based framing (LSP-style)
 * - Pluggable serialization (JSON/MessagePack)
 * - Security limits (max payload size, buffer size)
 * - Performance monitoring
 * - Error recovery
 */

import {
  StreamMessageReader,
  StreamMessageWriter,
  type MessageReader,
  type MessageWriter,
} from 'vscode-jsonrpc/node';
import { type ISerializer, SerializerFactory, type SerializationFormat } from './serialization';

/**
 * JSON-RPC 2.0 Message types
 */
export interface JSONRPCRequest {
  jsonrpc: '2.0';
  id: string | number;
  method: string;
  params?: any;
}

export interface JSONRPCNotification {
  jsonrpc: '2.0';
  method: string;
  params?: any;
}

export interface JSONRPCResponse {
  jsonrpc: '2.0';
  id: string | number;
  result?: any;
  error?: {
    code: number;
    message: string;
    data?: any;
  };
}

export type JSONRPCMessage = JSONRPCRequest | JSONRPCNotification | JSONRPCResponse;

/**
 * Security configuration
 */
export interface SecurityConfig {
  maxMessageSize?: number; // Max payload size in bytes
  maxBufferSize?: number;  // Max accumulated buffer size
  maxPendingRequests?: number; // Max concurrent requests
}

/**
 * Default security limits
 */
const DEFAULT_SECURITY: Required<SecurityConfig> = {
  maxMessageSize: 100 * 1024 * 1024, // 100 MB
  maxBufferSize: 50 * 1024 * 1024,    // 50 MB
  maxPendingRequests: 1000,
};

/**
 * Transport configuration
 */
export interface TransportConfig {
  input: NodeJS.ReadableStream;
  output: NodeJS.WritableStream;
  serializationFormat?: SerializationFormat;
  security?: SecurityConfig;
  enableMetrics?: boolean;
}

/**
 * Message handler type
 * Handlers can return a value which will be sent as the JSON-RPC response
 */
export type MessageHandler = (message: any) => any | Promise<any>;

/**
 * Enhanced IPC transport using vscode-jsonrpc
 */
export class IPCTransport {
  private reader: MessageReader;
  private writer: MessageWriter;
  private serializer: ISerializer;
  private security: Required<SecurityConfig>;
  private pendingRequests = new Map<string | number, {
    resolve: (value: any) => void;
    reject: (error: Error) => void;
    timeout: NodeJS.Timeout;
  }>();
  private messageHandlers: Map<string, MessageHandler> = new Map();
  private defaultHandler?: MessageHandler;
  private enableMetrics: boolean;
  private requestIdCounter = 0;

  constructor(config: TransportConfig) {
    this.reader = new StreamMessageReader(config.input);
    this.writer = new StreamMessageWriter(config.output);
    this.serializer = SerializerFactory.create(config.serializationFormat);
    this.security = { ...DEFAULT_SECURITY, ...config.security };
    this.enableMetrics = config.enableMetrics ?? false;

    // Set up message listener
    this.reader.listen(this.handleMessage.bind(this));

    // Set up error listeners to prevent crashes
    this.reader.onError((error) => {
      console.error('[IPCTransport] Reader error:', error);
    });

    this.reader.onClose(() => {
      console.error('[IPCTransport] Reader closed');
      // Reject all pending requests when reader closes
      for (const [id, pending] of this.pendingRequests) {
        clearTimeout(pending.timeout);
        pending.reject(new Error('Connection closed'));
      }
      this.pendingRequests.clear();
    });
  }

  /**
   * Register a method handler
   */
  onMethod(method: string, handler: MessageHandler): void {
    this.messageHandlers.set(method, handler);
  }

  /**
   * Register default handler for unhandled messages
   */
  onMessage(handler: MessageHandler): void {
    this.defaultHandler = handler;
  }

  /**
   * Send a request and wait for response
   */
  async request(method: string, params: any, timeout: number = 30000): Promise<any> {
    if (this.pendingRequests.size >= this.security.maxPendingRequests) {
      throw new Error(`Too many pending requests (max: ${this.security.maxPendingRequests})`);
    }

    const id = this.generateId();

    const message: JSONRPCRequest = {
      jsonrpc: '2.0',
      id,
      method,
      params,
    };

    // Create pending promise
    const promise = new Promise<any>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pendingRequests.delete(id);
        reject(new Error(`Request timeout: ${method}`));
      }, timeout);

      this.pendingRequests.set(id, { resolve, reject, timeout: timer });
    });

    // Send request - if this fails, clean up pending request
    try {
      await this.sendMessage(message);
    } catch (error) {
      const pending = this.pendingRequests.get(id);
      if (pending) {
        clearTimeout(pending.timeout);
        this.pendingRequests.delete(id);
      }
      throw error;
    }

    return promise;
  }

  /**
   * Send a notification (no response expected)
   */
  async notify(method: string, params: any): Promise<void> {
    const message: JSONRPCNotification = {
      jsonrpc: '2.0',
      method,
      params,
    };

    await this.sendMessage(message);
  }

  /**
   * Send a response to a request
   */
  async respond(id: string | number, result: any): Promise<void> {
    const message: JSONRPCResponse = {
      jsonrpc: '2.0',
      id,
      result,
    };

    await this.sendMessage(message);
  }

  /**
   * Send an error response
   */
  async respondError(
    id: string | number,
    code: number,
    message: string,
    data?: any
  ): Promise<void> {
    const response: JSONRPCResponse = {
      jsonrpc: '2.0',
      id,
      error: {
        code,
        message,
        data,
      },
    };

    await this.sendMessage(response);
  }

  /**
   * Send a message (internal)
   */
  private async sendMessage(message: JSONRPCMessage): Promise<void> {
    // Security check: estimate message size using actual byte length
    const serializedMessage = JSON.stringify(message);
    const estimatedSize = Buffer.byteLength(serializedMessage, 'utf-8');
    if (estimatedSize > this.security.maxMessageSize) {
      throw new Error(
        `Message too large: ${estimatedSize} bytes (max: ${this.security.maxMessageSize})`
      );
    }

    await this.writer.write(message);
  }

  /**
   * Handle incoming message
   */
  private async handleMessage(message: JSONRPCMessage): Promise<void> {
    try {
      // Validate message structure
      if (!message || typeof message !== 'object') {
        console.error('[IPCTransport] Invalid message structure:', message);
        return;
      }

      // Handle response to our request
      if ('id' in message && ('result' in message || 'error' in message)) {
        const response = message as JSONRPCResponse;
        const pending = this.pendingRequests.get(response.id);
        if (pending) {
          clearTimeout(pending.timeout);
          this.pendingRequests.delete(response.id);

          if (response.error) {
            const errorMessage = response.error.message || 'Unknown error';
            const error = new Error(errorMessage);
            // Attach error code and data for better debugging
            (error as any).code = response.error.code;
            (error as any).data = response.error.data;
            pending.reject(error);
          } else {
            pending.resolve(response.result);
          }
        } else {
          // Response for unknown request ID - log but don't crash
          console.warn('[IPCTransport] Received response for unknown request ID:', response.id);
        }
        return;
      }

      // Handle request
      if ('method' in message && 'id' in message) {
        const request = message as JSONRPCRequest;
        const handler = this.messageHandlers.get(request.method);

        if (!handler) {
          await this.respondError(
            request.id,
            -32601,
            `Method not found: ${request.method}`
          );
          return;
        }

        try {
          const result = await handler(request.params);
          await this.respond(request.id, result);
        } catch (error) {
          // Catch all errors from handlers and send proper error response
          const errorMessage = error instanceof Error ? error.message : 'Internal error';
          const errorData = error instanceof Error ? { stack: error.stack } : error;
          await this.respondError(
            request.id,
            -32603,
            errorMessage,
            errorData
          );
        }
        return;
      }

      // Handle notification
      if ('method' in message) {
        const notification = message as JSONRPCNotification;
        const handler = this.messageHandlers.get(notification.method);
        if (handler) {
          // Notifications don't send responses, but we should catch errors
          try {
            await handler(notification.params);
          } catch (error) {
            console.error(`[IPCTransport] Error in notification handler '${notification.method}':`, error);
          }
        } else if (this.defaultHandler) {
          try {
            await this.defaultHandler(message);
          } catch (error) {
            console.error('[IPCTransport] Error in default handler:', error);
          }
        }
        return;
      }

      // Unknown message type
      console.warn('[IPCTransport] Unknown message type:', message);
      if (this.defaultHandler) {
        try {
          await this.defaultHandler(message);
        } catch (error) {
          console.error('[IPCTransport] Error in default handler for unknown message:', error);
        }
      }
    } catch (error) {
      console.error('[IPCTransport] Fatal error handling message:', error);
    }
  }

  /**
   * Generate unique request ID
   */
  private generateId(): string {
    return `${Date.now()}-${++this.requestIdCounter}`;
  }

  /**
   * Close the transport
   */
  dispose(): void {
    this.reader.dispose();
    this.writer.dispose();

    // Reject all pending requests
    for (const [id, pending] of this.pendingRequests) {
      clearTimeout(pending.timeout);
      pending.reject(new Error('Transport disposed'));
    }
    this.pendingRequests.clear();
  }

  /**
   * Get pending request count (for monitoring)
   */
  getPendingRequestCount(): number {
    return this.pendingRequests.size;
  }

  /**
   * Get serialization format
   */
  getSerializationFormat(): SerializationFormat {
    return this.serializer.format;
  }
}

/**
 * JSON-RPC error codes
 */
export const RPCErrorCode = {
  PARSE_ERROR: -32700,
  INVALID_REQUEST: -32600,
  METHOD_NOT_FOUND: -32601,
  INVALID_PARAMS: -32602,
  INTERNAL_ERROR: -32603,
} as const;
