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
  type Message,
  type RequestMessage,
  type ResponseMessage,
  type NotificationMessage,
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
type VSCodeMessage = RequestMessage | ResponseMessage | NotificationMessage;

export type MessageHandler = (message: any) => any | Promise<any>;

/**
 * Enhanced IPC transport using vscode-jsonrpc
 */
const UNDEFINED_RESULT_SENTINEL = { __ipcUndefinedResult__: true } as const;

type IpcErrorPayload = {
  message?: string;
  code?: number;
  data?: any;
};

export class IPCTransport {
  private reader: MessageReader;
  private writer: MessageWriter;
  private serializer: ISerializer;
  private security: Required<SecurityConfig>;
  private pendingRequests = new Map<
    string | number,
    {
      resolve: (value: any) => void;
      timeout: NodeJS.Timeout;
    }
  >();
  private messageHandlers: Map<string, MessageHandler> = new Map();
  private defaultHandler?: MessageHandler;
  private enableMetrics: boolean;
  private requestIdCounter = 0;
  private disposed = false;

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
      this.rejectAllPendingRequests("Connection closed");
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
    if (this.disposed) {
      throw new Error("Transport disposed");
    }

    if (this.pendingRequests.size >= this.security.maxPendingRequests) {
      throw new Error(`Too many pending requests (max: ${this.security.maxPendingRequests})`);
    }

    const id = this.generateId();

    const message: RequestMessage = {
      jsonrpc: "2.0",
      id,
      method,
      params,
    };

    // Create pending promise
    const promise = new Promise<any>((resolve) => {
      const timer = setTimeout(() => {
        this.pendingRequests.delete(id);
        const timeoutPayload: IpcErrorPayload = {
          message: `Request timeout: ${method}`,
          code: RPCErrorCode.INTERNAL_ERROR,
          data: { __transportTimeout: true },
        };
        resolve({ __ipcError: timeoutPayload });
      }, timeout);

      this.pendingRequests.set(id, { resolve, timeout: timer });
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
      throw error instanceof Error ? error : new Error(String(error));
    }

    return promise.then((value) => {
      if (value && typeof value === "object" && "__ipcError" in value) {
        const payload = (value as any).__ipcError;
        const rejection =
          payload instanceof Error
            ? payload
            : {
                message: payload?.message ?? "Unknown error",
                code: payload?.code,
                data: payload?.data,
              };
        return Promise.reject(rejection);
      }
      return value;
    });
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
    const safeResult = result === undefined ? { ...UNDEFINED_RESULT_SENTINEL } : result;
    const message: VSCodeMessage = {
      jsonrpc: "2.0",
      id,
      result: safeResult,
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

    try {
      await this.writer.write(message);
    } catch (error) {
      if (
        error instanceof Error &&
        /stream was destroyed|connection (?:reset|closed)|write after/i.test(error.message)
      ) {
        throw new Error("Connection closed");
      }
      throw error instanceof Error ? error : new Error(String(error));
    }
  }

  /**
   * Handle incoming message
   */
  private async handleMessage(message: Message): Promise<void> {
    try {
      if (!message || typeof message !== "object") {
        console.error("[IPCTransport] Invalid message structure:", message);
        return;
      }

      if (this.isResponseMessage(message)) {
        const id = message.id;
        if (id === null) {
          console.warn("[IPCTransport] Received response with null id", message);
          return;
        }

        const pending = this.pendingRequests.get(id);
        if (pending) {
          clearTimeout(pending.timeout);
          this.pendingRequests.delete(id);

          if (message.error) {
            const errorMessage = message.error.message || "Unknown error";
            const errorPayload: IpcErrorPayload = {
              message: errorMessage,
              code: message.error.code,
              data: message.error.data,
            };
            pending.resolve({ __ipcError: errorPayload });
          } else {
            const result =
              message.result &&
              typeof message.result === "object" &&
              "__ipcUndefinedResult__" in (message.result as Record<string, unknown>)
                ? undefined
                : message.result;
            pending.resolve(result);
          }
        } else {
          console.warn("[IPCTransport] Received response for unknown request ID:", id);
        }
        return;
      }

      if (this.isRequestMessage(message)) {
        const id = message.id;
        if (id === null) {
          await this.respondError("unknown", RPCErrorCode.INVALID_REQUEST, "Request id is null");
          return;
        }

        const handler = this.messageHandlers.get(message.method);

        if (!handler) {
          await this.respondError(id, -32601, `Method not found: ${message.method}`);
          return;
        }

        try {
          const result = await handler(message.params);
          await this.respond(id, result);
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : "Internal error";
          const errorData = error instanceof Error ? { stack: error.stack } : error;
          await this.respondError(id, -32603, errorMessage, errorData);
        }
        return;
      }

      if (this.isNotificationMessage(message)) {
        const handler = this.messageHandlers.get(message.method);
        if (handler) {
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
    if (this.disposed) {
      return;
    }
    this.disposed = true;

    this.reader.dispose();
    this.writer.dispose();

    this.rejectAllPendingRequests("Transport disposed");
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

  private isResponseMessage(message: Message): message is ResponseMessage {
    return (
      typeof (message as any).id !== "undefined" &&
      ("result" in (message as any) || "error" in (message as any))
    );
  }

  private isRequestMessage(message: Message): message is RequestMessage {
    return typeof (message as any).id !== "undefined" && typeof (message as any).method === "string";
  }

  private isNotificationMessage(message: Message): message is NotificationMessage {
    return !("id" in (message as any)) && typeof (message as any).method === "string";
  }

  private rejectAllPendingRequests(message: string): void {
    for (const [id, pending] of this.pendingRequests.entries()) {
      clearTimeout(pending.timeout);
      this.pendingRequests.delete(id);
      const errorPayload: IpcErrorPayload = {
        message,
        code: RPCErrorCode.INTERNAL_ERROR,
        data: { __transportInternal: true, requestId: id },
      };
      pending.resolve({ __ipcError: errorPayload });
    }
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
