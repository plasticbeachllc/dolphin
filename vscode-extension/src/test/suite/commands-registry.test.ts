/**
 * Consolidated command registration tests.
 * This replaces duplicated command tests previously in 4 different files.
 */

import * as assert from "assert";
import { TEST_COMMANDS } from "../helpers/test-constants";
import { assertCommandsExist, activateExtension } from "../helpers/shared-fixtures";

suite("Command Registration", function () {
  this.timeout(10000);

  suiteSetup(async () => {
    await activateExtension();
  });

  test("All Phase 1 commands should be registered", async () => {
    const phase1Commands = [
      TEST_COMMANDS.FOCUS_INPUT,
      TEST_COMMANDS.NEW_CONVERSATION,
      TEST_COMMANDS.SET_API_KEY,
      TEST_COMMANDS.TEST,
    ];

    await assertCommandsExist(phase1Commands);
  });

  test("All Phase 2 commands should be registered", async () => {
    const phase2Commands = [
      TEST_COMMANDS.ASK_ABOUT_SELECTION,
      TEST_COMMANDS.REFACTOR_SELECTION,
      TEST_COMMANDS.ASK_ABOUT_FILE,
      TEST_COMMANDS.ASK_ABOUT_FOLDER,
      TEST_COMMANDS.APPLY_DIFF,
    ];

    await assertCommandsExist(phase2Commands);
  });

  test("All KB commands should be registered", async () => {
    const kbCommands = [TEST_COMMANDS.KB_SHOW_STATUS, TEST_COMMANDS.KB_RESTART];

    await assertCommandsExist(kbCommands);
  });

  test("Total command count should be at least 11", async () => {
    const allCommands = Object.values(TEST_COMMANDS);

    assert.ok(
      allCommands.length >= 11,
      `Should have at least 11 commands, found ${allCommands.length}`
    );
  });
});
