/**
 * Core type definitions for Dolphin v2 Orchestration Architecture
 * Based on: docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md
 */

// =============================================================================
// Workflow State Types
// =============================================================================

/**
 * Workflow execution modes
 */
export type WorkflowMode = "editor" | "architect";

/**
 * State machine states for workflow execution
 */
export type WorkflowState =
  | "idle"
  | "researching"
  | "clarifying"
  | "planning"
  | "awaiting_approval"
  | "plan_revision"
  | "executing"
  | "validating"
  | "complete"
  | "cancelled"
  | "error";

/**
 * Workflow phase identifiers
 */
export type WorkflowPhase = "research" | "planning" | "implementation" | "validation";

// =============================================================================
// Task Input & Context
// =============================================================================

/**
 * Context hints from the user/extension
 */
export interface ContextHints {
  files?: string[];
  folders?: string[];
  selection?: string;
}

/**
 * Input for starting a task
 */
export interface TaskInput {
  mode: WorkflowMode;
  message: string;
  context: ContextHints;
  conversationHistory?: Message[];
}

/**
 * Message format for conversation history
 */
export interface Message {
  role: "user" | "assistant";
  content: string | ContentBlock[];
}

/**
 * Content block for structured messages
 */
export interface ContentBlock {
  type: "text" | "thinking" | "tool_use" | "tool_result";
  text?: string;
  content?: string;
  tool_use_id?: string;
  [key: string]: unknown;
}

// =============================================================================
// Task Session & Metadata
// =============================================================================

/**
 * Session metadata tracking
 */
export interface SessionMetadata {
  modelUsed?: string[];
  tokensUsed: number;
  estimatedCost: number;
  startedAt: string;
  completedAt?: string;
}

/**
 * Task session state
 */
export interface TaskSession {
  id: string;
  mode: WorkflowMode;
  state: WorkflowState;
  plan?: Plan;
  execution?: ExecutionResult;
  metadata: SessionMetadata;
  input: TaskInput;
  research?: ResearchResult;
  clarification?: ClarificationResult;
}

// =============================================================================
// Plan Types
// =============================================================================

/**
 * Plan status
 */
export type PlanStatus = "pending_approval" | "approved" | "rejected" | "cancelled";

/**
 * Plan complexity estimate
 */
export type PlanComplexity = "low" | "medium" | "high";

/**
 * Plan revision history entry
 */
export interface PlanRevision {
  version: number;
  createdAt: string;
  rejectedAt?: string;
  rejectedReason?: string;
  contentPath: string;
}

/**
 * Implementation plan
 */
export interface Plan {
  version: number;
  status: PlanStatus;
  createdAt: string;
  approvedAt?: string;
  model: string;
  tokensUsed: number;
  estimatedCost: number;
  content: string;
  contentPath?: string;

  // Parsed plan fields
  overview?: string;
  filesToModify: string[];
  filesToCreate: string[];
  steps: string[];
  complexity: PlanComplexity;
  estimatedTokens: number;

  // Revision history
  revisions?: PlanRevision[];
}

// =============================================================================
// Research Types
// =============================================================================

/**
 * Knowledge Bank search result
 */
export interface KBResult {
  file: string;
  startLine: number;
  endLine: number;
  content: string;
  language: string;
  score: number;
  chunkId: string;
  tokens?: number;
}

/**
 * KB search record
 */
export interface KBSearch {
  query: string;
  resultsCount: number;
  topResult?: string;
}

/**
 * Research phase result
 */
export interface ResearchResult {
  completedAt: string;
  model: string;
  tokensUsed: number;
  findings: string;
  kbSearches: KBSearch[];
  relevantFiles: string[];
}

// =============================================================================
// Clarification Types
// =============================================================================

/**
 * Clarification question from LLM
 */
export interface ClarificationQuestion {
  question: string;
  priority: "critical" | "high" | "medium" | "low";
  reason: string;
}

/**
 * User's response to clarification questions
 */
export interface ClarificationResponse {
  answers: string;
  timestamp: string;
}

/**
 * Clarification phase result
 */
export interface ClarificationResult {
  completedAt: string;
  model: string;
  tokensUsed: number;
  conversationTurns: number;
  questions: ClarificationQuestion[];
  responses: ClarificationResponse[];
  readyForPlanning: boolean;
  finalContext: string;
}

// =============================================================================
// Execution Types
// =============================================================================

/**
 * Execution step status
 */
export type ExecutionStepStatus = "pending" | "in_progress" | "completed" | "failed";

/**
 * Individual execution step
 */
export interface ExecutionStep {
  stepNumber: number;
  description: string;
  status: ExecutionStepStatus;
  startedAt?: string;
  completedAt?: string;
  error?: string;
}

/**
 * Execution result
 */
export interface ExecutionResult {
  startedAt: string;
  completedAt?: string;
  model: string;
  tokensUsed: number;
  cost: number;
  steps: ExecutionStep[];
  success: boolean;
  error?: string;
}

// =============================================================================
// Context Types
// =============================================================================

/**
 * File content with metadata
 */
export interface FileContent {
  path: string;
  content: string;
  language: string;
  tokens: number;
}

/**
 * Assembled context for prompts
 */
export interface Context {
  kbResults: KBResult[];
  files: FileContent[];
  repoMap: string | null;
  totalTokens: number;
  truncated: boolean;
}

/**
 * Parameters for building context
 */
export interface ContextBuildParams {
  searchQuery?: string;
  files?: string[];
  maxTokens: number;
  includeRepoMap?: boolean;
  scope?: string;
  researchFindings?: ResearchResult;
}

// =============================================================================
// Claude Provider Types
// =============================================================================

/**
 * Claude model identifiers
 */
export type ClaudeModel =
  | "claude-opus-4-20250514"
  | "claude-sonnet-4-5-20250929"
  | "claude-haiku-4-20250514";

/**
 * Thinking mode for Claude
 */
export type ThinkingMode = "normal" | "extended";

/**
 * Authentication status
 */
export interface AuthStatus {
  authenticated: boolean;
  mode: "api_key" | "subscription" | "claude_cli" | "none";
  source?: string;
  warning?: string;
  error?: string;
}

/**
 * Tool definition
 */
export interface Tool {
  name: string;
  description: string;
  parameters?: Record<string, unknown>;
}

/**
 * Execution parameters for Claude
 */
export interface ExecutionParams {
  model: ClaudeModel;
  prompt: string;
  systemPrompt?: string;
  context?: Context;
  tools?: Tool[];
  thinkingMode?: ThinkingMode;
}

/**
 * Claude response chunk types
 */
export type ChunkType = "text" | "thinking" | "tool_use" | "tool_result";

/**
 * Claude response chunk
 */
export interface ClaudeChunk {
  type: ChunkType;
  content: string;
  toolName?: string;
  toolInput?: unknown;
  toolResult?: unknown;
}

// =============================================================================
// Workflow Update Events
// =============================================================================

/**
 * Workflow update event types
 */
export type WorkflowUpdateType = "state_change" | "progress" | "tool_call" | "chunk" | "error";

/**
 * Workflow update event
 */
export interface WorkflowUpdate {
  type: WorkflowUpdateType;
  sessionId: string;
  timestamp: string;
  data: unknown;
}

// =============================================================================
// JSON-RPC Types
// =============================================================================

/**
 * JSON-RPC message
 */
export interface JSONRPCMessage {
  jsonrpc: "2.0";
  id?: string | number;
  method?: string;
  params?: unknown;
  result?: unknown;
  error?: JSONRPCError;
}

/**
 * JSON-RPC error
 */
export interface JSONRPCError {
  code: number;
  message: string;
  data?: unknown;
}

// =============================================================================
// Prompt Builder Types
// =============================================================================

/**
 * Research prompt parameters
 */
export interface ResearchPromptParams {
  task: string;
  context: Context;
  systemPrompt: string;
}

/**
 * Planning prompt parameters
 */
export interface PlanningPromptParams {
  task: string;
  research: ResearchResult;
  context: Context;
  systemPrompt: string;
}

/**
 * Implementation prompt parameters
 */
export interface ImplementationPromptParams {
  plan: Plan;
  context: Context;
  systemPrompt: string;
}

/**
 * Editor prompt parameters
 */
export interface EditorPromptParams {
  message: string;
  context: Context;
  conversationHistory?: Message[];
}

// =============================================================================
// State Store Types
// =============================================================================

/**
 * Session summary for listing
 */
export interface SessionSummary {
  id: string;
  mode: WorkflowMode;
  state: WorkflowState;
  title: string;
  createdAt: Date;
  updatedAt: Date;
  tokensUsed: number;
  cost: number;
}

/**
 * Configuration for state store
 */
export interface StateStoreConfig {
  storagePath?: string;
}

// =============================================================================
// Orchestrator Interface
// =============================================================================

/**
 * Core orchestrator interface
 */
export interface IOrchestrator {
  // Workflow management
  startTask(input: TaskInput): Promise<TaskSession>;
  approveTask(sessionId: string): Promise<void>;
  rejectTask(sessionId: string, feedback?: string): Promise<void>;
  revisePlan(sessionId: string, feedback: string): Promise<void>;
  cancelTask(sessionId: string): Promise<void>;

  // State queries
  getSession(sessionId: string): Promise<TaskSession | null>;
  getCurrentPhase(sessionId: string): Promise<WorkflowPhase>;

  // Event streaming
  subscribeToUpdates(sessionId: string): AsyncIterableIterator<WorkflowUpdate>;
}

/**
 * Workflow interface
 */
export interface IWorkflow {
  execute(input: TaskInput): AsyncIterableIterator<WorkflowUpdate>;
}

// =============================================================================
// KB Client Types
// =============================================================================

/**
 * Search parameters for KB
 */
export interface SearchParams {
  query: string;
  topK?: number;
  diversityThreshold?: number;
  useReranking?: boolean;
  repoName?: string;
}

/**
 * KB search result
 */
export interface SearchResult {
  file_path: string;
  start_line: number;
  end_line: number;
  snippet_text: string;
  language: string;
  score: number;
  chunk_id: string;
}

/**
 * Fetch lines parameters
 */
export interface FetchLinesParams {
  repoName: string;
  filePath: string;
  startLine: number;
  endLine: number;
}

/**
 * File slice result
 */
export interface FileSlice {
  content: string;
  startLine: number;
  endLine: number;
}

/**
 * KB health status
 */
export interface HealthStatus {
  status: "ok" | "degraded" | "unavailable";
  details?: string;
}
