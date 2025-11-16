import * as vscode from "vscode";

export interface TestOutputChannel extends vscode.OutputChannel {
  getOutput(): string;
}

export function createMockOutputChannel(name = "Test Output Channel"): TestOutputChannel {
  const buffer: string[] = [];

  const channel: TestOutputChannel = {
    name,
    append: (value: string) => {
      buffer.push(value);
    },
    appendLine: (value: string) => {
      buffer.push(`${value}\n`);
    },
    replace: (value: string) => {
      buffer.length = 0;
      buffer.push(value);
    },
    clear: () => {
      buffer.length = 0;
    },
    show: () => {
      // no-op for tests
    },
    hide: () => {
      // no-op for tests
    },
    dispose: () => {
      buffer.length = 0;
    },
    getOutput: () => buffer.join(""),
  };

  return channel;
}
