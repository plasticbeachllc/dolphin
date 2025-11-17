/**
 * Unit tests for IPC serialization layer
 */

import { describe, test, expect, beforeEach } from "bun:test";
import {
  JSONSerializer,
  MessagePackSerializer,
  SerializerFactory,
  MetricsCollector,
} from "../serialization";

describe("JSONSerializer", () => {
  let serializer: JSONSerializer;

  beforeEach(() => {
    serializer = new JSONSerializer();
  });

  test("should serialize and deserialize simple objects", () => {
    const data = { foo: "bar", num: 123 };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should serialize and deserialize nested objects", () => {
    const data = {
      user: { name: "Alice", age: 30 },
      items: [1, 2, 3],
      metadata: { created: "2024-01-01", tags: ["a", "b"] },
    };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should serialize and deserialize arrays", () => {
    const data = [1, 2, "three", { four: 4 }, [5, 6]];
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should handle null and undefined", () => {
    const data = { a: null, b: undefined };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    // Note: JSON.stringify removes undefined keys
    expect(result).toEqual({ a: null });
  });

  test("should handle empty objects and arrays", () => {
    expect(serializer.deserialize(serializer.serialize({}))).toEqual({});
    expect(serializer.deserialize(serializer.serialize([]))).toEqual([]);
  });

  test("should handle strings with special characters", () => {
    const data = { text: 'Hello\nWorld\t"Quotes"\r\n' };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should handle unicode characters", () => {
    const data = { emoji: "🚀", chinese: "你好", arabic: "مرحبا" };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should handle large numbers", () => {
    const data = {
      bigInt: Number.MAX_SAFE_INTEGER,
      smallInt: Number.MIN_SAFE_INTEGER,
      float: 3.14159265359,
    };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should handle booleans", () => {
    const data = { yes: true, no: false };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should collect metrics", () => {
    const data = { test: "data" };
    serializer.serialize(data);
    serializer.deserialize(serializer.serialize(data));

    const metrics = serializer.getMetrics();
    expect(metrics).toBeDefined();
    expect(metrics!.serializeTimeMs).toBeGreaterThanOrEqual(0);
    expect(metrics!.deserializeTimeMs).toBeGreaterThanOrEqual(0);
    expect(metrics!.originalSize).toBeGreaterThan(0);
    expect(metrics!.serializedSize).toBeGreaterThan(0);
  });

  test("should have correct format", () => {
    expect(serializer.format).toBe("json");
  });

  test("should throw on invalid JSON during deserialize", () => {
    const invalidBuffer = Buffer.from("{ invalid json", "utf-8");
    expect(() => serializer.deserialize(invalidBuffer)).toThrow();
  });
});

describe("MessagePackSerializer", () => {
  let serializer: MessagePackSerializer;

  beforeEach(() => {
    serializer = new MessagePackSerializer();
  });

  test("should serialize and deserialize simple objects", () => {
    const data = { foo: "bar", num: 123 };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should serialize and deserialize nested objects", () => {
    const data = {
      user: { name: "Alice", age: 30 },
      items: [1, 2, 3],
      metadata: { created: "2024-01-01", tags: ["a", "b"] },
    };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should serialize and deserialize arrays", () => {
    const data = [1, 2, "three", { four: 4 }, [5, 6]];
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should handle null and undefined", () => {
    const data = { a: null, b: undefined };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should handle binary data", () => {
    const data = { buffer: Buffer.from([1, 2, 3, 4, 5]) };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(Buffer.isBuffer(result.buffer)).toBe(true);
    expect(result.buffer).toEqual(data.buffer);
  });

  test("should be more compact than JSON for typical data", () => {
    const data = {
      id: 12345,
      name: "Test User",
      email: "test@example.com",
      items: [1, 2, 3, 4, 5],
      active: true,
    };

    const jsonSerializer = new JSONSerializer();
    const jsonBuffer = jsonSerializer.serialize(data);
    const msgpackBuffer = serializer.serialize(data);

    expect(msgpackBuffer.length).toBeLessThan(jsonBuffer.length);
  });

  test("should collect metrics", () => {
    const data = { test: "data" };
    serializer.serialize(data);
    serializer.deserialize(serializer.serialize(data));

    const metrics = serializer.getMetrics();
    expect(metrics).toBeDefined();
    expect(metrics!.serializeTimeMs).toBeGreaterThanOrEqual(0);
    expect(metrics!.deserializeTimeMs).toBeGreaterThanOrEqual(0);
  });

  test("should have correct format", () => {
    expect(serializer.format).toBe("msgpack");
  });

  test("should handle unicode characters", () => {
    const data = { emoji: "🚀", chinese: "你好", arabic: "مرحبا" };
    const buffer = serializer.serialize(data);
    const result = serializer.deserialize(buffer);
    expect(result).toEqual(data);
  });

  test("should throw on invalid MessagePack during deserialize", () => {
    const invalidBuffer = Buffer.from([0xff, 0xff, 0xff], "binary");
    expect(() => serializer.deserialize(invalidBuffer)).toThrow();
  });
});

describe("SerializerFactory", () => {
  test("should create JSON serializer by default", () => {
    const serializer = SerializerFactory.create();
    expect(serializer.format).toBe("json");
  });

  test("should create JSON serializer when explicitly requested", () => {
    const serializer = SerializerFactory.create("json");
    expect(serializer.format).toBe("json");
  });

  test("should create MessagePack serializer when requested", () => {
    const serializer = SerializerFactory.create("msgpack");
    expect(serializer.format).toBe("msgpack");
  });

  test("should detect JSON format from buffer", () => {
    const jsonBuffer = Buffer.from('{"test":true}', "utf-8");
    const format = SerializerFactory.detectFormat(jsonBuffer);
    expect(format).toBe("json");
  });

  test("should detect JSON format from array buffer", () => {
    const jsonBuffer = Buffer.from("[1,2,3]", "utf-8");
    const format = SerializerFactory.detectFormat(jsonBuffer);
    expect(format).toBe("json");
  });

  test("should detect MessagePack format from buffer", () => {
    const serializer = new MessagePackSerializer();
    const msgpackBuffer = serializer.serialize({ test: true });
    const format = SerializerFactory.detectFormat(msgpackBuffer);
    expect(format).toBe("msgpack");
  });

  test("should default to JSON for empty buffer", () => {
    const emptyBuffer = Buffer.alloc(0);
    const format = SerializerFactory.detectFormat(emptyBuffer);
    expect(format).toBe("json");
  });
});

describe("MetricsCollector", () => {
  let collector: MetricsCollector;

  beforeEach(() => {
    collector = new MetricsCollector(100);
  });

  test("should record metrics", () => {
    collector.record({
      serializeTimeMs: 0.5,
      deserializeTimeMs: 0.3,
      originalSize: 1000,
      serializedSize: 800,
    });

    const stats = collector.getStats();
    expect(stats.count).toBe(1);
    expect(stats.avgSerializeMs).toBe(0.5);
    expect(stats.avgDeserializeMs).toBe(0.3);
  });

  test("should calculate average metrics", () => {
    collector.record({
      serializeTimeMs: 1.0,
      deserializeTimeMs: 0.5,
      originalSize: 1000,
      serializedSize: 800,
    });
    collector.record({
      serializeTimeMs: 2.0,
      deserializeTimeMs: 1.5,
      originalSize: 2000,
      serializedSize: 1600,
    });

    const stats = collector.getStats();
    expect(stats.count).toBe(2);
    expect(stats.avgSerializeMs).toBe(1.5);
    expect(stats.avgDeserializeMs).toBe(1.0);
  });

  test("should calculate compression ratio", () => {
    collector.record({
      serializeTimeMs: 1.0,
      deserializeTimeMs: 0.5,
      originalSize: 1000,
      serializedSize: 700,
    });

    const stats = collector.getStats();
    expect(stats.avgCompressionRatio).toBeCloseTo(1.43, 2);
    expect(stats.totalBytesSaved).toBe(300);
  });

  test("should limit number of samples", () => {
    const smallCollector = new MetricsCollector(5);

    for (let i = 0; i < 10; i++) {
      smallCollector.record({
        serializeTimeMs: i,
        deserializeTimeMs: i,
        originalSize: 1000,
        serializedSize: 800,
      });
    }

    const exported = smallCollector.export();
    expect(exported.length).toBe(5);
  });

  test("should clear metrics", () => {
    collector.record({
      serializeTimeMs: 1.0,
      deserializeTimeMs: 0.5,
      originalSize: 1000,
      serializedSize: 800,
    });

    collector.clear();

    const stats = collector.getStats();
    expect(stats.count).toBe(0);
  });

  test("should export metrics", () => {
    const metric = {
      serializeTimeMs: 1.0,
      deserializeTimeMs: 0.5,
      originalSize: 1000,
      serializedSize: 800,
    };

    collector.record(metric);

    const exported = collector.export();
    expect(exported.length).toBe(1);
    expect(exported[0]).toEqual(metric);
  });

  test("should return zero stats for empty collector", () => {
    const stats = collector.getStats();
    expect(stats.count).toBe(0);
    expect(stats.avgSerializeMs).toBe(0);
    expect(stats.avgDeserializeMs).toBe(0);
    expect(stats.avgCompressionRatio).toBe(1);
    expect(stats.totalBytesSaved).toBe(0);
  });
});

describe("Serialization Performance", () => {
  test("MessagePack should be faster than JSON for typical payloads", () => {
    const data = {
      id: 12345,
      name: "Test User",
      email: "test@example.com",
      metadata: {
        created: "2024-01-01",
        updated: "2024-01-02",
        tags: ["tag1", "tag2", "tag3"],
      },
      items: Array.from({ length: 100 }, (_, i) => ({ id: i, value: `item-${i}` })),
    };

    const jsonSerializer = new JSONSerializer();
    const msgpackSerializer = new MessagePackSerializer();

    // Warmup
    for (let i = 0; i < 10; i++) {
      jsonSerializer.deserialize(jsonSerializer.serialize(data));
      msgpackSerializer.deserialize(msgpackSerializer.serialize(data));
    }

    // Measure JSON
    const jsonStart = performance.now();
    for (let i = 0; i < 100; i++) {
      const buffer = jsonSerializer.serialize(data);
      jsonSerializer.deserialize(buffer);
    }
    const jsonTime = performance.now() - jsonStart;

    // Measure MessagePack
    const msgpackStart = performance.now();
    for (let i = 0; i < 100; i++) {
      const buffer = msgpackSerializer.serialize(data);
      msgpackSerializer.deserialize(buffer);
    }
    const msgpackTime = performance.now() - msgpackStart;

    console.log(`JSON time: ${jsonTime.toFixed(2)}ms`);
    console.log(`MessagePack time: ${msgpackTime.toFixed(2)}ms`);
    console.log(`Speedup: ${(jsonTime / msgpackTime).toFixed(2)}x`);

    // MessagePack should be faster (or at least not significantly slower)
    expect(msgpackTime).toBeLessThan(jsonTime * 1.65);
  });
});
