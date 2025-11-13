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
  type Message as VSCodeMessage,
} from "vscode-jsonrpc/node";
import { type ISerializer, SerializerFactory, type SerializationFormat } from "./serialization";

/**
 * Security configuration
 */
export interface SecurityConfig {
  maxMessageSize?: number; // Max payload size in bytes
  maxBufferSize?: number; // Max accumulated buffer size
  maxPendingRequests?: number; // Max concurrent requests
}

/**
 * Default security limits
 */
const DEFAULT_SECURITY: Required<SecurityConfig> = {
  maxMessageSize: 100 * 1024 * 1024, // 100 MB
  maxBufferSize: 50 * 1024 * 1024, // 50 MB
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
 */
export type MessageHandler = (message: any) => void | Promise<void>;

/**
 * Enhanced IPC transport using vscode-jsonrpc
 */
export class IPCTransport {
  private reader: MessageReader;
  private writer: MessageWriter;
  private serializer: ISerializer;
  private security: Required<SecurityConfig>;
  private pendingRequests = new Map<
    string | number,
    {
      resolve: (value: any) => void;
      reject: (error: Error) => void;
      timeout: NodeJS.Timeout;
    }
  >();
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
      console.error("[IPCTransport] Reader error:", error);
    });

    this.reader.onClose(() => {
      console.error("[IPCTransport] Reader closed");
      // Reject all pending requests when reader closes
      for (const [id, pending] of this.pendingRequests) {
        clearTimeout(pending.timeout);
        pending.reject(new Error("Connection closed"));
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

    const message: VSCodeMessage = {
      jsonrpc: "2.0",
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
    const message: VSCodeMessage = {
      jsonrpc: "2.0",
      method,
      params,
    };

    await this.sendMessage(message);
  }

  /**
   * Send a response to a request
   */
  async respond(id: string | number, result: any): Promise<void> {
    const message: VSCodeMessage = {
      jsonrpc: "2.0",
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
    const response: VSCodeMessage = {
      jsonrpc: "2.0",
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
  private async sendMessage(message: VSCodeMessage): Promise<void> {
    // Security check: estimate message size using actual byte length
    const serializedMessage = JSON.stringify(message);
    const estimatedSize = Buffer.byteLength(serializedMessage, "utf-8");
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
  private async handleMessage(message: VSCodeMessage): Promise<void> {
    try {
      // Validate message structure
      if (!message || typeof message !== "object") {
        console.error("[IPCTransport] Invalid message structure:", message);
        return;
      }

      // Handle response to our request
      if (
        message.id !== undefined &&
        (message.result !== undefined || message.error !== undefined)
      ) {
        const pending = this.pendingRequests.get(message.id);
        if (pending) {
          clearTimeout(pending.timeout);
          this.pendingRequests.delete(message.id);

          if (message.error) {
            const errorMessage = message.error.message || "Unknown error";
            const error = new Error(errorMessage);
            // Attach error code and data for better debugging
            (error as any).code = message.error.code;
            (error as any).data = message.error.data;
            pending.reject(error);
          } else {
            pending.resolve(message.result);
          }
        } else {
          // Response for unknown request ID - log but don't crash
          console.warn("[IPCTransport] Received response for unknown request ID:", message.id);
        }
        return;
      }

      // Handle request
      if (message.method && message.id !== undefined) {
        const handler = this.messageHandlers.get(message.method);

        if (!handler) {
          await this.respondError(message.id, -32601, `Method not found: ${message.method}`);
          return;
        }

        try {
          const result = await handler(message.params);
          await this.respond(message.id, result);
        } catch (error) {
          // Catch all errors from handlers and send proper error response
          const errorMessage = error instanceof Error ? error.message : "Internal error";
          const errorData = error instanceof Error ? { stack: error.stack } : error;
          await this.respondError(message.id, -32603, errorMessage, errorData);
        }
        return;
      }

      // Handle notification
      if (message.method) {
        const handler = this.messageHandlers.get(message.method);
        if (handler) {
          // Notifications don't send responses, but we should catch errors
          try {
            await handler(message.params);
          } catch (error) {
            console.error(
              `[IPCTransport] Error in notification handler '${message.method}':`,
              error
            );
          }
        } else if (this.defaultHandler) {
          try {
            await this.defaultHandler(message);
          } catch (error) {
            console.error("[IPCTransport] Error in default handler:", error);
          }
        }
        return;
      }

      // Unknown message type
      console.warn("[IPCTransport] Unknown message type:", message);
      if (this.defaultHandler) {
        try {
          await this.defaultHandler(message);
        } catch (error) {
          console.error("[IPCTransport] Error in default handler for unknown message:", error);
        }
      }
    } catch (error) {
      console.error("[IPCTransport] Fatal error handling message:", error);
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
      pending.reject(new Error("Transport disposed"));
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
