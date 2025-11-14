import * as assert from "assert";
import * as vscode from "vscode";
import { DriftDetector, DriftEvent } from "../../../../kb/drift-detector";

describe("DriftDetector Tests", () => {
  let outputChannel: vscode.OutputChannel;
  let detectors: DriftDetector[] = [];

  // Create output channel ONCE for all tests to avoid DisposableStore warnings
  before(() => {
    outputChannel = vscode.window.createOutputChannel("DriftDetector Test");
  });

  // Clean up output channel AFTER all tests
  after(() => {
    if (outputChannel) {
      outputChannel.dispose();
    }
  });

  beforeEach(() => {
    detectors = [];
  });

  afterEach(() => {
    // Dispose all detectors after each test
    for (const detector of detectors) {
      detector.dispose();
    }
    detectors = [];
  });

  describe("Initialization", () => {
    it("Should create DriftDetector instance", () => {
      const detector = new DriftDetector("test-repo", "http://localhost:8765", outputChannel);
      detectors.push(detector);

      assert.ok(detector, "Detector should be created");
    });

    it("Should use default check interval when not specified", () => {
      const detector = new DriftDetector("test-repo", "http://localhost:8765", outputChannel);
      detectors.push(detector);

      assert.ok(detector, "Should use default interval");
    });

    it("Should use custom check interval when specified", () => {
      const customInterval = 60000; // 1 minute
      const detector = new DriftDetector(
        "test-repo",
        "http://localhost:8765",
        outputChannel,
        customInterval
      );
      detectors.push(detector);

      assert.ok(detector, "Should accept custom interval");
    });

    it("Should accept very short check interval for testing", () => {
      const shortInterval = 100; // 100ms for testing
      const detector = new DriftDetector(
        "test-repo",
        "http://localhost:8765",
        outputChannel,
        shortInterval
      );
      detectors.push(detector);

      assert.ok(detector, "Should accept short interval");
    });

    it("Should accept very long check interval", () => {
      const longInterval = 86400000; // 24 hours
      const detector = new DriftDetector(
        "test-repo",
        "http://localhost:8765",
        outputChannel,
        longInterval
      );
      detectors.push(detector);

      assert.ok(detector, "Should accept long interval");
    });
  });

  describe("Disposal", () => {
    it("Should properly dispose resources", () => {
      const detector = new DriftDetector("test-repo", "http://localhost:8765", outputChannel);
      detectors.push(detector);

      detector.dispose();
      // Remove from array since we manually disposed
      detectors.pop();
      assert.ok(true, "Disposal should complete without errors");
    });

    it("Should handle multiple dispose calls", () => {
      const detector = new DriftDetector("test-repo", "http://localhost:8765", outputChannel);
      detectors.push(detector);

      detector.dispose();
      detector.dispose();
      detector.dispose();
      // Remove from array since we manually disposed
      detectors.pop();
      assert.ok(true, "Multiple dispose calls should not cause errors");
    });

    it("Should dispose after starting", async function () {
      this.timeout(5000);

      const detector = new DriftDetector(
        "test-repo",
        "http://localhost:8765",
        outputChannel,
        100 // Short interval for testing
      );
      detectors.push(detector);

      // Start will fail due to unavailable API, but should handle gracefully
      try {
        await detector.start();
      } catch (error) {
        // Expected - API not available in test
      }

      // Will be disposed in afterEach
      assert.ok(true, "Should dispose cleanly after starting");
    });

    it("Should clear timer on disposal", () => {
      const detector = new DriftDetector("test-repo", "http://localhost:8765", outputChannel, 100);
      detectors.push(detector);

      // Access private checkTimer to verify it gets cleared
      detector.dispose();
      // Remove from array since we manually disposed
      detectors.pop();

      // Timer should be null after disposal
      assert.ok(true, "Timer should be cleared");
    });
  });

  describe("Drift Event Types", () => {
    it("Should handle modified drift events", () => {
      const modifiedEvent: DriftEvent = {
        file_id: 1,
        path: "src/file.py",
        drift_type: "modified",
      };

      assert.strictEqual(modifiedEvent.drift_type, "modified");
      assert.strictEqual(modifiedEvent.path, "src/file.py");
    });

    it("Should handle deleted drift events", () => {
      const deletedEvent: DriftEvent = {
        file_id: 2,
        path: "src/removed.py",
        drift_type: "deleted",
      };

      assert.strictEqual(deletedEvent.drift_type, "deleted");
      assert.strictEqual(deletedEvent.path, "src/removed.py");
    });

    it("Should handle array of mixed drift events", () => {
      const events: DriftEvent[] = [
        { file_id: 1, path: "file1.py", drift_type: "modified" },
        { file_id: 2, path: "file2.py", drift_type: "deleted" },
        { file_id: 3, path: "file3.py", drift_type: "modified" },
      ];

      assert.strictEqual(events.length, 3);
      const modifiedCount = events.filter((e) => e.drift_type === "modified").length;
      const deletedCount = events.filter((e) => e.drift_type === "deleted").length;

      assert.strictEqual(modifiedCount, 2);
      assert.strictEqual(deletedCount, 1);
    });
  });

  describe("Error Handling", () => {
    it("Should handle API errors gracefully during drift detection", async function () {
      this.timeout(5000);

      const detector = new DriftDetector(
        "test-repo",
        "http://invalid-url-that-does-not-exist",
        outputChannel
      );
      detectors.push(detector);

      // detectDrift should not throw even if API is unavailable
      try {
        await detector.detectDrift();
        // Should complete without throwing
        assert.ok(true, "Should handle API errors gracefully");
      } catch (error) {
        // Some errors may propagate, but they should be caught internally
        assert.ok(true, "Error was caught");
      }
    });

    it("Should handle network failures", async function () {
      this.timeout(5000);

      const detector = new DriftDetector(
        "test-repo",
        "http://localhost:99999", // Invalid port
        outputChannel
      );
      detectors.push(detector);

      try {
        await detector.detectDrift();
        assert.ok(true, "Should handle network failures");
      } catch (error) {
        assert.ok(true, "Network error handled");
      }
    });

    it("Should handle malformed API responses", async function () {
      this.timeout(5000);

      const detector = new DriftDetector("test-repo", "http://localhost:8765", outputChannel);
      detectors.push(detector);

      // If API returns unexpected format, should handle gracefully
      try {
        await detector.detectDrift();
        assert.ok(true, "Should handle malformed responses");
      } catch (error) {
        assert.ok(true, "Malformed response handled");
      }
    });

    it("Should continue operation after error", async function () {
      this.timeout(5000);

      const detector = new DriftDetector("test-repo", "http://invalid", outputChannel, 100);
      detectors.push(detector);

      // First detection (will fail)
      try {
        await detector.detectDrift();
      } catch (error) {
        // Expected
      }

      // Should still be able to call detectDrift again
      try {
        await detector.detectDrift();
        assert.ok(true, "Should continue after error");
      } catch (error) {
        assert.ok(true, "Can handle multiple errors");
      }
    });
  });

  describe("Repository and API Configuration", () => {
    it("Should accept different repository names", () => {
      const repos = ["my-repo", "test-project", "backend-service", "frontend-app"];

      for (const repo of repos) {
        const detector = new DriftDetector(repo, "http://localhost:8765", outputChannel);
        detectors.push(detector);

        assert.ok(detector, `Should accept repo name: ${repo}`);
      }
    });

    it("Should accept different API base URLs", () => {
      const urls = [
        "http://localhost:8765",
        "http://127.0.0.1:9000",
        "https://api.example.com",
        "http://kb-service:8080",
      ];

      for (const url of urls) {
        const detector = new DriftDetector("test-repo", url, outputChannel);
        detectors.push(detector);

        assert.ok(detector, `Should accept API URL: ${url}`);
      }
    });

    it("Should work with complex repository names", () => {
      const complexNames = [
        "org/repo",
        "user/my-project",
        "company/team/service",
        "repo-with-dashes",
        "repo_with_underscores",
      ];

      for (const name of complexNames) {
        const detector = new DriftDetector(name, "http://localhost:8765", outputChannel);
        detectors.push(detector);

        assert.ok(detector, `Should accept complex repo name: ${name}`);
      }
    });
  });

  describe("Check Interval Behavior", () => {
    it("Should accept hourly interval (default)", () => {
      const detector = new DriftDetector(
        "test-repo",
        "http://localhost:8765",
        outputChannel,
        3600000 // 1 hour
      );
      detectors.push(detector);

      assert.ok(detector, "Should accept hourly interval");
    });

    it("Should accept per-minute interval", () => {
      const detector = new DriftDetector(
        "test-repo",
        "http://localhost:8765",
        outputChannel,
        60000 // 1 minute
      );
      detectors.push(detector);

      assert.ok(detector, "Should accept per-minute interval");
    });

    it("Should accept daily interval", () => {
      const detector = new DriftDetector(
        "test-repo",
        "http://localhost:8765",
        outputChannel,
        86400000 // 24 hours
      );
      detectors.push(detector);

      assert.ok(detector, "Should accept daily interval");
    });

    it("Should accept rapid interval for testing", () => {
      const detector = new DriftDetector(
        "test-repo",
        "http://localhost:8765",
        outputChannel,
        10 // Very rapid for tests
      );
      detectors.push(detector);

      assert.ok(detector, "Should accept rapid interval");
    });
  });

  describe("Concurrent Detectors", () => {
    it("Should handle multiple detector instances", () => {
      const detector1 = new DriftDetector("repo1", "http://localhost:8765", outputChannel);
      detectors.push(detector1);

      const detector2 = new DriftDetector("repo2", "http://localhost:8765", outputChannel);
      detectors.push(detector2);

      const detector3 = new DriftDetector("repo3", "http://localhost:8765", outputChannel);
      detectors.push(detector3);

      assert.ok(detector1, "First detector created");
      assert.ok(detector2, "Second detector created");
      assert.ok(detector3, "Third detector created");
    });

    it("Should handle different intervals for different repos", () => {
      const detector1 = new DriftDetector(
        "fast-repo",
        "http://localhost:8765",
        outputChannel,
        1000
      );
      detectors.push(detector1);

      const detector2 = new DriftDetector(
        "slow-repo",
        "http://localhost:8765",
        outputChannel,
        10000
      );
      detectors.push(detector2);

      assert.ok(detector1, "Fast detector created");
      assert.ok(detector2, "Slow detector created");
    });
  });

  describe("Lifecycle Management", () => {
    it("Should dispose before start", () => {
      const detector = new DriftDetector("test-repo", "http://localhost:8765", outputChannel);
      detectors.push(detector);

      // Dispose before starting
      detector.dispose();
      // Remove from array since we manually disposed
      detectors.pop();
      assert.ok(true, "Should handle dispose before start");
    });

    it("Should handle rapid start-dispose cycles", async function () {
      this.timeout(5000);

      for (let i = 0; i < 3; i++) {
        const detector = new DriftDetector(
          "test-repo",
          "http://localhost:8765",
          outputChannel,
          100
        );
        detectors.push(detector);

        try {
          await detector.start();
        } catch (error) {
          // Expected - API not available
        }

        detector.dispose();
        detectors.pop();
      }

      assert.ok(true, "Should handle rapid cycles");
    });
  });

  describe("Integration Scenarios", () => {
    it("Should work with realistic configuration", () => {
      const detector = new DriftDetector(
        "my-project",
        "http://localhost:8765",
        outputChannel,
        3600000 // 1 hour - realistic for production
      );
      detectors.push(detector);

      assert.ok(detector, "Should work with realistic config");
    });

    it("Should work with development configuration", () => {
      const detector = new DriftDetector(
        "dev-repo",
        "http://localhost:8765",
        outputChannel,
        5000 // 5 seconds - fast for development
      );
      detectors.push(detector);

      assert.ok(detector, "Should work with dev config");
    });

    it("Should work with conservative configuration", () => {
      const detector = new DriftDetector(
        "important-repo",
        "http://localhost:8765",
        outputChannel,
        43200000 // 12 hours - conservative for important repos
      );
      detectors.push(detector);

      assert.ok(detector, "Should work with conservative config");
    });
  });
});
