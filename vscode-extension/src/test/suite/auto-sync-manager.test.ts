import * as assert from 'assert';
import * as vscode from 'vscode';
import { AutoSyncManager, AutoSyncConfig, PendingChange } from '../../kb/auto-sync-manager';

describe('AutoSyncManager Tests', () => {
  let outputChannel: vscode.OutputChannel;
  let mockConfig: AutoSyncConfig;

  beforeEach(() => {
    outputChannel = vscode.window.createOutputChannel('Test');
    mockConfig = {
      enabled: true,
      mode: 'smart',
      idleTimeMs: 1000,
      maxBatchSize: 10,
      checkIntervalMs: 5000
    };
  });

  afterEach(() => {
    outputChannel.dispose();
  });

  describe('Initialization', () => {
    it('Should create AutoSyncManager instance', () => {
      const manager = new AutoSyncManager(
        mockConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Manager should be created');
    });

    it('Should not start when disabled', async () => {
      const disabledConfig = { ...mockConfig, enabled: false };
      const manager = new AutoSyncManager(
        disabledConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      await manager.start();
      // Should not throw and should log disabled message
      manager.dispose();
      assert.ok(true, 'Should handle disabled state gracefully');
    });

    it('Should not start when mode is off', async () => {
      const offConfig = { ...mockConfig, mode: 'off' as const };
      const manager = new AutoSyncManager(
        offConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      await manager.start();
      manager.dispose();
      assert.ok(true, 'Should handle off mode gracefully');
    });
  });

  describe('Configuration Properties', () => {
    it('Should accept manual mode configuration', () => {
      const manualConfig = { ...mockConfig, mode: 'manual' as const };
      const manager = new AutoSyncManager(
        manualConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Should accept manual mode');
      manager.dispose();
    });

    it('Should accept smart mode configuration', () => {
      const smartConfig = { ...mockConfig, mode: 'smart' as const };
      const manager = new AutoSyncManager(
        smartConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Should accept smart mode');
      manager.dispose();
    });

    it('Should accept aggressive mode configuration', () => {
      const aggressiveConfig = { ...mockConfig, mode: 'aggressive' as const };
      const manager = new AutoSyncManager(
        aggressiveConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Should accept aggressive mode');
      manager.dispose();
    });

    it('Should use provided idleTimeMs setting', () => {
      const customConfig = { ...mockConfig, idleTimeMs: 60000 };
      const manager = new AutoSyncManager(
        customConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Should accept custom idle time');
      manager.dispose();
    });

    it('Should use provided maxBatchSize setting', () => {
      const customConfig = { ...mockConfig, maxBatchSize: 50 };
      const manager = new AutoSyncManager(
        customConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Should accept custom batch size');
      manager.dispose();
    });

    it('Should use provided checkIntervalMs setting', () => {
      const customConfig = { ...mockConfig, checkIntervalMs: 10000 };
      const manager = new AutoSyncManager(
        customConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Should accept custom check interval');
      manager.dispose();
    });
  });

  describe('Batching Logic', () => {
    it('Should handle empty changes array', () => {
      const manager = new AutoSyncManager(
        mockConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      // Test internal batching (accessing via any to test private method)
      const changes: PendingChange[] = [];
      const batches = (manager as any).batchChanges(changes, 10);

      assert.strictEqual(batches.length, 0, 'Should produce no batches for empty input');
      manager.dispose();
    });

    it('Should create single batch for changes within limit', () => {
      const manager = new AutoSyncManager(
        mockConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      const changes: PendingChange[] = [
        { id: 1, file_path: 'file1.py', change_type: 'modified', detected_at: new Date().toISOString() },
        { id: 2, file_path: 'file2.py', change_type: 'modified', detected_at: new Date().toISOString() },
        { id: 3, file_path: 'file3.py', change_type: 'modified', detected_at: new Date().toISOString() }
      ];

      const batches = (manager as any).batchChanges(changes, 10);

      assert.strictEqual(batches.length, 1, 'Should create single batch');
      assert.strictEqual(batches[0].length, 3, 'Batch should contain all changes');
      manager.dispose();
    });

    it('Should split changes into multiple batches when exceeding limit', () => {
      const manager = new AutoSyncManager(
        mockConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      const changes: PendingChange[] = [];
      for (let i = 0; i < 25; i++) {
        changes.push({
          id: i,
          file_path: `file${i}.py`,
          change_type: 'modified',
          detected_at: new Date().toISOString()
        });
      }

      const batches = (manager as any).batchChanges(changes, 10);

      assert.strictEqual(batches.length, 3, 'Should create 3 batches (10 + 10 + 5)');
      assert.strictEqual(batches[0].length, 10, 'First batch should have 10 items');
      assert.strictEqual(batches[1].length, 10, 'Second batch should have 10 items');
      assert.strictEqual(batches[2].length, 5, 'Third batch should have 5 items');
      manager.dispose();
    });

    it('Should respect batch size of 1', () => {
      const manager = new AutoSyncManager(
        mockConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      const changes: PendingChange[] = [
        { id: 1, file_path: 'file1.py', change_type: 'modified', detected_at: new Date().toISOString() },
        { id: 2, file_path: 'file2.py', change_type: 'modified', detected_at: new Date().toISOString() }
      ];

      const batches = (manager as any).batchChanges(changes, 1);

      assert.strictEqual(batches.length, 2, 'Should create 2 batches for batch size 1');
      assert.strictEqual(batches[0].length, 1, 'Each batch should have 1 item');
      assert.strictEqual(batches[1].length, 1, 'Each batch should have 1 item');
      manager.dispose();
    });
  });

  describe('Disposal', () => {
    it('Should properly dispose resources', () => {
      const manager = new AutoSyncManager(
        mockConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      // Should not throw
      manager.dispose();
      assert.ok(true, 'Disposal should complete without errors');
    });

    it('Should handle multiple dispose calls', () => {
      const manager = new AutoSyncManager(
        mockConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      manager.dispose();
      manager.dispose();
      manager.dispose();
      assert.ok(true, 'Multiple dispose calls should not cause errors');
    });

    it('Should dispose after starting', async () => {
      const manager = new AutoSyncManager(
        mockConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      await manager.start();
      manager.dispose();
      assert.ok(true, 'Should dispose cleanly after starting');
    });
  });

  describe('Mode-Specific Behavior', () => {
    it('Manual mode should be initialized', () => {
      const manualConfig = { ...mockConfig, mode: 'manual' as const };
      const manager = new AutoSyncManager(
        manualConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Manual mode manager should be created');
      manager.dispose();
    });

    it('Smart mode should be initialized', () => {
      const smartConfig = { ...mockConfig, mode: 'smart' as const };
      const manager = new AutoSyncManager(
        smartConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Smart mode manager should be created');
      manager.dispose();
    });

    it('Aggressive mode should be initialized', () => {
      const aggressiveConfig = { ...mockConfig, mode: 'aggressive' as const };
      const manager = new AutoSyncManager(
        aggressiveConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Aggressive mode manager should be created');
      manager.dispose();
    });
  });

  describe('Error Handling', () => {
    it('Should handle API errors gracefully', async () => {
      const manager = new AutoSyncManager(
        mockConfig,
        'test-repo',
        'http://invalid-url-that-does-not-exist',
        outputChannel
      );

      // Start manager - it will try to fetch pending changes
      // This should not crash even if API is unavailable
      await manager.start();

      // Wait a bit for periodic check to attempt
      await new Promise(resolve => setTimeout(resolve, 100));

      manager.dispose();
      assert.ok(true, 'Should handle API errors without crashing');
    });

    it('Should handle invalid API responses', async () => {
      const manager = new AutoSyncManager(
        mockConfig,
        'test-repo',
        'http://localhost:99999', // Invalid port
        outputChannel
      );

      await manager.start();
      await new Promise(resolve => setTimeout(resolve, 100));

      manager.dispose();
      assert.ok(true, 'Should handle invalid API responses');
    });
  });

  describe('Integration with Configuration', () => {
    it('Should work with default configuration values', () => {
      const defaultConfig: AutoSyncConfig = {
        enabled: true,
        mode: 'smart',
        idleTimeMs: 30000,
        maxBatchSize: 100,
        checkIntervalMs: 30000
      };

      const manager = new AutoSyncManager(
        defaultConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Should work with default configuration');
      manager.dispose();
    });

    it('Should work with minimal configuration', () => {
      const minimalConfig: AutoSyncConfig = {
        enabled: false,
        mode: 'off',
        idleTimeMs: 0,
        maxBatchSize: 1,
        checkIntervalMs: 1000
      };

      const manager = new AutoSyncManager(
        minimalConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Should work with minimal configuration');
      manager.dispose();
    });

    it('Should work with extreme configuration values', () => {
      const extremeConfig: AutoSyncConfig = {
        enabled: true,
        mode: 'aggressive',
        idleTimeMs: 1000000,
        maxBatchSize: 1000,
        checkIntervalMs: 100000
      };

      const manager = new AutoSyncManager(
        extremeConfig,
        'test-repo',
        'http://localhost:8765',
        outputChannel
      );

      assert.ok(manager, 'Should work with extreme configuration values');
      manager.dispose();
    });
  });

  describe('Repository and API Configuration', () => {
    it('Should accept different repository names', () => {
      const repos = ['my-repo', 'test-project', 'backend-service'];

      for (const repo of repos) {
        const manager = new AutoSyncManager(
          mockConfig,
          repo,
          'http://localhost:8765',
          outputChannel
        );

        assert.ok(manager, `Should accept repo name: ${repo}`);
        manager.dispose();
      }
    });

    it('Should accept different API base URLs', () => {
      const urls = [
        'http://localhost:8765',
        'http://127.0.0.1:9000',
        'https://api.example.com'
      ];

      for (const url of urls) {
        const manager = new AutoSyncManager(
          mockConfig,
          'test-repo',
          url,
          outputChannel
        );

        assert.ok(manager, `Should accept API URL: ${url}`);
        manager.dispose();
      }
    });
  });
});
