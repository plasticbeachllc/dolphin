/**
 * Stress and load tests for IPC layer
 */

import { describe, test, expect } from "bun:test";
import { IPCTransport, type SecurityConfig } from "../transport";
import { PassThrough } from "stream";

type TransportPairOptions = {
  clientSecurity?: SecurityConfig;
  serverSecurity?: SecurityConfig;
};

function createTransportPair(options: TransportPairOptions = {}) {
  const clientToServer = new PassThrough();
  const serverToClient = new PassThrough();

  const client = new IPCTransport({
    input: serverToClient,
    output: clientToServer,
    security: options.clientSecurity,
  });

  const server = new IPCTransport({
    input: clientToServer,
    output: serverToClient,
    security: options.serverSecurity,
  });

  return { client, server };
}

describe("Stress Tests", () => {
  test("should handle 10,000 concurrent requests without memory leaks", async () => {
    const count = 10000;
    const securityOverride: SecurityConfig = { maxPendingRequests: count * 2 };
    const { client, server } = createTransportPair({
      clientSecurity: securityOverride,
      serverSecurity: securityOverride,
    });

    server.onMethod("process", async (params) => {
      return { result: params.value * 2 };
    });

    const initialMemory = process.memoryUsage().heapUsed;

    const results = await Promise.all(
      Array.from({ length: count }, (_, i) => client.request("process", { value: i }))
    );

    expect(results).toHaveLength(count);
    expect(results[0]).toEqual({ result: 0 });
    expect(results[count - 1]).toEqual({ result: (count - 1) * 2 });

    // Check for memory leaks
    const finalMemory = process.memoryUsage().heapUsed;
    const memoryGrowth = finalMemory - initialMemory;
    const memoryGrowthMB = memoryGrowth / 1024 / 1024;

    console.log(`Memory growth: ${memoryGrowthMB.toFixed(2)} MB`);

    // Memory growth should be reasonable (less than 100MB for 10k requests)
    expect(memoryGrowthMB).toBeLessThan(100);

    // All pending requests should be resolved
    expect(client.getPendingRequestCount()).toBe(0);

    client.dispose();
    server.dispose();
  }, 30000); // 30 second timeout

  test("should handle sustained load over time", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("work", async (params) => {
      // Simulate some work
      await new Promise((resolve) => setTimeout(resolve, 1));
      return { processed: params.id };
    });

    const duration = 5000; // 5 seconds
    const startTime = Date.now();
    let requestCount = 0;
    const errors: Error[] = [];

    while (Date.now() - startTime < duration) {
      try {
        await client.request("work", { id: requestCount });
        requestCount++;
      } catch (error: any) {
        errors.push(error);
      }
    }

    const requestsPerSecond = requestCount / (duration / 1000);

    console.log(`Sustained throughput: ${requestsPerSecond.toFixed(0)} req/s`);
    console.log(`Total requests: ${requestCount}`);
    console.log(`Errors: ${errors.length}`);

    // Should maintain reasonable throughput
    expect(requestsPerSecond).toBeGreaterThan(50);

    // Should have minimal errors
    expect(errors.length).toBeLessThan(requestCount * 0.01); // < 1% error rate

    client.dispose();
    server.dispose();
  }, 10000);

  test("should handle mixed notifications and requests", async () => {
    const { client, server } = createTransportPair();

    const notificationCount = { value: 0 };

    server.onMethod("increment", async () => {
      notificationCount.value++;
    });

    server.onMethod("get_count", async () => {
      return { count: notificationCount.value };
    });

    // Send a mix of notifications and requests
    const operations: Promise<any>[] = [];

    for (let i = 0; i < 1000; i++) {
      if (i % 2 === 0) {
        operations.push(client.notify("increment", {}));
      } else {
        operations.push(client.request("get_count", {}));
      }
    }

    await Promise.all(operations);

    // Give notifications time to process
    await new Promise((resolve) => setTimeout(resolve, 100));

    const finalCount = await client.request("get_count", {});

    expect(finalCount.count).toBe(500); // 500 notifications

    client.dispose();
    server.dispose();
  });

  test("should handle rapid connect/disconnect cycles", async () => {
    const cycles = 100;

    for (let i = 0; i < cycles; i++) {
      const { client, server } = createTransportPair();

      server.onMethod("ping", async () => ({ pong: true }));

      const result = await client.request("ping", {});
      expect(result).toEqual({ pong: true });

      client.dispose();
      server.dispose();
    }

    // If we got here without crashes, the test passes
    expect(true).toBe(true);
  });

  test("should handle large message payloads", async () => {
    const { client, server } = createTransportPair();

    // Create 10MB payload
    const largePayload = {
      data: "x".repeat(10 * 1024 * 1024),
    };

    server.onMethod("process_large", async (params) => {
      return { size: params.data.length };
    });

    const result = await client.request("process_large", largePayload, 10000);
    expect(result.size).toBe(10 * 1024 * 1024);

    client.dispose();
    server.dispose();
  }, 15000);

  test("should handle many concurrent slow requests", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("slow", async (params) => {
      await new Promise((resolve) => setTimeout(resolve, 100));
      return { processed: params.id };
    });

    const count = 100;
    const results = await Promise.all(
      Array.from({ length: count }, (_, i) => client.request("slow", { id: i }, 5000))
    );

    expect(results).toHaveLength(count);
    expect(client.getPendingRequestCount()).toBe(0);

    client.dispose();
    server.dispose();
  }, 15000);

  test("should recover from handler errors without affecting other requests", async () => {
    const { client, server } = createTransportPair();

    let successCount = 0;

    server.onMethod("sometimes_fails", async (params) => {
      if (params.id % 10 === 0) {
        throw new Error(`Failed for id ${params.id}`);
      }
      successCount++;
      return { success: true, id: params.id };
    });

    const results = await Promise.allSettled(
      Array.from({ length: 100 }, (_, i) => client.request("sometimes_fails", { id: i }))
    );

    const succeeded = results.filter((r) => r.status === "fulfilled").length;
    const failed = results.filter((r) => r.status === "rejected").length;

    expect(succeeded).toBe(90); // 90% success
    expect(failed).toBe(10); // 10% failure (every 10th)
    expect(successCount).toBe(90);

    client.dispose();
    server.dispose();
  });

  test("should handle request bursts", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("echo", async (params) => params);

    // Send bursts of 100 requests with pauses in between
    for (let burst = 0; burst < 10; burst++) {
      const results = await Promise.all(
        Array.from({ length: 100 }, (_, i) => client.request("echo", { burst, index: i }))
      );

      expect(results).toHaveLength(100);
      expect(client.getPendingRequestCount()).toBe(0);

      // Small pause between bursts
      await new Promise((resolve) => setTimeout(resolve, 10));
    }

    client.dispose();
    server.dispose();
  });
});

describe("Edge Cases", () => {
  test("should handle requests with circular references (should throw)", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("process", async (params) => params);

    const circular: any = { a: 1 };
    circular.self = circular;

    try {
      await client.request("process", circular);
      expect(true).toBe(false); // Should not reach here
    } catch (error: any) {
      // JSON.stringify will throw on circular references
      expect(error).toBeDefined();
    }

    client.dispose();
    server.dispose();
  });

  test("should handle requests with special characters", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("echo", async (params) => params);

    const specialChars = {
      null: null,
      undefined: undefined,
      emptyString: "",
      whitespace: "   \n\t\r   ",
      quotes: "\"Hello\" and 'World'",
      backslashes: "C:\\Users\\Test\\",
      unicode: "🚀 你好 مرحبا",
      control: "\x00\x01\x02",
      newlines: "Line1\nLine2\rLine3\r\nLine4",
    };

    const result = await client.request("echo", specialChars);

    // Note: undefined gets removed by JSON.stringify
    expect(result.null).toBe(null);
    expect(result.emptyString).toBe("");
    expect(result.quotes).toBe("\"Hello\" and 'World'");
    expect(result.unicode).toBe("🚀 你好 مرحبا");

    client.dispose();
    server.dispose();
  });

  test("should handle very deep nested objects", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("echo", async (params) => params);

    // Create deeply nested object
    let obj: any = { value: "bottom" };
    for (let i = 0; i < 100; i++) {
      obj = { nested: obj };
    }

    const result = await client.request("echo", obj);

    // Verify structure is preserved
    let current = result;
    for (let i = 0; i < 100; i++) {
      expect(current).toHaveProperty("nested");
      current = current.nested;
    }
    expect(current.value).toBe("bottom");

    client.dispose();
    server.dispose();
  });

  test("should handle requests with very long strings", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("length", async (params) => {
      return { length: params.text.length };
    });

    const longString = "x".repeat(1000000); // 1 million characters

    const result = await client.request("length", { text: longString });
    expect(result.length).toBe(1000000);

    client.dispose();
    server.dispose();
  });

  test("should handle simultaneous timeout and response", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("delayed", async (params) => {
      await new Promise((resolve) => setTimeout(resolve, params.delay));
      return { done: true };
    });

    // Request with delay slightly longer than timeout
    const promise = client.request("delayed", { delay: 150 }, 100);

    try {
      await promise;
      expect(true).toBe(false); // Should timeout
    } catch (error: any) {
      expect(error.message).toContain("timeout");
    }

    // Pending request should be cleaned up
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(client.getPendingRequestCount()).toBe(0);

    client.dispose();
    server.dispose();
  });

  test("should handle handler that returns undefined", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("return_undefined", async () => {
      return undefined;
    });

    const result = await client.request("return_undefined", {});
    expect(result).toBe(undefined);

    client.dispose();
    server.dispose();
  });

  test("should handle handler that returns Promise<void>", async () => {
    const { client, server } = createTransportPair();

    let sideEffect = 0;

    server.onMethod("side_effect", async () => {
      sideEffect++;
      // Implicitly returns undefined (Promise<void>)
    });

    const result = await client.request("side_effect", {});
    expect(result).toBe(undefined);
    expect(sideEffect).toBe(1);

    client.dispose();
    server.dispose();
  });

  test("should handle request IDs wrapping around", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("test", async (params) => params);

    // Simulate many requests to potentially wrap counter
    // (In practice, Date.now() makes this unlikely, but we test the logic)
    for (let i = 0; i < 1000; i++) {
      const result = await client.request("test", { index: i });
      expect(result.index).toBe(i);
    }

    client.dispose();
    server.dispose();
  });
});

describe("Memory Leak Detection", () => {
  test("should not leak memory with many short-lived requests", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("echo", async (params) => params);

    const iterations = 5;
    const requestsPerIteration = 1000;
    const memoryReadings: number[] = [];

    for (let i = 0; i < iterations; i++) {
      await Promise.all(
        Array.from({ length: requestsPerIteration }, (_, j) =>
          client.request("echo", { iteration: i, index: j })
        )
      );

      // Force garbage collection if available
      if (global.gc) {
        global.gc();
      }

      memoryReadings.push(process.memoryUsage().heapUsed);

      // Small delay between iterations
      await new Promise((resolve) => setTimeout(resolve, 100));
    }

    // Check that memory isn't growing consistently
    const firstReading = memoryReadings[0];
    const lastReading = memoryReadings[memoryReadings.length - 1];
    const growthMB = (lastReading - firstReading) / 1024 / 1024;

    console.log(
      "Memory readings (MB):",
      memoryReadings.map((m) => (m / 1024 / 1024).toFixed(2))
    );
    console.log(`Total growth: ${growthMB.toFixed(2)} MB`);

    // Memory growth should be minimal (less than 50MB)
    expect(growthMB).toBeLessThan(50);

    client.dispose();
    server.dispose();
  }, 30000);

  test("should cleanup timeouts properly", async () => {
    const { client, server } = createTransportPair();

    server.onMethod("echo", async () => ({ done: true }));

    // Create many requests with timeouts
    for (let i = 0; i < 100; i++) {
      await client.request("echo", {}, 10000); // 10s timeout
    }

    // All timeouts should be cleared
    expect(client.getPendingRequestCount()).toBe(0);

    client.dispose();
    server.dispose();
  });
});
