import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const DEFAULT_DEBUG_PORT = Number(process.env.VSCODE_REMOTE_PORT ?? 9333);

export default defineConfig({
  testDir: path.resolve(__dirname, "tests"),
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    trace: "on-first-retry",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
    baseURL: `http://127.0.0.1:${DEFAULT_DEBUG_PORT}`,
    ...devices["Desktop Chrome"],
  },
});
