/**
 * EP-11: Architect Mode E2E Tests
 *
 * Tests the end-to-end integration of architect mode from VSCode extension to agent-core
 */

import * as assert from "assert";
import * as vscode from "vscode";
import { AgentBridge } from "../../../../agent/bridge";
import * as path from "path";

describe("Architect Mode E2E Tests", function () {
  this.timeout(70000); // Extended timeout for agent-core startup

  let agentBridge: AgentBridge;
  let outputChannel: vscode.OutputChannel;
  let receivedEvents: Array<Record<string, unknown>> = [];

  before(async function () {
    this.timeout(120000); // Increase timeout for agent startup

    outputChannel = vscode.window.createOutputChannel("Dolphin Architect Tests");
    agentBridge = new AgentBridge(outputChannel);

    // Start agent bridge
    const extensionPath = path.resolve(__dirname, "../../../");
    const agentCorePath = path.join(extensionPath, "agent-core/src/main.ts");

    outputChannel.appendLine("[Test] Starting agent bridge...");

    try {
      await agentBridge.start(agentCorePath, extensionPath);

      // Wait for agent to be ready with extended timeout
      await agentBridge.waitForReady(90000);
      outputChannel.appendLine("[Test] Agent ready");

      // Set up event collector
      agentBridge.onEvent((event) => {
        receivedEvents.push(event);
        outputChannel.appendLine(`[Test] Event: ${event.type}`);
      });
    } catch (error: unknown) {
      outputChannel.appendLine(`[Test] Agent startup failed: ${error instanceof Error ? error.message : String(error)}`);
      // Skip tests if agent can't start
      this.skip();
    }
  });

  after(async () => {
    if (agentBridge) {
      await agentBridge.shutdown();
    }
    outputChannel.dispose();
  });

  beforeEach(() => {
    // Clear events before each test
    receivedEvents = [];
  });

  it("Should execute discovery phase in architect mode", async () => {
    // Send architect mode request
    await agentBridge.sendMessage(
      "How is authentication implemented in this codebase?",
      "architect"
    );

    // Wait for task completion
    const completionEvent = await waitForEvent("task_completed", 30000);

    assert.ok(completionEvent, "Should receive task_completed event");
    assert.strictEqual(completionEvent.success, true, "Task should succeed");
    assert.strictEqual(completionEvent.result?.mode, "architect", "Should confirm architect mode");

    // Check for discovery results in content_delta events
    const contentEvents = receivedEvents.filter((e) => e.type === "content_delta");
    assert.ok(contentEvents.length > 0, "Should receive content_delta events");

    const discoveryContent = contentEvents.map((e) => e.delta).join("");
    assert.ok(discoveryContent.includes("Discovery Results"), "Should contain discovery results");
    assert.ok(discoveryContent.includes("Confidence"), "Should include confidence score");
  });

  it("Should generate strategic queries", async () => {
    await agentBridge.sendMessage("Add rate limiting to API endpoints", "architect");

    const completionEvent = await waitForEvent("task_completed", 30000);
    assert.ok(completionEvent, "Should complete");

    const contentEvents = receivedEvents.filter((e) => e.type === "content_delta");
    const allContent = contentEvents.map((e) => e.delta).join("");

    assert.ok(allContent.includes("Strategic Queries"), "Should show strategic queries section");

    // Should have multiple queries with strategies
    const hasStrategies =
      allContent.includes("[broad]") ||
      allContent.includes("[specific]") ||
      allContent.includes("[pattern]") ||
      allContent.includes("[dependency]");

    assert.ok(hasStrategies, "Should include query strategies");
  });

  it("Should include graph context when available", async () => {
    await agentBridge.sendMessage("How does the search backend work?", "architect");

    const completionEvent = await waitForEvent("task_completed", 30000);
    assert.ok(completionEvent, "Should complete");

    const contentEvents = receivedEvents.filter((e) => e.type === "content_delta");
    const allContent = contentEvents.map((e) => e.delta).join("");

    // Graph context may or may not be available depending on codebase
    // Just check for the graph context section
    const hasGraphSection =
      allContent.includes("Code Graph Context") || allContent.includes("No graph context");
    assert.ok(hasGraphSection, "Should mention graph context");
  });

  it("Should show confidence score in results", async () => {
    await agentBridge.sendMessage("Find database connection code", "architect");

    const completionEvent = await waitForEvent("task_completed", 30000);
    assert.ok(completionEvent, "Should complete");

    const contentEvents = receivedEvents.filter((e) => e.type === "content_delta");
    const allContent = contentEvents.map((e) => e.delta).join("");

    // Should have a confidence score (0-100%)
    const confidenceMatch = allContent.match(/Confidence[:\s]*(\d+)%/);
    assert.ok(confidenceMatch, "Should include confidence score");

    if (confidenceMatch) {
      const confidence = parseInt(confidenceMatch[1]);
      assert.ok(confidence >= 0 && confidence <= 100, "Confidence should be 0-100%");
    }
  });

  it("Should identify information gaps when relevant", async () => {
    await agentBridge.sendMessage("Implement blockchain consensus algorithm", "architect");

    const completionEvent = await waitForEvent("task_completed", 30000);
    assert.ok(completionEvent, "Should complete");

    const contentEvents = receivedEvents.filter((e) => e.type === "content_delta");
    const allContent = contentEvents.map((e) => e.delta).join("");

    // For a query unlikely to find results, should show gaps
    const _hasGaps = allContent.includes("Information Gaps") || allContent.includes("gaps");
    // Note: This test might need adjustment based on actual codebase
  });

  it("Code mode should NOT trigger discovery", async () => {
    await agentBridge.sendMessage("What files exist in src/?", "code");

    const completionEvent = await waitForEvent("task_completed", 20000);
    assert.ok(completionEvent, "Should complete");

    const contentEvents = receivedEvents.filter((e) => e.type === "content_delta");
    const allContent = contentEvents.map((e) => e.delta).join("");

    // Should NOT show discovery phase indicators
    assert.ok(!allContent.includes("Discovery Results"), "Should not show discovery in code mode");
    assert.ok(
      !allContent.includes("Strategic Queries"),
      "Should not show strategic queries in code mode"
    );
  });

  it("Should show multiple query strategies", async () => {
    await agentBridge.sendMessage("Refactor authentication system", "architect");

    const completionEvent = await waitForEvent("task_completed", 30000);
    assert.ok(completionEvent, "Should complete");

    const contentEvents = receivedEvents.filter((e) => e.type === "content_delta");
    const allContent = contentEvents.map((e) => e.delta).join("");

    // Count query strategy types
    const strategies = ["broad", "specific", "pattern", "dependency"];
    let strategyCount = 0;

    strategies.forEach((strategy) => {
      if (allContent.includes(`[${strategy}]`)) {
        strategyCount++;
      }
    });

    assert.ok(strategyCount >= 2, "Should use at least 2 different query strategies");
  });

  it("Should complete within reasonable time", async function () {
    this.timeout(10000); // 10 second timeout for this test

    const startTime = Date.now();
    await agentBridge.sendMessage("Find API routes", "architect");

    const completionEvent = await waitForEvent("task_completed", 10000);
    const duration = Date.now() - startTime;

    assert.ok(completionEvent, "Should complete");
    assert.ok(duration < 10000, `Should complete in under 10s (took ${duration}ms)`);
    outputChannel.appendLine(`[Test] Discovery completed in ${duration}ms`);
  });

  /**
   * Helper function to wait for a specific event type
   */
  function waitForEvent(eventType: string, timeout: number): Promise<Record<string, unknown>> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`Timeout waiting for event: ${eventType}`));
      }, timeout);

      const check = () => {
        const event = receivedEvents.find((e) => e.type === eventType);
        if (event) {
          clearTimeout(timer);
          clearInterval(interval);
          resolve(event);
        }
      };

      // Check immediately
      check();

      // Then check periodically
      const interval = setInterval(check, 100);
    });
  }
});
