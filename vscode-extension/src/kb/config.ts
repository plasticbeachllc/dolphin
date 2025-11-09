// vscode-extension/src/kb/config.ts
import * as vscode from "vscode";
import type { WatcherConfig } from "./file-watcher";

export function loadWatcherConfig(): WatcherConfig {
  try {
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
  } catch (error) {
    // Gracefully handle case where config isn't ready (e.g., during tests)
    // Fall back to safe defaults
    console.warn("[KB Config] Failed to load config, using defaults:", error);
    return {
      debounceMs: 2000,
      batchIntervalMs: 5000,
      excludePatterns: [
        "**/node_modules/**",
        "**/dist/**",
        "**/build/**",
        "**/.git/**",
        "**/out/**",
        "**/*.min.js",
      ],
    };
  }
}
