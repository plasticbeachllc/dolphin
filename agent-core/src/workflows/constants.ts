/**
 * Constants for workflow configuration
 */

/**
 * Model identifiers for different workflow phases
 * Update these when Claude releases new model versions
 */
export const MODELS = {
  /** Fast, cost-effective model for research and discovery */
  RESEARCH: 'claude-haiku-4-20250514' as const,

  /** Balanced model for clarification and reasoning */
  CLARIFICATION: 'claude-sonnet-4-20250514' as const,

  /** Most capable model for complex planning */
  PLANNING: 'claude-opus-4-20250514' as const,
} as const;

/**
 * Approximate tokens per character for rough estimation
 * Based on typical English text with Claude's tokenizer
 * For accurate counting, use an actual tokenizer library
 */
export const CHARS_PER_TOKEN = 4;

/**
 * Default maximum clarification turns before proceeding to planning
 */
export const DEFAULT_MAX_CLARIFICATION_TURNS = 3;
