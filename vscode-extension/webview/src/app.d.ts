// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
  interface VSCodeAPI {
    postMessage(message: unknown): void;
    getState<T = unknown>(): T | undefined;
    setState<T = unknown>(state: T): void;
  }

  interface Window {
    acquireVsCodeApi?: () => VSCodeAPI;
  }

  var acquireVsCodeApi: undefined | (() => VSCodeAPI);

  namespace App {
    // interface Error {}
    // interface Locals {}
    // interface PageData {}
    // interface PageState {}
    // interface Platform {}
  }
}

export {};
