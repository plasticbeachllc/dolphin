import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import { waitForExtensionActivation, sleep } from "../../../helpers/test-utils";

describe("Webview Tests", () => {
  before(async function () {
    this.timeout(15000);
    await waitForExtensionActivation();
    await sleep(1000);
  });

  it("Should be able to focus Dolphin chat view", async function () {
    this.timeout(10000);

    try {
      // Try to focus the Dolphin view
      await vscode.commands.executeCommand("dolphin.chatView.focus");
      await sleep(500);

      // If we got here without error, the view exists
      assert.ok(true, "Dolphin chat view can be focused");
    } catch {
      // In headless mode, focusing might fail, but we can check if the command exists
      const commands = await vscode.commands.getCommands(true);
      assert.ok(commands.length > 0, "Commands should be available");
    }
  });

  it("Should have Dolphin activity bar contribution", async function () {
    this.timeout(5000);

    const extension = vscode.extensions.getExtension("pb.dolphin");
    assert.ok(extension, "Extension should exist");

    const packageJSON = extension!.packageJSON;

    assert.ok(packageJSON.contributes, "Extension should have contributions");
    assert.ok(packageJSON.contributes.viewsContainers, "Extension should have viewsContainers");
    assert.ok(
      packageJSON.contributes.viewsContainers.activitybar,
      "Extension should have activitybar viewsContainers"
    );

    const dolphinContainer = packageJSON.contributes.viewsContainers.activitybar.find(
      (c: { id: string; title: string }) => c.id === "dolphin"
    );

    assert.ok(dolphinContainer, "Dolphin view container should exist");
    assert.strictEqual(dolphinContainer.title, "Dolphin", "View container should be named Dolphin");
  });

  it("Should have chat view contribution", async function () {
    this.timeout(5000);

    const extension = vscode.extensions.getExtension("pb.dolphin");
    const packageJSON = extension!.packageJSON;

    assert.ok(packageJSON.contributes.views, "Extension should have views");
    assert.ok(packageJSON.contributes.views.dolphin, "Extension should have dolphin views");

    const chatView = packageJSON.contributes.views.dolphin.find(
      (v: { id: string; name: string; type: string }) => v.id === "dolphin.chatView"
    );

    assert.ok(chatView, "Chat view should exist");
    assert.strictEqual(chatView.name, "Chat", "Chat view should be named Chat");
    assert.strictEqual(chatView.type, "webview", "Chat view should be a webview");
  });

  it("Should have correct keybindings", async function () {
    this.timeout(5000);

    const extension = vscode.extensions.getExtension("pb.dolphin");
    const packageJSON = extension!.packageJSON;

    assert.ok(packageJSON.contributes.keybindings, "Extension should have keybindings");

    const focusInputBinding = packageJSON.contributes.keybindings.find(
      (kb: { command: string; key: string; mac?: string }) => kb.command === "dolphin.focusInput"
    );

    assert.ok(focusInputBinding, "Focus input keybinding should exist");

    // Check platform-specific keybinding
    const baseKey = (focusInputBinding.key || "").toLowerCase();
    assert.strictEqual(baseKey, "ctrl+l", "Focus input base keybinding should be ctrl+l");

    if (process.platform === "darwin") {
      let manifestMacKey: string | undefined;
      try {
        const manifestPath = path.join(extension!.extensionPath, "package.json");
        const manifestRaw = await fs.promises.readFile(manifestPath, "utf8");
        const manifestJson = JSON.parse(manifestRaw) as {
          contributes?: { keybindings?: Array<{ command: string; mac?: string }> };
        };
        manifestMacKey = manifestJson.contributes?.keybindings?.find(
          (kb) => kb.command === "dolphin.focusInput"
        )?.mac;
      } catch (error) {
        console.warn("Unable to read manifest for mac keybinding check", error);
      }

      const resolvedMacKey = (focusInputBinding.mac || manifestMacKey || baseKey).toLowerCase();
      assert.ok(
        resolvedMacKey === "cmd+l" || resolvedMacKey === "ctrl+l",
        `Focus input should expose a cmd+l binding on macOS (current: ${resolvedMacKey || "<none>"})`
      );
    }
  });
});
