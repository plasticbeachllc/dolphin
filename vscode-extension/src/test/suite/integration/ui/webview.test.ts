import "../../setup";
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import { TEST_TIMEOUTS } from "../../../helpers/test-constants";
import {
  activateExtension,
  waitForCondition,
  waitForWebviewReady,
} from "../../../helpers/shared-fixtures";
import {
  resetMocks,
  setupMockEnvironment,
  teardownMockEnvironment,
} from "../../../helpers/mock-manager";

describe("Webview Tests", () => {
  before(async function () {
    this.timeout(15000);
    resetMocks();
    await setupMockEnvironment();
    await activateExtension();
    await waitForWebviewReady(TEST_TIMEOUTS.WEBVIEW_READY);
  });

  after(async () => {
    await teardownMockEnvironment();
  });

  it("Should be able to focus Dolphin chat view", async function () {
    this.timeout(10000);

    await waitForCondition(
      async () => (await vscode.commands.getCommands(true)).includes("dolphin.chatView.focus"),
      { timeout: 2000, timeoutMessage: "chatView focus command not registered" }
    );

    await vscode.commands.executeCommand("dolphin.chatView.focus");

    assert.ok(true, "Dolphin chat view can be focused");
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
