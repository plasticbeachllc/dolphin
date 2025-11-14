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
// Conversation Message Schema
export const ConversationMessageSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  timestamp: z.string(),
  pinned: z.boolean().optional(),
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
