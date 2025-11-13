// agent-core-v2/src/workflows/editor-workflow.ts
import type {
  IWorkflow,
  TaskInput,
  WorkflowUpdate,
  Context,
} from '../types/index';
import type { ClaudeProvider } from '../execution/claude-provider';
import type { ContextBuilder } from '../context/context-builder';
import type { PromptBuilder } from '../prompts/prompt-builder';
import type { StateStore } from '../state/state-store';
import type { AgentEvent } from '../../../../shared/types/events';

/**
 * Configuration for EditorWorkflow
 */
export interface EditorWorkflowConfig {
  claudeProvider: ClaudeProvider;
  contextBuilder: ContextBuilder;
  promptBuilder: PromptBuilder;
  stateStore: StateStore;
  workspaceRoot: string;
}

/**
 * EditorWorkflow implements fast-path execution for simple tasks
 *
 * Workflow Steps:
 * 1. Input → Accept task input
 * 2. Context → Gather minimal context (current file, KB search if relevant)
 * 3. Execute → Single Claude call with Sonnet 4.5
 * 4. Stream → Stream response back to user via events
 * 5. Complete → Save state and finish
 */
export class EditorWorkflow implements IWorkflow {
  private config: EditorWorkflowConfig;

  constructor(config: EditorWorkflowConfig) {
    this.config = config;
  }

  /**
   * Execute the editor workflow
   */
  async *execute(input: TaskInput): AsyncIterableIterator<WorkflowUpdate> {
    const sessionId = `editor_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

    try {
      // State: Idle → Executing
      yield {
        type: 'state_change',
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: 'executing' },
      };

      // Step 1: Build context (lightweight for editor mode)
      console.error('[EditorWorkflow] Building context...');

      const context = await this.config.contextBuilder.build({
        files: input.context.files || [],
        searchQuery: this.extractSearchIntent(input.message),
        maxTokens: 8000, // Smaller context for fast execution
      });

      yield {
        type: 'progress',
        sessionId,
        timestamp: new Date().toISOString(),
        data: {
          phase: 'context',
          message: `Context assembled: ${context.kbResults.length} KB results, ${context.files.length} files`,
        },
      };

      // Step 2: Build prompt
      console.error('[EditorWorkflow] Building prompt...');

      const systemPrompt = this.config.promptBuilder.buildEditorPrompt({
        message: input.message,
        context,
        conversationHistory: input.conversationHistory,
      });

      // Step 3: Execute with Claude (using event-driven approach)
      console.error('[EditorWorkflow] Executing with Claude Sonnet...');

      let textContent = '';
      const startTime = Date.now();

      // Collect events and forward them
      const result = await this.config.claudeProvider.execute({
        message: systemPrompt,
        conversationHistory: input.conversationHistory,
        onEvent: (event: AgentEvent) => {
          // Forward content_delta events
          if (event.type === 'content_delta') {
            textContent += event.delta;
          }

          // Forward tool events
          if (event.type === 'tool_call_started' || event.type === 'tool_call_completed') {
            // Event will be sent via the iterator
          }
        },
      });

      const executionTime = Date.now() - startTime;

      // Step 4: Complete
      yield {
        type: 'progress',
        sessionId,
        timestamp: new Date().toISOString(),
        data: {
          phase: 'complete',
          message: `Task completed in ${executionTime}ms (${result.usage.inputTokens + result.usage.outputTokens} tokens, ${result.toolRounds} tool rounds)`,
        },
      };

      yield {
        type: 'state_change',
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: 'complete' },
      };

      // Step 5: Save state
      try {
        await this.config.stateStore.saveSession({
          id: sessionId,
          mode: 'editor',
          state: 'complete',
          metadata: {
            modelUsed: ['claude-sonnet-4-20250514'],
            tokensUsed: result.usage.inputTokens + result.usage.outputTokens,
            estimatedCost: 0, // TODO: calculate based on mode
            startedAt: new Date(startTime).toISOString(),
            completedAt: new Date().toISOString(),
          },
          input,
        });
      } catch (error) {
        console.error('[EditorWorkflow] Failed to save state:', error);
        // Don't fail the workflow if state save fails
      }

    } catch (error) {
      console.error('[EditorWorkflow] Error:', error);

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

  // =============================================================================
  // Private Methods
  // =============================================================================

  /**
   * Extract search intent from user message
   */
  private extractSearchIntent(message: string): string | undefined {
    // Simple heuristics to determine if KB search would be helpful
    const searchKeywords = [
      'find', 'search', 'look for', 'locate', 'where',
      'how does', 'how is', 'what is', 'explain',
      'show me', 'implement', 'add', 'modify',
    ];

    const lowerMessage = message.toLowerCase();
    const hasSearchKeyword = searchKeywords.some(keyword => lowerMessage.includes(keyword));

    if (hasSearchKeyword) {
      // Extract main topic from message
      return message;
    }

    return undefined;
  }
}
