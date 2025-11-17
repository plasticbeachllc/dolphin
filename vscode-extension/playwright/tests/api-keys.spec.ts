import { chromium, expect, test, Page, Browser } from "@playwright/test";
import { spawn, ChildProcess } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CODE_BIN = process.env.VSCODE_BIN ?? "code";
const DEBUG_PORT = Number(process.env.VSCODE_REMOTE_PORT ?? 9333);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PLAYWRIGHT_USER_DATA = path.join(
  os.tmpdir(),
  `dolphin-vscode-playwright-${process.pid}-${Date.now()}`
);

async function waitForDebugger(port: number, retries = 60): Promise<void> {
  for (let attempt = 0; attempt < retries; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) {
        return;
      }
    } catch {
      // ignore and retry
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("VS Code debugger never became ready");
}

async function connectToVSCode(): Promise<Browser> {
  await waitForDebugger(DEBUG_PORT);
  return chromium.connectOverCDP(`http://127.0.0.1:${DEBUG_PORT}`);
}

function launchVSCode(): ChildProcess {
  if (!fs.existsSync(PLAYWRIGHT_USER_DATA)) {
    fs.mkdirSync(PLAYWRIGHT_USER_DATA, { recursive: true });
  }

  const workspacePath = path.resolve(__dirname, "../../test-workspace");
  const extensionPath = path.resolve(__dirname, "..", "..");

  const args = [
    workspacePath,
    `--extensionDevelopmentPath=${extensionPath}`,
    `--user-data-dir=${PLAYWRIGHT_USER_DATA}`,
    `--remote-debugging-port=${DEBUG_PORT}`,
    "--disable-workspace-trust",
    "--skip-release-notes",
    "--skip-welcome",
    "--disable-telemetry",
    "--disable-updates",
    "--disable-gpu",
    "--force-device-scale-factor=1",
    "--locale=en",
  ];

  const child = spawn(CODE_BIN, args, { stdio: "inherit" });
  return child;
}

function modifier(): string {
  return process.platform === "darwin" ? "Meta" : "Control";
}

async function openCommandPalette(page: Page): Promise<void> {
  await page.keyboard.press(`${modifier()}+Shift+P`);
  const quickInput = page.locator(".quick-input-widget");
  await quickInput.waitFor({ state: "visible" });
}

async function runCommand(page: Page, label: string): Promise<void> {
  await openCommandPalette(page);
  await page.keyboard.press(`${modifier()}+A`);
  await page.keyboard.type(label, { delay: 20 });
  const option = page
    .locator(".quick-input-widget .monaco-list-row")
    .filter({ hasText: label })
    .first();
  await option.waitFor({ timeout: 10_000 });
  await option.click();
}

async function fillSecretInput(page: Page, placeholderToken: string, value: string): Promise<void> {
  const secretInput = page
    .locator(`.quick-input-widget input[placeholder*="${placeholderToken}"]`)
    .first();
  await secretInput.waitFor({ timeout: 5_000 });
  await secretInput.fill(value);
  await page.keyboard.press("Enter");
}

async function expectNotification(page: Page, message: string): Promise<void> {
  const item = page
    .locator(".notifications-list-container .notification-list-item .message")
    .filter({ hasText: message })
    .first();
  await item.waitFor({ timeout: 10_000 });
}

async function clickNotificationButton(page: Page, label: string): Promise<void> {
  const button = page
    .locator(".notifications-list-container .monaco-text-button")
    .filter({ hasText: label })
    .first();
  await button.waitFor({ timeout: 5_000 });
  await button.click();
}

test.describe("Dolphin extension API key UX", () => {
  let vsCodeProcess: ChildProcess | undefined;
  let browser: Browser | undefined;
  let page: Page | undefined;

  test.beforeAll(async () => {
    vsCodeProcess = launchVSCode();
    browser = await connectToVSCode();
    const [context] = browser.contexts();
    page = context.pages()[0] ?? (await context.waitForEvent("page"));
    await page.waitForSelector(".monaco-workbench", { timeout: 30_000 });
  });

  test.afterAll(async () => {
    await browser?.close();
    if (vsCodeProcess && !vsCodeProcess.killed) {
      vsCodeProcess.kill("SIGTERM");
    }
    if (fs.existsSync(PLAYWRIGHT_USER_DATA)) {
      fs.rmSync(PLAYWRIGHT_USER_DATA, { recursive: true, force: true });
    }
  });

  test("user can set Anthropic and KB API keys via commands", async () => {
    if (!page) {
      test.fail(true, "VS Code page not initialized");
      return;
    }

    await runCommand(page, "Dolphin: Set API Key");
    await fillSecretInput(page, "sk-ant", "sk-ant-test-1234567890");
    await expectNotification(page, "API key stored securely");

    await runCommand(page, "Dolphin: Set KB API Key");
    await fillSecretInput(page, "kb-local-secret", "kb-key-test-123456");
    await expectNotification(
      page,
      "KB API key stored securely. Restart the Dolphin KB to apply it to the agent?"
    );

    await clickNotificationButton(page, "Later");
  });
});
