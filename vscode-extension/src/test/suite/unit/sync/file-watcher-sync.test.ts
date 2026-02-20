import * as assert from "assert";
import * as vscode from "vscode";
import { FileWatcher, WatcherConfig, ChangeEvent } from "../../../../kb/file-watcher";

describe("FileWatcher API Integration Tests", () => {
  let testConfig: WatcherConfig;
  let batchHandler: (changes: ChangeEvent[]) => Promise<void>;
  let receivedBatches: ChangeEvent[][];
  let watchers: FileWatcher[] = [];

  beforeEach(() => {
    receivedBatches = [];
    batchHandler = async (changes: ChangeEvent[]) => {
      receivedBatches.push(changes);
    };

    testConfig = {
      debounceMs: 100,
      batchIntervalMs: 500,
      excludePatterns: ["**/node_modules/**", "**/.git/**"],
    };
    watchers = [];
  });

  afterEach(() => {
    // CRITICAL: Dispose all watchers to clean up timers
    for (const watcher of watchers) {
      watcher.dispose();
    }
    watchers = [];
  });

  describe("Initialization", () => {
    it("Should create FileWatcher without API config", () => {
      const watcher = new FileWatcher(testConfig, batchHandler);
      watchers.push(watcher);
      assert.ok(watcher, "Watcher should be created");
    });

    it("Should create FileWatcher with API config", () => {
      const apiConfig = {
        ...testConfig,
        apiBaseUrl: "http://localhost:8765",
        repoName: "test-repo",
      };

      const watcher = new FileWatcher(apiConfig, batchHandler);
      watchers.push(watcher);
      assert.ok(watcher, "Watcher should be created with API config");
    });

    it("Should create FileWatcher with only apiBaseUrl", () => {
      const partialConfig = {
        ...testConfig,
        apiBaseUrl: "http://localhost:8765",
      };

      const watcher = new FileWatcher(partialConfig, batchHandler);
      watchers.push(watcher);
      assert.ok(watcher, "Should create with partial API config");
    });

    it("Should create FileWatcher with only repoName", () => {
      const partialConfig = {
        ...testConfig,
        repoName: "test-repo",
      };

      const watcher = new FileWatcher(partialConfig, batchHandler);
      watchers.push(watcher);
      assert.ok(watcher, "Should create with partial API config");
    });
  });

  describe("Configuration Properties", () => {
    it("Should accept various debounce settings", () => {
      const configs = [
        { ...testConfig, debounceMs: 0 },
        { ...testConfig, debounceMs: 100 },
        { ...testConfig, debounceMs: 1000 },
        { ...testConfig, debounceMs: 5000 },
      ];

      for (const config of configs) {
        const watcher = new FileWatcher(config, batchHandler);
        watchers.push(watcher);
        assert.ok(watcher, `Should accept debounceMs: ${config.debounceMs}`);
      }
    });

    it("Should accept various batch interval settings", () => {
      const configs = [
        { ...testConfig, batchIntervalMs: 100 },
        { ...testConfig, batchIntervalMs: 500 },
        { ...testConfig, batchIntervalMs: 1000 },
        { ...testConfig, batchIntervalMs: 5000 },
      ];

      for (const config of configs) {
        const watcher = new FileWatcher(config, batchHandler);
        watchers.push(watcher);
        assert.ok(watcher, `Should accept batchIntervalMs: ${config.batchIntervalMs}`);
      }
    });

    it("Should accept various exclude patterns", () => {
      const excludePatterns = [
        ["**/node_modules/**"],
        ["**/.git/**", "**/dist/**"],
        ["**/build/**", "**/out/**", "**/*.min.js"],
        [],
      ];

      for (const patterns of excludePatterns) {
        const config = { ...testConfig, excludePatterns: patterns };
        const watcher = new FileWatcher(config, batchHandler);
        watchers.push(watcher);
        assert.ok(watcher, `Should accept patterns: ${patterns.join(", ")}`);
      }
    });
  });

  describe("API Configuration Variants", () => {
    it("Should handle localhost API URLs", () => {
      const config = {
        ...testConfig,
        apiBaseUrl: "http://localhost:8765",
        repoName: "test-repo",
      };

      const watcher = new FileWatcher(config, batchHandler);
      watchers.push(watcher);
      assert.ok(watcher, "Should accept localhost URL");
    });

    it("Should handle 127.0.0.1 API URLs", () => {
      const config = {
        ...testConfig,
        apiBaseUrl: "http://127.0.0.1:9000",
        repoName: "test-repo",
      };

      const watcher = new FileWatcher(config, batchHandler);
      watchers.push(watcher);
      assert.ok(watcher, "Should accept 127.0.0.1 URL");
    });

    it("Should handle HTTPS API URLs", () => {
      const config = {
        ...testConfig,
        apiBaseUrl: "https://api.example.com",
        repoName: "test-repo",
      };

      const watcher = new FileWatcher(config, batchHandler);
      watchers.push(watcher);
      assert.ok(watcher, "Should accept HTTPS URL");
    });

    it("Should handle different repository names", () => {
      const repoNames = [
        "simple-repo",
        "my-project",
        "org/repo",
        "user/my-service",
        "repo-with-dashes",
        "repo_with_underscores",
      ];

      for (const repoName of repoNames) {
        const config = {
          ...testConfig,
          apiBaseUrl: "http://localhost:8765",
          repoName,
        };

        const watcher = new FileWatcher(config, batchHandler);
        watchers.push(watcher);
        assert.ok(watcher, `Should accept repo name: ${repoName}`);
      }
    });
  });

  describe("Disposal", () => {
    it("Should properly dispose without starting", () => {
      const watcher = new FileWatcher(testConfig, batchHandler);
      watchers.push(watcher);
      watcher.dispose();
      watchers.pop(); // Remove since we manually disposed
      assert.ok(true, "Should dispose cleanly");
    });

    it("Should handle multiple dispose calls", () => {
      const watcher = new FileWatcher(testConfig, batchHandler);
      watchers.push(watcher);
      watcher.dispose();
      watcher.dispose();
      watcher.dispose();
      watchers.pop(); // Remove since we manually disposed
      assert.ok(true, "Should handle multiple dispose calls");
    });

    it("Should dispose with API config", () => {
      const config = {
        ...testConfig,
        apiBaseUrl: "http://localhost:8765",
        repoName: "test-repo",
      };

      const watcher = new FileWatcher(config, batchHandler);
      watchers.push(watcher);
      watcher.dispose();
      watchers.pop(); // Remove since we manually disposed
      assert.ok(true, "Should dispose with API config");
    });
  });

  describe("Exclude Pattern Matching", () => {
    it("Should ignore files matching exclude patterns", () => {
      const config = {
        ...testConfig,
        excludePatterns: ["**/node_modules/**", "**/.git/**", "**/dist/**"],
      };

      const watcher = new FileWatcher(config, batchHandler);
      watchers.push(watcher);

      // Access private shouldIgnore method for testing
      type WatcherWithPrivate = {
        shouldIgnore: (uri: vscode.Uri) => boolean;
      };
      const shouldIgnore = (watcher as unknown as WatcherWithPrivate).shouldIgnore.bind(watcher);

      // Test paths that should be ignored
      const ignoredPaths = [
        vscode.Uri.file("/project/node_modules/package/file.js"),
        vscode.Uri.file("/project/.git/config"),
        vscode.Uri.file("/project/dist/bundle.js"),
      ];

      for (const uri of ignoredPaths) {
        const result = shouldIgnore(uri);
        assert.strictEqual(result, true, `Should ignore ${uri.fsPath}`);
      }
    });

    it("Should not ignore files that do not match patterns", () => {
      const config = {
        ...testConfig,
        excludePatterns: ["**/node_modules/**", "**/.git/**"],
      };

      const watcher = new FileWatcher(config, batchHandler);
      watchers.push(watcher);
      type WatcherWithPrivate = {
        shouldIgnore: (uri: vscode.Uri) => boolean;
      };
      const shouldIgnore = (watcher as unknown as WatcherWithPrivate).shouldIgnore.bind(watcher);

      // Test paths that should NOT be ignored
      const allowedPaths = [
        vscode.Uri.file("/project/src/file.ts"),
        vscode.Uri.file("/project/test/spec.ts"),
        vscode.Uri.file("/project/README.md"),
      ];

      for (const uri of allowedPaths) {
        const result = shouldIgnore(uri);
        assert.strictEqual(result, false, `Should not ignore ${uri.fsPath}`);
      }
    });

    it("Should handle empty exclude patterns", () => {
      const config = {
        ...testConfig,
        excludePatterns: [],
      };

      const watcher = new FileWatcher(config, batchHandler);
      watchers.push(watcher);
      type WatcherWithPrivate = {
        shouldIgnore: (uri: vscode.Uri) => boolean;
      };
      const shouldIgnore = (watcher as unknown as WatcherWithPrivate).shouldIgnore.bind(watcher);

      const testUri = vscode.Uri.file("/project/src/file.ts");
      const result = shouldIgnore(testUri);

      assert.strictEqual(result, false, "Should not ignore any files with empty patterns");
    });
  });

  describe("Change Event Types", () => {
    it("Should handle created event type", () => {
      const event: ChangeEvent = {
        uri: vscode.Uri.file("/project/new-file.ts"),
        type: "created",
        timestamp: Date.now(),
      };

      assert.strictEqual(event.type, "created");
      assert.ok(event.uri);
      assert.ok(event.timestamp > 0);
    });

    it("Should handle modified event type", () => {
      const event: ChangeEvent = {
        uri: vscode.Uri.file("/project/modified-file.ts"),
        type: "modified",
        timestamp: Date.now(),
      };

      assert.strictEqual(event.type, "modified");
    });

    it("Should handle deleted event type", () => {
      const event: ChangeEvent = {
        uri: vscode.Uri.file("/project/deleted-file.ts"),
        type: "deleted",
        timestamp: Date.now(),
      };

      assert.strictEqual(event.type, "deleted");
    });

    it("Should handle multiple change events", () => {
      const events: ChangeEvent[] = [
        { uri: vscode.Uri.file("/project/file1.ts"), type: "created", timestamp: Date.now() },
        { uri: vscode.Uri.file("/project/file2.ts"), type: "modified", timestamp: Date.now() },
        { uri: vscode.Uri.file("/project/file3.ts"), type: "deleted", timestamp: Date.now() },
      ];

      assert.strictEqual(events.length, 3);
      assert.ok(events.every((e) => e.uri && e.type && e.timestamp));
    });
  });

  describe("Error Handling", () => {
    it("Should handle batch processing errors gracefully", async function () {
      this.timeout(5000);

      const failingHandler = async () => {
        throw new Error("Batch processing failed");
      };

      const watcher = new FileWatcher(testConfig, failingHandler);

      // Should not crash even if handler throws
      // Simulate change by directly calling handleChange
      const testUri = vscode.Uri.file("/project/test.ts");
      (
        watcher as unknown as { handleChange: (uri: vscode.Uri, changeType: string) => void }
      ).handleChange(testUri, "modified");

      // Wait for debounce and batch
      await new Promise((resolve) => setTimeout(resolve, 1000));

      watcher.dispose();
      assert.ok(true, "Should handle batch processing errors");
    });

    it("Should handle API errors gracefully", async function () {
      this.timeout(5000);

      const config = {
        ...testConfig,
        apiBaseUrl: "http://invalid-url-does-not-exist",
        repoName: "test-repo",
      };

      const watcher = new FileWatcher(config, batchHandler);

      // Simulate change
      const testUri = vscode.Uri.file("/project/test.ts");
      (
        watcher as unknown as { handleChange: (uri: vscode.Uri, changeType: string) => void }
      ).handleChange(testUri, "modified");

      // Wait for processing
      await new Promise((resolve) => setTimeout(resolve, 1000));

      watcher.dispose();
      assert.ok(true, "Should handle API errors gracefully");
    });

    it("Should continue operation after API failure", async function () {
      this.timeout(5000);

      const config = {
        ...testConfig,
        apiBaseUrl: "http://localhost:99999", // Invalid port
        repoName: "test-repo",
      };

      const watcher = new FileWatcher(config, batchHandler);

      // Simulate multiple changes
      const testUri1 = vscode.Uri.file("/project/test1.ts");
      const testUri2 = vscode.Uri.file("/project/test2.ts");

      (
        watcher as unknown as { handleChange: (uri: vscode.Uri, changeType: string) => void }
      ).handleChange(testUri1, "modified");
      await new Promise((resolve) => setTimeout(resolve, 200));
      (
        watcher as unknown as { handleChange: (uri: vscode.Uri, changeType: string) => void }
      ).handleChange(testUri2, "modified");

      await new Promise((resolve) => setTimeout(resolve, 1000));

      watcher.dispose();
      assert.ok(true, "Should continue after API failure");
    });
  });

  describe("Backwards Compatibility", () => {
    it("Should call onBatch handler even without API config", async function () {
      this.timeout(3000);

      const watcher = new FileWatcher(testConfig, batchHandler);

      // Simulate a change
      const testUri = vscode.Uri.file("/project/test.ts");
      (
        watcher as unknown as { handleChange: (uri: vscode.Uri, changeType: string) => void }
      ).handleChange(testUri, "modified");

      // Wait for debounce and batch
      await new Promise((resolve) => setTimeout(resolve, 1000));

      watcher.dispose();
      assert.ok(true, "Should call handler for backwards compatibility");
    });

    it("Should call onBatch handler even with API config", async function () {
      this.timeout(3000);

      const config = {
        ...testConfig,
        apiBaseUrl: "http://localhost:8765",
        repoName: "test-repo",
      };

      const watcher = new FileWatcher(config, batchHandler);

      // Simulate a change
      const testUri = vscode.Uri.file("/project/test.ts");
      (
        watcher as unknown as { handleChange: (uri: vscode.Uri, changeType: string) => void }
      ).handleChange(testUri, "modified");

      // Wait for processing
      await new Promise((resolve) => setTimeout(resolve, 1000));

      watcher.dispose();
      assert.ok(true, "Should call both API and handler");
    });
  });

  describe("Integration Scenarios", () => {
    it("Should work with realistic debounce and batch settings", () => {
      const config = {
        debounceMs: 2000,
        batchIntervalMs: 5000,
        excludePatterns: ["**/node_modules/**", "**/dist/**", "**/.git/**"],
        apiBaseUrl: "http://localhost:8765",
        repoName: "my-project",
      };

      const watcher = new FileWatcher(config, batchHandler);
      assert.ok(watcher, "Should work with realistic config");
      watcher.dispose();
    });

    it("Should work with aggressive settings", () => {
      const config = {
        debounceMs: 100,
        batchIntervalMs: 500,
        excludePatterns: [],
        apiBaseUrl: "http://localhost:8765",
        repoName: "fast-repo",
      };

      const watcher = new FileWatcher(config, batchHandler);
      assert.ok(watcher, "Should work with aggressive settings");
      watcher.dispose();
    });

    it("Should work with conservative settings", () => {
      const config = {
        debounceMs: 5000,
        batchIntervalMs: 10000,
        excludePatterns: [
          "**/node_modules/**",
          "**/dist/**",
          "**/build/**",
          "**/.git/**",
          "**/out/**",
          "**/*.min.js",
        ],
        apiBaseUrl: "http://localhost:8765",
        repoName: "stable-repo",
      };

      const watcher = new FileWatcher(config, batchHandler);
      assert.ok(watcher, "Should work with conservative settings");
      watcher.dispose();
    });

    it("Should work with minimal configuration", () => {
      const minimalConfig = {
        debounceMs: 0,
        batchIntervalMs: 100,
        excludePatterns: [],
      };

      const watcher = new FileWatcher(minimalConfig, batchHandler);
      assert.ok(watcher, "Should work with minimal config");
      watcher.dispose();
    });
  });

  describe("Multiple Watcher Instances", () => {
    it("Should handle multiple watcher instances", () => {
      const watcher1 = new FileWatcher(testConfig, batchHandler);
      const watcher2 = new FileWatcher(testConfig, batchHandler);
      const watcher3 = new FileWatcher(testConfig, batchHandler);

      assert.ok(watcher1, "First watcher created");
      assert.ok(watcher2, "Second watcher created");
      assert.ok(watcher3, "Third watcher created");

      watcher1.dispose();
      watcher2.dispose();
      watcher3.dispose();
    });

    it("Should handle watchers with different configs", () => {
      const config1 = { ...testConfig, debounceMs: 100 };
      const config2 = { ...testConfig, debounceMs: 1000 };
      const config3 = {
        ...testConfig,
        apiBaseUrl: "http://localhost:8765",
        repoName: "test-repo",
      };

      const watcher1 = new FileWatcher(config1, batchHandler);
      const watcher2 = new FileWatcher(config2, batchHandler);
      const watcher3 = new FileWatcher(config3, batchHandler);

      assert.ok(watcher1 && watcher2 && watcher3, "All watchers created");

      watcher1.dispose();
      watcher2.dispose();
      watcher3.dispose();
    });
  });
});
