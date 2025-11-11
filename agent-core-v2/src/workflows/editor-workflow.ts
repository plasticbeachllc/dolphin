/**
 * EditorWorkflow - Fast/Direct Execution for Dolphin v2
 * 
 * Fast-path execution for simple, well-defined tasks that don't require planning.
 * 
 * Based on: docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md
 */

import type {
  IWorkflow,
  TaskInput,
  WorkflowUpdate,
  Context,
} from '../types/index.js';
import type { ClaudeProvider } from '../execution/claude-provider.js';
import type { ContextBuilder } from '../context/context-builder.js';
import type { PromptBuilder } from '../prompts/prompt-builder.js';

/**
 * Configuration for EditorWorkflow
 */
export interface EditorWorkflowConfig {
  claudeProvider: ClaudeProvider;
  contextBuilder: ContextBuilder;
  promptBuilder: PromptBuilder;
}

/**
 * EditorWorkflow implements fast-path execution for simple tasks
 * 
 * Workflow Steps:
 * 1. Input → Accept task input
 * 2. Context → Gather minimal context (current file, KB search if relevant)
 * 3. Execute → Single Claude CLI call with Sonnet 4.5
 * 4. Stream → Stream response back to user
 * 5. Complete → Done
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
        files: input.context.files,
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
      
      const prompt = this.config.promptBuilder.buildEditorPrompt({
        message: input.message,
        context,
        conversationHistory: input.conversationHistory,
      });

      // Step 3: Execute with Sonnet (fast, capable model)
      console.error('[EditorWorkflow] Executing with Claude Sonnet...');
      
      const stream = this.config.claudeProvider.execute({
        model: 'claude-sonnet-4-20250514',
        prompt: input.message,
        systemPrompt: prompt,
        context,
        tools: this.getEditorTools(),
        thinkingMode: 'normal', // No extended thinking for editor mode
      });

      // Step 4: Stream results
      let tokenCount = 0;
      for await (const chunk of stream) {
        if (chunk.type === 'text') {
          tokenCount += chunk.content.split(/\s+/).length; // Rough estimate
        }

        yield {
          type: 'chunk',
          sessionId,
          timestamp: new Date().toISOString(),
          data: chunk,
        };

        // Handle tool calls
        if (chunk.type === 'tool_use') {
          yield {
            type: 'tool_call',
            sessionId,
            timestamp: new Date().toISOString(),
            data: {
              toolName: chunk.toolName,
              toolInput: chunk.toolInput,
            },
          };
        }
      }

      // Step 5: Complete
      yield {
        type: 'state_change',
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: 'complete' },
      };

      yield {
        type: 'progress',
        sessionId,
        timestamp: new Date().toISOString(),
        data: {
          phase: 'complete',
          message: `Task completed (~${tokenCount} tokens)`,
        },
      };

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

  /**
   * Get tools available in editor mode
   */
  private getEditorTools() {
    return [
      {
        name: 'read_file',
        description: 'Read the contents of a file',
        parameters: {
          type: 'object',
          properties: {
            path: { type: 'string', description: 'File path relative to workspace' },
          },
          required: ['path'],
        },
      },
      {
        name: 'write_file',
        description: 'Write content to a file',
        parameters: {
          type: 'object',
          properties: {
            path: { type: 'string', description: 'File path relative to workspace' },
            content: { type: 'string', description: 'Content to write' },
          },
          required: ['path', 'content'],
        },
      },
      {
        name: 'apply_diff',
        description: 'Apply a diff to an existing file',
        parameters: {
          type: 'object',
          properties: {
            path: { type: 'string', description: 'File path' },
            diff: { type: 'string', description: 'Unified diff format' },
          },
          required: ['path', 'diff'],
        },
      },
      {
        name: 'search_knowledge',
        description: 'Search the knowledge bank for relevant code',
        parameters: {
          type: 'object',
          properties: {
            query: { type: 'string', description: 'Search query' },
            top_k: { type: 'number', description: 'Number of results to return' },
          },
          required: ['query'],
        },
      },
      {
        name: 'execute_command',
        description: 'Execute a shell command',
        parameters: {
          type: 'object',
          properties: {
            command: { type: 'string', description: 'Command to execute' },
            cwd: { type: 'string', description: 'Working directory' },
          },
          required: ['command'],
        },
      },
    ];
  }
}