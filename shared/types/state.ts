// shared/types/state.ts
import { z } from "zod";

// Plan Step Schema
export const PlanStepSchema = z.object({
  id: z.string(),
  order: z.number(),
  description: z.string(),
  action_type: z.enum(["tool_call", "llm_generation", "user_interaction"]),
  tool: z.string().optional(),
  status: z.enum(["pending", "running", "completed", "failed"]),
  started_at: z.string().optional(),
  completed_at: z.string().optional(),
  input: z.record(z.any()).optional(),
  output: z.record(z.any()).optional(),
  error: z.string().optional(),
});

// Plan Schema
export const PlanSchema = z.object({
  schema_version: z.string().default("1.0"),
  plan: z.object({
    id: z.string(),
    created_at: z.string(),
    updated_at: z.string(),
    status: z.enum(["pending", "executing", "completed", "failed", "blocked"]),
    mode: z.enum(["architect", "editor"]),
    task: z.string(),
    workspace_root: z.string(),
  }),
  steps: z.array(PlanStepSchema),
});

// Token Usage Schema for per-message tracking
export const TokenUsageSchema = z.object({
  input: z.number().default(0),
  output: z.number().default(0),
  cacheRead: z.number().optional(),
  cacheWrite: z.number().optional(),
});

// Conversation Message Schema
export const ConversationMessageSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  timestamp: z.string(),
  pinned: z.boolean().optional(),
  tokens: TokenUsageSchema.optional(),
});

// Conversation Metadata Schema (Phase 5)
export const ConversationMetadataSchema = z.object({
  // Core metadata
  title: z.string().default("Untitled Conversation"),

  // File tracking
  files: z.array(z.string()).default([]),

  // Token tracking
  token_count: z.number().default(0),

  // UI state
  pinned: z.boolean().default(false),

  // Parent conversation (for branching)
  parent_conversation_id: z.string().optional(),
  branch_point_message_id: z.string().optional(),

  // Last active timestamp
  last_active_at: z.string().optional(),
});

// Conversation Schema
export const ConversationSchema = z.object({
  schema_version: z.string().default("1.0"),
  conversation: z.object({
    id: z.string(),
    created_at: z.string(),
    updated_at: z.string(),
    workspace_root: z.string(),
  }),

  // NEW: Metadata section (Phase 5)
  metadata: ConversationMetadataSchema.optional().default({}),

  messages: z.array(ConversationMessageSchema),
  summaries: z
    .array(
      z.object({
        range_start: z.number(),
        range_end: z.number(),
        key_points: z.array(z.string()),
        created_at: z.string(),
      })
    )
    .optional(),
});

export type Plan = z.infer<typeof PlanSchema>;
export type PlanStep = z.infer<typeof PlanStepSchema>;
export type Conversation = z.infer<typeof ConversationSchema>;
export type ConversationMessage = z.infer<typeof ConversationMessageSchema>;
export type ConversationMetadata = z.infer<typeof ConversationMetadataSchema>;
export type TokenUsage = z.infer<typeof TokenUsageSchema>;
