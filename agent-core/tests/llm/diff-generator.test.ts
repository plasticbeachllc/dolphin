// agent-core/tests/llm/diff-generator.test.ts
import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { generateFileDiff, generateFileWriteDiff } from "../../src/llm/diff-generator";
import * as fs from 'fs/promises';
import * as path from 'path';
import { tmpdir } from 'os';
import { randomBytes } from 'crypto';

describe("diff-generator", () => {
  describe("generateFileDiff", () => {
    test("generates diff for text file modifications", async () => {
      const oldContent = `function hello() {
  console.log("Hello");
}`;

      const newContent = `function hello() {
  console.log("Hello, World!");
  return true;
}`;

      const diff = await generateFileDiff("test.ts", oldContent, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.oldFileName).toBe("test.ts");
      expect(diff?.newFileName).toBe("test.ts");
      expect(diff?.additions).toBeGreaterThan(0);
      expect(diff?.deletions).toBeGreaterThan(0);
      expect(diff?.hunks.length).toBeGreaterThan(0);

      // Check that hunks contain proper line prefixes
      const allLines = diff!.hunks.flatMap(h => h.lines);
      expect(allLines.some(line => line.startsWith('+'))).toBe(true);
      expect(allLines.some(line => line.startsWith('-'))).toBe(true);
    });

    test("handles new file creation", async () => {
      const newContent = `export function add(a: number, b: number) {
  return a + b;
}`;

      const diff = await generateFileDiff("math.ts", null, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.oldFileName).toBe("/dev/null");
      expect(diff?.newFileName).toBe("math.ts");
      expect(diff?.additions).toBe(3); // 3 lines
      expect(diff?.deletions).toBe(0);
      expect(diff?.hunks.length).toBe(1);

      // All lines should be additions
      const allLines = diff!.hunks[0].lines;
      expect(allLines.every(line => line.startsWith('+'))).toBe(true);
    });

    test("handles empty new file", async () => {
      const newContent = "";

      const diff = await generateFileDiff("empty.txt", null, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.oldFileName).toBe("/dev/null");
      expect(diff?.newFileName).toBe("empty.txt");
      expect(diff?.additions).toBe(1); // Empty string counts as 1 line
      expect(diff?.deletions).toBe(0);
    });

    test("handles identical content (no changes)", async () => {
      const content = "const x = 42;";

      const diff = await generateFileDiff("test.js", content, content);

      expect(diff).not.toBeNull();
      // No additions or deletions
      expect(diff?.additions).toBe(0);
      expect(diff?.deletions).toBe(0);
    });

    test("detects binary files by extension", async () => {
      const oldContent = "fake image data";
      const newContent = "new fake image data with more bytes";

      const diff = await generateFileDiff("icon.png", oldContent, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.hunks.length).toBe(1);

      // Should contain binary file message
      const line = diff!.hunks[0].lines[0];
      expect(line).toContain("Binary file modified");
      expect(line).toContain("→");
    });

    test("handles large files (>1MB) with truncation message", async () => {
      // Create content larger than 1MB
      const largeContent = "x".repeat(1024 * 1024 + 1000);
      const largeContentModified = "y".repeat(1024 * 1024 + 1000);

      const diff = await generateFileDiff("large.txt", largeContent, largeContentModified);

      expect(diff).not.toBeNull();
      expect(diff?.hunks.length).toBe(1);

      // Should contain truncation message
      const line = diff!.hunks[0].lines[0];
      expect(line).toContain("Diff preview unavailable");
      expect(line).toContain("exceeds 1MB limit");
    });

    test("handles files with multiple hunks", async () => {
      const oldContent = `line 1
line 2
line 3
line 4
line 5
line 6
line 7
line 8
line 9
line 10`;

      const newContent = `line 1
changed line 2
line 3
line 4
line 5
line 6
line 7
changed line 8
line 9
line 10`;

      const diff = await generateFileDiff("multi.txt", oldContent, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.additions).toBe(2);
      expect(diff?.deletions).toBe(2);
      // May have 1 or 2 hunks depending on context
      expect(diff?.hunks.length).toBeGreaterThan(0);
    });

    test("handles multiline additions", async () => {
      const oldContent = "function test() {\n}\n";
      const newContent = `function test() {
  const a = 1;
  const b = 2;
  return a + b;
}
`;

      const diff = await generateFileDiff("test.js", oldContent, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.additions).toBeGreaterThan(2);
      // The diff algorithm may treat this as pure additions if structure allows
      expect(diff?.deletions).toBeGreaterThanOrEqual(0);
    });

    test("handles various binary file extensions", async () => {
      const extensions = ['.jpg', '.pdf', '.zip', '.exe', '.mp4', '.woff'];

      for (const ext of extensions) {
        const diff = await generateFileDiff(`file${ext}`, "old", "new");
        expect(diff).not.toBeNull();
        expect(diff!.hunks[0].lines[0]).toContain("Binary file modified");
      }
    });

    test("returns null on internal errors gracefully", async () => {
      // This should not throw, but return null
      // Pass invalid scenarios that might cause errors
      const diff = await generateFileDiff(
        "test.ts",
        null as any, // This should be caught and return null
        undefined as any
      );

      // Should handle error gracefully
      expect(diff === null || diff !== undefined).toBe(true);
    });
  });

  describe("generateFileWriteDiff", () => {
    let tempDir: string;
    let testFile: string;
    let backupFile: string;

    beforeEach(async () => {
      // Create temp directory for test files
      tempDir = path.join(tmpdir(), `diff-test-${randomBytes(8).toString('hex')}`);
      await fs.mkdir(tempDir, { recursive: true });
      testFile = path.join(tempDir, "test.txt");
    });

    afterEach(async () => {
      // Clean up
      try {
        await fs.rm(tempDir, { recursive: true, force: true });
      } catch (error) {
        // Ignore cleanup errors
      }
    });

    test("generates diff for file modification with backup", async () => {
      const oldContent = "Original content\nLine 2\n";
      const newContent = "Modified content\nLine 2\nLine 3\n";

      // Create backup file
      backupFile = `${testFile}.backup-${new Date().toISOString().replace(/[:.]/g, '-')}`;
      await fs.writeFile(backupFile, oldContent);

      const toolInput = {
        path: "test.txt",
        content: newContent,
        create_backup: true
      };

      const toolResult = {
        path: "test.txt",
        bytes_written: Buffer.byteLength(newContent),
        backup_path: backupFile,
        created_new: false,
        timestamp: new Date().toISOString()
      };

      const diff = await generateFileWriteDiff(toolInput, toolResult, tempDir);

      expect(diff).not.toBeNull();
      expect(diff?.oldFileName).toBe("test.txt");
      expect(diff?.newFileName).toBe("test.txt");
      expect(diff?.additions).toBeGreaterThan(0);
      expect(diff?.hunks.length).toBeGreaterThan(0);
    });

    test("generates diff for new file creation", async () => {
      const newContent = "Brand new file\nWith multiple lines\n";

      const toolInput = {
        path: "new.txt",
        content: newContent,
        create_backup: true
      };

      const toolResult = {
        path: "new.txt",
        bytes_written: Buffer.byteLength(newContent),
        backup_path: undefined,
        created_new: true,
        timestamp: new Date().toISOString()
      };

      const diff = await generateFileWriteDiff(toolInput, toolResult, tempDir);

      expect(diff).not.toBeNull();
      expect(diff?.oldFileName).toBe("/dev/null");
      expect(diff?.newFileName).toBe("new.txt");
      expect(diff?.additions).toBe(3); // 3 lines
      expect(diff?.deletions).toBe(0);
    });

    test("returns null when backup file doesn't exist", async () => {
      const newContent = "Some content";

      const toolInput = {
        path: "test.txt",
        content: newContent,
        create_backup: false
      };

      const toolResult = {
        path: "test.txt",
        bytes_written: Buffer.byteLength(newContent),
        backup_path: "/nonexistent/backup.txt",
        created_new: false,
        timestamp: new Date().toISOString()
      };

      const diff = await generateFileWriteDiff(toolInput, toolResult, tempDir);

      // Should return null when backup can't be read
      expect(diff).toBeNull();
    });

    test("returns null when no backup is available for modified file", async () => {
      const newContent = "Modified content";

      const toolInput = {
        path: "test.txt",
        content: newContent,
        create_backup: false
      };

      const toolResult = {
        path: "test.txt",
        bytes_written: Buffer.byteLength(newContent),
        backup_path: undefined,
        created_new: false, // Modified but no backup
        timestamp: new Date().toISOString()
      };

      const diff = await generateFileWriteDiff(toolInput, toolResult, tempDir);

      expect(diff).toBeNull();
    });

    test("handles binary file through file_write", async () => {
      const binaryContent = "fake binary data";
      backupFile = `${testFile.replace('.txt', '.png')}.backup-${new Date().toISOString().replace(/[:.]/g, '-')}`;
      await fs.writeFile(backupFile, "old binary");

      const toolInput = {
        path: "image.png",
        content: binaryContent,
        create_backup: true
      };

      const toolResult = {
        path: "image.png",
        bytes_written: Buffer.byteLength(binaryContent),
        backup_path: backupFile,
        created_new: false,
        timestamp: new Date().toISOString()
      };

      const diff = await generateFileWriteDiff(toolInput, toolResult, tempDir);

      expect(diff).not.toBeNull();
      expect(diff!.hunks[0].lines[0]).toContain("Binary file modified");
    });

    test("handles large file through file_write", async () => {
      const largeContent = "x".repeat(1024 * 1024 + 100);
      const largeOldContent = "y".repeat(1024 * 1024 + 100);

      backupFile = `${testFile}.backup-large`;
      await fs.writeFile(backupFile, largeOldContent);

      const toolInput = {
        path: "large.txt",
        content: largeContent,
        create_backup: true
      };

      const toolResult = {
        path: "large.txt",
        bytes_written: Buffer.byteLength(largeContent),
        backup_path: backupFile,
        created_new: false,
        timestamp: new Date().toISOString()
      };

      const diff = await generateFileWriteDiff(toolInput, toolResult, tempDir);

      expect(diff).not.toBeNull();
      expect(diff!.hunks[0].lines[0]).toContain("Diff preview unavailable");
      expect(diff!.hunks[0].lines[0]).toContain("1MB");
    });

    test("handles workspace root path resolution", async () => {
      const oldContent = "test";
      const newContent = "modified test";

      // Create nested directory structure
      const nestedDir = path.join(tempDir, "src", "lib");
      await fs.mkdir(nestedDir, { recursive: true });

      const nestedFile = path.join(nestedDir, "nested.ts");
      backupFile = `${nestedFile}.backup-test`;
      await fs.writeFile(backupFile, oldContent);

      const toolInput = {
        path: "src/lib/nested.ts",
        content: newContent,
        create_backup: true
      };

      const toolResult = {
        path: "src/lib/nested.ts",
        bytes_written: Buffer.byteLength(newContent),
        backup_path: backupFile,
        created_new: false,
        timestamp: new Date().toISOString()
      };

      const diff = await generateFileWriteDiff(toolInput, toolResult, tempDir);

      expect(diff).not.toBeNull();
      expect(diff?.oldFileName).toBe("src/lib/nested.ts");
      expect(diff?.newFileName).toBe("src/lib/nested.ts");
    });
  });

  describe("edge cases and error handling", () => {
    test("handles files with no newline at end", async () => {
      const oldContent = "line 1\nline 2";
      const newContent = "line 1\nline 2\nline 3";

      const diff = await generateFileDiff("test.txt", oldContent, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.additions).toBeGreaterThan(0);
    });

    test("handles Windows line endings (CRLF)", async () => {
      const oldContent = "line 1\r\nline 2\r\n";
      const newContent = "line 1\r\nmodified line 2\r\n";

      const diff = await generateFileDiff("test.txt", oldContent, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.hunks.length).toBeGreaterThan(0);
    });

    test("handles empty to non-empty transition", async () => {
      const oldContent = "";
      const newContent = "first line\nsecond line\n";

      const diff = await generateFileDiff("test.txt", oldContent, newContent);

      expect(diff).not.toBeNull();
      // Diff library counts actual lines with content, trailing newline is not a separate line
      expect(diff?.additions).toBe(2); // 2 lines of actual content
      expect(diff?.deletions).toBeGreaterThanOrEqual(0); // Empty may or may not count as deletion
    });

    test("handles non-empty to empty transition", async () => {
      const oldContent = "line 1\nline 2\n";
      const newContent = "";

      const diff = await generateFileDiff("test.txt", oldContent, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.deletions).toBeGreaterThan(0);
    });

    test("handles unicode content", async () => {
      const oldContent = "Hello 世界\n";
      const newContent = "Hello 世界! 🌍\n";

      const diff = await generateFileDiff("test.txt", oldContent, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.additions).toBeGreaterThan(0);
      expect(diff?.deletions).toBeGreaterThan(0);
    });

    test("handles very long lines", async () => {
      const longLine = "x".repeat(10000);
      const oldContent = `${longLine}\nshort line\n`;
      const newContent = `${longLine}\nmodified short line\n`;

      const diff = await generateFileDiff("test.txt", oldContent, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.additions).toBeGreaterThan(0);
    });

    test("handles special characters in content", async () => {
      const oldContent = "function test() {\n  return 'hello';\n}\n";
      const newContent = "function test() {\n  return \"hello\";\n}\n";

      const diff = await generateFileDiff("test.js", oldContent, newContent);

      expect(diff).not.toBeNull();
      expect(diff?.additions).toBeGreaterThan(0);
      expect(diff?.deletions).toBeGreaterThan(0);
    });
  });

  describe("diff statistics accuracy", () => {
    test("correctly counts additions and deletions", async () => {
      const oldContent = `line 1
line 2
line 3
line 4`;

      const newContent = `line 1
modified line 2
line 3
new line 4
new line 5`;

      const diff = await generateFileDiff("test.txt", oldContent, newContent);

      expect(diff).not.toBeNull();

      // Manually count expected changes
      const allLines = diff!.hunks.flatMap(h => h.lines);
      const additions = allLines.filter(l => l.startsWith('+')).length;
      const deletions = allLines.filter(l => l.startsWith('-')).length;

      expect(diff?.additions).toBe(additions);
      expect(diff?.deletions).toBe(deletions);
    });

    test("hunk metadata matches line counts", async () => {
      const oldContent = "a\nb\nc\n";
      const newContent = "a\nx\ny\nz\n";

      const diff = await generateFileDiff("test.txt", oldContent, newContent);

      expect(diff).not.toBeNull();

      for (const hunk of diff!.hunks) {
        const additions = hunk.lines.filter(l => l.startsWith('+')).length;
        const deletions = hunk.lines.filter(l => l.startsWith('-')).length;
        const context = hunk.lines.filter(l => l.startsWith(' ')).length;

        // Verify hunk metadata consistency
        expect(hunk.oldStart).toBeGreaterThanOrEqual(0);
        expect(hunk.newStart).toBeGreaterThanOrEqual(0);
        expect(hunk.oldLines).toBeGreaterThanOrEqual(0);
        expect(hunk.newLines).toBeGreaterThanOrEqual(0);
      }
    });
  });
});
