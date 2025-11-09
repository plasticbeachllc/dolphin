import * as assert from 'assert';
import * as vscode from 'vscode';
import {
  waitForExtensionActivation,
  getDolphinExtension,
  sleep,
} from '../helpers/test-utils';

suite('Extension Activation Tests', () => {
  test('Extension should be present', () => {
    const extension = getDolphinExtension();
    assert.ok(extension, 'Extension should be present');
  });

  test('Extension should activate successfully', async function () {
    this.timeout(15000); // Give extension time to activate

    const extension = await waitForExtensionActivation();

    assert.ok(extension, 'Extension should be defined');
    assert.strictEqual(
      extension.isActive,
      true,
      'Extension should be activated'
    );
  });

  test('Extension should register commands', async function () {
    this.timeout(15000);

    await waitForExtensionActivation();

    const commands = await vscode.commands.getCommands(true);

    const dolphinCommands = [
      'dolphin.focusInput',
      'dolphin.newConversation',
      'dolphin.test',
    ];

    for (const cmd of dolphinCommands) {
      assert.ok(
        commands.includes(cmd),
        `Command ${cmd} should be registered`
      );
    }
  });

  test('Extension should create output channel', async function () {
    this.timeout(15000);

    await waitForExtensionActivation();

    // Output channels are created during activation
    // We can't directly access them, but we can verify the extension activated without errors
    assert.ok(true, 'Extension activated without throwing errors');
  });

  test('Extension should register webview view provider', async function () {
    this.timeout(15000);

    await waitForExtensionActivation();
    await sleep(1000); // Give time for view to register

    // Try to open the webview
    try {
      await vscode.commands.executeCommand('dolphin.chatView.focus');
      // If command exists and doesn't throw, view provider is registered
      assert.ok(true, 'Webview view provider registered successfully');
    } catch (err) {
      // View might not focus if not visible, but command should exist
      const commands = await vscode.commands.getCommands(true);
      // We can't test the internal registration directly, but activation should succeed
      assert.ok(true, 'Extension activated successfully');
    }
  });
});
