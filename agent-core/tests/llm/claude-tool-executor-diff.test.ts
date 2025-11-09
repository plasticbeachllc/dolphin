// agent-core/tests/llm/claude-tool-executor-diff.test.ts
import { describe, test, expect, beforeAll, afterAll, beforeEach } from "bun:test";
import { ClaudeToolExecutor } from "../../src/llm/claude-tool-executor";
import { MCPClient } from "../../src/mcp/client";
import type { AgentEvent, FileDiff } from "../../../shared/types/events";
import * as path from "path";
import * as fs from 'fs/promises';
import { tmpdir } from 'os';
import { randomBytes } from 'crypto';

describe("ClaudeToolExecutor - Diff Generation", () => {
  let mcpClient: MCPClient;
  let tempDir: string;
  let originalCwd: string;
  const mcpBridgePath = path.join(__dirname, "../../../mcp-bridge/src/index.ts");

  beforeAll(async () => {
    // Save original cwd
    originalCwd = process.cwd();

    // Create temp directory for test files
    tempDir = path.join(tmpdir(), `executor-diff-test-${randomBytes(8).toString('hex')}`);
    await fs.mkdir(tempDir, { recursive: true });

    // Change to temp directory BEFORE starting MCP client
    // so the MCP bridge inherits the correct working directory
    process.chdir(tempDir);

    // Start MCP client (will spawn with tempDir as cwd)
    mcpClient = new MCPClient();
    await mcpClient.start(mcpBridgePath);
  });

  afterAll(async () => {
    try {
      mcpClient.shutdown();
    } catch (error) {
      // Ignore MCP shutdown errors
    }

    // Always restore cwd, even if shutdown fails
    try {
      process.chdir(originalCwd);
    } catch (error) {
      console.error('Failed to restore working directory:', error);
    }

    // Clean up temp directory
    try {
      await fs.rm(tempDir, { recursive: true, force: true });
    } catch (error) {
      // Ignore cleanup errors
    }
  });

  beforeEach(async () => {
    // Clean up any test files from previous runs (skip .backup files from file_write)
    const files = await fs.readdir(tempDir);
    for (const file of files) {
      if (!file.includes('.backup-')) {
        await fs.rm(path.join(tempDir, file), { force: true, recursive: true });
      }
    }
  });

  test("generates diff when file_write modifies existing file", async () => {
    const events: AgentEvent[] = [];

    // Create a test file first
    const testFile = path.join(tempDir, "test-modify.txt");
    await fs.writeFile(testFile, "Original line 1\nOriginal line 2\n");

    const executor = new ClaudeToolExecutor({
      claudeClient: null as any, // Not needed for this test
      mcpClient,
      maxToolRounds: 1,
      onEvent: (event: AgentEvent) => {
        events.push(event);
      }
    });

    // Initialize executor (loads tools)
    await executor.initialize();

    const newContent = "Modified line 1\nOriginal line 2\nNew line 3\n";

    // Execute file_write directly via MCP client
    const toolCall = {
      id: "test-1",
      name: "file_write",
      input: {
        path: "test-modify.txt",
        content: newContent,
        create_backup: true
      }
    };

    // Call the private executeToolCalls method
    await (executor as any).executeToolCalls([toolCall]);

    // Find the tool_call_completed event
    const completedEvent = events.find(e =>
      e.type === "tool_call_completed" &&
      (e as any).toolId === "test-1"
    ) as any;

    expect(completedEvent).toBeDefined();
    expect(completedEvent.diff).toBeDefined();

    const diff: FileDiff = completedEvent.diff;
    expect(diff.oldFileName).toBe("test-modify.txt");
    expect(diff.newFileName).toBe("test-modify.txt");
    expect(diff.additions).toBeGreaterThan(0);
    expect(diff.deletions).toBeGreaterThan(0);
    expect(diff.hunks.length).toBeGreaterThan(0);

    // Verify diff contains expected changes
    const allLines = diff.hunks.flatMap(h => h.lines);
    expect(allLines.some(line => line.includes("Modified line 1"))).toBe(true);
  });

  test("generates diff for new file creation", async () => {
    const events: AgentEvent[] = [];

    const executor = new ClaudeToolExecutor({
      claudeClient: null as any,
      mcpClient,
      maxToolRounds: 1,
      onEvent: (event: AgentEvent) => {
        events.push(event);
      }
    });

    await executor.initialize();

    const newContent = "Line 1\nLine 2\nLine 3\n";

    const toolCall = {
      id: "test-2",
      name: "file_write",
      input: {
        path: "new-file.txt",
        content: newContent,
        create_backup: false
      }
    };

    await (executor as any).executeToolCalls([toolCall]);

    const completedEvent = events.find(e =>
      e.type === "tool_call_completed" &&
      (e as any).toolId === "test-2"
    ) as any;

    expect(completedEvent).toBeDefined();
    expect(completedEvent.diff).toBeDefined();

    const diff: FileDiff = completedEvent.diff;
    expect(diff.oldFileName).toBe("/dev/null");
    expect(diff.newFileName).toBe("new-file.txt");
    expect(diff.additions).toBe(4); // 4 lines including empty line at end
    expect(diff.deletions).toBe(0);
    expect(diff.hunks.length).toBe(1);

    // All lines should be additions
    const allLines = diff.hunks[0].lines;
    expect(allLines.every(line => line.startsWith('+'))).toBe(true);
  });

  test("generates diff for binary file with size info", async () => {
    const events: AgentEvent[] = [];

    // Create existing binary file
    const binaryFile = path.join(tempDir, "image.png");
    await fs.writeFile(binaryFile, "old binary content");

    const executor = new ClaudeToolExecutor({
      claudeClient: null as any,
      mcpClient,
      maxToolRounds: 1,
      onEvent: (event: AgentEvent) => {
        events.push(event);
      }
    });

    await executor.initialize();

    const newBinaryContent = "new binary content with more data";

    const toolCall = {
      id: "test-3",
      name: "file_write",
      input: {
        path: "image.png",
        content: newBinaryContent,
        create_backup: true
      }
    };

    await (executor as any).executeToolCalls([toolCall]);

    const completedEvent = events.find(e =>
      e.type === "tool_call_completed" &&
      (e as any).toolId === "test-3"
    ) as any;

    expect(completedEvent).toBeDefined();
    expect(completedEvent.diff).toBeDefined();

    const diff: FileDiff = completedEvent.diff;
    expect(diff.hunks.length).toBe(1);
    expect(diff.hunks[0].lines[0]).toContain("Binary file modified");
  });

  test("generates truncation message for large files", async () => {
    const events: AgentEvent[] = [];

    // Create large existing file
    const largeContent = "x".repeat(1024 * 1024 + 1000);
    const largeFile = path.join(tempDir, "large.txt");
    await fs.writeFile(largeFile, largeContent);

    const executor = new ClaudeToolExecutor({
      claudeClient: null as any,
      mcpClient,
      maxToolRounds: 1,
      onEvent: (event: AgentEvent) => {
        events.push(event);
      }
    });

    await executor.initialize();

    const newLargeContent = "y".repeat(1024 * 1024 + 2000);

    const toolCall = {
      id: "test-4",
      name: "file_write",
      input: {
        path: "large.txt",
        content: newLargeContent,
        create_backup: true
      }
    };

    await (executor as any).executeToolCalls([toolCall]);

    const completedEvent = events.find(e =>
      e.type === "tool_call_completed" &&
      (e as any).toolId === "test-4"
    ) as any;

    expect(completedEvent).toBeDefined();
    expect(completedEvent.diff).toBeDefined();

    const diff: FileDiff = completedEvent.diff;
    expect(diff.hunks.length).toBe(1);
    expect(diff.hunks[0].lines[0]).toContain("Diff preview unavailable");
    expect(diff.hunks[0].lines[0]).toContain("1MB");
  });

  test("rejects path traversal outside workspace", async () => {
    const events: AgentEvent[] = [];

    const executor = new ClaudeToolExecutor({
      claudeClient: null as any,
      mcpClient,
      maxToolRounds: 1,
      onEvent: (event: AgentEvent) => {
        events.push(event);
      }
    });

    await executor.initialize();

    // Attempt to write outside workspace using path traversal
    const toolCall = {
      id: "test-5",
      name: "file_write",
      input: {
        path: "../../../etc/outside-workspace.txt",
        content: "Should fail",
        create_backup: false
      }
    };

    await (executor as any).executeToolCalls([toolCall]);

    const completedEvent = events.find(e =>
      e.type === "tool_call_completed" &&
      (e as any).toolId === "test-5"
    ) as any;

    expect(completedEvent).toBeDefined();

    // Should have error (path outside workspace) and no diff
    expect(completedEvent.error).toBeDefined();
    expect(completedEvent.error).toContain("outside workspace");
    expect(completedEvent.diff).toBeUndefined();
  });

  test("handles missing backup gracefully", async () => {
    const events: AgentEvent[] = [];

    // Create file without backup setting
    const testFile = path.join(tempDir, "no-backup.txt");
    await fs.writeFile(testFile, "Original content");

    const executor = new ClaudeToolExecutor({
      claudeClient: null as any,
      mcpClient,
      maxToolRounds: 1,
      onEvent: (event: AgentEvent) => {
        events.push(event);
      }
    });

    await executor.initialize();

    const toolCall = {
      id: "test-6",
      name: "file_write",
      input: {
        path: "no-backup.txt",
        content: "Modified content",
        create_backup: false
      }
    };

    await (executor as any).executeToolCalls([toolCall]);

    const completedEvent = events.find(e =>
      e.type === "tool_call_completed" &&
      (e as any).toolId === "test-6"
    ) as any;

    expect(completedEvent).toBeDefined();

    // Should succeed but have no diff (no backup available)
    expect(completedEvent.error).toBeUndefined();
    expect(completedEvent.diff).toBeUndefined();
  });

  test("generates correct diff with multiple hunks", async () => {
    const events: AgentEvent[] = [];

    // Create file with spaced-out changes
    const originalContent = `line 1
line 2
line 3
line 4
line 5
line 6
line 7
line 8
line 9
line 10`;

    const testFile = path.join(tempDir, "multi-hunk.txt");
    await fs.writeFile(testFile, originalContent);

    const executor = new ClaudeToolExecutor({
      claudeClient: null as any,
      mcpClient,
      maxToolRounds: 1,
      onEvent: (event: AgentEvent) => {
        events.push(event);
      }
    });

    await executor.initialize();

    const modifiedContent = `line 1
CHANGED line 2
line 3
line 4
line 5
line 6
line 7
CHANGED line 8
line 9
line 10`;

    const toolCall = {
      id: "test-7",
      name: "file_write",
      input: {
        path: "multi-hunk.txt",
        content: modifiedContent,
        create_backup: true
      }
    };

    await (executor as any).executeToolCalls([toolCall]);

    const completedEvent = events.find(e =>
      e.type === "tool_call_completed" &&
      (e as any).toolId === "test-7"
    ) as any;

    expect(completedEvent).toBeDefined();
    expect(completedEvent.diff).toBeDefined();

    const diff: FileDiff = completedEvent.diff;
    expect(diff.additions).toBe(2);
    expect(diff.deletions).toBe(2);

    // Verify hunks have proper structure
    for (const hunk of diff.hunks) {
      expect(hunk.oldStart).toBeGreaterThan(0);
      expect(hunk.newStart).toBeGreaterThan(0);
      expect(hunk.lines.length).toBeGreaterThan(0);

      // All lines should start with ' ', '+', or '-'
      for (const line of hunk.lines) {
        expect([' ', '+', '-'].includes(line[0])).toBe(true);
      }
    }
  });

  test("preserves event timing information", async () => {
    const events: AgentEvent[] = [];

    const testFile = path.join(tempDir, "timing-test.txt");
    await fs.writeFile(testFile, "Original");

    const executor = new ClaudeToolExecutor({
      claudeClient: null as any,
      mcpClient,
      maxToolRounds: 1,
      onEvent: (event: AgentEvent) => {
        events.push(event);
      }
    });

    await executor.initialize();

    const toolCall = {
      id: "test-8",
      name: "file_write",
      input: {
        path: "timing-test.txt",
        content: "Modified",
        create_backup: true
      }
    };

    await (executor as any).executeToolCalls([toolCall]);

    const completedEvent = events.find(e =>
      e.type === "tool_call_completed" &&
      (e as any).toolId === "test-8"
    ) as any;

    expect(completedEvent).toBeDefined();
    expect(completedEvent.executionTime).toBeDefined();
    expect(completedEvent.executionTime).toBeGreaterThanOrEqual(0);
    expect(completedEvent.result).toBeDefined();
    expect(completedEvent.diff).toBeDefined();
  });

  test("handles nested directory paths", async () => {
    const events: AgentEvent[] = [];

    // Create nested structure
    const nestedDir = path.join(tempDir, "src", "lib", "utils");
    await fs.mkdir(nestedDir, { recursive: true });

    const nestedFile = path.join(nestedDir, "helper.ts");
    await fs.writeFile(nestedFile, "export const helper = () => {}");

    const executor = new ClaudeToolExecutor({
      claudeClient: null as any,
      mcpClient,
      maxToolRounds: 1,
      onEvent: (event: AgentEvent) => {
        events.push(event);
      }
    });

    await executor.initialize();

    const newContent = "export const helper = () => { return true; }";

    const toolCall = {
      id: "test-9",
      name: "file_write",
      input: {
        path: "src/lib/utils/helper.ts",
        content: newContent,
        create_backup: true
      }
    };

    await (executor as any).executeToolCalls([toolCall]);

    const completedEvent = events.find(e =>
      e.type === "tool_call_completed" &&
      (e as any).toolId === "test-9"
    ) as any;

    expect(completedEvent).toBeDefined();
    expect(completedEvent.diff).toBeDefined();

    const diff: FileDiff = completedEvent.diff;
    expect(diff.oldFileName).toBe("src/lib/utils/helper.ts");
    expect(diff.newFileName).toBe("src/lib/utils/helper.ts");
  });
});
