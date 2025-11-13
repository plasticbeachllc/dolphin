/**
 * IPC Serialization Abstraction Layer
 *
 * Provides a pluggable serialization interface that supports:
 * - JSON (default, human-readable, debugging-friendly)
 * - MessagePack (binary, faster, smaller payloads)
 *
 * Design goals:
 * 1. Zero-cost abstraction for JSON mode (direct pass-through)
 * 2. Easy protocol negotiation via environment variable
 * 3. Type-safe serialization/deserialization
 * 4. Performance monitoring via metrics
 */

import msgpack from 'msgpack5';

/**
 * Serialization format
 */
export type SerializationFormat = 'json' | 'msgpack';

/**
 * Serialization metrics for benchmarking
 */
export interface SerializationMetrics {
  serializeTimeMs: number;
  deserializeTimeMs: number;
  originalSize: number;
  serializedSize: number;
}

/**
 * Serialization strategy interface
 */
export interface ISerializer {
  readonly format: SerializationFormat;

  /**
   * Serialize data to bytes
   */
  serialize(data: any): Buffer;

  /**
   * Deserialize bytes to data
   */
  deserialize(buffer: Buffer): any;

  /**
   * Get serialization metrics (optional, for benchmarking)
   */
  getMetrics?(): SerializationMetrics | null;
}

/**
 * JSON serializer (default)
 */
export class JSONSerializer implements ISerializer {
  readonly format: SerializationFormat = 'json';
  private lastMetrics: SerializationMetrics | null = null;

  serialize(data: any): Buffer {
    const startTime = performance.now();
    const json = JSON.stringify(data);
    const buffer = Buffer.from(json, 'utf-8');
    const endTime = performance.now();

    this.lastMetrics = {
      serializeTimeMs: endTime - startTime,
      deserializeTimeMs: 0,
      originalSize: Buffer.byteLength(JSON.stringify(data), 'utf-8'),
      serializedSize: buffer.length,
    };

    return buffer;
  }

  deserialize(buffer: Buffer): any {
    const startTime = performance.now();
    const json = buffer.toString('utf-8');
    const data = JSON.parse(json);
    const endTime = performance.now();

    if (this.lastMetrics) {
      this.lastMetrics.deserializeTimeMs = endTime - startTime;
    }

    return data;
  }

  getMetrics(): SerializationMetrics | null {
    return this.lastMetrics;
  }
}

/**
 * MessagePack serializer (binary, faster, smaller)
 */
export class MessagePackSerializer implements ISerializer {
  readonly format: SerializationFormat = 'msgpack';
  private codec = msgpack();
  private lastMetrics: SerializationMetrics | null = null;

  serialize(data: any): Buffer {
    const startTime = performance.now();
    const buffer = this.codec.encode(data);
    const endTime = performance.now();

    this.lastMetrics = {
      serializeTimeMs: endTime - startTime,
      deserializeTimeMs: 0,
      originalSize: Buffer.byteLength(JSON.stringify(data), 'utf-8'), // For comparison
      serializedSize: buffer.length,
    };

    return buffer;
  }

  deserialize(buffer: Buffer): any {
    const startTime = performance.now();
    const data = this.codec.decode(buffer);
    const endTime = performance.now();

    if (this.lastMetrics) {
      this.lastMetrics.deserializeTimeMs = endTime - startTime;
    }

    return data;
  }

  getMetrics(): SerializationMetrics | null {
    return this.lastMetrics;
  }
}

/**
 * Serializer factory - creates appropriate serializer based on config
 */
export class SerializerFactory {
  /**
   * Create serializer from environment variable or explicit format
   */
  static create(format?: SerializationFormat): ISerializer {
    const selectedFormat = format ||
      (process.env.DOLPHIN_IPC_FORMAT as SerializationFormat) ||
      'json';

    switch (selectedFormat) {
      case 'msgpack':
        return new MessagePackSerializer();
      case 'json':
      default:
        return new JSONSerializer();
    }
  }

  /**
   * Detect format from buffer (useful for auto-detection)
   */
  static detectFormat(buffer: Buffer): SerializationFormat {
    // MessagePack buffers typically start with specific bytes
    // JSON starts with printable ASCII ('{', '[', '"', digits, etc.)
    if (buffer.length === 0) {
      return 'json'; // Default
    }

    const firstByte = buffer[0];

    // JSON typically starts with: '{' (123), '[' (91), '"' (34), or digits
    if (
      firstByte === 123 || // {
      firstByte === 91 ||  // [
      firstByte === 34 ||  // "
      (firstByte >= 48 && firstByte <= 57) // 0-9
    ) {
      return 'json';
    }

    // MessagePack starts with specific marker bytes
    // See: https://github.com/msgpack/msgpack/blob/master/spec.md
    return 'msgpack';
  }
}

/**
 * Serialization metrics collector for benchmarking
 */
export class MetricsCollector {
  private metrics: SerializationMetrics[] = [];
  private maxSamples: number;

  constructor(maxSamples: number = 1000) {
    this.maxSamples = maxSamples;
  }

  /**
   * Record a serialization metric
   */
  record(metric: SerializationMetrics): void {
    this.metrics.push(metric);

    // Keep only last N samples
    if (this.metrics.length > this.maxSamples) {
      this.metrics.shift();
    }
  }

  /**
   * Get aggregate statistics
   */
  getStats(): {
    count: number;
    avgSerializeMs: number;
    avgDeserializeMs: number;
    avgCompressionRatio: number;
    totalBytesSaved: number;
  } {
    if (this.metrics.length === 0) {
      return {
        count: 0,
        avgSerializeMs: 0,
        avgDeserializeMs: 0,
        avgCompressionRatio: 1,
        totalBytesSaved: 0,
      };
    }

    const sum = this.metrics.reduce(
      (acc, m) => ({
        serializeMs: acc.serializeMs + m.serializeTimeMs,
        deserializeMs: acc.deserializeMs + m.deserializeTimeMs,
        originalSize: acc.originalSize + m.originalSize,
        serializedSize: acc.serializedSize + m.serializedSize,
      }),
      { serializeMs: 0, deserializeMs: 0, originalSize: 0, serializedSize: 0 }
    );

    return {
      count: this.metrics.length,
      avgSerializeMs: sum.serializeMs / this.metrics.length,
      avgDeserializeMs: sum.deserializeMs / this.metrics.length,
      avgCompressionRatio: sum.originalSize / sum.serializedSize,
      totalBytesSaved: sum.originalSize - sum.serializedSize,
    };
  }

  /**
   * Clear metrics
   */
  clear(): void {
    this.metrics = [];
  }

  /**
   * Export metrics for analysis
   */
  export(): SerializationMetrics[] {
    return [...this.metrics];
  }
}
