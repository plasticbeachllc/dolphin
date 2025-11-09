// vscode-extension/src/kb/config.ts
import * as vscode from "vscode";
import type { WatcherConfig } from "./file-watcher";

export function loadWatcherConfig(): WatcherConfig {
  const config = vscode.workspace.getConfiguration("dolphin.kb");

  return {
    debounceMs: config.get("debounceMs", 2000),
    batchIntervalMs: config.get("batchIntervalMs", 5000),
    excludePatterns: config.get("excludePatterns", [
      "**/node_modules/**",
      "**/dist/**",
      "**/build/**",
      "**/.git/**",
      "**/out/**",
      "**/*.min.js",
    ]),
  };
}
