import * as assert from "assert";
import * as vscode from "vscode";
import { DolphinCodeActionProvider } from "../../../../editor/code-actions";

// Helper to resolve code actions from provider result
async function resolveActions(
  result: vscode.ProviderResult<(vscode.CodeAction | vscode.Command)[]>
): Promise<(vscode.CodeAction | vscode.Command)[]> {
  if (Array.isArray(result)) {
    return result;
  } else if (result && typeof result === "object" && "then" in result) {
    const awaited = await result;
    return awaited || [];
  }
  return [];
}

describe("DolphinCodeActionProvider Tests", () => {
  let provider: DolphinCodeActionProvider;
  let mockViewProvider: {
    prefillInput: (text: string) => void;
  };

  beforeEach(() => {
    // Create mock view provider
    mockViewProvider = {
      prefillInput: (_text: string) => {
        // Mock implementation
      },
    };
    provider = new DolphinCodeActionProvider(mockViewProvider);
  });

  describe("provideCodeActions", () => {
    it("Should return empty array for empty selection", async () => {
      const document = await vscode.workspace.openTextDocument({
        content: "const x = 1;",
        language: "typescript",
      });

      const range = new vscode.Range(0, 0, 0, 0);
      const context = {
        diagnostics: [],
        only: undefined,
        triggerKind: vscode.CodeActionTriggerKind.Invoke,
      };

      const result = provider.provideCodeActions(
        document,
        range,
        context,
        {} as vscode.CancellationToken
      );
      const actions = await resolveActions(result);

      assert.strictEqual(actions.length, 0, "Should return empty array for empty selection");
    });

    it("Should return code actions for non-empty selection", async () => {
      const document = await vscode.workspace.openTextDocument({
        content: "function test() {\n  return 42;\n}",
        language: "typescript",
      });

      const range = new vscode.Range(0, 0, 2, 1);
      const context = {
        diagnostics: [],
        only: undefined,
        triggerKind: vscode.CodeActionTriggerKind.Invoke,
      };

      const result = provider.provideCodeActions(
        document,
        range,
        context,
        {} as vscode.CancellationToken
      );
      const actions = await resolveActions(result);

      assert.ok(actions.length > 0, "Should return code actions for non-empty selection");
      assert.strictEqual(actions.length, 4, "Should return 4 code actions");
    });

    it('Should provide "Explain this code" action', async () => {
      const document = await vscode.workspace.openTextDocument({
        content: "const x = 42;",
        language: "typescript",
      });

      const range = new vscode.Range(0, 0, 0, 13);
      const context = {
        diagnostics: [],
        only: undefined,
        triggerKind: vscode.CodeActionTriggerKind.Invoke,
      };

      const result = provider.provideCodeActions(
        document,
        range,
        context,
        {} as vscode.CancellationToken
      );
      const actions = await resolveActions(result);

      assert.ok(actions.length > 0);
      const explainAction = actions.find((a) =>
        (a as vscode.CodeAction).title?.includes("Explain")
      ) as vscode.CodeAction;

      assert.ok(explainAction, 'Should include "Explain this code" action');
      assert.strictEqual(explainAction?.kind, vscode.CodeActionKind.QuickFix);
      assert.ok(explainAction?.command, "Action should have a command");
      assert.strictEqual(explainAction?.command?.command, "dolphin.explainCode");
    });

    it('Should provide "Refactor this code" action', async () => {
      const document = await vscode.workspace.openTextDocument({
        content: "const x = 42;",
        language: "typescript",
      });

      const range = new vscode.Range(0, 0, 0, 13);
      const context = {
        diagnostics: [],
        only: undefined,
        triggerKind: vscode.CodeActionTriggerKind.Invoke,
      };

      const result = provider.provideCodeActions(
        document,
        range,
        context,
        {} as vscode.CancellationToken
      );
      const actions = await resolveActions(result);

      const refactorAction = actions.find((a) =>
        (a as vscode.CodeAction).title?.includes("Refactor")
      ) as vscode.CodeAction;

      assert.ok(refactorAction, 'Should include "Refactor this code" action');
      assert.strictEqual(refactorAction?.kind, vscode.CodeActionKind.RefactorRewrite);
      assert.strictEqual(refactorAction?.command?.command, "dolphin.refactorCode");
    });

    it('Should provide "Add tests" action', async () => {
      const document = await vscode.workspace.openTextDocument({
        content: "function calculate(a: number) { return a * 2; }",
        language: "typescript",
      });

      const range = new vscode.Range(0, 0, 0, 47);
      const context = {
        diagnostics: [],
        only: undefined,
        triggerKind: vscode.CodeActionTriggerKind.Invoke,
      };

      const result = provider.provideCodeActions(
        document,
        range,
        context,
        {} as vscode.CancellationToken
      );
      const actions = await resolveActions(result);

      const testAction = actions.find((a) =>
        (a as vscode.CodeAction).title?.includes("tests")
      ) as vscode.CodeAction;

      assert.ok(testAction, 'Should include "Add tests" action');
      assert.strictEqual(testAction?.command?.command, "dolphin.addTests");
    });

    it('Should provide "Document this code" action', async () => {
      const document = await vscode.workspace.openTextDocument({
        content: "function undocumented() { }",
        language: "typescript",
      });

      const range = new vscode.Range(0, 0, 0, 27);
      const context = {
        diagnostics: [],
        only: undefined,
        triggerKind: vscode.CodeActionTriggerKind.Invoke,
      };

      const result = provider.provideCodeActions(
        document,
        range,
        context,
        {} as vscode.CancellationToken
      );
      const actions = await resolveActions(result);

      const documentAction = actions.find((a) =>
        (a as vscode.CodeAction).title?.includes("Document")
      ) as vscode.CodeAction;

      assert.ok(documentAction, 'Should include "Document this code" action');
      assert.strictEqual(documentAction?.command?.command, "dolphin.documentCode");
    });

    it("Should pass correct arguments to command", async () => {
      const testCode = 'const greeting = "Hello";';
      const document = await vscode.workspace.openTextDocument({
        content: testCode,
        language: "javascript",
      });

      const range = new vscode.Range(0, 0, 0, testCode.length);
      const context = {
        diagnostics: [],
        only: undefined,
        triggerKind: vscode.CodeActionTriggerKind.Invoke,
      };

      const result = provider.provideCodeActions(
        document,
        range,
        context,
        {} as vscode.CancellationToken
      );
      const actions = await resolveActions(result);

      const explainAction = actions.find((a) =>
        (a as vscode.CodeAction).title?.includes("Explain")
      ) as vscode.CodeAction;

      assert.ok(explainAction?.command);
      assert.ok(Array.isArray(explainAction.command.arguments));
      assert.strictEqual(explainAction.command.arguments?.length, 3);

      // First argument should be the selected code
      assert.strictEqual(explainAction.command.arguments[0], testCode);

      // Second argument should be the file name (relative path)
      assert.ok(typeof explainAction.command.arguments[1] === "string");

      // Third argument should be the language
      assert.strictEqual(explainAction.command.arguments[2], "javascript");
    });

    it("Should handle whitespace-only selection", async () => {
      const document = await vscode.workspace.openTextDocument({
        content: "const x = 1;\n   \nconst y = 2;",
        language: "typescript",
      });

      // Select only whitespace
      const range = new vscode.Range(1, 0, 1, 3);
      const context = {
        diagnostics: [],
        only: undefined,
        triggerKind: vscode.CodeActionTriggerKind.Invoke,
      };

      const result = provider.provideCodeActions(
        document,
        range,
        context,
        {} as vscode.CancellationToken
      );
      const actions = await resolveActions(result);

      assert.strictEqual(
        actions.length,
        0,
        "Should return empty array for whitespace-only selection"
      );
    });

    it("Should work with different programming languages", async () => {
      const languages = ["typescript", "javascript", "python", "java", "go"];

      for (const lang of languages) {
        const document = await vscode.workspace.openTextDocument({
          content: "some code here",
          language: lang,
        });

        const range = new vscode.Range(0, 0, 0, 14);
        const context = {
          diagnostics: [],
          only: undefined,
          triggerKind: vscode.CodeActionTriggerKind.Invoke,
        };

        const result = provider.provideCodeActions(
          document,
          range,
          context,
          {} as vscode.CancellationToken
        );
        const actions = await resolveActions(result);

        assert.ok(actions.length === 4, `Should provide 4 actions for ${lang}`);

        const explainAction = actions.find((a) =>
          (a as vscode.CodeAction).title?.includes("Explain")
        ) as vscode.CodeAction;
        assert.strictEqual(
          explainAction?.command?.arguments?.[2],
          lang,
          `Language should be ${lang}`
        );
      }
    });
  });
});
