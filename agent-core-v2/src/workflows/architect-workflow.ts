// agent-core-v2/src/workflows/architect-workflow.ts
import type {
  IWorkflow,
  TaskInput,
  WorkflowUpdate,
  Context,
  ResearchResult,
  Plan,
} from '../types/index';
import type { ClaudeProvider } from '../execution/claude-provider';
import type { ContextBuilder } from '../context/context-builder';
import type { PromptBuilder } from '../prompts/prompt-builder';
import type { StateStore } from '../state/state-store';
import type { AgentEvent } from '../../../../shared/types/events';
import { PlanStore } from '../storage/plan-store';

/**
 * Configuration for ArchitectWorkflow
 */
export interface ArchitectWorkflowConfig {
  claudeProvider: ClaudeProvider;
  contextBuilder: ContextBuilder;
  promptBuilder: PromptBuilder;
  stateStore: StateStore;
  planStore: PlanStore;
  workspaceRoot: string;
}

/**
 * ArchitectWorkflow implements multi-phase execution for complex tasks
 *
 * Workflow Phases:
 * 1. Research → Explore codebase and understand requirements
 * 2. Planning → Create detailed implementation plan
 * 3. Approval → Wait for user approval
 * 4. Execution → Implement the approved plan
 * 5. Validation → Verify changes and run tests
 */
export class ArchitectWorkflow implements IWorkflow {
  private config: ArchitectWorkflowConfig;

  constructor(config: ArchitectWorkflowConfig) {
    this.config = config;
  }

  /**
   * Execute the architect workflow
   */
  async *execute(input: TaskInput): AsyncIterableIterator<WorkflowUpdate> {
    const sessionId = `arch_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

    try {
      // Phase 1: Research
      yield* this.researchPhase(sessionId, input);

      // Phase 2: Planning
      const plan = yield* this.planningPhase(sessionId, input);

      // Phase 3: Await Approval (orchestrator handles this)
      yield {
        type: 'state_change',
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: 'awaiting_approval', plan },
      };

      // Execution continues after approval (orchestrator will resume)

    } catch (error) {
      console.error('[ArchitectWorkflow] Error:', error);

      yield {
        type: 'error',
        sessionId,
        timestamp: new Date().toISOString(),
        data: {
          error: error instanceof Error ? error.message : String(error),
          recoverable: false,
        },
      };

      yield {
        type: 'state_change',
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: 'error' },
      };
    }
  }

  /**
   * Execute plan after approval (called by orchestrator)
   */
  async *executeApprovedPlan(
    sessionId: string,
    plan: Plan,
    input: TaskInput
  ): AsyncIterableIterator<WorkflowUpdate> {
    try {
      // Phase 4: Execution
      yield* this.executionPhase(sessionId, plan, input);

      // Phase 5: Complete
      yield {
        type: 'state_change',
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: 'complete' },
      };

    } catch (error) {
      console.error('[ArchitectWorkflow] Execution error:', error);

      yield {
        type: 'error',
        sessionId,
        timestamp: new Date().toISOString(),
        data: {
          error: error instanceof Error ? error.message : String(error),
          recoverable: true,
        },
      };
    }
  }

  // =============================================================================
  // Phase Implementations
  // =============================================================================

  /**
   * Phase 1: Research the codebase
   */
  private async *researchPhase(
    sessionId: string,
    input: TaskInput
  ): AsyncIterableIterator<WorkflowUpdate> {
    yield {
      type: 'state_change',
      sessionId,
      timestamp: new Date().toISOString(),
      data: { state: 'researching' },
    };

    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'research',
        message: 'Starting codebase research...',
      },
    };

    // Build initial context
    const context = await this.config.contextBuilder.build({
      files: input.context.files || [],
      searchQuery: input.message,
      maxTokens: 20000, // Larger context for research
    });

    // Build research prompt
    const researchPrompt = this.config.promptBuilder.buildResearchPrompt({
      task: input.message,
      context,
      systemPrompt: '', // PromptBuilder includes system prompt
    });

    // Execute research with Claude
    const startTime = Date.now();
    let researchFindings = '';

    const result = await this.config.claudeProvider.execute({
      message: researchPrompt,
      conversationHistory: input.conversationHistory,
      onEvent: (event: AgentEvent) => {
        if (event.type === 'content_delta') {
          researchFindings += event.delta;
        }
      },
    });

    const research: ResearchResult = {
      completedAt: new Date().toISOString(),
      model: 'claude-sonnet-4-20250514',
      tokensUsed: result.usage.inputTokens + result.usage.outputTokens,
      findings: researchFindings,
      kbSearches: [], // TODO: track KB searches from tool calls
      relevantFiles: context.files.map(f => f.path),
    };

    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'research',
        message: `Research complete (${result.usage.inputTokens + result.usage.outputTokens} tokens, ${Date.now() - startTime}ms)`,
        research,
      },
    };
  }

  /**
   * Phase 2: Create implementation plan
   */
  private async *planningPhase(
    sessionId: string,
    input: TaskInput
  ): AsyncIterableIterator<Plan> {
    yield {
      type: 'state_change',
      sessionId,
      timestamp: new Date().toISOString(),
      data: { state: 'planning' },
    };

    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'planning',
        message: 'Creating implementation plan...',
      },
    };

    // Build planning context
    const context = await this.config.contextBuilder.build({
      files: input.context.files || [],
      maxTokens: 15000,
    });

    // TODO: Include research findings
    const research: ResearchResult = {
      completedAt: new Date().toISOString(),
      model: 'claude-sonnet-4-20250514',
      tokensUsed: 0,
      findings: '',
      kbSearches: [],
      relevantFiles: [],
    };

    // Build planning prompt
    const planningPrompt = this.config.promptBuilder.buildPlanningPrompt({
      task: input.message,
      research,
      context,
      systemPrompt: '',
    });

    // Execute planning with Claude Opus (best reasoning)
    const startTime = Date.now();
    let planContent = '';

    const result = await this.config.claudeProvider.execute({
      message: planningPrompt,
      conversationHistory: [],
      onEvent: (event: AgentEvent) => {
        if (event.type === 'content_delta') {
          planContent += event.delta;
        }
      },
    });

    // Parse plan
    const plan: Plan = {
      version: 1,
      status: 'pending_approval',
      createdAt: new Date().toISOString(),
      model: 'claude-opus-4-20250514',
      tokensUsed: result.usage.inputTokens + result.usage.outputTokens,
      estimatedCost: 0, // TODO: calculate
      content: planContent,
      filesToModify: this.extractFilesToModify(planContent),
      filesToCreate: this.extractFilesToCreate(planContent),
      steps: this.extractSteps(planContent),
      complexity: this.estimateComplexity(planContent),
      estimatedTokens: this.estimateImplementationTokens(planContent),
    };

    // Save plan
    await this.config.planStore.savePlan({
      schema_version: '1.0',
      plan: {
        id: `plan_${sessionId}`,
        created_at: plan.createdAt,
        updated_at: plan.createdAt,
        task_description: input.message,
        model_used: plan.model,
        status: 'pending_approval',
      },
      content: plan.content,
      metadata: {
        files_to_modify: plan.filesToModify,
        files_to_create: plan.filesToCreate,
        estimated_complexity: plan.complexity,
        estimated_tokens: plan.estimatedTokens,
      },
    });

    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'planning',
        message: `Plan created (${plan.tokensUsed} tokens)`,
        plan,
      },
    };

    return plan;
  }

  /**
   * Phase 4: Execute the approved plan
   */
  private async *executionPhase(
    sessionId: string,
    plan: Plan,
    input: TaskInput
  ): AsyncIterableIterator<WorkflowUpdate> {
    yield {
      type: 'state_change',
      sessionId,
      timestamp: new Date().toISOString(),
      data: { state: 'executing' },
    };

    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'implementation',
        message: 'Starting implementation...',
      },
    };

    // Build execution context
    const context = await this.config.contextBuilder.build({
      files: [...plan.filesToModify, ...plan.filesToCreate],
      maxTokens: 25000, // Large context for implementation
    });

    // Build implementation prompt
    const implementationPrompt = this.config.promptBuilder.buildImplementationPrompt({
      plan,
      context,
      systemPrompt: '',
    });

    // Execute implementation with Claude
    const startTime = Date.now();

    const result = await this.config.claudeProvider.execute({
      message: implementationPrompt,
      conversationHistory: [],
      onEvent: (event: AgentEvent) => {
        // Forward all events
        // Tool execution events are particularly important here
      },
    });

    const executionTime = Date.now() - startTime;

    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'implementation',
        message: `Implementation complete (${result.usage.inputTokens + result.usage.outputTokens} tokens, ${executionTime}ms, ${result.toolRounds} tool rounds)`,
      },
    };

    // Save final state
    try {
      await this.config.stateStore.saveSession({
        id: sessionId,
        mode: 'architect',
        state: 'complete',
        plan,
        metadata: {
          modelUsed: ['claude-opus-4-20250514', 'claude-sonnet-4-20250514'],
          tokensUsed: result.usage.inputTokens + result.usage.outputTokens + plan.tokensUsed,
          estimatedCost: 0,
          startedAt: plan.createdAt,
          completedAt: new Date().toISOString(),
        },
        input,
      });
    } catch (error) {
      console.error('[ArchitectWorkflow] Failed to save state:', error);
    }
  }

  // =============================================================================
  // Helper Methods
  // =============================================================================

  private extractFilesToModify(planContent: string): string[] {
    // Simple regex to find file paths (improve later)
    const matches = planContent.match(/(?:modify|update|change|edit)\s+[`']?([a-zA-Z0-9_\-/.]+\.[a-z]+)[`']?/gi);
    return matches ? Array.from(new Set(matches.map(m => m.split(/[`'\s]+/).pop() || ''))) : [];
  }

  private extractFilesToCreate(planContent: string): string[] {
    const matches = planContent.match(/(?:create|add|new)\s+[`']?([a-zA-Z0-9_\-/.]+\.[a-z]+)[`']?/gi);
    return matches ? Array.from(new Set(matches.map(m => m.split(/[`'\s]+/).pop() || ''))) : [];
  }

  private extractSteps(planContent: string): string[] {
    // Extract numbered steps (improve later)
    const steps = planContent.match(/^\d+\.\s+(.+)$/gm);
    return steps || [];
  }

  private estimateComplexity(planContent: string): 'low' | 'medium' | 'high' {
    const wordCount = planContent.split(/\s+/).length;
    if (wordCount < 500) return 'low';
    if (wordCount < 1500) return 'medium';
    return 'high';
  }

  private estimateImplementationTokens(planContent: string): number {
    // Rough estimate: plan tokens * 3-5x for implementation
    const planTokens = Math.ceil(planContent.length / 4);
    return planTokens * 4;
  }
}
