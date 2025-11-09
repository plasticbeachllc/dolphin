// vscode-extension/src/editor/code-actions.ts
import * as vscode from "vscode";

/**
 * Provides code actions (quick fixes) for Dolphin AI assistance
 */
export class DolphinCodeActionProvider implements vscode.CodeActionProvider {
  private viewProvider: any;

  constructor(viewProvider: any) {
    this.viewProvider = viewProvider;
  }

  public provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range | vscode.Selection,
    context: vscode.CodeActionContext,
    token: vscode.CancellationToken
  ): vscode.ProviderResult<(vscode.CodeAction | vscode.Command)[]> {
    const selection = document.getText(range);

    // Only provide actions if there's a selection
    if (!selection || selection.trim().length === 0) {
      return [];
    }

    const actions: vscode.CodeAction[] = [];
    const fileName = vscode.workspace.asRelativePath(document.fileName);
    const language = document.languageId;

    // "Explain selection" action
    const explainAction = new vscode.CodeAction(
      "Dolphin: Explain this code",
      vscode.CodeActionKind.QuickFix
    );
    explainAction.command = {
      command: "dolphin.explainCode",
      title: "Explain with Dolphin",
      arguments: [selection, fileName, language]
    };
    actions.push(explainAction);

    // "Refactor selection" action
    const refactorAction = new vscode.CodeAction(
      "Dolphin: Refactor this code",
      vscode.CodeActionKind.RefactorRewrite
    );
    refactorAction.command = {
      command: "dolphin.refactorCode",
      title: "Refactor with Dolphin",
      arguments: [selection, fileName, language]
    };
    actions.push(refactorAction);

    // "Add tests" action
    const testAction = new vscode.CodeAction(
      "Dolphin: Add tests for this code",
      vscode.CodeActionKind.QuickFix
    );
    testAction.command = {
      command: "dolphin.addTests",
      title: "Add tests with Dolphin",
      arguments: [selection, fileName, language]
    };
    actions.push(testAction);

    // "Document function" action
    const documentAction = new vscode.CodeAction(
      "Dolphin: Document this code",
      vscode.CodeActionKind.QuickFix
    );
    documentAction.command = {
      command: "dolphin.documentCode",
      title: "Document with Dolphin",
      arguments: [selection, fileName, language]
    };
    actions.push(documentAction);

    return actions;
  }
}
