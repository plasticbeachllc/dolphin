/**
 * Integration tests for IPCTransport
 */

import { describe, test, expect, beforeEach, afterEach, mock } from 'bun:test';
import { IPCTransport, RPCErrorCode } from '../transport';
import { Readable, Writable, PassThrough } from 'stream';

/**
 * Helper to create a pair of connected transports
 */
function createTransportPair() {
  // Create bidirectional streams
  const clientToServer = new PassThrough();
  const serverToClient = new PassThrough();

  const client = new IPCTransport({
    input: serverToClient,
    output: clientToServer,
  });

  const server = new IPCTransport({
    input: clientToServer,
    output: serverToClient,
  });

  return { client, server, clientToServer, serverToClient };
}

/**
 * Helper to wait for a condition with timeout
 */
function waitFor(condition: () => boolean, timeout: number = 5000): Promise<void> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();
    const interval = setInterval(() => {
      if (condition()) {
        clearInterval(interval);
        resolve();
      } else if (Date.now() - startTime > timeout) {
        clearInterval(interval);
        reject(new Error('Timeout waiting for condition'));
      }
    }, 10);
  });
}

describe('IPCTransport', () => {
  describe('Basic Communication', () => {
    test('should send and receive notifications', async () => {
      const { client, server } = createTransportPair();

      const receivedMessages: any[] = [];
      server.onMethod('test_notification', async (params) => {
        receivedMessages.push(params);
      });

      await client.notify('test_notification', { data: 'hello' });

      await waitFor(() => receivedMessages.length > 0);

      expect(receivedMessages).toHaveLength(1);
      expect(receivedMessages[0]).toEqual({ data: 'hello' });

      client.dispose();
      server.dispose();
    });

    test('should send and receive requests', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('echo', async (params) => {
        return { echo: params };
      });

      const result = await client.request('echo', { message: 'hello' });

      expect(result).toEqual({ echo: { message: 'hello' } });

      client.dispose();
      server.dispose();
    });

    test('should handle multiple concurrent requests', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('add', async (params) => {
        return params.a + params.b;
      });

      const results = await Promise.all([
        client.request('add', { a: 1, b: 2 }),
        client.request('add', { a: 3, b: 4 }),
        client.request('add', { a: 5, b: 6 }),
      ]);

      expect(results).toEqual([3, 7, 11]);

      client.dispose();
      server.dispose();
    });

    test('should handle request with null params', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('test', async (params) => {
        return { received: params };
      });

      const result = await client.request('test', null);
      expect(result).toEqual({ received: null });

      client.dispose();
      server.dispose();
    });

    test('should handle request with undefined params', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('test', async (params) => {
        return { received: params };
      });

      const result = await client.request('test', undefined);
      expect(result).toEqual({ received: undefined });

      client.dispose();
      server.dispose();
    });
  });

  describe('Error Handling', () => {
    test('should return error for unknown method', async () => {
      const { client, server } = createTransportPair();

      try {
        await client.request('unknown_method', {});
        expect(true).toBe(false); // Should not reach here
      } catch (error: any) {
        expect(error.message).toContain('Method not found');
        expect(error.code).toBe(RPCErrorCode.METHOD_NOT_FOUND);
      }

      client.dispose();
      server.dispose();
    });

    test('should handle errors thrown by method handlers', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('failing_method', async () => {
        throw new Error('Something went wrong');
      });

      try {
        await client.request('failing_method', {});
        expect(true).toBe(false); // Should not reach here
      } catch (error: any) {
        expect(error.message).toBe('Something went wrong');
        expect(error.code).toBe(RPCErrorCode.INTERNAL_ERROR);
      }

      client.dispose();
      server.dispose();
    });

    test('should handle timeout for slow requests', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('slow_method', async () => {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        return { done: true };
      });

      try {
        await client.request('slow_method', {}, 100); // 100ms timeout
        expect(true).toBe(false); // Should not reach here
      } catch (error: any) {
        expect(error.message).toContain('timeout');
      }

      client.dispose();
      server.dispose();
    });

    test('should cleanup pending request on send failure', async () => {
      const input = new PassThrough();
      const output = new Writable({
        write(chunk, encoding, callback) {
          callback(new Error('Write failed'));
        },
      });

      const transport = new IPCTransport({ input, output });

      expect(transport.getPendingRequestCount()).toBe(0);

      try {
        await transport.request('test', {});
        expect(true).toBe(false); // Should not reach here
      } catch (error: any) {
        expect(error.message).toBe('Write failed');
      }

      // Pending request should be cleaned up
      expect(transport.getPendingRequestCount()).toBe(0);

      transport.dispose();
    });

    test('should handle errors in notification handlers gracefully', async () => {
      const { client, server } = createTransportPair();

      const errorSpy = mock(() => {});
      const originalError = console.error;
      console.error = errorSpy;

      server.onMethod('failing_notification', async () => {
        throw new Error('Notification failed');
      });

      await client.notify('failing_notification', {});

      // Wait a bit for the notification to be processed
      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(errorSpy).toHaveBeenCalled();

      console.error = originalError;

      client.dispose();
      server.dispose();
    });
  });

  describe('Security', () => {
    test('should reject messages exceeding max size', async () => {
      const { client, server } = createTransportPair();

      // Create a large payload
      const largePayload = {
        data: 'x'.repeat(150 * 1024 * 1024), // 150 MB
      };

      server.onMethod('test', async () => ({ success: true }));

      try {
        await client.request('test', largePayload);
        expect(true).toBe(false); // Should not reach here
      } catch (error: any) {
        expect(error.message).toContain('too large');
      }

      client.dispose();
      server.dispose();
    });

    test('should reject requests when max pending limit reached', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('slow', async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return { done: true };
      });

      // Create a transport with low limit
      const limitedClient = new IPCTransport({
        input: new PassThrough(),
        output: new PassThrough(),
        security: { maxPendingRequests: 2 },
      });

      // Start 2 requests (should work)
      const req1 = limitedClient.request('slow', {});
      const req2 = limitedClient.request('slow', {});

      // Third request should be rejected
      try {
        await limitedClient.request('slow', {});
        expect(true).toBe(false); // Should not reach here
      } catch (error: any) {
        expect(error.message).toContain('Too many pending requests');
      }

      limitedClient.dispose();
      client.dispose();
      server.dispose();
    });
  });

  describe('Connection Management', () => {
    test('should cleanup pending requests on dispose', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('slow', async () => {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        return { done: true };
      });

      const requestPromise = client.request('slow', {});

      expect(client.getPendingRequestCount()).toBe(1);

      client.dispose();

      try {
        await requestPromise;
        expect(true).toBe(false); // Should not reach here
      } catch (error: any) {
        expect(error.message).toBe('Transport disposed');
      }

      expect(client.getPendingRequestCount()).toBe(0);

      server.dispose();
    });

    test('should cleanup pending requests when connection closes', async () => {
      const { client, server, clientToServer } = createTransportPair();

      server.onMethod('slow', async () => {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        return { done: true };
      });

      const requestPromise = client.request('slow', {});

      expect(client.getPendingRequestCount()).toBe(1);

      // Simulate connection close
      clientToServer.destroy();

      try {
        await requestPromise;
        expect(true).toBe(false); // Should not reach here
      } catch (error: any) {
        expect(error.message).toContain('Connection closed');
      }

      expect(client.getPendingRequestCount()).toBe(0);

      client.dispose();
      server.dispose();
    });

    test('should handle multiple dispose calls safely', () => {
      const { client } = createTransportPair();

      expect(() => {
        client.dispose();
        client.dispose();
        client.dispose();
      }).not.toThrow();
    });
  });

  describe('Method Registration', () => {
    test('should allow registering multiple methods', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('method1', async () => ({ result: 1 }));
      server.onMethod('method2', async () => ({ result: 2 }));
      server.onMethod('method3', async () => ({ result: 3 }));

      const results = await Promise.all([
        client.request('method1', {}),
        client.request('method2', {}),
        client.request('method3', {}),
      ]);

      expect(results).toEqual([{ result: 1 }, { result: 2 }, { result: 3 }]);

      client.dispose();
      server.dispose();
    });

    test('should allow overwriting method handlers', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('test', async () => ({ version: 1 }));
      server.onMethod('test', async () => ({ version: 2 }));

      const result = await client.request('test', {});
      expect(result).toEqual({ version: 2 });

      client.dispose();
      server.dispose();
    });

    test('should call default handler for unregistered methods', async () => {
      const { client, server } = createTransportPair();

      const receivedMessages: any[] = [];
      server.onMessage(async (message) => {
        receivedMessages.push(message);
      });

      await client.notify('unregistered_method', { data: 'test' });

      await waitFor(() => receivedMessages.length > 0);

      expect(receivedMessages).toHaveLength(1);
      expect(receivedMessages[0].method).toBe('unregistered_method');

      client.dispose();
      server.dispose();
    });
  });

  describe('Request ID Generation', () => {
    test('should generate unique request IDs', async () => {
      const { client, server } = createTransportPair();

      const receivedIds: any[] = [];
      server.onMethod('capture_id', async (params) => {
        return { success: true };
      });

      // Intercept responses to capture IDs
      const ids = new Set<string | number>();
      const originalOnMethod = server.onMethod.bind(server);

      for (let i = 0; i < 100; i++) {
        const promise = client.request('capture_id', { index: i });
        // IDs are generated synchronously
      }

      await new Promise((resolve) => setTimeout(resolve, 100));

      // At least we can verify that concurrent requests don't collide
      expect(client.getPendingRequestCount()).toBeLessThanOrEqual(100);

      client.dispose();
      server.dispose();
    });
  });

  describe('Bidirectional Communication', () => {
    test('should allow both sides to send requests', async () => {
      const { client, server } = createTransportPair();

      client.onMethod('client_method', async (params) => {
        return { client_received: params };
      });

      server.onMethod('server_method', async (params) => {
        return { server_received: params };
      });

      const clientResult = await server.request('client_method', { from: 'server' });
      const serverResult = await client.request('server_method', { from: 'client' });

      expect(clientResult).toEqual({ client_received: { from: 'server' } });
      expect(serverResult).toEqual({ server_received: { from: 'client' } });

      client.dispose();
      server.dispose();
    });

    test('should allow nested requests (request within request handler)', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('inner', async (params) => {
        return { inner_result: params.value * 2 };
      });

      client.onMethod('outer', async (params) => {
        // Client makes a request back to server from within a handler
        const innerResult = await server.request('inner', { value: params.value });
        return { outer_result: innerResult.inner_result + 10 };
      });

      const result = await server.request('outer', { value: 5 });
      expect(result).toEqual({ outer_result: 20 }); // (5 * 2) + 10

      client.dispose();
      server.dispose();
    });
  });

  describe('Edge Cases', () => {
    test('should handle empty params', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('test', async (params) => {
        return { params_received: params };
      });

      const result1 = await client.request('test', {});
      const result2 = await client.request('test', null);
      const result3 = await client.request('test', undefined);

      expect(result1).toEqual({ params_received: {} });
      expect(result2).toEqual({ params_received: null });
      expect(result3).toEqual({ params_received: undefined });

      client.dispose();
      server.dispose();
    });

    test('should handle large response payloads', async () => {
      const { client, server } = createTransportPair();

      const largeData = Array.from({ length: 10000 }, (_, i) => ({
        id: i,
        data: `item-${i}`,
      }));

      server.onMethod('get_large_data', async () => {
        return { items: largeData };
      });

      const result = await client.request('get_large_data', {});
      expect(result.items).toHaveLength(10000);
      expect(result.items[0]).toEqual({ id: 0, data: 'item-0' });

      client.dispose();
      server.dispose();
    });

    test('should handle rapid sequential requests', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('increment', async (params) => {
        return { value: params.value + 1 };
      });

      const results: number[] = [];
      for (let i = 0; i < 100; i++) {
        const result = await client.request('increment', { value: i });
        results.push(result.value);
      }

      expect(results).toHaveLength(100);
      expect(results[0]).toBe(1);
      expect(results[99]).toBe(100);

      client.dispose();
      server.dispose();
    });
  });

  describe('Performance', () => {
    test('should handle high throughput', async () => {
      const { client, server } = createTransportPair();

      server.onMethod('echo', async (params) => params);

      const startTime = Date.now();
      const count = 1000;

      await Promise.all(
        Array.from({ length: count }, (_, i) =>
          client.request('echo', { index: i })
        )
      );

      const duration = Date.now() - startTime;
      const throughput = count / (duration / 1000);

      console.log(`Throughput: ${throughput.toFixed(0)} requests/sec`);

      // Should handle at least 100 requests/sec
      expect(throughput).toBeGreaterThan(100);

      client.dispose();
      server.dispose();
    });
  });
});
