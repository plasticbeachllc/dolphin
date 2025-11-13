/**
 * Integration tests using mock KB server.
 * Tests the extension with mocked external dependencies.
 */

import * as assert from 'assert';
import * as vscode from 'vscode';
import { setupMockEnvironment, teardownMockEnvironment, resetMocks, getMockEnvironment } from '../helpers/mock-manager';
import { activateExtension, waitForCondition } from '../helpers/shared-fixtures';
import { TEST_COMMANDS } from '../helpers/test-constants';

suite('Integration Tests with Mock KB', function() {
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

  test('Mock KB API server should be running and healthy', async () => {
    const { kbServer } = getMockEnvironment();

    assert.ok(kbServer, 'Mock server should be initialized');
    assert.ok(kbServer.port > 0, 'Mock server should have a port assigned');

    // Test health endpoint
    const http = require('http');
    const response = await new Promise<any>((resolve, reject) => {
      const req = http.get(
        `http://localhost:${kbServer.port}/health`,
        (res: any) => {
          let data = '';
          res.on('data', (chunk: any) => {
            data += chunk;
          });
          res.on('end', () => {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
          });
        }
      );
      req.on('error', reject);
    });

    assert.strictEqual(response.status, 200, 'Health check should return 200');
    assert.strictEqual(response.data.status, 'ok', 'Health check should return ok status');
  });

  test('Extension should be active', async () => {
    const extension = vscode.extensions.getExtension('pb.dolphin');
    assert.ok(extension, 'Extension should exist');
    assert.ok(extension.isActive, 'Extension should be active');
  });

  test('Mock KB API should handle search requests', async () => {
    const { kbServer } = getMockEnvironment();
    const http = require('http');

    const searchRequest = {
      query: 'test search',
      top_k: 10,
    };

    const response = await new Promise<any>((resolve, reject) => {
      const postData = JSON.stringify(searchRequest);

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
        res.on('data', (chunk: any) => {
          data += chunk;
        });
        res.on('end', () => {
          resolve({ status: res.statusCode, data: JSON.parse(data) });
        });
      });

      req.on('error', reject);
      req.write(postData);
      req.end();
    });

    assert.strictEqual(response.status, 200, 'Search should return 200');
    assert.ok(response.data.hits, 'Search should return hits');
    assert.ok(Array.isArray(response.data.hits), 'Hits should be an array');
    assert.ok(response.data.hits.length > 0, 'Should return at least one hit');
  });

  test('Complete workflow: Extension activation → Commands → Mock KB', async () => {
    const { kbServer } = getMockEnvironment();

    // 1. Verify extension is active
    const extension = vscode.extensions.getExtension('pb.dolphin');
    assert.ok(extension?.isActive, 'Extension should be active');

    // 2. Verify commands are registered
    const commands = await vscode.commands.getCommands(true);
    const dolphinCommands = commands.filter((cmd) => cmd.startsWith('dolphin.'));
    assert.ok(dolphinCommands.length >= 10, 'At least 10 Dolphin commands should be registered');

    // Verify specific commands
    assert.ok(commands.includes(TEST_COMMANDS.FOCUS_INPUT), 'focusInput command should be registered');
    assert.ok(commands.includes(TEST_COMMANDS.NEW_CONVERSATION), 'newConversation command should be registered');
    assert.ok(commands.includes(TEST_COMMANDS.KB_SHOW_STATUS), 'KB status command should be registered');

    // 3. Verify package.json contributions are correct
    const packageJSON = extension!.packageJSON;
    assert.ok(packageJSON.contributes.viewsContainers, 'Should have viewsContainers');
    assert.ok(packageJSON.contributes.views, 'Should have views');
    assert.ok(packageJSON.contributes.commands, 'Should have commands');

    // 4. Verify mock KB is accessible
    const requestsBefore = kbServer.getRequestHistory().length;

    // Make a request to KB
    const http = require('http');
    await new Promise((resolve) => {
      http.get(`http://localhost:${kbServer.port}/health`, (res: any) => {
        res.on('data', () => {});
        res.on('end', resolve);
      });
    });

    // Verify request was logged
    const requestsAfter = kbServer.getRequestHistory().length;
    assert.ok(requestsAfter > requestsBefore, 'KB should have logged the request');
  });
});
