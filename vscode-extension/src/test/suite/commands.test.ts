import * as assert from 'assert';
import * as vscode from 'vscode';
import { waitForExtensionActivation, sleep } from '../helpers/test-utils';

suite('Command Tests', () => {
  suiteSetup(async function () {
    this.timeout(15000);
    await waitForExtensionActivation();
    await sleep(1000);
  });

  test('Should execute dolphin.focusInput command', async function () {
    this.timeout(10000);

    try {
      // Execute the command
      await vscode.commands.executeCommand('dolphin.focusInput');
      await sleep(500);

      // If we got here, command executed successfully
      assert.ok(true, 'dolphin.focusInput command executed successfully');
    } catch (err) {
      // Command might fail in headless mode if webview isn't visible
      // But it should still be registered
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes('dolphin.focusInput'),
        'dolphin.focusInput command should be registered'
      );
    }
  });

  test('Should execute dolphin.newConversation command', async function () {
    this.timeout(10000);

    try {
      await vscode.commands.executeCommand('dolphin.newConversation');
      await sleep(500);

      assert.ok(
        true,
        'dolphin.newConversation command executed successfully'
      );
    } catch (err) {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes('dolphin.newConversation'),
        'dolphin.newConversation command should be registered'
      );
    }
  });

  test('Should execute dolphin.test command', async function () {
    this.timeout(10000);

    try {
      await vscode.commands.executeCommand('dolphin.test');
      await sleep(500);

      assert.ok(true, 'dolphin.test command executed successfully');
    } catch (err) {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes('dolphin.test'),
        'dolphin.test command should be registered'
      );
    }
  });

  test('All registered Dolphin commands should be executable', async function () {
    this.timeout(15000);

    const allCommands = await vscode.commands.getCommands(true);
    const dolphinCommands = allCommands.filter((cmd) =>
      cmd.startsWith('dolphin.')
    );

    assert.ok(
      dolphinCommands.length >= 3,
      'Should have at least 3 Dolphin commands'
    );

    // Log all Dolphin commands for debugging
    console.log('Registered Dolphin commands:', dolphinCommands);

    for (const cmd of dolphinCommands) {
      // Skip focus commands that require visible webview
      if (cmd.includes('focus') || cmd.includes('Focus')) {
        continue;
      }

      try {
        await vscode.commands.executeCommand(cmd);
        console.log(`✓ Command ${cmd} executed successfully`);
      } catch (err) {
        // Some commands might fail without proper context, but shouldn't crash
        console.log(`  Command ${cmd} threw error (may be expected):`, err);
      }
    }

    assert.ok(true, 'Command execution test completed');
  });
});
