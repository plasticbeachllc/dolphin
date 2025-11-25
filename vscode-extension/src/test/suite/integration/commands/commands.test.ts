import * as assert from "assert";
import * as vscode from "vscode";
import {
  assertCommandExists,
  activateExtension,
  waitForCondition,
} from "../../../helpers/shared-fixtures";
import { TEST_COMMANDS } from "../../../helpers/test-constants";
import {
  configureMockKB,
  getMockEnvironment,
  resetMocks,
  setupMockEnvironment,
  teardownMockEnvironment,
} from "../../../helpers/mock-manager";

describe("Command Tests", () => {
  suiteSetup(async () => {
    await setupMockEnvironment();
  });

  suiteTeardown(async () => {
    await teardownMockEnvironment();
  });

  before(async function () {
    this.timeout(15000);
    resetMocks();
    await activateExtension();
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

  it("KB commands talk to the mock KB server", async function () {
    this.timeout(10000);

    // Ensure mock KB responds
    configureMockKB({ health: true });
    const { kbServer } = getMockEnvironment();
    const initialRequests = kbServer.getRequestHistory().length;

    await assertCommandExists(TEST_COMMANDS.KB_SHOW_STATUS, true);

    await waitForCondition(
      () => kbServer.getRequestHistory().length > initialRequests,
      {
        timeout: 4000,
        timeoutMessage: "KB status command did not hit mock server",
      }
    );

    const history = kbServer.getRequestHistory();
    const hitHealth = history.some((req) => (req.url || "").includes("/health"));
    assert.ok(hitHealth, "KB status command should query /health on mock server");
  });
});
