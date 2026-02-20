/**
 * Consolidated extension activation tests.
 * This replaces duplicated activation tests previously in 5 different files.
 */

import * as assert from "assert";
import * as vscode from "vscode";
import { activateExtension } from "../../../helpers/shared-fixtures";

describe("Extension Activation", function () {
  this.timeout(10000);

  it("Extension should be present", () => {
    const ext = vscode.extensions.getExtension("pb.dolphin");
    assert.ok(ext, "Extension should be installed");
  });

  it("Extension should activate successfully", async () => {
    const ext = await activateExtension();
    assert.ok(ext.isActive, "Extension should be active");
  });

  it("Extension should provide exports", async () => {
    const ext = await activateExtension();
    const exports = ext.exports;

    assert.ok(exports, "Extension should export an API");
    // The extension may provide various exports depending on implementation
    // This test just verifies that exports exist
  });

  it("Extension should have correct package metadata", () => {
    const ext = vscode.extensions.getExtension("pb.dolphin");
    assert.ok(ext, "Extension should be installed");

    const packageJSON = ext.packageJSON;
    assert.strictEqual(packageJSON.name, "dolphin", "Package name should be dolphin");
    assert.strictEqual(packageJSON.publisher, "pb", "Publisher should be pb");
    assert.ok(packageJSON.version, "Should have version");
  });

  it("Extension should register activity bar view", () => {
    const ext = vscode.extensions.getExtension("pb.dolphin");
    assert.ok(ext, "Extension should be installed");

    const packageJSON = ext.packageJSON;
    assert.ok(packageJSON.contributes, "Should have contributions");
    assert.ok(packageJSON.contributes.viewsContainers, "Should contribute view containers");
    assert.ok(
      packageJSON.contributes.viewsContainers.activitybar,
      "Should contribute to activity bar"
    );

    const dolphinContainer = packageJSON.contributes.viewsContainers.activitybar.find(
      (c: { id: string; title: string }) => c.id === "dolphin"
    );
    assert.ok(dolphinContainer, "Should have dolphin view container");
    assert.strictEqual(dolphinContainer.title, "Dolphin", "Container title should be Dolphin");
  });

  it("Extension should register chat view", () => {
    const ext = vscode.extensions.getExtension("pb.dolphin");
    assert.ok(ext, "Extension should be installed");

    const packageJSON = ext.packageJSON;
    assert.ok(packageJSON.contributes.views, "Should contribute views");
    assert.ok(packageJSON.contributes.views.dolphin, "Should contribute to dolphin container");

    const chatView = packageJSON.contributes.views.dolphin.find(
      (v: { id: string; type: string }) => v.id === "dolphin.chatView"
    );
    assert.ok(chatView, "Should have chat view");
    assert.strictEqual(chatView.type, "webview", "Chat view should be webview type");
  });
});
