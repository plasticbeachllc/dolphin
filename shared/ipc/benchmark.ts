/**
 * IPC Serialization Benchmark Suite
 *
 * Compares JSON vs MessagePack performance across different payload sizes
 *
 * Usage:
 *   bun run benchmark.ts
 *   node benchmark.ts
 */

import { JSONSerializer, MessagePackSerializer, MetricsCollector } from './serialization';

interface BenchmarkResult {
  format: string;
  payloadSize: number;
  iterations: number;
  avgSerializeMs: number;
  avgDeserializeMs: number;
  avgTotalMs: number;
  avgPayloadBytes: number;
  throughputMsgPerSec: number;
}

/**
 * Generate test payload of specified size
 */
function generatePayload(sizeBytes: number): any {
  const targetChars = Math.floor(sizeBytes / 2); // Rough estimate for JSON

  const data: any = {
    timestamp: Date.now(),
    type: 'benchmark_message',
    metadata: {
      version: '1.0',
      source: 'benchmark',
    },
    payload: '',
  };

  // Fill with random data to reach target size
  const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let payload = '';
  for (let i = 0; i < targetChars; i++) {
    payload += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  data.payload = payload;

  return data;
}

/**
 * Run benchmark for a specific serializer and payload
 */
function runBenchmark(
  serializerName: string,
  serializer: JSONSerializer | MessagePackSerializer,
  payload: any,
  iterations: number
): BenchmarkResult {
  const metrics = new MetricsCollector(iterations);

  let totalSerializeMs = 0;
  let totalDeserializeMs = 0;
  let totalBytes = 0;

  for (let i = 0; i < iterations; i++) {
    // Serialize
    const startSerialize = performance.now();
    const buffer = serializer.serialize(payload);
    const endSerialize = performance.now();

    // Deserialize
    const startDeserialize = performance.now();
    const decoded = serializer.deserialize(buffer);
    const endDeserialize = performance.now();

    totalSerializeMs += endSerialize - startSerialize;
    totalDeserializeMs += endDeserialize - startDeserialize;
    totalBytes += buffer.length;

    // Verify roundtrip
    if (JSON.stringify(decoded) !== JSON.stringify(payload)) {
      throw new Error('Roundtrip verification failed!');
    }
  }

  const avgSerializeMs = totalSerializeMs / iterations;
  const avgDeserializeMs = totalDeserializeMs / iterations;
  const avgTotalMs = avgSerializeMs + avgDeserializeMs;
  const avgPayloadBytes = totalBytes / iterations;
  const throughputMsgPerSec = 1000 / avgTotalMs;

  return {
    format: serializerName,
    payloadSize: JSON.stringify(payload).length,
    iterations,
    avgSerializeMs,
    avgDeserializeMs,
    avgTotalMs,
    avgPayloadBytes,
    throughputMsgPerSec,
  };
}

/**
 * Format results as table
 */
function printResults(results: BenchmarkResult[]) {
  console.log('\n📊 Serialization Benchmark Results\n');
  console.log('═'.repeat(120));
  console.log(
    'Format'.padEnd(12) +
    'Payload'.padEnd(12) +
    'Iterations'.padEnd(12) +
    'Serialize'.padEnd(14) +
    'Deserialize'.padEnd(14) +
    'Total'.padEnd(14) +
    'Size'.padEnd(12) +
    'Throughput'
  );
  console.log('═'.repeat(120));

  for (const result of results) {
    console.log(
      result.format.padEnd(12) +
      `${(result.payloadSize / 1024).toFixed(1)} KB`.padEnd(12) +
      result.iterations.toString().padEnd(12) +
      `${result.avgSerializeMs.toFixed(3)} ms`.padEnd(14) +
      `${result.avgDeserializeMs.toFixed(3)} ms`.padEnd(14) +
      `${result.avgTotalMs.toFixed(3)} ms`.padEnd(14) +
      `${result.avgPayloadBytes} B`.padEnd(12) +
      `${Math.floor(result.throughputMsgPerSec)} msg/s`
    );
  }

  console.log('═'.repeat(120) + '\n');
}

/**
 * Compare two results
 */
function printComparison(jsonResult: BenchmarkResult, msgpackResult: BenchmarkResult) {
  const serializeSpeedup = jsonResult.avgSerializeMs / msgpackResult.avgSerializeMs;
  const deserializeSpeedup = jsonResult.avgDeserializeMs / msgpackResult.avgDeserializeMs;
  const totalSpeedup = jsonResult.avgTotalMs / msgpackResult.avgTotalMs;
  const sizeReduction = ((jsonResult.avgPayloadBytes - msgpackResult.avgPayloadBytes) / jsonResult.avgPayloadBytes) * 100;
  const throughputIncrease = ((msgpackResult.throughputMsgPerSec - jsonResult.throughputMsgPerSec) / jsonResult.throughputMsgPerSec) * 100;

  console.log('📈 MessagePack vs JSON Comparison\n');
  console.log(`  Serialize:     ${serializeSpeedup.toFixed(2)}x faster`);
  console.log(`  Deserialize:   ${deserializeSpeedup.toFixed(2)}x faster`);
  console.log(`  Total:         ${totalSpeedup.toFixed(2)}x faster`);
  console.log(`  Size:          ${sizeReduction.toFixed(1)}% smaller`);
  console.log(`  Throughput:    ${throughputIncrease.toFixed(1)}% higher\n`);
}

/**
 * Main benchmark
 */
async function main() {
  console.log('🚀 Starting IPC Serialization Benchmarks...\n');

  const payloadSizes = [
    1 * 1024,      // 1 KB - small messages
    10 * 1024,     // 10 KB - medium messages
    100 * 1024,    // 100 KB - large messages
    1024 * 1024,   // 1 MB - very large messages
  ];

  const iterations = 1000;
  const allResults: BenchmarkResult[] = [];

  for (const size of payloadSizes) {
    console.log(`\n Testing ${(size / 1024).toFixed(0)} KB payload (${iterations} iterations)...`);

    const payload = generatePayload(size);
    const jsonSerializer = new JSONSerializer();
    const msgpackSerializer = new MessagePackSerializer();

    // Warmup
    for (let i = 0; i < 10; i++) {
      const buffer = jsonSerializer.serialize(payload);
      jsonSerializer.deserialize(buffer);
    }

    // Run benchmarks
    const jsonResult = runBenchmark('JSON', jsonSerializer, payload, iterations);
    const msgpackResult = runBenchmark('MessagePack', msgpackSerializer, payload, iterations);

    allResults.push(jsonResult, msgpackResult);

    printComparison(jsonResult, msgpackResult);
  }

  // Print all results
  printResults(allResults);

  // Summary
  console.log('✅ Benchmark complete!\n');
  console.log('💡 Recommendations:');
  console.log('   - Use JSON for small payloads (< 1 KB) or when debugging');
  console.log('   - Use MessagePack for high throughput or large payloads (> 10 KB)');
  console.log('   - Set DOLPHIN_IPC_FORMAT=msgpack to enable MessagePack\n');
}

// Run benchmark
main().catch(console.error);
