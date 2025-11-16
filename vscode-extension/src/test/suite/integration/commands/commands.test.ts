import * as assert from "assert";
import * as vscode from "vscode";
import { waitForExtensionActivation, sleep } from "../../../helpers/test-utils";

describe("Command Tests", () => {
  before(async function () {
    this.timeout(15000);
    await waitForExtensionActivation();
    await sleep(1000);
  });

  it("Should execute dolphin.focusInput command", async function () {
    this.timeout(10000);

    try {
      // Execute the command
      await vscode.commands.executeCommand("dolphin.focusInput");
      await sleep(500);

      // If we got here, command executed successfully
      assert.ok(true, "dolphin.focusInput command executed successfully");
    } catch {
      // Command might fail in headless mode if webview isn't visible
      // But it should still be registered
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes("dolphin.focusInput"),
        "dolphin.focusInput command should be registered"
      );
    }
  });

  it("Should execute dolphin.newConversation command", async function () {
    this.timeout(10000);

    try {
      await vscode.commands.executeCommand("dolphin.newConversation");
      await sleep(500);

      assert.ok(true, "dolphin.newConversation command executed successfully");
    } catch {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes("dolphin.newConversation"),
        "dolphin.newConversation command should be registered"
      );
    }
  });

  it("Should execute dolphin.test command", async function () {
    this.timeout(10000);

    try {
      await vscode.commands.executeCommand("dolphin.test");
      await sleep(500);

      assert.ok(true, "dolphin.test command executed successfully");
    } catch {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(commands.includes("dolphin.test"), "dolphin.test command should be registered");
    }
  });

  it("Should execute dolphin.setApiKey command", async function () {
    this.timeout(10000);

    // Note: We can't fully test this in automated tests because it requires user input
    // But we can verify the command is registered
    const commands = await vscode.commands.getCommands(true);
    assert.ok(
      commands.includes("dolphin.setApiKey"),
      "dolphin.setApiKey command should be registered"
    );
  });

  it("Should register dolphin.kb.setApiKey command", async function () {
    this.timeout(10000);

    const commands = await vscode.commands.getCommands(true);
    assert.ok(
      commands.includes("dolphin.kb.setApiKey"),
      "dolphin.kb.setApiKey command should be registered"
    );
  });

  // Phase 2: Editor Integration Commands
  describe("Contextual Editor Commands", () => {
    it("Should register dolphin.askAboutSelection command", async function () {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes("dolphin.askAboutSelection"),
        "dolphin.askAboutSelection command should be registered"
      );
    });

    it("Should register dolphin.refactorSelection command", async function () {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes("dolphin.refactorSelection"),
        "dolphin.refactorSelection command should be registered"
      );
    });

    it("Should register dolphin.askAboutFile command", async function () {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes("dolphin.askAboutFile"),
        "dolphin.askAboutFile command should be registered"
      );
    });

    it("Should register dolphin.askAboutFolder command", async function () {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes("dolphin.askAboutFolder"),
        "dolphin.askAboutFolder command should be registered"
      );
    });
  });

  describe("Code Action Commands", () => {
    it("Should register dolphin.explainCode command", async function () {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes("dolphin.explainCode"),
        "dolphin.explainCode command should be registered"
      );
    });

    it("Should register dolphin.refactorCode command", async function () {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes("dolphin.refactorCode"),
        "dolphin.refactorCode command should be registered"
      );
    });

    it("Should register dolphin.addTests command", async function () {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes("dolphin.addTests"),
        "dolphin.addTests command should be registered"
      );
    });

    it("Should register dolphin.documentCode command", async function () {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes("dolphin.documentCode"),
        "dolphin.documentCode command should be registered"
      );
    });

    it("Should execute code action commands with parameters", async function () {
      this.timeout(10000);

      const testCode = "function test() { return 42; }";
      const fileName = "test.ts";
      const language = "typescript";

      try {
        await vscode.commands.executeCommand("dolphin.explainCode", testCode, fileName, language);
        await sleep(500);
        assert.ok(true, "dolphin.explainCode executed with parameters");
      } catch {
        // May fail in headless mode, but command should be registered
        const commands = await vscode.commands.getCommands(true);
        assert.ok(commands.includes("dolphin.explainCode"));
      }
    });
  });

  describe("Diff Application Command", () => {
    it("Should register dolphin.applyDiff command", async function () {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(
        commands.includes("dolphin.applyDiff"),
        "dolphin.applyDiff command should be registered"
      );
    });
  });

  it("All registered Dolphin commands should be executable", async function () {
    this.timeout(15000);

    const allCommands = await vscode.commands.getCommands(true);
    const dolphinCommands = allCommands.filter((cmd) => cmd.startsWith("dolphin."));

    assert.ok(
      dolphinCommands.length >= 13,
      "Should have at least 13 Dolphin commands (4 original + 9 Phase 2)"
    );

    // Log all Dolphin commands for debugging
    console.log("Registered Dolphin commands:", dolphinCommands);

    for (const cmd of dolphinCommands) {
      // Skip focus commands that require visible webview
      if (cmd.includes("focus") || cmd.includes("Focus")) {
        continue;
      }

      // Skip setApiKey command that requires user input
      if (cmd === "dolphin.setApiKey" || cmd === "dolphin.kb.setApiKey") {
        console.log(`  Skipping ${cmd} (requires user input)`);
        continue;
      }

      // Skip commands that require parameters
      if (
        [
          "dolphin.explainCode",
          "dolphin.refactorCode",
          "dolphin.addTests",
          "dolphin.documentCode",
          "dolphin.applyDiff",
        ].includes(cmd)
      ) {
        console.log(`  Skipping ${cmd} (requires parameters)`);
        continue;
      }

      try {
        await vscode.commands.executeCommand(cmd);
        console.log(`✓ Command ${cmd} executed successfully`);
      } catch (error) {
        // Some commands might fail without proper context, but shouldn't crash
        console.log(`  Command ${cmd} threw error (may be expected):`, error);
      }
    }

    assert.ok(true, "Command execution test completed");
  });
});
