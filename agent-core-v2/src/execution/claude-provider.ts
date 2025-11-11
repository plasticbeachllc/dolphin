/**
 * ClaudeProvider - Multi-Model Execution for Dolphin v2
 * 
 * Manages Claude CLI subprocess spawning with multi-model support and
 * streaming response handling.
 * 
 * Based on: docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md
 */

import { spawn, ChildProcess } from 'child_process';
import { homedir } from 'os';
import { join } from 'path';
import { existsSync } from 'fs';
import type {
  ClaudeModel,
  ThinkingMode,
  ExecutionParams,
  ClaudeChunk,
  AuthStatus,
  Tool,
  Context,
} from '../types/index.js';

/**
 * Configuration for ClaudeProvider
 */
export interface ClaudeProviderConfig {
  claudeCodePath?: string;
  workspaceRoot: string;
}

/**
 * Model configuration mapping
 */
export const MODEL_CONFIG = {
  research: 'claude-haiku-4-20250514' as ClaudeModel,
  planning: 'claude-opus-4-20250514' as ClaudeModel,
  coding: 'claude-sonnet-4-20250514' as ClaudeModel,
  editor: 'claude-sonnet-4-20250514' as ClaudeModel,
} as const;

/**
 * ClaudeProvider manages Claude CLI subprocess execution with multi-model support
 */
export class ClaudeProvider {
  private cliPath: string;
  private workspaceRoot: string;
  private activeProcesses: Map<string, ChildProcess> = new Map();

  constructor(config: ClaudeProviderConfig) {
    this.cliPath = config.claudeCodePath || 'claude';
    this.workspaceRoot = config.workspaceRoot;
  }

  /**
   * Execute a prompt with Claude and stream responses
   */
  async *execute(params: ExecutionParams): AsyncIterableIterator<ClaudeChunk> {
    // Build CLI arguments
    const args = this.buildCliArgs(params);
    
    // Spawn subprocess
    const processId = this.generateProcessId();
    const process = spawn(this.cliPath, args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd: this.workspaceRoot,
      env: {
        ...process.env,
        // Let CLI handle auth - don't pass ANTHROPIC_API_KEY
      },
    });

    this.activeProcesses.set(processId, process);

    try {
      // Set up error handling
      let stderr = '';
      process.stderr.on('data', (chunk) => {
        stderr += chunk.toString();
        console.error('[ClaudeProvider] stderr:', chunk.toString());
      });

      // Set up process exit handler
      const exitPromise = new Promise<number>((resolve) => {
        process.on('exit', (code) => {
          resolve(code || 0);
        });
      });

      // Write prompt to stdin
      const fullPrompt = this.buildFullPrompt(params);
      process.stdin.write(fullPrompt);
      process.stdin.end();

      // Parse streaming output
      let buffer = '';
      const stream = process.stdout;

      for await (const chunk of stream) {
        buffer += chunk.toString();

        // Try to extract complete chunks
        const chunks = this.extractChunks(buffer);
        for (const extractedChunk of chunks) {
          const parsed = this.parseChunk(extractedChunk);
          if (parsed) {
            yield parsed;
          }
        }
      }

      // Wait for process to exit
      const exitCode = await exitPromise;

      if (exitCode !== 0) {
        console.error(`[ClaudeProvider] Process exited with code ${exitCode}`);
        if (stderr) {
          console.error(`[ClaudeProvider] stderr: ${stderr}`);
        }
        throw new Error(`Claude CLI exited with code ${exitCode}: ${stderr}`);
      }

    } finally {
      // Clean up
      this.activeProcesses.delete(processId);
      if (!process.killed) {
        process.kill();
      }
    }
  }

  /**
   * Execute a prompt and collect full response (non-streaming)
   */
  async executeSync(params: ExecutionParams): Promise<{
    content: string;
    usage: {
      inputTokens: number;
      outputTokens: number;
    };
  }> {
    let content = '';
    let usage = {
      inputTokens: 0,
      outputTokens: 0,
    };

    for await (const chunk of this.execute(params)) {
      if (chunk.type === 'text') {
        content += chunk.content;
      }
      // Track usage if available
      if ((chunk as any).usage) {
        usage.inputTokens += (chunk as any).usage.inputTokens || 0;
        usage.outputTokens += (chunk as any).usage.outputTokens || 0;
      }
    }

    return { content, usage };
  }

  /**
   * Detect authentication status
   */
  async detectAuthStatus(): Promise<AuthStatus> {
    // Check for Claude CLI settings
    const settingsPath = join(homedir(), '.claude', 'settings.json');
    const hasOAuth = existsSync(settingsPath);
    const hasApiKey = Boolean(process.env.ANTHROPIC_API_KEY);

    if (hasOAuth && !hasApiKey) {
      return {
        authenticated: true,
        mode: 'subscription',
        source: 'Claude CLI OAuth',
      };
    }

    if (!hasOAuth && hasApiKey) {
      return {
        authenticated: true,
        mode: 'api_key',
        source: 'ANTHROPIC_API_KEY',
        warning: 'Using pay-as-you-go billing',
      };
    }

    if (hasOAuth && hasApiKey) {
      return {
        authenticated: true,
        mode: 'subscription',
        warning: 'ANTHROPIC_API_KEY ignored, using OAuth',
      };
    }

    return {
      authenticated: false,
      mode: 'none',
      error: 'No authentication configured. Run: claude',
    };
  }

  /**
   * Ensure Claude is authenticated
   */
  async ensureAuthenticated(): Promise<void> {
    const status = await this.detectAuthStatus();

    if (!status.authenticated) {
      throw new Error(
        'Claude CLI not authenticated. Run: claude (and select authentication method)'
      );
    }

    if (status.warning) {
      console.warn('[ClaudeProvider]', status.warning);
    }
  }

  /**
   * Abort a running process
   */
  abort(processId?: string): void {
    if (processId) {
      const process = this.activeProcesses.get(processId);
      if (process && !process.killed) {
        process.kill();
        this.activeProcesses.delete(processId);
      }
    } else {
      // Abort all processes
      for (const [id, process] of this.activeProcesses) {
        if (!process.killed) {
          process.kill();
        }
      }
      this.activeProcesses.clear();
    }
  }

  // =============================================================================
  // Private Methods
  // =============================================================================

  /**
   * Build CLI arguments for subprocess
   */
  private buildCliArgs(params: ExecutionParams): string[] {
    const args = [
      '-p', // Non-interactive mode
      '--model', params.model,
      '--output-format', 'stream-json',
    ];

    // Add thinking mode if extended
    if (params.thinkingMode === 'extended') {
      args.push('--thinking', 'extended');
    }

    return args;
  }

  /**
   * Build full prompt with system instructions, context, and tools
   */
  private buildFullPrompt(params: ExecutionParams): string {
    let prompt = '';

    // System instructions
    if (params.systemPrompt) {
      prompt += `${params.systemPrompt}\n\n`;
    }

    // Context
    if (params.context) {
      prompt += this.formatContext(params.context);
      prompt += '\n\n';
    }

    // Tools (if any)
    if (params.tools && params.tools.length > 0) {
      prompt += this.formatTools(params.tools);
      prompt += '\n\n';
    }

    // User message
    prompt += params.prompt;

    return prompt;
  }

  /**
   * Format context for prompt
   */
  private formatContext(context: Context): string {
    let formatted = '# Context\n\n';

    if (context.kbResults && context.kbResults.length > 0) {
      formatted += '## Knowledge Bank Search Results\n\n';
      for (const result of context.kbResults) {
        formatted += `### ${result.file}:${result.startLine}-${result.endLine}\n`;
        formatted += '```' + result.language + '\n';
        formatted += result.content + '\n';
        formatted += '```\n\n';
      }
    }

    if (context.files && context.files.length > 0) {
      formatted += '## Current Files\n\n';
      for (const file of context.files) {
        formatted += `### ${file.path}\n`;
        formatted += '```' + file.language + '\n';
        formatted += file.content + '\n';
        formatted += '```\n\n';
      }
    }

    if (context.repoMap) {
      formatted += '## Repository Map\n\n';
      formatted += '```\n';
      formatted += context.repoMap;
      formatted += '\n```\n\n';
    }

    return formatted;
  }

  /**
   * Format tools for prompt
   */
  private formatTools(tools: Tool[]): string {
    let formatted = '# Available Tools\n\n';
    formatted += 'You have access to the following tools:\n\n';

    for (const tool of tools) {
      formatted += `## ${tool.name}\n`;
      formatted += `${tool.description}\n\n`;
      if (tool.parameters) {
        formatted += 'Parameters:\n';
        formatted += JSON.stringify(tool.parameters, null, 2);
        formatted += '\n\n';
      }
    }

    return formatted;
  }

  /**
   * Extract complete chunks from buffer
   */
  private extractChunks(buffer: string): string[] {
    const chunks: string[] = [];
    const lines = buffer.split('\n');

    for (const line of lines) {
      if (line.trim()) {
        chunks.push(line);
      }
    }

    return chunks;
  }

  /**
   * Parse a chunk into ClaudeChunk
   */
  private parseChunk(chunk: string): ClaudeChunk | null {
    try {
      const parsed = JSON.parse(chunk);

      // Handle different message types
      if (parsed.type === 'assistant' && parsed.message) {
        // Extract text content
        const message = parsed.message;
        let text = '';

        if (message.content) {
          for (const block of message.content) {
            if (block.type === 'text') {
              text += block.text;
            }
          }
        }

        return {
          type: 'text',
          content: text,
        };
      }

      // Handle thinking blocks
      if (parsed.type === 'thinking') {
        return {
          type: 'thinking',
          content: parsed.content || '',
        };
      }

      // Handle tool use
      if (parsed.type === 'tool_use') {
        return {
          type: 'tool_use',
          content: '',
          toolName: parsed.name,
          toolInput: parsed.input,
        };
      }

      // Handle tool result
      if (parsed.type === 'tool_result') {
        return {
          type: 'tool_result',
          content: '',
          toolResult: parsed.content,
        };
      }

      return null;
    } catch (error) {
      // Not valid JSON, might be partial
      return null;
    }
  }

  /**
   * Generate unique process ID
   */
  private generateProcessId(): string {
    return `proc_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
  }
}

/**
 * Authentication manager for detecting Claude CLI auth status
 */
export class AuthManager {
  /**
   * Detect authentication status
   */
  async detectAuthStatus(): Promise<AuthStatus> {
    const settingsPath = join(homedir(), '.claude', 'settings.json');
    const hasOAuth = existsSync(settingsPath);
    const hasApiKey = Boolean(process.env.ANTHROPIC_API_KEY);

    if (hasOAuth && !hasApiKey) {
      return {
        authenticated: true,
        mode: 'subscription',
        source: 'Claude CLI OAuth',
      };
    }

    if (!hasOAuth && hasApiKey) {
      return {
        authenticated: true,
        mode: 'api_key',
        source: 'ANTHROPIC_API_KEY',
        warning: 'Using pay-as-you-go billing',
      };
    }

    if (hasOAuth && hasApiKey) {
      return {
        authenticated: true,
        mode: 'subscription',
        warning: 'ANTHROPIC_API_KEY ignored, using OAuth',
      };
    }

    return {
      authenticated: false,
      mode: 'none',
      error: 'No authentication configured',
    };
  }

  /**
   * Ensure authentication is configured
   */
  async ensureAuthenticated(): Promise<void> {
    const status = await this.detectAuthStatus();

    if (!status.authenticated) {
      throw new Error(
        'Claude CLI not authenticated. Run: claude (and select authentication method)'
      );
    }

    if (status.warning) {
      console.warn('[AuthManager]', status.warning);
    }
  }
}