/**
 * Dolphin IPC Module
 *
 * Provides robust, performant IPC communication with:
 * - vscode-jsonrpc for message framing (battle-tested LSP protocol)
 * - Pluggable serialization (JSON/MessagePack)
 * - Security hardening (payload limits, buffer limits)
 * - Performance monitoring
 *
 * Usage:
 *
 * ```typescript
 * import { IPCTransport } from '@dolphin/shared/ipc';
 *
 * // Create transport
 * const transport = new IPCTransport({
 *   input: process.stdin,
 *   output: process.stdout,
 *   serializationFormat: 'json', // or 'msgpack'
 * });
 *
 * // Register method handlers
 * transport.onMethod('my_method', async (params) => {
 *   return { result: 'success' };
 * });
 *
 * // Send requests
 * const result = await transport.request('remote_method', { arg: 'value' });
 *
 * // Send notifications
 * await transport.notify('event', { data: 'something happened' });
 * ```
 */

export {
  IPCTransport,
  type TransportConfig,
  type SecurityConfig,
  type MessageHandler,
  RPCErrorCode,
} from "./transport";

export {
  SerializerFactory,
  JSONSerializer,
  MessagePackSerializer,
  MetricsCollector,
  type ISerializer,
  type SerializationFormat,
  type SerializationMetrics,
} from "./serialization";
