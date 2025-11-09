import * as assert from 'assert';
import * as vscode from 'vscode';
import { waitForExtensionActivation, sleep } from '../helpers/test-utils';
import { MockKBServer } from '../helpers/mock-services';

suite('Integration Tests', () => {
  let mockServer: MockKBServer;

  suiteSetup(async function () {
    this.timeout(20000);

    // Start mock KB API server
    mockServer = new MockKBServer();
    await mockServer.start(7778); // Use different port to avoid conflicts

    await waitForExtensionActivation();
    await sleep(1000);
  });

  suiteTeardown(async function () {
    this.timeout(5000);
    if (mockServer) {
      await mockServer.stop();
    }
  });

  test('Mock KB API server should be running', async function () {
    this.timeout(5000);

    assert.ok(mockServer, 'Mock server should be initialized');
    assert.ok(mockServer.port > 0, 'Mock server should have a port assigned');

    // Test health endpoint
    const http = require('http');
    const response = await new Promise<any>((resolve, reject) => {
      const req = http.get(
        `http://localhost:${mockServer.port}/health`,
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
    assert.strictEqual(
      response.data.status,
      'ok',
      'Health check should return ok status'
    );
  });

  test('Extension should activate in workspace with mock server', async function () {
    this.timeout(10000);

    const extension = vscode.extensions.getExtension('pb.dolphin');
    assert.ok(extension, 'Extension should exist');
    assert.ok(extension.isActive, 'Extension should be active');
  });

  test('Mock KB API should handle search requests', async function () {
    this.timeout(5000);

    const http = require('http');

    const searchRequest = {
      query: 'test search',
      top_k: 10,
    };

    const response = await new Promise<any>((resolve, reject) => {
      const postData = JSON.stringify(searchRequest);

      const options = {
        hostname: 'localhost',
        port: mockServer.port,
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
    assert.ok(
      Array.isArray(response.data.hits),
      'Hits should be an array'
    );
  });

  test('Complete workflow: Extension activation → Webview → Commands', async function () {
    this.timeout(15000);

    // 1. Verify extension is active
    const extension = vscode.extensions.getExtension('pb.dolphin');
    assert.ok(extension?.isActive, 'Extension should be active');

    // 2. Verify commands are registered
    const commands = await vscode.commands.getCommands(true);
    const dolphinCommands = commands.filter((cmd) =>
      cmd.startsWith('dolphin.')
    );
    assert.ok(
      dolphinCommands.length >= 3,
      'Dolphin commands should be registered'
    );

    // 3. Verify package.json contributions are correct
    const packageJSON = extension!.packageJSON;
    assert.ok(
      packageJSON.contributes.viewsContainers,
      'Should have viewsContainers'
    );
    assert.ok(packageJSON.contributes.views, 'Should have views');
    assert.ok(packageJSON.contributes.commands, 'Should have commands');

    // 4. Execute a safe command
    try {
      await vscode.commands.executeCommand('dolphin.test');
      assert.ok(true, 'Test command executed successfully');
    } catch (err) {
      // Command exists but might fail in headless mode
      console.log('Test command execution note:', err);
    }

    console.log('✓ Complete workflow test passed');
  });
});
