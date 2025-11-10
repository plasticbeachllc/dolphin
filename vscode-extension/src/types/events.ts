// vscode-extension/src/types/events.ts

// Extension → Agent Core
export type ExtensionRequest =
  | { type: "send_message"; messageId: string; content: string; context?: any }
  | { type: "abort_generation" }
  | { type: "approve_plan"; planId: string }
  | { type: "reject_plan"; planId: string; feedback?: string }
  | { type: "approve_diff"; diffId: string }
  | { type: "reject_diff"; diffId: string; feedback?: string }
  | { type: "cancel_operation"; operationId: string }
  | { type: "list_conversations" }
  | { type: "load_conversation"; conversationId: string }
  | { type: "delete_conversation"; conversationId: string }
  | { type: "rename_conversation"; conversationId: string; newTitle: string };

// Agent Core → Extension
// All events include an optional requestId for correlation/logging
export type AgentEvent =
  | { type: "agent_ready"; version: string; capabilities: string[]; requestId?: string }
  | { type: "content_delta"; delta: string; requestId?: string }
  | { type: "plan_generated"; plan: Plan; requestId?: string }
  | { type: "plan_step_started"; stepId: string; description: string; requestId?: string }
  | { type: "plan_step_completed"; stepId: string; result: any; requestId?: string }
  | { type: "tool_call_started"; toolId: string; tool: string; input: any; requestId?: string }
  | {
      type: "tool_call_progress";
      toolId: string;
      chunk?: string;
      bytes?: number;
      requestId?: string;
    }
  | {
      type: "tool_call_completed";
      toolId: string;
      result: any;
      error?: any;
      executionTime?: number;
      diff?: FileDiff;
      requestId?: string;
    }
  | {
      type: "require_confirmation";
      confirmId: string;
      title: string;
      message: string;
      options: string[];
      requestId?: string;
    }
  | { type: "task_completed"; success: boolean; result?: any; error?: any }
  | { type: "error"; error: AgentError }
  | { type: "focus_input" }
  | { type: "clear_conversation" }
  | { type: "prefill_input"; text: string }
  | { type: "conversation_loaded"; conversation: any; branchInfo?: { originalId: string; originalTitle: string } }
  | { type: "conversations_listed"; conversations: ConversationListItem[] }
  | { type: "conversation_deleted"; conversationId: string }
  | { type: "conversation_renamed"; conversationId: string; newTitle: string };

export interface Plan {
  id: string;
  mode: "architect" | "editor";
  task: string;
  steps: PlanStep[];
  status: "pending" | "executing" | "completed" | "failed" | "blocked";
  created_at: string;
  updated_at: string;
}

export interface PlanStep {
  id: string;
  order: number;
  description: string;
  action_type: "tool_call" | "llm_generation" | "user_interaction";
  tool?: string;
  status: "pending" | "running" | "completed" | "failed";
  started_at?: string;
  completed_at?: string;
  input?: Record<string, any>;
  output?: Record<string, any>;
}

export interface AgentError {
  code: ErrorCode;
  message: string;
  details?: string;
  suggestions: string[];
  recoverable: boolean;
}

export type ErrorCode =
  | "FILE_NOT_FOUND"
  | "PERMISSION_DENIED"
  | "RATE_LIMIT_EXCEEDED"
  | "COMMAND_NOT_ALLOWED"
  | "DIFF_APPLY_FAILED"
  | "CONTEXT_OVERFLOW"
  | "PLAN_BLOCKED"
  | "SERVICE_UNAVAILABLE";

export interface FileDiff {
  oldFileName: string;
  newFileName: string;
  additions: number;
  deletions: number;
  hunks: DiffHunk[];
}

export interface DiffHunk {
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: string[];
}

// Phase 5: Conversation Management Types

export interface ConversationListItem {
  id: string;
  metadata: ConversationMetadata;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationMetadata {
  title: string;
  files: string[];
  token_count: number;
  pinned: boolean;
  parent_conversation_id?: string;
  branch_point_message_id?: string;
  last_active_at?: string;
}

export interface LoadConversationResult {
  conversation: any; // Full Conversation object from state.ts
  branchInfo?: {
    originalId: string;
    originalTitle: string;
  };
}