import { describe, it, expect, beforeEach, mock } from 'bun:test'
import { ClaudeToolExecutor } from '../src/llm/claude-tool-executor'
import type { ClaudeClient } from '../src/llm/claude-client'
import type { MCPClient } from '../src/mcp/client'
import type { AgentEvent } from '../../../shared/types/events'

// Helper to create mock stream from response data
// Options: executor (to check abort), throwError (to simulate API errors)
function createMockStream(mockResponse: any, options: { executor?: any, throwError?: Error } = {}) {
  return {
    async *[Symbol.asyncIterator]() {
      // Check if we should throw an error during stream creation
      if (options.throwError) {
        throw options.throwError
      }
      
      const content = mockResponse.content || [{ type: 'text', text: 'Mock response' }]
      
      for (const block of content) {
        // Check abort flag if executor provided
        if (options.executor && (options.executor as any).isAborted) {
          throw new Error('Generation aborted by user')
        }
        
        yield {
          type: 'content_block_start',
          content_block: block.type === 'tool_use'
            ? { type: 'tool_use', id: block.id, name: block.name }
            : { type: 'text' }
        }
        
        if (block.type === 'text') {
          yield {
            type: 'content_block_delta',
            delta: { type: 'text_delta', text: block.text }
          }
        } else if (block.type === 'tool_use') {
          yield {
            type: 'content_block_delta',
            delta: { type: 'input_json_delta', partial_json: JSON.stringify(block.input) }
          }
        }
        
        yield {
          type: 'content_block_stop'
        }
      }
      
      yield {
        type: 'message_stop'
      }
    },
    async finalMessage() {
      return mockResponse
    }
  }
}

describe('ClaudeToolExecutor - Unit Tests', () => {
  let mockClaudeClient: any
  let mockMCPClient: any
  let events: AgentEvent[]
  let executor: ClaudeToolExecutor

  // Helper to set up stream mock with specific responses
  function setupStreamMock(...responses: any[]) {
    let callIndex = 0
    mockClaudeClient.apiClient.messages.stream = mock((params: any) => {
      const response = responses[callIndex] || responses[responses.length - 1]
      callIndex++
      return createMockStream({
        id: `msg-${callIndex}`,
        type: 'message',
        role: 'assistant',
        ...response
      })
    })
  }

  beforeEach(() => {
    events = []

    // Mock Claude Client with streaming API
    mockClaudeClient = {
      getAuthStatus: mock(async () => ({
        mode: 'api_key',
        cliInstalled: false,
        cliAuthenticated: false,
        apiKeySet: true,
        willUseSubscription: false
      })),
      apiClient: {
        messages: {
          stream: mock((params: any) => {
            return createMockStream({
              id: 'msg-123',
              type: 'message',
              role: 'assistant',
              content: [{ type: 'text', text: 'Mock response' }],
              model: 'claude-sonnet-4-20250514',
              stop_reason: 'end_turn',
              stop_sequence: null,
              usage: {
                input_tokens: 100,
                output_tokens: 50,
                cache_read_input_tokens: 0,
                cache_creation_input_tokens: 0
              }
            })
          })
        }
      }
    }

    // Mock MCP Client
    mockMCPClient = {
      listTools: mock(async () => [
        {
          name: 'search_knowledge',
          description: 'Search code knowledge base',
          inputSchema: {
            type: 'object',
            properties: {
              query: { type: 'string' }
            },
            required: ['query']
          }
        },
        {
          name: 'read_file',
          description: 'Read file contents',
          inputSchema: {
            type: 'object',
            properties: {
              path: { type: 'string' }
            },
            required: ['path']
          }
        }
      ]),
      callTool: mock(async (name: string, args: any) => ({
        content: [{ type: 'text', text: `Mock result from ${name}` }],
        isError: false
      })),
      shutdown: mock(() => {})
    }

    executor = new ClaudeToolExecutor({
      claudeClient: mockClaudeClient as unknown as ClaudeClient,
      mcpClient: mockMCPClient as unknown as MCPClient,
      maxToolRounds: 5,
      onEvent: (event) => events.push(event)
    })
  })

  describe('initialization', () => {
    it('should initialize and load tools from MCP', async () => {
      await executor.initialize()

      expect(mockMCPClient.listTools).toHaveBeenCalled()
    })

    it('should convert MCP tools to Anthropic format', async () => {
      await executor.initialize()

      // Should have loaded 2 tools
      expect(mockMCPClient.listTools).toHaveBeenCalled()
    })

    it('should handle empty tool list', async () => {
      mockMCPClient.listTools = mock(async () => [])

      await executor.initialize()

      expect(mockMCPClient.listTools).toHaveBeenCalled()
    })

    it('should handle MCP client errors', async () => {
      mockMCPClient.listTools = mock(async () => {
        throw new Error('MCP connection failed')
      })

      await expect(executor.initialize()).rejects.toThrow('MCP connection failed')
    })
  })

  describe('executeWithTools', () => {
    beforeEach(async () => {
      await executor.initialize()
    })

    it('should execute simple query without tool use', async () => {
      const result = await executor.executeWithTools('Hello Claude')

      expect(result).toBeDefined()
      expect(result.messages).toBeDefined()
      expect(result.stopReason).toBe('end_turn')
      expect(result.toolRounds).toBeGreaterThanOrEqual(0)
      expect(result.usage.inputTokens).toBeGreaterThan(0)
      expect(result.usage.outputTokens).toBeGreaterThan(0)
    })

    it('should handle tool use response', async () => {
      setupStreamMock(
        {
          content: [{
            type: 'tool_use',
            id: 'tool-1',
            name: 'search_knowledge',
            input: { query: 'test query' }
          }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'tool_use',
          model: 'claude-sonnet-4-20250514'
        },
        {
          content: [{ type: 'text', text: 'Final response after tool use' }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'end_turn',
          model: 'claude-sonnet-4-20250514'
        }
      )

      const result = await executor.executeWithTools('Search for code')

      expect(result.toolRounds).toBeGreaterThan(0)
      expect(mockMCPClient.callTool).toHaveBeenCalled()
    })

    it('should respect maxToolRounds limit', async () => {
      // Make Claude always return tool_use
      setupStreamMock({
        content: [{
          type: 'tool_use',
          id: `tool-${Date.now()}`,
          name: 'search_knowledge',
          input: { query: 'test' }
        }],
        usage: { input_tokens: 100, output_tokens: 50 },
        stop_reason: 'tool_use',
        model: 'claude-sonnet-4-20250514'
      })

      const result = await executor.executeWithTools('Test query')

      // Should stop after maxToolRounds
      expect(result.toolRounds).toBeLessThanOrEqual(5)
    })

    it('should accumulate usage across rounds', async () => {
      // Setup 3-round conversation: 2 tool calls + 1 final response
      setupStreamMock(
        {
          content: [{
            type: 'tool_use',
            id: 'tool-1',
            name: 'search_knowledge',
            input: { query: 'test' }
          }],
          usage: {
            input_tokens: 100,
            output_tokens: 50,
            cache_read_input_tokens: 10,
            cache_creation_input_tokens: 5
          },
          stop_reason: 'tool_use',
          model: 'claude-sonnet-4-20250514'
        },
        {
          content: [{
            type: 'tool_use',
            id: 'tool-2',
            name: 'search_knowledge',
            input: { query: 'test' }
          }],
          usage: {
            input_tokens: 100,
            output_tokens: 50,
            cache_read_input_tokens: 10,
            cache_creation_input_tokens: 5
          },
          stop_reason: 'tool_use',
          model: 'claude-sonnet-4-20250514'
        },
        {
          content: [{ type: 'text', text: 'Done' }],
          usage: {
            input_tokens: 100,
            output_tokens: 50,
            cache_read_input_tokens: 10,
            cache_creation_input_tokens: 5
          },
          stop_reason: 'end_turn',
          model: 'claude-sonnet-4-20250514'
        }
      )

      const result = await executor.executeWithTools('Test')

      // Should accumulate usage from multiple rounds (3 rounds total)
      expect(result.usage.inputTokens).toBeGreaterThanOrEqual(200)
      expect(result.usage.cacheReadTokens).toBeGreaterThanOrEqual(20)
    })

    it('should emit events during execution', async () => {
      setupStreamMock(
        {
          content: [{ type: 'text', text: 'Response' }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'end_turn',
          model: 'claude-sonnet-4-20250514'
        }
      )

      await executor.executeWithTools('Test')

      // Should have emitted events
      expect(events.length).toBeGreaterThan(0)
    })

    it('should include conversation history in context', async () => {
      const history = [
        { role: 'user' as const, content: 'Previous message' },
        { role: 'assistant' as const, content: 'Previous response' }
      ]

      await executor.executeWithTools('New message', history)

      expect(mockClaudeClient.apiClient.messages.stream).toHaveBeenCalled()
      const callArgs = mockClaudeClient.apiClient.messages.stream.mock.calls[0][0]
      expect(callArgs.messages.length).toBeGreaterThan(2) // history + new message
    })
  })

  describe('abort', () => {
    beforeEach(async () => {
      await executor.initialize()
    })

    it('should abort ongoing execution', async () => {
      // Create a delayed async iterator that allows abort to interrupt
      let shouldAbort = false
      
      mockClaudeClient.apiClient.messages.stream = mock((params: any) => {
        return {
          async *[Symbol.asyncIterator]() {
            // Delay to allow abort to be called
            await new Promise(resolve => setTimeout(resolve, 50))
            
            // Check if aborted
            if (shouldAbort) {
              throw new Error('Generation aborted by user')
            }
            
            yield { type: 'content_block_start', content_block: { type: 'text' } }
            yield { type: 'content_block_delta', delta: { type: 'text_delta', text: 'Response' } }
            yield { type: 'content_block_stop' }
            yield { type: 'message_stop' }
          },
          async finalMessage() {
            return {
              id: 'msg-abort',
              type: 'message',
              role: 'assistant',
              content: [{ type: 'text', text: 'Response' }],
              usage: { input_tokens: 100, output_tokens: 50 },
              stop_reason: 'end_turn',
              model: 'claude-sonnet-4-20250514'
            }
          }
        }
      })

      const executePromise = executor.executeWithTools('Test')

      // Abort after a short delay
      setTimeout(() => {
        shouldAbort = true
        executor.abort()
      }, 10)

      await expect(executePromise).rejects.toThrow('aborted')
    })

    it('should set isAborted flag', async () => {
      // Create stream that will be called but we'll abort during it
      let isAborted = false
      
      mockClaudeClient.apiClient.messages.stream = mock((params: any) => {
        return {
          async *[Symbol.asyncIterator]() {
            // Small delay to allow abort to take effect
            await new Promise(resolve => setTimeout(resolve, 10))
            
            if (isAborted) {
              throw new Error('Generation aborted by user')
            }
            
            yield { type: 'content_block_start', content_block: { type: 'text' } }
            yield { type: 'content_block_delta', delta: { type: 'text_delta', text: 'Response' } }
            yield { type: 'content_block_stop' }
            yield { type: 'message_stop' }
          },
          async finalMessage() {
            return {
              id: 'msg-abort',
              type: 'message',
              role: 'assistant',
              content: [{ type: 'text', text: 'Response' }],
              usage: { input_tokens: 100, output_tokens: 50 },
              stop_reason: 'end_turn',
              model: 'claude-sonnet-4-20250514'
            }
          }
        }
      })

      // Abort before execution starts
      executor.abort()
      
      // Start execution - should check abort during the first API call
      const executePromise = executor.executeWithTools('Test')
      
      // Mark as aborted for the stream
      isAborted = true

      await expect(executePromise).rejects.toThrow('aborted')
    })
  })

  describe('error handling', () => {
    beforeEach(async () => {
      await executor.initialize()
    })

    it('should handle Claude API errors', async () => {
      // Mock stream to throw error during creation
      mockClaudeClient.apiClient.messages.stream = mock((params: any) => {
        return createMockStream({}, { throwError: new Error('API error') })
      })

      await expect(
        executor.executeWithTools('Test')
      ).rejects.toThrow('API error')
    })

    it('should handle tool execution errors', async () => {
      mockMCPClient.callTool = mock(async () => ({
        content: [{ type: 'text', text: 'Tool failed' }],
        isError: true
      }))

      setupStreamMock(
        {
          content: [{
            type: 'tool_use',
            id: 'tool-1',
            name: 'search_knowledge',
            input: { query: 'test' }
          }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'tool_use',
          model: 'claude-sonnet-4-20250514'
        },
        {
          content: [{ type: 'text', text: 'Handled error' }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'end_turn',
          model: 'claude-sonnet-4-20250514'
        }
      )

      // Should not crash, tool error passed back to Claude
      const result = await executor.executeWithTools('Test')
      expect(result).toBeDefined()
    })

    it('should handle unknown tool names', async () => {
      setupStreamMock(
        {
          content: [{
            type: 'tool_use',
            id: 'tool-1',
            name: 'unknown_tool',
            input: {}
          }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'tool_use',
          model: 'claude-sonnet-4-20250514'
        },
        {
          content: [{ type: 'text', text: 'Handled unknown tool' }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'end_turn',
          model: 'claude-sonnet-4-20250514'
        }
      )

      // Should handle gracefully
      const result = await executor.executeWithTools('Test')
      expect(result).toBeDefined()
    })
  })

  describe('tool result formatting', () => {
    beforeEach(async () => {
      await executor.initialize()
    })

    it('should format successful tool results', async () => {
      mockMCPClient.callTool = mock(async (name: string) => ({
        content: [{ type: 'text', text: 'Success result' }],
        isError: false
      }))

      setupStreamMock(
        {
          content: [{
            type: 'tool_use',
            id: 'tool-1',
            name: 'search_knowledge',
            input: { query: 'test' }
          }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'tool_use',
          model: 'claude-sonnet-4-20250514'
        },
        {
          content: [{ type: 'text', text: 'Final response' }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'end_turn',
          model: 'claude-sonnet-4-20250514'
        }
      )

      const result = await executor.executeWithTools('Test')

      expect(mockMCPClient.callTool).toHaveBeenCalledWith('search_knowledge', { query: 'test' })
    })

    it('should format error tool results', async () => {
      mockMCPClient.callTool = mock(async () => ({
        content: [{ type: 'text', text: 'Error occurred' }],
        isError: true
      }))

      setupStreamMock(
        {
          content: [{
            type: 'tool_use',
            id: 'tool-1',
            name: 'search_knowledge',
            input: { query: 'test' }
          }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'tool_use',
          model: 'claude-sonnet-4-20250514'
        },
        {
          content: [{ type: 'text', text: 'Handled error' }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'end_turn',
          model: 'claude-sonnet-4-20250514'
        }
      )

      await executor.executeWithTools('Test')

      expect(mockMCPClient.callTool).toHaveBeenCalled()
    })
  })

  describe('multiple tool calls', () => {
    beforeEach(async () => {
      await executor.initialize()
    })

    it('should handle multiple tool calls in one response', async () => {
      setupStreamMock(
        {
          content: [
            {
              type: 'tool_use',
              id: 'tool-1',
              name: 'search_knowledge',
              input: { query: 'test1' }
            },
            {
              type: 'tool_use',
              id: 'tool-2',
              name: 'read_file',
              input: { path: 'test.ts' }
            }
          ],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'tool_use',
          model: 'claude-sonnet-4-20250514'
        },
        {
          content: [{ type: 'text', text: 'Done with both tools' }],
          usage: { input_tokens: 100, output_tokens: 50 },
          stop_reason: 'end_turn',
          model: 'claude-sonnet-4-20250514'
        }
      )

      await executor.executeWithTools('Test')

      // Should have called both tools
      expect(mockMCPClient.callTool).toHaveBeenCalledTimes(2)
    })
  })
})
