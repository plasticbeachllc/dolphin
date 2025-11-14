// agent-core/src/llm/diff-generator.ts
import * as Diff from "diff";
import * as fs from "fs/promises";
import * as path from "path";
import { PathValidator } from "../../../shared/security/path-validator";
import type { FileDiff, DiffHunk } from "../../../shared/types/events";

const MAX_FILE_SIZE = 1024 * 1024; // 1MB
const BINARY_FILE_EXTENSIONS = new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".bmp",
  ".ico",
  ".webp",
  ".svg",
  ".pdf",
  ".zip",
  ".tar",
  ".gz",
  ".7z",
  ".rar",
  ".mp3",
  ".mp4",
  ".avi",
  ".mov",
  ".mkv",
  ".wav",
  ".exe",
  ".dll",
  ".so",
  ".dylib",
  ".woff",
  ".woff2",
  ".ttf",
  ".eot",
  ".otf",
]);

/**
 * Checks if a file is likely binary based on extension or content
 */
function isBinaryFile(filePath: string, content?: Buffer): boolean {
  const ext = path.extname(filePath).toLowerCase();
  if (BINARY_FILE_EXTENSIONS.has(ext)) {
    return true;
  }

  // Check for null bytes (common in binary files)
  if (content) {
    const sample = content.slice(0, 8000);
    return sample.includes(0);
  }

  return false;
}

/**
 * Creates a special FileDiff for new file creation
 */
function createNewFileDiff(filePath: string, content: string): FileDiff {
  const lines = content.split("\n");
  const additions = lines.length;

  return {
    oldFileName: "/dev/null",
    newFileName: filePath,
    additions,
    deletions: 0,
    hunks: [
      {
        oldStart: 0,
        oldLines: 0,
        newStart: 1,
        newLines: additions,
        lines: lines.map((line) => `+${line}`),
      },
    ],
  };
}

/**
 * Creates a FileDiff indicating that a new binary file was created
 */
function createBinaryNewFileDiff(filePath: string, newSize: number): FileDiff {
  const message = `Binary file created: ${formatBytes(newSize)}`;

  return {
    oldFileName: "/dev/null",
    newFileName: filePath,
    additions: 0,
    deletions: 0,
    hunks: [
      {
        oldStart: 1,
        oldLines: 0,
        newStart: 1,
        newLines: 0,
        lines: [` ${message}`],
      },
    ],
  };
}

/**
 * Creates a FileDiff for large newly created files that were truncated
 */
function createTruncatedNewFileDiff(filePath: string, fileSize: number): FileDiff {
  const message = `⚠️ Diff preview unavailable: New file size (${formatBytes(fileSize)}) exceeds 1MB limit`;
  const subMessage = `   The file was created successfully, but the diff is too large to display.`;

  return {
    oldFileName: "/dev/null",
    newFileName: filePath,
    additions: 0,
    deletions: 0,
    hunks: [
      {
        oldStart: 1,
        oldLines: 0,
        newStart: 1,
        newLines: 0,
        lines: [` ${message}`, ` ${subMessage}`],
      },
    ],
  };
}

/**
 * Creates a FileDiff for binary files showing size change
 */
function createBinaryFileDiff(filePath: string, oldSize: number, newSize: number): FileDiff {
  const message = `Binary file modified: ${formatBytes(oldSize)} → ${formatBytes(newSize)}`;

  return {
    oldFileName: filePath,
    newFileName: filePath,
    additions: 0,
    deletions: 0,
    hunks: [
      {
        oldStart: 1,
        oldLines: 1,
        newStart: 1,
        newLines: 1,
        lines: [` ${message}`],
      },
    ],
  };
}

/**
 * Creates a FileDiff for large files that were truncated
 */
function createTruncatedFileDiff(filePath: string, fileSize: number): FileDiff {
  const message = `⚠️ Diff preview unavailable: File size (${formatBytes(fileSize)}) exceeds 1MB limit`;
  const subMessage = `   The file was modified successfully, but the diff is too large to display.`;

  return {
    oldFileName: filePath,
    newFileName: filePath,
    additions: 0,
    deletions: 0,
    hunks: [
      {
        oldStart: 1,
        oldLines: 0,
        newStart: 1,
        newLines: 0,
        lines: [` ${message}`, ` ${subMessage}`],
      },
    ],
  };
}

/**
 * Formats bytes to human-readable size
 */
function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

/**
 * Parses a unified diff string into DiffHunk objects
 */
function parseUnifiedDiff(diffString: string): DiffHunk[] {
  const hunks: DiffHunk[] = [];
  const lines = diffString.split("\n");

  let currentHunk: DiffHunk | null = null;
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Parse hunk header: @@ -oldStart,oldLines +newStart,newLines @@
    const hunkHeaderMatch = line.match(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/);

    if (hunkHeaderMatch) {
      // Save previous hunk
      if (currentHunk) {
        hunks.push(currentHunk);
      }

      const oldStart = parseInt(hunkHeaderMatch[1], 10);
      const oldLines = hunkHeaderMatch[2] ? parseInt(hunkHeaderMatch[2], 10) : 1;
      const newStart = parseInt(hunkHeaderMatch[3], 10);
      const newLines = hunkHeaderMatch[4] ? parseInt(hunkHeaderMatch[4], 10) : 1;

      currentHunk = {
        oldStart,
        oldLines,
        newStart,
        newLines,
        lines: [],
      };
    } else if (
      currentHunk &&
      (line.startsWith(" ") || line.startsWith("+") || line.startsWith("-"))
    ) {
      // Add line to current hunk
      currentHunk.lines.push(line);
    }

    i++;
  }

  // Save last hunk
  if (currentHunk) {
    hunks.push(currentHunk);
  }

  return hunks;
}

/**
 * Generates a FileDiff object for a file editing operation
 *
 * @param filePath - Path to the file that was modified
 * @param oldContent - Content before modification (null for new files)
 * @param newContent - Content after modification
 * @returns FileDiff object or null if diff generation fails
 */
export async function generateFileDiff(
  filePath: string,
  oldContent: string | null,
  newContent: string
): Promise<FileDiff | null> {
  try {
    // Handle new file creation
    if (oldContent === null) {
      const newBuffer = Buffer.from(newContent, "utf-8");
      const newSize = newBuffer.byteLength;

      if (isBinaryFile(filePath, newBuffer)) {
        return createBinaryNewFileDiff(filePath, newSize);
      }

      if (newSize > MAX_FILE_SIZE) {
        return createTruncatedNewFileDiff(filePath, newSize);
      }

      return createNewFileDiff(filePath, newContent);
    }

    // Check for binary files
    const isBinary = isBinaryFile(filePath);
    if (isBinary) {
      const oldSize = Buffer.byteLength(oldContent, "utf-8");
      const newSize = Buffer.byteLength(newContent, "utf-8");
      return createBinaryFileDiff(filePath, oldSize, newSize);
    }

    // Check file size limits
    const newSize = Buffer.byteLength(newContent, "utf-8");
    const oldSize = Buffer.byteLength(oldContent, "utf-8");

    if (newSize > MAX_FILE_SIZE || oldSize > MAX_FILE_SIZE) {
      return createTruncatedFileDiff(filePath, Math.max(oldSize, newSize));
    }

    // Generate unified diff using the diff library
    const patch = Diff.createPatch(filePath, oldContent, newContent, "before", "after");

    // Parse the unified diff
    const hunks = parseUnifiedDiff(patch);

    // Count additions and deletions
    let additions = 0;
    let deletions = 0;

    for (const hunk of hunks) {
      for (const line of hunk.lines) {
        if (line.startsWith("+")) additions++;
        if (line.startsWith("-")) deletions++;
      }
    }

    return {
      oldFileName: filePath,
      newFileName: filePath,
      additions,
      deletions,
      hunks,
    };
  } catch (error) {
    console.warn(`Failed to generate diff for ${filePath}:`, error);
    return null;
  }
}

/**
 * Generates a FileDiff for the file_write tool
 * Reads the old content from disk or backup if available
 *
 * @param toolInput - Input parameters from the file_write tool
 * @param toolResult - Result from the file_write tool execution
 * @param workspaceRoot - Root directory of the workspace
 * @returns FileDiff object or null if diff generation fails
 */
export async function generateFileWriteDiff(
  toolInput: any,
  toolResult: any,
  workspaceRoot: string
): Promise<FileDiff | null> {
  try {
    const filePath = toolInput.path;
    const newContent = toolInput.content;

    // Validate path to prevent directory traversal attacks
    const validator = new PathValidator({ baseDir: workspaceRoot });
    const _fullPath = validator.validate(filePath);

    // Check if this was a new file creation
    if (toolResult.created_new) {
      return generateFileDiff(filePath, null, newContent);
    }

    // Try to read old content from backup
    let oldContent: string | null = null;

    if (toolResult.backup_path) {
      try {
        // Validate backup path as well
        const validatedBackupPath = validator.validate(toolResult.backup_path);
        oldContent = await fs.readFile(validatedBackupPath, "utf-8");
      } catch (error) {
        console.warn(`Failed to read backup file ${toolResult.backup_path}:`, error);
      }
    }

    // If no backup or backup read failed, we can't generate diff
    // (file has already been overwritten at this point)
    if (oldContent === null) {
      console.warn(`Cannot generate diff for ${filePath}: no backup available`);
      return null;
    }

    return generateFileDiff(filePath, oldContent, newContent);
  } catch (error) {
    console.warn("Failed to generate file_write diff:", error);
    return null;
  }
}
