/**
 * Unit tests for JSON-RPC communication layer
 */

import { describe, it, expect, beforeEach, mock } from "bun:test";
import {
  JSONRPCParser,
  JSONRPCSerializer,
  JSONRPCServer,
  JSONRPCErrorCode,
} from "../../src/utils/json-rpc";
import type { JSONRPCMessage } from "../../src/types/index";

describe("JSONRPCParser", () => {
  let parser: JSONRPCParser;
  let receivedMessages: JSONRPCMessage[] = [];

  beforeEach(() => {
    receivedMessages = [];
    parser = new JSONRPCParser((message) => {
      receivedMessages.push(message);
    });
  });

  it("should parse a complete framed message", async () => {
    const message = { jsonrpc: "2.0", method: "test", params: {} };
    const payload = JSON.stringify(message);
    const contentLength = Buffer.byteLength(payload, "utf-8");
    const framedMessage = `Content-Length: ${contentLength}\r\n\r\n${payload}`;

    await parser.processChunk(Buffer.from(framedMessage));

    expect(receivedMessages.length).toBe(1);
    expect(receivedMessages[0].method).toBe("test");
  });

  it("should handle messages split across chunks", async () => {
    const message = { jsonrpc: "2.0", method: "test", params: {} };
    const payload = JSON.stringify(message);
    const contentLength = Buffer.byteLength(payload, "utf-8");
    const framedMessage = `Content-Length: ${contentLength}\r\n\r\n${payload}`;

    // Split the message into two chunks
    const buffer = Buffer.from(framedMessage);
    const midpoint = Math.floor(buffer.length / 2);
    const chunk1 = buffer.slice(0, midpoint);
    const chunk2 = buffer.slice(midpoint);

    await parser.processChunk(chunk1);
    expect(receivedMessages.length).toBe(0); // Not complete yet

    await parser.processChunk(chunk2);
    expect(receivedMessages.length).toBe(1);
  });

  it("should handle multiple messages in one chunk", async () => {
    const message1 = { jsonrpc: "2.0", id: 1, method: "test1" };
    const message2 = { jsonrpc: "2.0", id: 2, method: "test2" };

    const payload1 = JSON.stringify(message1);
    const payload2 = JSON.stringify(message2);

    const framedMessage1 = `Content-Length: ${Buffer.byteLength(payload1)}\r\n\r\n${payload1}`;
    const framedMessage2 = `Content-Length: ${Buffer.byteLength(payload2)}\r\n\r\n${payload2}`;

    await parser.processChunk(Buffer.from(framedMessage1 + framedMessage2));

    expect(receivedMessages.length).toBe(2);
    expect(receivedMessages[0].id).toBe(1);
    expect(receivedMessages[1].id).toBe(2);
  });

  it("should handle LF line endings", async () => {
    const message = { jsonrpc: "2.0", method: "test" };
    const payload = JSON.stringify(message);
    const contentLength = Buffer.byteLength(payload, "utf-8");
    const framedMessage = `Content-Length: ${contentLength}\n\n${payload}`;

    await parser.processChunk(Buffer.from(framedMessage));

    expect(receivedMessages.length).toBe(1);
  });

  it("should skip messages with missing Content-Length", async () => {
    const message = { jsonrpc: "2.0", method: "test" };
    const payload = JSON.stringify(message);
    const framedMessage = `\r\n\r\n${payload}`;

    await parser.processChunk(Buffer.from(framedMessage));

    expect(receivedMessages.length).toBe(0);
  });

  it("should clear buffer", () => {
    parser.clear();
    expect(() => parser.clear()).not.toThrow();
  });
});

describe("JSONRPCSerializer", () => {
  let serializer: JSONRPCSerializer;
  let outputBuffer: string[];

  beforeEach(() => {
    outputBuffer = [];
    serializer = new JSONRPCSerializer();
  });

  const createMockOutput = () =>
    ({
      write: (data: string, callback?: () => void) => {
        outputBuffer.push(data);
        if (callback) callback();
        return true;
      },
    }) as any;

  it("should serialize message with Content-Length header", async () => {
    const message: JSONRPCMessage = {
      jsonrpc: "2.0",
      id: 1,
      method: "test",
      params: { foo: "bar" },
    };

    const output = createMockOutput();
    await serializer.send(message, output);

    expect(outputBuffer.length).toBe(1);
    expect(outputBuffer[0]).toMatch(/^Content-Length: \d+\r\n\r\n/);
    expect(outputBuffer[0]).toContain('"method":"test"');
  });

  it("should send notification without id", async () => {
    const output = createMockOutput();
    await serializer.notify("notify_test", { data: "test" }, output);

    expect(outputBuffer.length).toBe(1);
    expect(outputBuffer[0]).toContain('"method":"notify_test"');
    expect(outputBuffer[0]).not.toContain('"id"');
  });

  it("should send response with result", async () => {
    const output = createMockOutput();
    await serializer.respond(1, { success: true }, output);

    expect(outputBuffer.length).toBe(1);
    expect(outputBuffer[0]).toContain('"id":1');
    expect(outputBuffer[0]).toContain('"result"');
    expect(outputBuffer[0]).toContain('"success":true');
  });

  it("should send error response", async () => {
    const output = createMockOutput();
    await serializer.respondError(1, -32601, "Method not found", undefined, output);

    expect(outputBuffer.length).toBe(1);
    expect(outputBuffer[0]).toContain('"error"');
    expect(outputBuffer[0]).toContain('"code":-32601');
    expect(outputBuffer[0]).toContain("Method not found");
  });

  it("should queue multiple sends to prevent interleaving", async () => {
    const output = createMockOutput();

    // Send multiple messages rapidly
    const promises = [
      serializer.notify("test1", {}, output),
      serializer.notify("test2", {}, output),
      serializer.notify("test3", {}, output),
    ];

    await Promise.all(promises);

    expect(outputBuffer.length).toBe(3);

    // Verify each message is complete
    for (const data of outputBuffer) {
      expect(data).toMatch(/^Content-Length: \d+\r\n\r\n/);
      const match = data.match(/Content-Length: (\d+)\r\n\r\n/);
      expect(match).not.toBeNull();
      const contentLength = parseInt(match![1]);
      const payload = data.substring(match![0].length);
      expect(Buffer.byteLength(payload, "utf-8")).toBe(contentLength);
    }
  });
});

describe("JSONRPCServer", () => {
  let server: JSONRPCServer;
  let _inputChunks: Buffer[] = [];
  let outputData: string[] = [];

  beforeEach(() => {
    _inputChunks = [];
    outputData = [];

    const mockInput = {
      on: (event: string, handler: (chunk: Buffer) => void) => {
        if (event === "data") {
          // Store handler for later triggering
          (mockInput as any)._dataHandler = handler;
        }
      },
      emit: (event: string, data: Buffer) => {
        if (event === "data" && (mockInput as any)._dataHandler) {
          (mockInput as any)._dataHandler(data);
        }
      },
    } as any;

    const mockOutput = {
      write: (data: string, callback?: () => void) => {
        outputData.push(data);
        if (callback) callback();
        return true;
      },
    } as any;

    server = new JSONRPCServer(mockInput, mockOutput);

    // Store mock input for triggering events
    (server as any)._mockInput = mockInput;
  });

  it("should register and call method handlers", async () => {
    const handler = mock(async (_params: any) => ({ success: true }));
    server.registerMethod("test_method", handler);

    const message: JSONRPCMessage = {
      jsonrpc: "2.0",
      id: 1,
      method: "test_method",
      params: { foo: "bar" },
    };

    const payload = JSON.stringify(message);
    const framedMessage = `Content-Length: ${Buffer.byteLength(payload)}\r\n\r\n${payload}`;

    (server as any)._mockInput.emit("data", Buffer.from(framedMessage));

    // Wait for async processing
    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(handler).toHaveBeenCalledWith({ foo: "bar" });
    expect(outputData.length).toBeGreaterThan(0);
    expect(outputData[0]).toContain('"result"');
  });

  it("should return error for unknown methods", async () => {
    const message: JSONRPCMessage = {
      jsonrpc: "2.0",
      id: 1,
      method: "unknown_method",
    };

    const payload = JSON.stringify(message);
    const framedMessage = `Content-Length: ${Buffer.byteLength(payload)}\r\n\r\n${payload}`;

    (server as any)._mockInput.emit("data", Buffer.from(framedMessage));

    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(outputData.length).toBeGreaterThan(0);
    expect(outputData[0]).toContain('"error"');
    expect(outputData[0]).toContain("Method not found");
  });

  it("should handle method errors gracefully", async () => {
    const handler = mock(async () => {
      throw new Error("Handler failed");
    });

    server.registerMethod("error_method", handler);

    const message: JSONRPCMessage = {
      jsonrpc: "2.0",
      id: 1,
      method: "error_method",
    };

    const payload = JSON.stringify(message);
    const framedMessage = `Content-Length: ${Buffer.byteLength(payload)}\r\n\r\n${payload}`;

    (server as any)._mockInput.emit("data", Buffer.from(framedMessage));

    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(outputData.length).toBeGreaterThan(0);
    expect(outputData[0]).toContain('"error"');
    expect(outputData[0]).toContain("Handler failed");
  });

  it("should unregister method handlers", async () => {
    const handler = mock(async () => ({ success: true }));

    server.registerMethod("temp_method", handler);
    server.unregisterMethod("temp_method");

    const message: JSONRPCMessage = {
      jsonrpc: "2.0",
      id: 1,
      method: "temp_method",
    };

    const payload = JSON.stringify(message);
    const framedMessage = `Content-Length: ${Buffer.byteLength(payload)}\r\n\r\n${payload}`;

    (server as any)._mockInput.emit("data", Buffer.from(framedMessage));

    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(handler).not.toHaveBeenCalled();
    expect(outputData[0]).toContain("Method not found");
  });

  it("should send notifications to client", async () => {
    await server.sendNotification("client_notification", { message: "hello" });

    expect(outputData.length).toBe(1);
    expect(outputData[0]).toContain('"method":"client_notification"');
    expect(outputData[0]).not.toContain('"id"');
  });
});

describe("JSONRPCErrorCode", () => {
  it("should define standard error codes", () => {
    expect(JSONRPCErrorCode.PARSE_ERROR).toBe(-32700);
    expect(JSONRPCErrorCode.INVALID_REQUEST).toBe(-32600);
    expect(JSONRPCErrorCode.METHOD_NOT_FOUND).toBe(-32601);
    expect(JSONRPCErrorCode.INVALID_PARAMS).toBe(-32602);
    expect(JSONRPCErrorCode.INTERNAL_ERROR).toBe(-32603);
  });
});
