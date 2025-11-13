// vscode-extension/webview/src/lib/api/vscode.ts
// API for communicating with VS Code extension

import type { AgentEvent } from "@shared/types/events";

// VS Code API singleton
let vscodeApi: any = null;

// Get or initialize VS Code API
export function getVSCodeAPI() {
  if (vscodeApi) return vscodeApi;

  // @ts-ignore - acquireVsCodeApi is injected by VS Code
  if (typeof acquireVsCodeApi !== "undefined") {
    // @ts-ignore
    vscodeApi = acquireVsCodeApi();
  } else {
    // Mock API for browser development
    console.warn("[VSCode API] Running in browser mode - using mock API");
    vscodeApi = {
      postMessage: (message: any) => {
        console.log("[VSCode API] Mock postMessage:", message);
      },
      setState: (state: any) => {
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

// Send message to extension
export function sendMessage(message: string, mode?: "code" | "architect") {
  const api = getVSCodeAPI();
  api.postMessage({
    type: "send_message",
    content: message,
    mode: mode || "code",
    timestamp: Date.now(),
  });
}

// Abort current generation
export function abortGeneration() {
  const api = getVSCodeAPI();
  api.postMessage({
    type: "abort_generation",
    timestamp: Date.now(),
  });
}

// Phase 5: Conversation Management

// List all conversations
export function listConversations() {
  const api = getVSCodeAPI();
  api.postMessage({
    type: "list_conversations",
    timestamp: Date.now(),
  });
}

// Load a conversation (creates a branch)
export function loadConversation(conversationId: string) {
  const api = getVSCodeAPI();
  api.postMessage({
    type: "load_conversation",
    conversationId,
    timestamp: Date.now(),
  });
}

// Delete a conversation
export function deleteConversation(conversationId: string) {
  const api = getVSCodeAPI();
  api.postMessage({
    type: "delete_conversation",
    conversationId,
    timestamp: Date.now(),
  });
}

// Rename a conversation
export function renameConversation(conversationId: string, newTitle: string) {
  const api = getVSCodeAPI();
  api.postMessage({
    type: "rename_conversation",
    conversationId,
    newTitle,
    timestamp: Date.now(),
  });
}

// Save webview state
export function saveState(state: any) {
  const api = getVSCodeAPI();
  api.setState(state);
}

// Get webview state
export function getState(): any {
  const api = getVSCodeAPI();
  return api.getState();
}

// Event listeners for messages from extension
type MessageHandler = (event: AgentEvent) => void;
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
  const vscode = getVSCodeAPI();
  vscode.postMessage({ type: "webview_loaded" });
  console.log("[VSCode API] Sent webview_loaded confirmation to extension");

  window.addEventListener("message", (event) => {
    const message = event.data;
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
