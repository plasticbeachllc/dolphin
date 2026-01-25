import { z } from "zod";

export const SearchRequestSchema = z.object({
  query: z.string().min(1),
  repos: z.array(z.string()).optional(),
  path_prefix: z.array(z.string()).optional(),
  exclude_paths: z.array(z.string()).optional(),
  exclude_patterns: z.array(z.string()).optional(),
  top_k: z.number().int().min(1).optional(),
  max_snippets: z.number().int().min(1).optional(),
  deadline_ms: z.number().int().min(50).optional(),
  embed_model: z.enum(["small", "large"]).optional(),
  score_cutoff: z.number().optional(),
  mmr_enabled: z.boolean().optional(),
  mmr_lambda: z.number().min(0).max(1).optional(),
  cursor: z.string().optional(),
  include_prompt_ready: z.boolean().optional(),
  include_snippets: z.boolean().optional(),
  ann_strategy: z.enum(["speed", "accuracy", "adaptive", "custom"]).optional(),
  ann_nprobes: z.number().int().min(1).max(50).optional(),
  ann_refine_factor: z.number().int().min(1).max(100).optional(),
  include_graph_context: z.boolean().optional(),
  context_lines_before: z.number().int().min(0).max(10).optional(),
  context_lines_after: z.number().int().min(0).max(10).optional(),
});

export type SearchRequestBody = z.infer<typeof SearchRequestSchema>;
