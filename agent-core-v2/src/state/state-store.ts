/**
 * StateStore - TOML Persistence Layer for Dolphin v2
 * 
 * Persists conversation state, plans, and workflow history in human-readable TOML format.
 * 
 * Based on: docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md
 */

import * as TOML from '@iarna/toml';
import { readFile, writeFile, mkdir, readdir, unlink, stat } from 'fs/promises';
import { join, dirname, resolve, relative } from 'path';
import { existsSync } from 'fs';
import { z } from 'zod';
import type {
  TaskSession,
  Plan,
  SessionSummary,
  StateStoreConfig,
} from '../types/index.js';

/**
 * TOML-serializable session format
 */
interface SessionTOML {
  session: {
    id: string;
    mode: string;
    state: string;
    created_at: string;
    updated_at: string;
  };
  input: {
    message: string;
    context: {
      files: string[];
      folders: string[];
      selection: string;
    };
  };
  research?: {
    completed_at: string;
    model: string;
    tokens_used: number;
    findings: string;
    kb_searches: Array<{
      query: string;
      results_count: number;
      top_result?: string;
    }>;
  };
  clarification?: {
    completed_at: string;
    model: string;
    tokens_used: number;
    conversation_turns: number;
    ready_for_planning: boolean;
    final_context: string;
    questions: Array<{
      question: string;
      priority: string;
      reason: string;
    }>;
    responses: Array<{
      answers: string;
      timestamp: string;
    }>;
  };
  plan?: {
    version: number;
    status: string;
    created_at: string;
    approved_at?: string;
    model: string;
    tokens_used: number;
    estimated_cost: number;
    content_path: string;
    revisions?: Array<{
      version: number;
      created_at: string;
      rejected_at?: string;
      rejected_reason?: string;
      content_path: string;
    }>;
  };
  execution?: {
    started_at: string;
    completed_at?: string;
    model: string;
    tokens_used: number;
    cost: number;
    steps: Array<{
      step_number: number;
      description: string;
      status: string;
      started_at?: string;
      completed_at?: string;
    }>;
  };
  metadata: {
    total_tokens: number;
    total_cost: number;
    models_used: string[];
    started_at: string;
    completed_at?: string;
  };
}

/**
 * Zod schemas for runtime validation of TOML data
 */
const SessionTOMLSchema = z.object({
  session: z.object({
    id: z.string(),
    mode: z.string(),
    state: z.string(),
    created_at: z.string(),
    updated_at: z.string(),
  }),
  input: z.object({
    message: z.string(),
    context: z.object({
      files: z.array(z.string()),
      folders: z.array(z.string()),
      selection: z.string(),
    }),
  }),
  research: z.object({
    completed_at: z.string(),
    model: z.string(),
    tokens_used: z.number(),
    findings: z.string(),
    kb_searches: z.array(z.object({
      query: z.string(),
      results_count: z.number(),
      top_result: z.string().optional(),
    })),
  }).optional(),
  clarification: z.object({
    completed_at: z.string(),
    model: z.string(),
    tokens_used: z.number(),
    conversation_turns: z.number(),
    ready_for_planning: z.boolean(),
    final_context: z.string(),
    questions: z.array(z.object({
      question: z.string(),
      priority: z.string(),
      reason: z.string(),
    })),
    responses: z.array(z.object({
      answers: z.string(),
      timestamp: z.string(),
    })),
  }).optional(),
  plan: z.object({
    version: z.number(),
    status: z.string(),
    created_at: z.string(),
    approved_at: z.string().optional(),
    model: z.string(),
    tokens_used: z.number(),
    estimated_cost: z.number(),
    content_path: z.string(),
    revisions: z.array(z.object({
      version: z.number(),
      created_at: z.string(),
      rejected_at: z.string().optional(),
      rejected_reason: z.string().optional(),
      content_path: z.string(),
    })).optional(),
  }).optional(),
  execution: z.object({
    started_at: z.string(),
    completed_at: z.string().optional(),
    model: z.string(),
    tokens_used: z.number(),
    cost: z.number(),
    steps: z.array(z.object({
      step_number: z.number(),
      description: z.string(),
      status: z.string(),
      started_at: z.string().optional(),
      completed_at: z.string().optional(),
    })),
  }).optional(),
  metadata: z.object({
    total_tokens: z.number(),
    total_cost: z.number(),
    models_used: z.array(z.string()),
    started_at: z.string(),
    completed_at: z.string().optional(),
  }),
});

/**
 * StateStore manages persistent storage of sessions, plans, and conversations
 */
export class StateStore {
  private storagePath: string;
  private sessionsDir: string;
  private plansDir: string;
  private conversationsDir: string;

  constructor(config: StateStoreConfig = {}) {
    this.storagePath = config.storagePath || '.dolphin';
    this.sessionsDir = join(this.storagePath, 'sessions');
    this.plansDir = join(this.storagePath, 'plans');
    this.conversationsDir = join(this.storagePath, 'conversations');
    
    // Ensure directories exist
    this.ensureDirectories();
  }

  /**
   * Ensure storage directories exist
   */
  private async ensureDirectories(): Promise<void> {
    const dirs = [
      this.storagePath,
      this.sessionsDir,
      this.plansDir,
      this.conversationsDir,
    ];

    for (const dir of dirs) {
      if (!existsSync(dir)) {
        await mkdir(dir, { recursive: true });
      }
    }
  }

  /**
   * Save a session to disk
   */
  async saveSession(session: TaskSession): Promise<void> {
    await this.ensureDirectories();
    
    const sessionPath = join(this.sessionsDir, `${session.id}.toml`);
    const toml = this.serializeSession(session);
    
    await writeFile(sessionPath, toml, 'utf-8');
  }

  /**
   * Load a session from disk
   */
  async loadSession(sessionId: string): Promise<TaskSession | null> {
    const sessionPath = join(this.sessionsDir, `${sessionId}.toml`);

    if (!existsSync(sessionPath)) {
      return null;
    }

    try {
      const toml = await readFile(sessionPath, 'utf-8');
      return await this.deserializeSession(toml);
    } catch (error) {
      console.error(`[StateStore] Failed to load session ${sessionId}:`, error);
      return null;
    }
  }

  /**
   * Save a plan to disk
   * Returns the path where the plan content was saved
   */
  async savePlan(sessionId: string, plan: Plan): Promise<string> {
    await this.ensureDirectories();

    // Save plan content as markdown
    const planPath = join(this.plansDir, `plan_${sessionId}_v${plan.version}.md`);
    await writeFile(planPath, plan.content, 'utf-8');

    // Update session with plan metadata
    const session = await this.loadSession(sessionId);
    if (session) {
      session.plan = {
        ...plan,
        contentPath: planPath,
      };
      await this.saveSession(session);
    }

    return planPath;
  }

  /**
   * Load a plan from disk
   */
  async loadPlan(sessionId: string, version?: number): Promise<Plan | null> {
    const session = await this.loadSession(sessionId);
    if (!session?.plan) {
      return null;
    }

    const planVersion = version || session.plan.version;
    const planPath = join(this.plansDir, `plan_${sessionId}_v${planVersion}.md`);
    
    if (!existsSync(planPath)) {
      return null;
    }

    try {
      const content = await readFile(planPath, 'utf-8');
      return {
        ...session.plan,
        content,
      };
    } catch (error) {
      console.error(`[StateStore] Failed to load plan ${sessionId} v${planVersion}:`, error);
      return null;
    }
  }

  /**
   * List all sessions with metadata
   */
  async listSessions(): Promise<SessionSummary[]> {
    await this.ensureDirectories();
    
    try {
      const files = await readdir(this.sessionsDir);
      const sessionFiles = files.filter(f => f.endsWith('.toml'));
      
      const summaries: SessionSummary[] = [];
      
      for (const file of sessionFiles) {
        const sessionId = file.replace('.toml', '');
        const session = await this.loadSession(sessionId);
        
        if (session) {
          summaries.push(this.toSummary(session));
        }
      }
      
      // Sort by most recent first
      return summaries.sort((a, b) => 
        b.updatedAt.getTime() - a.updatedAt.getTime()
      );
    } catch (error) {
      console.error('[StateStore] Failed to list sessions:', error);
      return [];
    }
  }

  /**
   * Delete a session and its associated files
   */
  async deleteSession(sessionId: string): Promise<void> {
    // Delete session file
    const sessionPath = join(this.sessionsDir, `${sessionId}.toml`);
    if (existsSync(sessionPath)) {
      await unlink(sessionPath);
    }

    // Delete associated plan files
    try {
      const planFiles = await readdir(this.plansDir);
      const sessionPlans = planFiles.filter(f => f.startsWith(`plan_${sessionId}_`));
      
      for (const planFile of sessionPlans) {
        await unlink(join(this.plansDir, planFile));
      }
    } catch (error) {
      console.error(`[StateStore] Error deleting plans for ${sessionId}:`, error);
    }
  }

  /**
   * Get storage statistics
   */
  async getStats(): Promise<{
    totalSessions: number;
    totalPlans: number;
    storageSize: number;
  }> {
    await this.ensureDirectories();
    
    const sessionFiles = await readdir(this.sessionsDir);
    const planFiles = await readdir(this.plansDir);
    
    let storageSize = 0;
    
    // Calculate storage size
    for (const file of sessionFiles) {
      const filePath = join(this.sessionsDir, file);
      const stats = await stat(filePath);
      storageSize += stats.size;
    }
    
    for (const file of planFiles) {
      const filePath = join(this.plansDir, file);
      const stats = await stat(filePath);
      storageSize += stats.size;
    }
    
    return {
      totalSessions: sessionFiles.length,
      totalPlans: planFiles.length,
      storageSize,
    };
  }

  // =============================================================================
  // Serialization Methods
  // =============================================================================

  /**
   * Serialize a TaskSession to TOML format
   */
  private serializeSession(session: TaskSession): string {
    const tomlObject: SessionTOML = {
      session: {
        id: session.id,
        mode: session.mode,
        state: session.state,
        created_at: session.metadata.startedAt,
        updated_at: new Date().toISOString(),
      },
      input: {
        message: session.input.message,
        context: {
          files: session.input.context.files || [],
          folders: session.input.context.folders || [],
          selection: session.input.context.selection || '',
        },
      },
      metadata: {
        total_tokens: session.metadata.tokensUsed,
        total_cost: session.metadata.estimatedCost,
        models_used: session.metadata.modelUsed || [],
        started_at: session.metadata.startedAt,
        completed_at: session.metadata.completedAt,
      },
    };

    // Add research if present
    if (session.research) {
      tomlObject.research = {
        completed_at: session.research.completedAt,
        model: session.research.model,
        tokens_used: session.research.tokensUsed,
        findings: session.research.findings,
        kb_searches: session.research.kbSearches.map(s => ({
          query: s.query,
          results_count: s.resultsCount,
          top_result: s.topResult,
        })),
      };
    }

    // Add clarification if present
    if (session.clarification) {
      tomlObject.clarification = {
        completed_at: session.clarification.completedAt,
        model: session.clarification.model,
        tokens_used: session.clarification.tokensUsed,
        conversation_turns: session.clarification.conversationTurns,
        ready_for_planning: session.clarification.readyForPlanning,
        final_context: session.clarification.finalContext,
        questions: session.clarification.questions.map(q => ({
          question: q.question,
          priority: q.priority,
          reason: q.reason,
        })),
        responses: session.clarification.responses.map(r => ({
          answers: r.answers,
          timestamp: r.timestamp,
        })),
      };
    }

    // Add plan if present
    if (session.plan) {
      tomlObject.plan = {
        version: session.plan.version,
        status: session.plan.status,
        created_at: session.plan.createdAt,
        approved_at: session.plan.approvedAt,
        model: session.plan.model,
        tokens_used: session.plan.tokensUsed,
        estimated_cost: session.plan.estimatedCost,
        content_path: session.plan.contentPath || '',
        revisions: session.plan.revisions,
      };
    }

    // Add execution if present
    if (session.execution) {
      tomlObject.execution = {
        started_at: session.execution.startedAt,
        completed_at: session.execution.completedAt,
        model: session.execution.model,
        tokens_used: session.execution.tokensUsed,
        cost: session.execution.cost,
        steps: session.execution.steps.map(s => ({
          step_number: s.stepNumber,
          description: s.description,
          status: s.status,
          started_at: s.startedAt,
          completed_at: s.completedAt,
        })),
      };
    }

    return TOML.stringify(tomlObject as any);
  }

  /**
   * Validate that a file path is within the expected directory
   * Prevents path traversal attacks
   */
  private validatePath(filePath: string, expectedDir: string): string {
    const resolvedPath = resolve(filePath);
    const resolvedDir = resolve(expectedDir);
    const relativePath = relative(resolvedDir, resolvedPath);

    // Check if path escapes the expected directory
    if (relativePath.startsWith('..') || resolve(relativePath) === resolvedPath) {
      throw new Error(`Invalid file path: ${filePath} is outside expected directory ${expectedDir}`);
    }

    return resolvedPath;
  }

  /**
   * Deserialize a TOML string to TaskSession
   */
  private async deserializeSession(toml: string): Promise<TaskSession> {
    // Parse TOML
    const parsed = TOML.parse(toml);

    // Validate with Zod schema
    const validationResult = SessionTOMLSchema.safeParse(parsed);
    if (!validationResult.success) {
      throw new Error(`Invalid session TOML: ${validationResult.error.message}`);
    }

    const obj = validationResult.data;
    
    const session: TaskSession = {
      id: obj.session.id,
      mode: obj.session.mode,
      state: obj.session.state,
      input: {
        mode: obj.session.mode,
        message: obj.input.message,
        context: {
          files: obj.input.context.files || [],
          folders: obj.input.context.folders || [],
          selection: obj.input.context.selection || '',
        },
      },
      metadata: {
        tokensUsed: obj.metadata.total_tokens,
        estimatedCost: obj.metadata.total_cost,
        modelUsed: obj.metadata.models_used,
        startedAt: obj.metadata.started_at,
        completedAt: obj.metadata.completed_at,
      },
    };

    // Add research if present
    if (obj.research) {
      session.research = {
        completedAt: obj.research.completed_at,
        model: obj.research.model,
        tokensUsed: obj.research.tokens_used,
        findings: obj.research.findings,
        kbSearches: obj.research.kb_searches.map((s: any) => ({
          query: s.query,
          resultsCount: s.results_count,
          topResult: s.top_result,
        })),
        relevantFiles: [], // Will be populated from research findings
      };
    }

    // Add clarification if present
    if (obj.clarification) {
      session.clarification = {
        completedAt: obj.clarification.completed_at,
        model: obj.clarification.model,
        tokensUsed: obj.clarification.tokens_used,
        conversationTurns: obj.clarification.conversation_turns,
        readyForPlanning: obj.clarification.ready_for_planning,
        finalContext: obj.clarification.final_context,
        questions: obj.clarification.questions.map((q: any) => ({
          question: q.question,
          priority: q.priority,
          reason: q.reason,
        })),
        responses: obj.clarification.responses.map((r: any) => ({
          answers: r.answers,
          timestamp: r.timestamp,
        })),
      };
    }

    // Add plan if present
    if (obj.plan) {
      // Load plan content from file with security validation
      let planContent = '';
      let loadError: string | undefined;

      if (obj.plan.content_path) {
        try {
          // Validate path is within plans directory
          const validatedPath = this.validatePath(obj.plan.content_path, this.plansDir);

          if (existsSync(validatedPath)) {
            planContent = await readFile(validatedPath, 'utf-8');
          } else {
            loadError = `Plan file not found: ${obj.plan.content_path}`;
            console.error(`[StateStore] ${loadError}`);
          }
        } catch (error) {
          loadError = error instanceof Error ? error.message : String(error);
          console.error(`[StateStore] Failed to load plan content from ${obj.plan.content_path}:`, error);
          // Throw on security violations
          if (loadError.includes('outside expected directory')) {
            throw new Error(`Security violation: ${loadError}`);
          }
        }
      }

      session.plan = {
        version: obj.plan.version,
        status: obj.plan.status,
        createdAt: obj.plan.created_at,
        approvedAt: obj.plan.approved_at,
        model: obj.plan.model,
        tokensUsed: obj.plan.tokens_used,
        estimatedCost: obj.plan.estimated_cost,
        content: planContent,
        contentPath: obj.plan.content_path,
        filesToModify: [],
        filesToCreate: [],
        steps: [],
        complexity: 'medium',
        estimatedTokens: 0,
        revisions: obj.plan.revisions,
        // Add metadata about load failures
        ...(loadError && { loadError }),
      };
    }

    // Add execution if present
    if (obj.execution) {
      session.execution = {
        startedAt: obj.execution.started_at,
        completedAt: obj.execution.completed_at,
        model: obj.execution.model,
        tokensUsed: obj.execution.tokens_used,
        cost: obj.execution.cost,
        success: true, // Will be determined from steps
        steps: obj.execution.steps.map((s: any) => ({
          stepNumber: s.step_number,
          description: s.description,
          status: s.status,
          startedAt: s.started_at,
          completedAt: s.completed_at,
        })),
      };
    }

    return session;
  }

  /**
   * Convert TaskSession to SessionSummary
   */
  private toSummary(session: TaskSession): SessionSummary {
    // Generate title from first message or plan
    let title = session.input.message.substring(0, 50);
    if (title.length < session.input.message.length) {
      title += '...';
    }

    return {
      id: session.id,
      mode: session.mode,
      state: session.state,
      title,
      createdAt: new Date(session.metadata.startedAt),
      updatedAt: new Date(session.metadata.completedAt || session.metadata.startedAt),
      tokensUsed: session.metadata.tokensUsed,
      cost: session.metadata.estimatedCost,
    };
  }
}