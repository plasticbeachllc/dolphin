// vscode-extension/src/editor/diff-handler.ts
import * as vscode from "vscode";
import * as path from "path";

export interface DiffChange {
  filePath: string;
  oldContent: string;
  newContent: string;
}

/**
 * Handles applying diffs to workspace files
 */
export class DiffHandler {
  /**
   * Show a diff preview and apply changes if user accepts
   */
  public static async applyDiff(diff: DiffChange): Promise<boolean> {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
      vscode.window.showErrorMessage("No workspace folder open");
      return false;
    }

    // Resolve the file path
    const fileUri = vscode.Uri.joinPath(workspaceFolder.uri, diff.filePath);

    // Create temporary URIs for diff preview
    const originalUri = vscode.Uri.parse(`dolphin-original:${diff.filePath}`);
    const modifiedUri = vscode.Uri.parse(`dolphin-modified:${diff.filePath}`);

    // Register temporary document providers
    const originalProvider = vscode.workspace.registerTextDocumentContentProvider(
      "dolphin-original",
      {
        provideTextDocumentContent: () => diff.oldContent,
      }
    );

    const modifiedProvider = vscode.workspace.registerTextDocumentContentProvider(
      "dolphin-modified",
      {
        provideTextDocumentContent: () => diff.newContent,
      }
    );

    try {
      // Show diff preview
      await vscode.commands.executeCommand(
        "vscode.diff",
        originalUri,
        modifiedUri,
        `Dolphin: ${path.basename(diff.filePath)}`,
        { preview: true }
      );

      // Ask user to confirm
      const choice = await vscode.window.showInformationMessage(
        `Apply changes to ${diff.filePath}?`,
        { modal: true },
        "Apply",
        "Cancel"
      );

      if (choice === "Apply") {
        // Apply the changes using WorkspaceEdit
        const edit = new vscode.WorkspaceEdit();

        // Read current file content
        let fileExists = true;
        try {
          const fileContent = await vscode.workspace.fs.readFile(fileUri);
          const _currentContent = Buffer.from(fileContent).toString("utf8");
        } catch {
          // File might not exist yet, that's ok
          fileExists = false;
        }

        // Replace entire file content
        const fullRange = new vscode.Range(
          new vscode.Position(0, 0),
          new vscode.Position(Number.MAX_SAFE_INTEGER, 0)
        );

        if (fileExists) {
          edit.replace(fileUri, fullRange, diff.newContent);
        } else {
          edit.createFile(fileUri, { overwrite: false });
          edit.insert(fileUri, new vscode.Position(0, 0), diff.newContent);
        }

        const success = await vscode.workspace.applyEdit(edit);

        if (success) {
          vscode.window.showInformationMessage(`Applied changes to ${diff.filePath}`);
          // Open the file
          await vscode.window.showTextDocument(fileUri);
          return true;
        } else {
          vscode.window.showErrorMessage(`Failed to apply changes to ${diff.filePath}`);
          return false;
        }
      }

      return false;
    } finally {
      // Clean up providers
      originalProvider.dispose();
      modifiedProvider.dispose();
    }
  }

  /**
   * Parse a unified diff format and extract changes
   * This is a simple parser for basic diff formats
   */
  public static parseDiff(diffText: string): DiffChange | null {
    // This is a simplified parser - in production you might want to use a library
    // Look for file path markers
    const fileMatch = diffText.match(/^---\s+(.+?)$/m);
    if (!fileMatch) {
      return null;
    }

    const _filePath = fileMatch[1].replace(/^[ab]\//, ""); // Remove a/ or b/ prefix

    // For now, we'll just return null as this requires more complex parsing
    // In practice, the agent should send structured diff data
    return null;
  }

  /**
   * Apply multiple diffs at once
   */
  public static async applyMultipleDiffs(diffs: DiffChange[]): Promise<boolean[]> {
    const results: boolean[] = [];

    for (const diff of diffs) {
      const result = await this.applyDiff(diff);
      results.push(result);
    }

    return results;
  }
}
