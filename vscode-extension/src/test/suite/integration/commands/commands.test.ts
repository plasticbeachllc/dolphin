import * as assert from "assert";
import * as vscode from "vscode";
import {
  assertCommandExists,
  assertCommandsExist,
  activateExtension,
} from "../../../helpers/shared-fixtures";
import { TEST_COMMANDS } from "../../../helpers/test-constants";

describe("Command Tests", () => {
  before(async function () {
    this.timeout(15000);
    await activateExtension();
  });

  it("Registers all Phase 1 commands", async () => {
    await assertCommandsExist([
      TEST_COMMANDS.FOCUS_INPUT,
      TEST_COMMANDS.NEW_CONVERSATION,
      TEST_COMMANDS.SET_API_KEY,
      TEST_COMMANDS.TEST,
    ]);
  });

  it("Registers all Phase 2 editor commands", async () => {
    await assertCommandsExist([
      TEST_COMMANDS.ASK_ABOUT_SELECTION,
      TEST_COMMANDS.REFACTOR_SELECTION,
      TEST_COMMANDS.ASK_ABOUT_FILE,
      TEST_COMMANDS.ASK_ABOUT_FOLDER,
      TEST_COMMANDS.APPLY_DIFF,
    ]);
  });

  it("Registers KB commands", async () => {
    await assertCommandsExist([
      TEST_COMMANDS.KB_SHOW_STATUS,
      TEST_COMMANDS.KB_RESTART,
      TEST_COMMANDS.KB_SET_API_KEY,
    ]);
  });

  it("Executes smoke-test friendly commands", async function () {
    this.timeout(15000);

    // Commands that should execute without UI prompts or parameters
    await assertCommandExists(TEST_COMMANDS.TEST, true);
    await assertCommandExists(TEST_COMMANDS.KB_SHOW_STATUS, true);
    await assertCommandExists(TEST_COMMANDS.KB_RESTART, true);
  });

  it("Exposes all Dolphin commands via VS Code registry", async () => {
    const allCommands = await vscode.commands.getCommands(true);
    const dolphinCommands = allCommands.filter((cmd) => cmd.startsWith("dolphin."));

    assert.ok(dolphinCommands.length >= 13, "Should register all expected Dolphin commands");
    assert.ok(
      dolphinCommands.includes(TEST_COMMANDS.FOCUS_INPUT),
      "focusInput should be registered"
    );
    assert.ok(
      dolphinCommands.includes(TEST_COMMANDS.ASK_ABOUT_SELECTION),
      "askAboutSelection should be registered"
    );
    assert.ok(dolphinCommands.includes(TEST_COMMANDS.APPLY_DIFF), "applyDiff should be registered");
  });
});
