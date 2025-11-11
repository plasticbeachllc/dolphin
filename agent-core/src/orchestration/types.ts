// agent-core/src/orchestration/types.ts

/**
 * EP-11: Architect Mode KB Discovery Enhancement
 *
 * Shared types for the 3-phase orchestration workflow:
 * 1. Discovery Phase - Systematic KB search
 * 2. Synthesis Phase - Analysis and questions
 * 3. Planning Phase - Implementation plan
 */

import type { Message } from "../llm/claude-tool-executor";

// ============================================================================
// Discovery Phase Types
// ============================================================================

export interface DiscoveryConfig {
  maxQueries: number;              // Default: 5
  maxResultsPerQuery: number;      // Default: 5
  includeGraphContext: boolean;    // Default: true
  confidenceThreshold: number;     // Default: 0.6
  timeoutMs: number;               // Default: 5000
}

export interface DiscoveryQuery {
  text: string;
  strategy: "broad" | "specific" | "pattern" | "dependency";
  priority: number;
  expectedResultType: "function" | "class" | "file" | "pattern" | "any";
}

export interface EnrichedChunk {
  chunk_id: string;
  repo: string;
  path: string;
  start_line: number;
  end_line: number;
  language?: string;
  symbol_kind?: string | null;
  symbol_name?: string | null;
  symbol_path?: string | null;
  score: number;
  snippet: string;
  commit?: string;
  branch?: string;
  graph_context?: GraphContext;
}

export interface GraphContext {
  nodes: GraphNode[];
  relationships: GraphRelationship[];
}

export interface GraphNode {
  type: string;                    // "function", "class", "method", etc.
  qualified_name: string;          // Full path like "pkg.mod.Class.method"
  signature?: string;              // Function/method signature
  line_range: [number, number];   // [start, end] line numbers
}

export interface GraphRelationship {
  type: "calls" | "inherits" | "implements" | "imports";
  direction: "incoming" | "outgoing";
  source: GraphNode;
  target: GraphNode;
  line_number?: number;
}

export interface DiscoveryResult {
  queries: DiscoveryQuery[];
  retrievedChunks: EnrichedChunk[];
  graphContext: GraphContext | null;
  confidence: number;
  gaps: string[];                  // Identified information gaps
  summary: string;
  executionTimeMs: number;
}

// ============================================================================
// Synthesis Phase Types
// ============================================================================

export interface SynthesisResult {
  analysis: string;
  assumptions: Assumption[];
  clarifyingQuestions: ClarifyingQuestion[];
  risks: Risk[];
  confidence: number;
}

export interface Assumption {
  statement: string;
  confidence: "high" | "medium" | "low";
  basedOn: string[];  // Source attributions
  needsValidation: boolean;
}

export interface ClarifyingQuestion {
  question: string;
  priority: "critical" | "high" | "medium" | "low";
  reason: string;
  suggestedAnswers?: string[];
}

export interface Risk {
  description: string;
  severity: "high" | "medium" | "low";
  mitigation?: string;
}

// ============================================================================
// Planning Phase Types
// ============================================================================

export interface Plan {
  title: string;
  summary: string;
  phases: PlanPhase[];
  todoList: TodoItem[];
  risks: string[];
  assumptions: string[];
  estimatedComplexity: "low" | "medium" | "high";
  references: CodeReference[];
}

export interface PlanPhase {
  name: string;
  description: string;
  steps: string[];
  affectedFiles: string[];
  estimatedTime: string;
}

export interface TodoItem {
  id: string;
  description: string;
  status: "pending" | "in_progress" | "completed";
  priority: number;
  dependencies: string[];
  fileReferences: string[];
}

export interface CodeReference {
  file: string;
  symbol?: string;
  lineRange?: [number, number];
  description: string;
}

// ============================================================================
// Orchestrator Types
// ============================================================================

export interface ArchitectContext {
  userQuery: string;
  workspaceRoot: string;
  repoName: string;
  conversationHistory: Message[];
}

export interface ArchitectResult {
  discovery: DiscoveryResult;
  synthesis?: SynthesisResult;  // Phase 2 - not implemented in Phase 1
  plan?: Plan;                   // Phase 3 - not implemented in Phase 1
}
