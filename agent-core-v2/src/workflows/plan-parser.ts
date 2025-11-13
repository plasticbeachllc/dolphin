/**
 * Robust Plan Parser - Multi-pass Markdown/TOML extraction with auto-repair
 *
 * Handles messy LLM-generated Markdown by:
 * 1. Extracting TOML candidates from multiple sources (fenced, unlabeled, free-text)
 * 2. Scoring candidates with heuristics
 * 3. Normalizing/repairing common LLM mistakes
 * 4. Strict parsing and schema validation
 */

import { marked } from 'marked';
import * as TOML from 'toml';
import { z } from 'zod';

/**
 * Zod schema for plan TOML structure
 */
const PlanSchema = z.object({
  plan_version: z.number().int().default(1),

  overview: z.string().min(10).optional(),

  complexity: z.enum(['low', 'medium', 'high']).default('medium'),

  estimated_tokens: z.number().int().positive().optional(),

  files_to_modify: z.array(z.string().min(1)).default([]),

  files_to_create: z.array(z.string().min(1)).default([]),

  steps: z.array(z.object({
    id: z.number().int().positive(),
    description: z.string().min(1),
    files: z.array(z.string()).default([]),
    estimated_tokens: z.number().int().positive().optional(),
  })).default([]),

  dependencies: z.array(z.string()).default([]),

  risks: z.array(z.object({
    description: z.string().min(1),
    mitigation: z.string().optional(),
  })).default([]),

  generated_at: z.string().datetime().optional(),
}).strict();

export type PlanToml = z.infer<typeof PlanSchema>;

interface Candidate {
  src: string;
  where: string;
  score: number;
}

interface ParseResult {
  plan: PlanToml;
  rawToml: string;
  source: string;
}

/**
 * Parse plan from LLM-generated Markdown
 * Uses multi-pass extraction with auto-repair
 */
export function parsePlanFromMarkdown(md: string): ParseResult {
  const candidates = collectTomlCandidates(md);

  if (candidates.length === 0) {
    throw new Error('No plausible TOML found in plan markdown. Expected a TOML code block with plan structure.');
  }

  const errors: Array<{ where: string; err: unknown }> = [];

  // Try each candidate, both raw and repaired
  for (const cand of candidates.sort((a, b) => b.score - a.score)) {
    for (const repaired of [cand.src, normalizeToml(cand.src)]) {
      try {
        const obj = TOML.parse(repaired);
        const plan = PlanSchema.parse(obj);
        return { plan, rawToml: repaired, source: cand.where };
      } catch (err) {
        errors.push({ where: cand.where, err });
      }
    }
  }

  // All candidates failed
  const top = errors[0];
  const errMsg = top?.err instanceof Error ? top.err.message : String(top?.err);
  throw new Error(`TOML parse/validate failed (${top?.where}): ${errMsg}`);
}

/**
 * Collect TOML candidates from markdown in three passes
 */
function collectTomlCandidates(md: string): Candidate[] {
  const out: Candidate[] = [];

  // Pass 1: Explicit TOML fences
  const tokens = marked.lexer(md, { gfm: true });
  for (const token of tokens) {
    if (token.type === 'code') {
      const lang = (token as any).lang?.toLowerCase() || '';
      const text = (token as any).text as string;

      if (lang === 'toml') {
        out.push(scoreCandidate(text, 'fenced:toml'));
      }
    }
  }

  // Pass 2: Unlabeled code fences that look like TOML
  for (const token of tokens) {
    if (token.type === 'code') {
      const lang = (token as any).lang?.toLowerCase() || '';
      const text = (token as any).text as string;

      if (!lang && looksLikeToml(text)) {
        out.push(scoreCandidate(text, 'fenced:unlabeled'));
      }
    }
  }

  // Pass 3: Free-text TOML (greedy but safe)
  const freeText = findFreeTextToml(md);
  if (freeText) {
    out.push(scoreCandidate(freeText, 'free-text'));
  }

  // Deduplicate identical candidates
  const dedup = new Map(out.map(c => [c.src, c]));
  return [...dedup.values()];
}

/**
 * Score a candidate based on TOML-like characteristics
 */
function scoreCandidate(src: string, where: string): Candidate {
  const lines = src.split(/\r?\n/);
  const n = lines.length || 1;

  // Key-value pairs (e.g., "key = value")
  const kvCount = lines.filter(l => /^\s*[\w.+-]+\s*=\s*.+$/.test(l)).length;
  const kvRatio = kvCount / n;

  // Table headers (e.g., "[section]")
  const tblCount = lines.filter(l => /^\s*\[[^\]\n]+\]\s*$/.test(l)).length;
  const tblRatio = tblCount / n;

  // Penalty for stray fences inside the block
  const badFence = /```/.test(src) ? -0.25 : 0;

  // Penalty for unrealistic length
  const lenPenalty = (n > 10000 || n < 3) ? -0.5 : 0;

  // Weighted score
  const score = 0.6 * kvRatio + 0.3 * tblRatio + badFence + lenPenalty;

  return { src, where, score };
}

/**
 * Check if text looks like TOML
 */
function looksLikeToml(s: string): boolean {
  const lines = s.split(/\r?\n/);
  const kv = lines.filter(l => /^\s*[\w.+-]+\s*=\s*.+$/.test(l)).length;
  const tbl = lines.filter(l => /^\s*\[[^\]\n]+\]\s*$/.test(l)).length;
  return kv + tbl >= 2;
}

/**
 * Find free-text TOML (not in code fences)
 */
function findFreeTextToml(md: string): string | null {
  // Grab from first table header to next blank line block or end
  const m = md.match(/^\s*\[[^\]\n]+\][\s\S]+?(?:\n```|\n{2,}|\n#+\s|\s*$)/m);
  if (m) {
    return m[0].replace(/```+.*$/s, '').trim();
  }

  // Fallback: gather consecutive key=value lines
  const m2 = md.match(/((?:^\s*[\w.+-]+\s*=\s*.+\n?){3,})/m);
  return m2 ? m2[1].trim() : null;
}

/**
 * Normalize/repair common LLM mistakes in TOML
 */
function normalizeToml(t: string): string {
  let s = t;

  // Smart quotes → ASCII
  s = s.replace(/[""]/g, '"').replace(/['']/g, "'");

  // Trailing commas before ] or } (invalid in TOML)
  s = s.replace(/,\s*(\]|\})/g, '$1');

  // Lowercase booleans
  s = s.replace(/\b(True|False)\b/g, m => m.toLowerCase());
  s = s.replace(/\b(Inf|NaN)\b/g, m => m.toLowerCase());

  // Tabs → spaces
  s = s.replace(/\t/g, '  ');

  // Strip accidental fences in the block
  s = s.replace(/^\s*```+\s*\w*\s*$/gm, '');

  // Trim BOM
  s = s.replace(/^\uFEFF/, '');

  // Strip stray leading/trailing underscores in numbers
  s = s.replace(/(?<=\D)_(\d)/g, '$1').replace(/(\d)_(?=\D|$)/g, '$1');

  return s.trim();
}

/**
 * Legacy fallback parser for markdown-only plans (without TOML)
 * Used as a last resort if TOML extraction completely fails
 */
export function parseLegacyMarkdownPlan(content: string): Partial<PlanToml> {
  const filesToModify: string[] = [];
  const filesToCreate: string[] = [];
  const steps: Array<{ id: number; description: string; files: string[] }> = [];
  let overview = '';
  let complexity: 'low' | 'medium' | 'high' = 'medium';

  // Extract overview
  const overviewMatch = content.match(/##?\s*(?:Overview|Summary)\s*\n\n([\s\S]*?)(?:\n##|$)/i);
  if (overviewMatch) {
    overview = overviewMatch[1].trim();
  }

  // Extract files to modify
  const modifyMatch = content.match(/##?\s*Files?\s+to\s+Modify\s*\n([\s\S]*?)(?:\n##|$)/i);
  if (modifyMatch) {
    const fileLines = modifyMatch[1].split('\n');
    for (const line of fileLines) {
      const fileMatch = line.match(/[-*]\s*`?([a-zA-Z0-9_/.]+\.[a-zA-Z0-9]+)`?/);
      if (fileMatch) {
        filesToModify.push(fileMatch[1]);
      }
    }
  }

  // Extract files to create
  const createMatch = content.match(/##?\s*Files?\s+to\s+Create\s*\n([\s\S]*?)(?:\n##|$)/i);
  if (createMatch) {
    const fileLines = createMatch[1].split('\n');
    for (const line of fileLines) {
      const fileMatch = line.match(/[-*]\s*`?([a-zA-Z0-9_/.]+\.[a-zA-Z0-9]+)`?/);
      if (fileMatch) {
        filesToCreate.push(fileMatch[1]);
      }
    }
  }

  // Extract steps
  const stepsMatch = content.match(/##?\s*(?:Steps|Implementation\s+Steps?)\s*\n([\s\S]*?)(?:\n##|$)/i);
  if (stepsMatch) {
    const stepLines = stepsMatch[1].split('\n');
    let stepId = 1;
    for (const line of stepLines) {
      const stepMatch = line.match(/^\s*\d+\.\s+(.+)$/);
      if (stepMatch) {
        steps.push({
          id: stepId++,
          description: stepMatch[1].trim(),
          files: [],
        });
      }
    }
  }

  // Extract complexity
  const complexityMatch = content.match(/complexity:?\s*(low|medium|high)/i);
  if (complexityMatch) {
    complexity = complexityMatch[1].toLowerCase() as 'low' | 'medium' | 'high';
  }

  return {
    overview,
    files_to_modify: filesToModify,
    files_to_create: filesToCreate,
    steps,
    complexity,
    estimated_tokens: steps.length * 500,
  };
}
