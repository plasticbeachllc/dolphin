/**
 * KB lifecycle management tests using mock infrastructure.
 * Tests KB server startup, health checks, and status monitoring with mocks.
 */

import * as assert from 'assert';
import * as vscode from 'vscode';
import {
  setupMockEnvironment,
  teardownMockEnvironment,
  resetMocks,
  getMockEnvironment,
  configureMockKB
} from '../helpers/mock-manager';
import { activateExtension, waitForCondition, assertCommandExists } from '../helpers/shared-fixtures';
import { TEST_COMMANDS } from '../helpers/test-constants';

suite('KB Lifecycle Management', function() {
  this.timeout(10000);

  suiteSetup(async () => {
    await setupMockEnvironment();
    await activateExtension();
  });

  suiteTeardown(async () => {
    await teardownMockEnvironment();
  });

  setup(() => {
    resetMocks();
  });

  suite('KB Server Health', () => {
    test('Mock KB server should be running', async () => {
      const { kbServer } = getMockEnvironment();

      assert.ok(kbServer, 'KB server mock should be initialized');
      assert.ok(kbServer.port > 0, 'KB server should have valid port');
      assert.strictEqual(kbServer.port, 7778, 'Should use configured test port');
    });

    test('KB server should respond to health checks', async () => {
      const { kbServer } = getMockEnvironment();

      // Configure KB as healthy
      configureMockKB({ health: true });

      const http = require('http');
      const response = await new Promise<any>((resolve, reject) => {
        http.get(`http://localhost:${kbServer.port}/health`, (res: any) => {
          let data = '';
          res.on('data', (chunk: any) => { data += chunk; });
          res.on('end', () => {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
          });
        });
      });

      assert.strictEqual(response.status, 200, 'Health check should return 200');
      assert.strictEqual(response.data.status, 'ok', 'Should return ok status');
    });

    test('KB server should report unhealthy state when configured', async () => {
      const { kbServer } = getMockEnvironment();

      // Configure KB as unhealthy
      configureMockKB({ health: false });

      const http = require('http');
      const response = await new Promise<any>((resolve, reject) => {
        http.get(`http://localhost:${kbServer.port}/health`, (res: any) => {
          let data = '';
          res.on('data', (chunk: any) => { data += chunk; });
          res.on('end', () => {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
          });
        });
      });

      assert.strictEqual(response.status, 503, 'Unhealthy check should return 503');
      assert.strictEqual(response.data.status, 'error', 'Should return error status');
    });
  });

  suite('KB Commands', () => {
    test('KB status command should be registered', async () => {
      await assertCommandExists(TEST_COMMANDS.KB_SHOW_STATUS);
    });

    test('KB restart command should be registered', async () => {
      await assertCommandExists(TEST_COMMANDS.KB_RESTART);
    });

    test('KB status command should execute', async () => {
      // Command should execute without throwing
      await vscode.commands.executeCommand(TEST_COMMANDS.KB_SHOW_STATUS);
      // If we get here, command executed (may or may not show UI in headless mode)
    });

    test('KB restart command should execute', async () => {
      // Command should execute without throwing
      await vscode.commands.executeCommand(TEST_COMMANDS.KB_RESTART);
      // If we get here, command executed
    });
  });

  suite('KB API Operations', () => {
    test('KB should handle search requests', async () => {
      const { kbServer } = getMockEnvironment();

      configureMockKB({
        searchResults: [
          {
            chunk_id: 'test-1',
            repo: 'test-repo',
            path: 'file.ts',
            content: 'test content',
            score: 0.9,
            line_start: 1,
            line_end: 3,
          }
        ]
      });

      const http = require('http');
      const response = await new Promise<any>((resolve, reject) => {
        const postData = JSON.stringify({ query: 'test', top_k: 10 });
        const options = {
          hostname: 'localhost',
          port: kbServer.port,
          path: '/search',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(postData),
          },
        };

        const req = http.request(options, (res: any) => {
          let data = '';
          res.on('data', (chunk: any) => { data += chunk; });
          res.on('end', () => {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
          });
        });

        req.on('error', reject);
        req.write(postData);
        req.end();
      });

      assert.strictEqual(response.status, 200, 'Search should return 200');
      assert.ok(response.data.hits, 'Should return hits');
      assert.strictEqual(response.data.hits.length, 1, 'Should return configured result');
      assert.strictEqual(response.data.hits[0].chunk_id, 'test-1', 'Should return configured chunk');
    });

    test('KB should return metadata', async () => {
      const { kbServer } = getMockEnvironment();

      configureMockKB({
        metadata: {
          repos: [{ name: 'custom-repo', path: '/custom/path', files: 5, chunks: 25 }],
          total_chunks: 25,
          total_files: 5,
        }
      });

      const http = require('http');
      const response = await new Promise<any>((resolve, reject) => {
        http.get(`http://localhost:${kbServer.port}/metadata/test`, (res: any) => {
          let data = '';
          res.on('data', (chunk: any) => { data += chunk; });
          res.on('end', () => {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
          });
        });
      });

      assert.strictEqual(response.status, 200, 'Metadata should return 200');
      assert.ok(response.data.repos, 'Should have repos');
      assert.strictEqual(response.data.total_chunks, 25, 'Should return configured total');
    });

    test('KB should log request history', async () => {
      const { kbServer } = getMockEnvironment();

      const requestsBefore = kbServer.getRequestHistory().length;

      // Make multiple requests
      const http = require('http');
      await new Promise((resolve) => {
        http.get(`http://localhost:${kbServer.port}/health`, (res: any) => {
          res.on('data', () => {});
          res.on('end', resolve);
        });
      });

      await new Promise((resolve) => {
        http.get(`http://localhost:${kbServer.port}/metadata/test`, (res: any) => {
          res.on('data', () => {});
          res.on('end', resolve);
        });
      });

      const requestsAfter = kbServer.getRequestHistory().length;
      assert.strictEqual(requestsAfter - requestsBefore, 2, 'Should have logged 2 requests');

      const history = kbServer.getRequestHistory();
      assert.ok(history.every(r => r.timestamp), 'Each request should have timestamp');
      assert.ok(history.every(r => r.method), 'Each request should have method');
      assert.ok(history.every(r => r.url), 'Each request should have URL');
    });
  });

  suite('KB Configuration', () => {
    test('KB configuration keys should exist', () => {
      const config = vscode.workspace.getConfiguration('dolphin');

      // Verify KB-related configuration is defined in package.json
      const kbDebounce = config.inspect('kb.debounceMs');
      const kbBatchInterval = config.inspect('kb.batchIntervalMs');
      const autoSyncEnabled = config.inspect('kb.autoSync.enabled');

      assert.ok(kbDebounce, 'kb.debounceMs should be defined');
      assert.ok(kbBatchInterval, 'kb.batchIntervalMs should be defined');
      assert.ok(autoSyncEnabled, 'kb.autoSync.enabled should be defined');
    });

    test('KB configuration should have valid types', () => {
      const config = vscode.workspace.getConfiguration('dolphin');

      const kbDebounce = config.get<number>('kb.debounceMs');
      const excludePatterns = config.get<string[]>('kb.excludePatterns');
      const autoSyncEnabled = config.get<boolean>('kb.autoSync.enabled');

      assert.strictEqual(typeof kbDebounce, 'number', 'debounceMs should be number');
      assert.ok(Array.isArray(excludePatterns), 'excludePatterns should be array');
      assert.strictEqual(typeof autoSyncEnabled, 'boolean', 'autoSync.enabled should be boolean');
    });
  });

  suite('KB Performance', () => {
    test('KB status checks should be fast', async () => {
      const { kbServer } = getMockEnvironment();

      const startTime = Date.now();

      const http = require('http');
      await new Promise((resolve) => {
        http.get(`http://localhost:${kbServer.port}/health`, (res: any) => {
          res.on('data', () => {});
          res.on('end', resolve);
        });
      });

      const elapsed = Date.now() - startTime;

      // Mock KB should respond very quickly
      assert.ok(elapsed < 1000, `Health check took ${elapsed}ms, should be < 1000ms`);
    });

    test('KB search should be reasonably fast', async () => {
      const { kbServer } = getMockEnvironment();

      const startTime = Date.now();

      const http = require('http');
      await new Promise((resolve, reject) => {
        const postData = JSON.stringify({ query: 'test', top_k: 10 });
        const options = {
          hostname: 'localhost',
          port: kbServer.port,
          path: '/search',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(postData),
          },
        };

        const req = http.request(options, (res: any) => {
          res.on('data', () => {});
          res.on('end', resolve);
        });

        req.on('error', reject);
        req.write(postData);
        req.end();
      });

      const elapsed = Date.now() - startTime;

      // Mock KB should respond very quickly
      assert.ok(elapsed < 1000, `Search took ${elapsed}ms, should be < 1000ms`);
    });
  });
});
