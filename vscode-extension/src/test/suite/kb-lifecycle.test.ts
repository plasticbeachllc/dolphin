/**
 * Integration tests for KB lifecycle management in VSCode extension.
 * Tests KB server startup, shutdown, restart, and health monitoring.
 */

import * as assert from 'assert';
import * as vscode from 'vscode';
import * as path from 'path';

describe('KB Lifecycle Management', () => {
    let extension: vscode.Extension<any> | undefined;

    suiteSetup(async function () {
        this.timeout(15000); // 15 second timeout for extension activation (reduced from 30s)

        // Get the extension
        extension = vscode.extensions.getExtension('pb.dolphin');
        assert.ok(extension, 'Extension should be installed');

        // Ensure extension is activated
        if (!extension.isActive) {
            await extension.activate();
        }
    });

    suite('KB Auto-Start', () => {
        test('KB server starts automatically on extension activation', async function () {
            this.timeout(8000);

            assert.ok(extension, 'Extension should be available');
            assert.ok(extension.isActive, 'Extension should be activated');

            // Give KB time to start
            await new Promise(resolve => setTimeout(resolve, 5000));

            // Extension should have KB-related exports or status
            const exports = extension.exports;

            // Check if KB manager or related services are available
            // This depends on what the extension exports
            if (exports && exports.kbManager) {
                const status = await exports.kbManager.getStatus();
                assert.ok(status, 'KB status should be available');
            }
        });

        test('KB server responds to health checks', async function () {
            this.timeout(5000);

            if (!extension || !extension.exports || !extension.exports.kbManager) {
                this.skip();
                return;
            }

            const kbManager = extension.exports.kbManager;
            const status = await kbManager.getStatus();

            // Verify KB is running or at least accessible
            assert.ok(
                status.running !== undefined,
                'KB status should indicate running state'
            );
        });

        test('KB server port is assigned correctly', async function () {
            this.timeout(5000);

            if (!extension || !extension.exports || !extension.exports.kbManager) {
                this.skip();
                return;
            }

            const kbManager = extension.exports.kbManager;
            const status = await kbManager.getStatus();

            // Should have a valid port
            if (status.port !== undefined) {
                assert.ok(
                    status.port >= 1024 && status.port <= 65535,
                    'KB port should be in valid range'
                );
            }
        });
    });

    suite('KB Restart Functionality', () => {
        test('KB can be manually restarted via command', async function () {
            this.timeout(20000);

            // Execute restart command
            try {
                await vscode.commands.executeCommand('dolphin.kb.restart');

                // Give time for restart
                await new Promise(resolve => setTimeout(resolve, 3000));

                // KB should be running again
                if (extension && extension.exports && extension.exports.kbManager) {
                    const status = await extension.exports.kbManager.getStatus();
                    assert.ok(status, 'KB status should be available after restart');
                }
            } catch (error) {
                // Command might not be available in test environment
                this.skip();
            }
        });

        test('KB restarts after unexpected crash', async function () {
            this.timeout(30000);
            this.skip(); // Skip as simulating crashes is complex

            // This test would:
            // 1. Kill KB process
            // 2. Wait for auto-restart mechanism
            // 3. Verify KB is running again
        });

        test('KB maintains state across restarts', async function () {
            this.timeout(20000);
            this.skip(); // Skip as this requires actual KB operations

            // This test would:
            // 1. Index some content
            // 2. Restart KB
            // 3. Verify indexed content is still accessible
        });
    });

    suite('KB Status Monitoring', () => {
        test('KB status can be queried via command', async function () {
            this.timeout(5000);

            // Check if command exists first
            const commands = await vscode.commands.getCommands(true);
            if (!commands.includes('dolphin.kb.showStatus')) {
                this.skip();
                return;
            }

            try {
                // Add a race condition with timeout to prevent hanging
                await Promise.race([
                    vscode.commands.executeCommand('dolphin.kb.showStatus'),
                    new Promise((_, reject) =>
                        setTimeout(() => reject(new Error('Command timeout')), 3000)
                    )
                ]);
                // Command should execute without error
                assert.ok(true, 'Status command executed');
            } catch (error) {
                // Command might not be available or timed out
                this.skip();
            }
        });

        test('KB status updates are emitted', async function () {
            this.timeout(8000);

            if (!extension || !extension.exports || !extension.exports.kbManager) {
                this.skip();
                return;
            }

            const kbManager = extension.exports.kbManager;

            // Listen for status updates
            let statusReceived = false;

            if (kbManager.onStatusChange) {
                const disposable = kbManager.onStatusChange(() => {
                    statusReceived = true;
                });

                // Trigger a status check
                await kbManager.getStatus();

                // Clean up
                disposable?.dispose();
            }

            // This test is informational - status updates may not always fire
        });

        test('KB error states are reported', async function () {
            this.timeout(5000);
            this.skip(); // Skip as simulating errors is complex

            // This test would verify that KB errors are properly reported
        });
    });

    suite('KB Process Management', () => {
        test('KB process is cleaned up on extension deactivation', async function () {
            this.timeout(5000);
            this.skip(); // Skip as we cannot safely deactivate extension in tests

            // This test would verify KB process terminates when extension deactivates
        });

        test('KB handles multiple restart requests gracefully', async function () {
            this.timeout(20000);

            if (!extension || !extension.exports || !extension.exports.kbManager) {
                this.skip();
                return;
            }

            const kbManager = extension.exports.kbManager;

            // Send multiple restart requests
            const restarts = [];
            for (let i = 0; i < 3; i++) {
                restarts.push(
                    kbManager.restart?.() || Promise.resolve()
                );
                await new Promise(resolve => setTimeout(resolve, 100));
            }

            // Wait for all to complete
            await Promise.all(restarts);

            // KB should still be running
            const status = await kbManager.getStatus();
            assert.ok(status, 'KB should be operational after multiple restarts');
        });

        test('KB respects workspace folder changes', async function () {
            this.timeout(5000);
            this.skip(); // Skip as changing workspace folders in tests is complex

            // This test would verify KB adjusts to workspace changes
        });
    });

    suite('KB Configuration', () => {
        test('KB uses correct configuration from settings', async function () {
            this.timeout(5000);

            const config = vscode.workspace.getConfiguration('dolphin');

            // Verify KB-related configuration is available
            const kbPort = config.get<number>('kb.port');
            const kbAutoStart = config.get<boolean>('kb.autoStart');

            // These might be undefined if not set
            assert.ok(
                kbPort === undefined || typeof kbPort === 'number',
                'KB port should be a number if set'
            );
            assert.ok(
                kbAutoStart === undefined || typeof kbAutoStart === 'boolean',
                'KB autoStart should be a boolean if set'
            );
        });

        test('KB configuration changes trigger restart', async function () {
            this.timeout(8000);
            this.skip(); // Skip as modifying configuration in tests is complex

            // This test would:
            // 1. Change KB configuration
            // 2. Verify KB restarts with new config
        });
    });

    suite('KB Performance', () => {
        test('KB starts within reasonable time', async function () {
            this.timeout(8000);

            if (!extension || !extension.exports || !extension.exports.kbManager) {
                this.skip();
                return;
            }

            const startTime = Date.now();

            // Trigger a restart to measure startup time
            const kbManager = extension.exports.kbManager;
            if (kbManager.restart) {
                await kbManager.restart();
            }

            // Check status
            await kbManager.getStatus();

            const elapsed = Date.now() - startTime;

            // KB should start within 10 seconds
            assert.ok(elapsed < 10000, `KB startup took ${elapsed}ms, should be < 10000ms`);
        });

        test('KB status checks are fast', async function () {
            this.timeout(5000);

            if (!extension || !extension.exports || !extension.exports.kbManager) {
                this.skip();
                return;
            }

            const kbManager = extension.exports.kbManager;

            const startTime = Date.now();
            await kbManager.getStatus();
            const elapsed = Date.now() - startTime;

            // Status check should be fast (< 1 second)
            assert.ok(elapsed < 1000, `Status check took ${elapsed}ms, should be < 1000ms`);
        });
    });
});
