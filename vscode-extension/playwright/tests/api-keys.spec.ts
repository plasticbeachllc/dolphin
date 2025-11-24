import { expect, test, Page } from "@playwright/test";
import { _electron as electron, ElectronApplication } from "playwright";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const EXTENSION_ROOT = path.resolve(__dirname, "..", "..");
const DEFAULT_VSCODE_PATH =
  process.platform === "darwin"
    ? "/Applications/Visual Studio Code.app/Contents/MacOS/Electron"
    : process.platform === "win32"
      ? "C:\\Program Files\\Microsoft VS Code\\Code.exe"
      : "/usr/bin/code";

function resolveCodeExecutable(): string {
  const candidates: Array<string | undefined> = [
    process.env.VSCODE_BIN,
    DEFAULT_VSCODE_PATH,
    // Prefer the already-downloaded VS Code used by integration tests
    path.join(
      EXTENSION_ROOT,
      ".vscode-test",
      "vscode-darwin-arm64-1.106.0",
      "Contents",
      "MacOS",
      "Electron"
    ),
    path.join(EXTENSION_ROOT, ".vscode-test", "vscode-linux-x64-1.106.0", "bin", "code"),
    path.join(EXTENSION_ROOT, ".vscode-test", "vscode-win32-x64-1.106.0", "Code.exe"),
  ];

  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }

  throw new Error(
    "VS Code executable not found. Set VSCODE_BIN to a VS Code binary or ensure integration-test download exists."
  );
}

// Default ON; set PLAYWRIGHT_VSCODE_ENABLED=0 to skip locally.
const RUN_VSCODE_UI = process.env.PLAYWRIGHT_VSCODE_ENABLED !== "0";
let CODE_BIN: string | null = null;
if (RUN_VSCODE_UI) {
  try {
    CODE_BIN = resolveCodeExecutable();
  } catch {
    CODE_BIN = null;
  }
}
const PLAYWRIGHT_USER_DATA = path.join(
  os.tmpdir(),
  `dolphin-vscode-playwright-${process.pid}-${Date.now()}`
);

function ensureTempDir(dir: string): void {
  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  fs.mkdirSync(dir, { recursive: true });
}

async function launchVSCode(): Promise<ElectronApplication> {
  ensureTempDir(PLAYWRIGHT_USER_DATA);

  const workspacePath = path.resolve(__dirname, "../../test-workspace");
  const extensionPath = path.resolve(__dirname, "..", "..");

  const args = [
    workspacePath,
    `--extensionDevelopmentPath=${extensionPath}`,
    `--user-data-dir=${PLAYWRIGHT_USER_DATA}`,
    "--disable-workspace-trust",
    "--skip-release-notes",
    "--skip-welcome",
    "--disable-telemetry",
    "--disable-updates",
    "--disable-gpu",
    "--force-device-scale-factor=1",
    "--locale=en",
  ];

  return electron.launch({
    executablePath: CODE_BIN,
    args,
    env: {
      ...process.env,
      ELECTRON_ENABLE_LOGGING: "1",
      ELECTRON_ENABLE_STACK_DUMPING: "1",
    },
  });
}

function modifier(): string {
  return process.platform === "darwin" ? "Meta" : "Control";
}

async function openCommandPalette(page: Page): Promise<void> {
  const quickInput = page.locator(".quick-input-widget");

  // Give VS Code focus before sending shortcuts
  await page.click(".monaco-workbench", { position: { x: 10, y: 10 } }).catch(() => {});

  const attempts = 6;
  for (let i = 0; i < attempts; i++) {
    // Try F1 (default Command Palette) then Ctrl/Cmd+Shift+P
    await page.keyboard.press("F1").catch(() => {});
    if (await quickInput.isVisible()) return;

    await page.keyboard.press(`${modifier()}+Shift+P`).catch(() => {});
    try {
      await quickInput.waitFor({ state: "visible", timeout: 1500 });
      return;
    } catch {
      // palette not visible yet, try again
    }
    await page.waitForTimeout(250);
  }

  // Last check before failing
  await quickInput.waitFor({ state: "visible", timeout: 2000 });
}

async function runCommand(page: Page, label: string): Promise<void> {
  await openCommandPalette(page);
  await page.keyboard.press(`${modifier()}+A`);
  await page.keyboard.type(`>${label}`, { delay: 15 });
  const targetEntry = page
    .locator(".quick-input-widget .monaco-list-row")
    .filter({ hasText: label })
    .first();
  await targetEntry.waitFor({ timeout: 3_000 }).catch(() => {});
  await page.keyboard.press("Enter");
}

async function fillSecretInput(
  page: Page,
  placeholderToken: string,
  value: string,
  retry?: () => Promise<void>
): Promise<void> {
  const secretInput = page
    .locator(`.quick-input-widget input[placeholder*="${placeholderToken}"]`)
    .first();
  try {
    await secretInput.waitFor({ timeout: 5_000 });
  } catch (error) {
    if (!retry) {
      throw error;
    }
    await retry();
    await secretInput.waitFor({ timeout: 5_000 });
  }
  await secretInput.fill(value);
  await page.keyboard.press("Enter");
}

async function showOutputPanel(page: Page): Promise<ReturnType<Page["locator"]>> {
  const outputPanel = page.locator(".output-view");

  const runCommand = async (command: string) => {
    await openCommandPalette(page);
    await page.keyboard.press(`${modifier()}+A`);
    await page.keyboard.type(command, { delay: 15 });
    await page.keyboard.press("Enter");
  };

  await runCommand(">View: Show Output");
  try {
    await outputPanel.waitFor({ state: "visible", timeout: 10_000 });
  } catch {
    await runCommand(">View: Toggle Panel");
    await runCommand(">View: Show Output");
    await outputPanel.waitFor({ state: "visible", timeout: 10_000 });
  }

  return outputPanel;
}

async function expectOutputLog(page: Page, text: string): Promise<void> {
  const outputPanel = await showOutputPanel(page);

  // Select Dolphin output channel
  await openCommandPalette(page);
  await page.keyboard.press(`${modifier()}+A`);
  await page.keyboard.type(">Developer: Select Log Output", { delay: 15 });
  await page.keyboard.press("Enter");
  await page.keyboard.type("Dolphin", { delay: 30 });
  await page.keyboard.press("Enter");

  const logLines = outputPanel.locator(".monaco-scrollable-element .view-lines");
  await expect(logLines).toContainText(text, { timeout: 20_000 });
}

async function delay(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function cleanupProcess(app: ElectronApplication | undefined): Promise<void> {
  await app?.close().catch(() => {});
}

test.describe("Dolphin extension API key UX", () => {
  let electronApp: ElectronApplication | undefined;
  let page: Page | undefined;
  let launchFailed = false;

  test.beforeAll(async () => {
    if (!RUN_VSCODE_UI) {
      launchFailed = true;
      test.skip(
        true,
        "Playwright VS Code UI tests disabled (set PLAYWRIGHT_VSCODE_ENABLED=1 to run)."
      );
      return;
    }
    if (!CODE_BIN) {
      launchFailed = true;
      test.skip(true, "VS Code executable not available; skipping Playwright UX test");
      return;
    }

    const maxAttempts = 2;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        electronApp = await launchVSCode();
        page = await electronApp.firstWindow();
        await page.waitForSelector(".monaco-workbench", { timeout: 60_000 });
        return;
      } catch (error) {
        await cleanupProcess(electronApp);
        electronApp = undefined;
        if (attempt === maxAttempts) {
          launchFailed = true;
          test.skip(true, "VS Code executable not available for Playwright run");
        }
        await delay(3_000);
      }
    }
  });

  test.afterAll(async () => {
    await cleanupProcess(electronApp);
    if (fs.existsSync(PLAYWRIGHT_USER_DATA)) {
      fs.rmSync(PLAYWRIGHT_USER_DATA, { recursive: true, force: true });
    }
  });

  test("user can set Anthropic and KB API keys via commands", async () => {
    if (launchFailed) {
      test.skip(true, "VS Code executable not available for Playwright run");
      return;
    }
    if (!page) {
      test.fail(true, "VS Code page not initialized");
      return;
    }

    await runCommand(page, "Dolphin: Set API Key");
    await fillSecretInput(page, "sk-ant", "sk-ant-test-1234567890", async () => {
      await runCommand(page, "Dolphin: Set API Key");
    });
    await expectOutputLog(page, "API key stored in SecretStorage");

    await runCommand(page, "Dolphin: Set KB API Key");
    await fillSecretInput(page, "kb-local-secret", "kb-key-test-123456", async () => {
      await runCommand(page, "Dolphin: Set KB API Key");
    });
    await expectOutputLog(page, "KB API key stored securely");
  });
});
