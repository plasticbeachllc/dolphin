// vscode-extension/webview/src/lib/api/vscode.ts
// API for communicating with VS Code extension

import type { ExtensionToWebviewMessage, WebviewToExtensionMessage } from "@extension-shared/messages";
import type { ProviderId } from "@extension-config/provider-options";

interface VSCodeApi {
  postMessage(message: WebviewToExtensionMessage): void;
  setState(state: unknown): void;
  getState(): unknown;
}

// VS Code API singleton
let vscodeApi: VSCodeApi | null = null;

// Get or initialize VS Code API
export function getVSCodeAPI(): VSCodeApi {
  if (vscodeApi) return vscodeApi;

  // @ts-ignore - acquireVsCodeApi is injected by VS Code
  if (typeof acquireVsCodeApi !== "undefined") {
    // @ts-ignore
    vscodeApi = acquireVsCodeApi();
  } else {
    // Mock API for browser development
    console.warn("[VSCode API] Running in browser mode - using mock API");
    vscodeApi = {
      postMessage: (message: WebviewToExtensionMessage) => {
        console.log("[VSCode API] Mock postMessage:", message);
      },
      setState: (state: unknown) => {
        console.log("[VSCode API] Mock setState:", state);
      },
      getState: () => {
        console.log("[VSCode API] Mock getState");
        return null;
      },
    };
  }

  return vscodeApi;
}

function postVSCodeMessage(message: WebviewToExtensionMessage): void {
  const api = getVSCodeAPI();
  api.postMessage(message);
}

// Send message to extension
export function sendMessage(message: string, mode?: "code" | "architect") {
  postVSCodeMessage({
    type: "send_message",
    content: message,
    mode: mode || "code",
    timestamp: Date.now(),
  });
}

// Abort current generation
export function abortGeneration() {
  postVSCodeMessage({ type: "abort_generation" });
}

// Phase 5: Conversation Management

// List all conversations
export function listConversations() {
  postVSCodeMessage({ type: "list_conversations" });
}

// Load a conversation (creates a branch)
export function loadConversation(conversationId: string) {
  postVSCodeMessage({
    type: "load_conversation",
    conversationId,
  });
}

// Delete a conversation
export function deleteConversation(conversationId: string) {
  postVSCodeMessage({
    type: "delete_conversation",
    conversationId,
  });
}

// Rename a conversation
export function renameConversation(conversationId: string, newTitle: string) {
  postVSCodeMessage({
    type: "rename_conversation",
    conversationId,
    newTitle,
  });
}

export function requestSecret(provider: ProviderId) {
  postVSCodeMessage({ type: "setSecret", provider });
}

// Save webview state
export function saveState(state: unknown) {
  const api = getVSCodeAPI();
  api.setState(state);
}

// Get webview state
export function getState(): unknown {
  const api = getVSCodeAPI();
  return api.getState();
}

// Event listeners for messages from extension
type MessageHandler = (event: ExtensionToWebviewMessage) => void;
const messageHandlers: MessageHandler[] = [];

export function onMessage(handler: MessageHandler) {
  messageHandlers.push(handler);

  // Return unsubscribe function
  return () => {
    const index = messageHandlers.indexOf(handler);
    if (index > -1) {
      messageHandlers.splice(index, 1);
    }
  };
}

// Set up global message listener (called once on init)
if (typeof window !== "undefined") {
  console.log("[VSCode API] Setting up global message listener");

  // CRITICAL: Post a message back to extension to confirm webview is loaded
  postVSCodeMessage({ type: "webview_loaded" });
  console.log("[VSCode API] Sent webview_loaded confirmation to extension");

  window.addEventListener("message", (event) => {
    const message = event.data as ExtensionToWebviewMessage;
    console.log("[VSCode API] Received message:", message);
    console.log("[VSCode API] Current handlers count:", messageHandlers.length);

    // Dispatch to all handlers
    messageHandlers.forEach((handler) => {
      try {
        handler(message);
      } catch (error) {
        console.error("[VSCode API] Error in message handler:", error);
      }
    });
  });
  console.log("[VSCode API] Global message listener registered");
}
