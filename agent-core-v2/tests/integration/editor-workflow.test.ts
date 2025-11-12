/**
 * Integration tests for EditorWorkflow
 * 
 * Tests end-to-end execution with KB integration and Claude CLI
 */

import { describe, it, expect, beforeEach, mock } from 'bun:test';
import { EditorWorkflow } from '../../src/workflows/editor-workflow';
import { ClaudeProvider } from '../../src/execution/claude-provider';
import { ContextBuilder } from '../../src/context/context-builder';
import { PromptBuilder } from '../../src/prompts/prompt-builder';
import type { TaskInput, WorkflowUpdate, ClaudeChunk } from '../../src/types/index';

describe('EditorWorkflow Integration', () => {
  let workflow: EditorWorkflow;
  let mockClaudeProvider: any;
  let contextBuilder: ContextBuilder;
  let promptBuilder: PromptBuilder;

  beforeEach(() => {
    // Mock ClaudeProvider
    mockClaudeProvider = {
      execute: mock(async function* (params: any): AsyncIterableIterator<ClaudeChunk> {
        // Simulate Claude response
        yield {
          type: 'text',
          content: 'I will help you with this task.',
        };
        
        yield {
          type: 'tool_use',
          content: '',
          toolName: 'read_file',
          toolInput: { path: 'test.ts' },
        };
        
        yield {
          type: 'tool_result',
          content: '',
          toolResult: 'const x = 1;',
        };
        
        yield {
          type: 'text',
          content: 'I have completed the task.',
        };
      }),
      ensureAuthenticated: mock(async () => {}),
    };

    // Real ContextBuilder with mocked KB
    contextBuilder = new ContextBuilder({
      workspaceRoot: '/test/workspace',
      kbUrl: 'http://localhost:7777',
    });

    // Real PromptBuilder
    promptBuilder = new PromptBuilder();

    // Create workflow
    workflow = new EditorWorkflow({
      claudeProvider: mockClaudeProvider,
      contextBuilder,
      promptBuilder,
    });
  });

  describe('execute()', () => {
    it('should execute simple task end-to-end', async () => {
      const input: TaskInput = {
        mode: 'editor',
        message: 'Add a comment to the file',
        context: { files: ['test.ts'] },
      };

      const updates: WorkflowUpdate[] = [];

      for await (const update of workflow.execute(input)) {
        updates.push(update);
      }

      // Verify workflow progression
      expect(updates.length).toBeGreaterThan(0);
      
      // Should have state change to executing
      const executingUpdate = updates.find(
        u => u.type === 'state_change' && u.data.state === 'executing'
      );
      expect(executingUpdate).toBeDefined();

      // Should have completion state
      const completeUpdate = updates.find(
        u => u.type === 'state_change' && u.data.state === 'complete'
      );
      expect(completeUpdate).toBeDefined();

      // Should have chunks
      const chunks = updates.filter(u => u.type === 'chunk');
      expect(chunks.length).toBeGreaterThan(0);

      // Should have called Claude
      expect(mockClaudeProvider.execute).toHaveBeenCalled();
    });

    it('should handle KB search integration', async () => {
      // Mock KB search to return results
      global.fetch = mock(async (url: string) => {
        if (url.includes('/v1/search')) {
          return {
            ok: true,
            json: async () => [
              {
                file_path: 'src/utils.ts',
                start_line: 1,
                end_line: 10,
                snippet_text: 'export function helper() {}',
                language: 'typescript',
                score: 0.95,
                chunk_id: 'chunk1',
              },
            ],
          };
        }
        return { ok: false };
      }) as any;

      const input: TaskInput = {
        mode: 'editor',
        message: 'Find the helper function and modify it',
        context: {},
      };

      const updates: WorkflowUpdate[] = [];

      for await (const update of workflow.execute(input)) {
        updates.push(update);
      }

      // Should have progress update about context
      const contextUpdate = updates.find(
        u => u.type === 'progress' && u.data.phase === 'context'
      );
      expect(contextUpdate).toBeDefined();

      // Should complete successfully
      const completeUpdate = updates.find(
        u => u.type === 'state_change' && u.data.state === 'complete'
      );
      expect(completeUpdate).toBeDefined();
    });

    it('should handle tool calls during execution', async () => {
      const input: TaskInput = {
        mode: 'editor',
        message: 'Read and modify test.ts',
        context: { files: ['test.ts'] },
      };

      const updates: WorkflowUpdate[] = [];

      for await (const update of workflow.execute(input)) {
        updates.push(update);
      }

      // Should have tool call updates
      const toolCalls = updates.filter(u => u.type === 'tool_call');
      expect(toolCalls.length).toBeGreaterThan(0);

      // Should have read_file tool call
      const readFileTool = toolCalls.find(
        u => u.data.toolName === 'read_file'
      );
      expect(readFileTool).toBeDefined();
    });

    it('should handle errors gracefully', async () => {
      // Mock provider to throw error
      mockClaudeProvider.execute = mock(async function* () {
        throw new Error('Claude CLI failed');
      });

      const input: TaskInput = {
        mode: 'editor',
        message: 'This will fail',
        context: {},
      };

      const updates: WorkflowUpdate[] = [];

      for await (const update of workflow.execute(input)) {
        updates.push(update);
      }

      // Should have error update
      const errorUpdate = updates.find(u => u.type === 'error');
      expect(errorUpdate).toBeDefined();
      expect(errorUpdate?.data.error).toContain('Claude CLI failed');

      // Should transition to error state
      const errorState = updates.find(
        u => u.type === 'state_change' && u.data.state === 'error'
      );
      expect(errorState).toBeDefined();
    });

    it('should track token usage', async () => {
      const input: TaskInput = {
        mode: 'editor',
        message: 'Simple task',
        context: {},
      };

      const updates: WorkflowUpdate[] = [];

      for await (const update of workflow.execute(input)) {
        updates.push(update);
      }

      // Should have completion message with token estimate
      const completeProgress = updates.find(
        u => u.type === 'progress' && u.data.phase === 'complete'
      );
      expect(completeProgress).toBeDefined();
      expect(completeProgress?.data.message).toContain('tokens');
    });

    it('should respect context token limits', async () => {
      // Create a large file that would exceed limits
      const largeContent = 'x'.repeat(100000);
      
      global.fetch = mock(async (url: string) => {
        if (url.includes('/v1/search')) {
          return {
            ok: true,
            json: async () => Array(50).fill({
              file_path: 'large.ts',
              start_line: 1,
              end_line: 1000,
              snippet_text: largeContent,
              language: 'typescript',
              score: 0.95,
              chunk_id: 'chunk1',
            }),
          };
        }
        return { ok: false };
      }) as any;

      const input: TaskInput = {
        mode: 'editor',
        message: 'Search for large files',
        context: {},
      };

      const updates: WorkflowUpdate[] = [];

      for await (const update of workflow.execute(input)) {
        updates.push(update);
      }

      // Should still complete even with truncated context
      const completeUpdate = updates.find(
        u => u.type === 'state_change' && u.data.state === 'complete'
      );
      expect(completeUpdate).toBeDefined();
    });
  });

  describe('Context Building', () => {
    it('should build context with explicit files', async () => {
      // Mock file reading
      const mockReadFile = mock(async () => 'const test = 1;');
      
      const input: TaskInput = {
        mode: 'editor',
        message: 'Modify test files',
        context: {
          files: ['test1.ts', 'test2.ts'],
        },
      };

      const updates: WorkflowUpdate[] = [];

      for await (const update of workflow.execute(input)) {
        updates.push(update);
      }

      // Should have context assembly progress
      const contextUpdate = updates.find(
        u => u.type === 'progress' && u.data.phase === 'context'
      );
      expect(contextUpdate).toBeDefined();
    });

    it('should handle KB unavailable gracefully', async () => {
      // Mock KB to fail
      global.fetch = mock(async () => {
        throw new Error('KB unavailable');
      }) as any;

      const input: TaskInput = {
        mode: 'editor',
        message: 'Search for something',
        context: {},
      };

      const updates: WorkflowUpdate[] = [];

      for await (const update of workflow.execute(input)) {
        updates.push(update);
      }

      // Should still complete without KB results
      const completeUpdate = updates.find(
        u => u.type === 'state_change' && u.data.state === 'complete'
      );
      expect(completeUpdate).toBeDefined();
    });
  });

  describe('Prompt Building', () => {
    it('should include conversation history', async () => {
      const input: TaskInput = {
        mode: 'editor',
        message: 'Continue from previous task',
        context: {},
        conversationHistory: [
          {
            role: 'user',
            content: 'Previous question',
          },
          {
            role: 'assistant',
            content: 'Previous answer',
          },
        ],
      };

      const updates: WorkflowUpdate[] = [];

      for await (const update of workflow.execute(input)) {
        updates.push(update);
      }

      // Should call Claude with prompt including history
      expect(mockClaudeProvider.execute).toHaveBeenCalled();
      
      const completeUpdate = updates.find(
        u => u.type === 'state_change' && u.data.state === 'complete'
      );
      expect(completeUpdate).toBeDefined();
    });
  });

  describe('Performance', () => {
    it('should complete simple task quickly', async () => {
      const input: TaskInput = {
        mode: 'editor',
        message: 'Quick task',
        context: {},
      };

      const startTime = Date.now();
      const updates: WorkflowUpdate[] = [];

      for await (const update of workflow.execute(input)) {
        updates.push(update);
      }

      const duration = Date.now() - startTime;

      // Should complete in reasonable time (< 5s for mocked test)
      expect(duration).toBeLessThan(5000);
    });
  });
});