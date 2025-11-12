/**
 * ArchitectWorkflow - Research → Clarification → Planning workflow
 *
 * Implements a structured approach to complex coding tasks:
 * 1. Research: Discover relevant codebase context via KB searches
 * 2. Clarification: Interactive Q&A loop to refine understanding
 * 3. Planning: Generate structured implementation plan
 *
 * Key difference from EditorWorkflow: Includes mandatory clarification phase
 * to ensure LLM has complete context before generating plan.
 */

import type {
  IWorkflow,
  TaskInput,
  WorkflowUpdate,
  ResearchResult,
  ClarificationResult,
  ClarificationQuestion,
  ClarificationResponse,
  Plan,
  KBSearch,
} from '../types/index.js';

import type { ContextBuilder } from '../context/context-builder.js';
import type { PromptBuilder } from '../prompts/prompt-builder.js';
import type { ClaudeProvider } from '../execution/claude-provider.js';

export interface ArchitectWorkflowConfig {
  claudeProvider: ClaudeProvider;
  contextBuilder: ContextBuilder;
  promptBuilder: PromptBuilder;
  maxClarificationTurns?: number;
}

/**
 * ArchitectWorkflow orchestrates the research → clarification → planning flow
 */
export class ArchitectWorkflow implements IWorkflow {
  private config: ArchitectWorkflowConfig;
  private maxClarificationTurns: number;
  private aborted = false;

  constructor(config: ArchitectWorkflowConfig) {
    this.config = config;
    this.maxClarificationTurns = config.maxClarificationTurns || 3;
  }

  /**
   * Execute the architect workflow
   */
  async *execute(input: TaskInput): AsyncIterableIterator<WorkflowUpdate> {
    const sessionId = `architect_${Date.now()}`;
    this.aborted = false;

    try {
      // ========================================================================
      // Phase 1: Research - Discover codebase context
      // ========================================================================
      yield {
        type: 'state_change',
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: 'researching' },
      };

      const research = yield* this.executeResearchPhase(sessionId, input);

      // ========================================================================
      // Phase 2: Clarification - Interactive Q&A loop
      // ========================================================================
      yield {
        type: 'state_change',
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: 'clarifying' },
      };

      const clarification = yield* this.executeClarificationPhase(
        sessionId,
        input,
        research
      );

      // ========================================================================
      // Phase 3: Planning - Generate structured plan
      // ========================================================================
      yield {
        type: 'state_change',
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: 'planning' },
      };

      const plan = yield* this.executePlanningPhase(
        sessionId,
        input,
        research,
        clarification
      );

      // ========================================================================
      // Phase 4: Await User Approval
      // ========================================================================
      yield {
        type: 'state_change',
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: 'awaiting_approval' },
      };

      yield {
        type: 'progress',
        sessionId,
        timestamp: new Date().toISOString(),
        data: {
          phase: 'planning',
          message: 'Plan ready for review',
          plan,
        },
      };

      // Note: Orchestrator will handle approval/rejection flow
      // This workflow yields and waits for orchestrator to resume

    } catch (error) {
      yield {
        type: 'error',
        sessionId,
        timestamp: new Date().toISOString(),
        data: {
          error: error instanceof Error ? error.message : String(error),
        },
      };
    }
  }

  /**
   * Phase 1: Research Phase
   * - Execute KB searches to understand codebase
   * - Identify relevant files and patterns
   * - Summarize findings
   */
  private async *executeResearchPhase(
    sessionId: string,
    input: TaskInput
  ): AsyncGenerator<WorkflowUpdate, ResearchResult, unknown> {
    const startTime = Date.now();
    const kbSearches: KBSearch[] = [];
    const relevantFiles: string[] = [];

    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'research',
        message: 'Searching knowledge base for relevant context...',
      },
    };

    // Build context with KB search
    const context = await this.config.contextBuilder.build({
      searchQuery: input.message,
      files: input.context.files,
      maxTokens: 12000,
      includeRepoMap: false,
      scope: 'architect',
    });

    // Track KB searches
    for (const kbResult of context.kbResults) {
      if (!relevantFiles.includes(kbResult.file)) {
        relevantFiles.push(kbResult.file);
      }
    }

    kbSearches.push({
      query: input.message,
      resultsCount: context.kbResults.length,
      topResult: context.kbResults[0]?.file,
    });

    // Generate research prompt and execute with Claude
    const researchPrompt = this.config.promptBuilder.buildResearchPrompt({
      task: input.message,
      context,
      systemPrompt: this.getResearchSystemPrompt(),
    });

    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'research',
        message: 'Analyzing codebase and generating research findings...',
      },
    };

    // Execute research with Haiku (fast, cost-effective)
    let findings = '';
    for await (const chunk of this.config.claudeProvider.execute({
      model: 'claude-haiku-4-20250514',
      prompt: researchPrompt,
      systemPrompt: this.getResearchSystemPrompt(),
      context,
      thinkingMode: 'normal',
    })) {
      if (chunk.type === 'text') {
        findings += chunk.content;

        yield {
          type: 'chunk',
          sessionId,
          timestamp: new Date().toISOString(),
          data: {
            type: 'text',
            content: chunk.content,
            phase: 'research',
          },
        };
      }
    }

    const result: ResearchResult = {
      completedAt: new Date().toISOString(),
      model: 'claude-haiku-4-20250514',
      tokensUsed: Math.floor((findings.length / 4)), // Rough estimate
      findings,
      kbSearches,
      relevantFiles,
    };

    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'research',
        message: `Research complete. Found ${relevantFiles.length} relevant files.`,
        result,
      },
    };

    return result;
  }

  /**
   * Phase 2: Clarification Phase
   * - Interactive Q&A loop with the LLM
   * - LLM can ask questions and continue using KB tools
   * - Continues until LLM signals ready OR max turns reached
   */
  private async *executeClarificationPhase(
    sessionId: string,
    input: TaskInput,
    research: ResearchResult
  ): AsyncGenerator<WorkflowUpdate, ClarificationResult, unknown> {
    const questions: ClarificationQuestion[] = [];
    const responses: ClarificationResponse[] = [];
    let conversationTurns = 0;
    let readyForPlanning = false;
    let conversationHistory: Array<{role: 'user' | 'assistant'; content: string}> = [];

    // Initial clarification prompt with research context
    conversationHistory.push({
      role: 'user',
      content: this.buildInitialClarificationPrompt(input, research),
    });

    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'clarification',
        message: 'Initiating clarification phase...',
      },
    };

    // Clarification loop: continue until LLM signals ready or max turns
    while (conversationTurns < this.maxClarificationTurns && !readyForPlanning) {
      if (this.aborted) {
        throw new Error('Workflow aborted');
      }

      conversationTurns++;

      yield {
        type: 'progress',
        sessionId,
        timestamp: new Date().toISOString(),
        data: {
          phase: 'clarification',
          message: `Clarification turn ${conversationTurns}/${this.maxClarificationTurns}`,
        },
      };

      // Execute clarification with Sonnet (good reasoning, balanced cost)
      let llmResponse = '';
      for await (const chunk of this.config.claudeProvider.execute({
        model: 'claude-sonnet-4-20250514',
        prompt: conversationHistory[conversationHistory.length - 1].content,
        systemPrompt: this.getClarificationSystemPrompt(conversationTurns),
        thinkingMode: 'normal',
      })) {
        if (chunk.type === 'text') {
          llmResponse += chunk.content;

          yield {
            type: 'chunk',
            sessionId,
            timestamp: new Date().toISOString(),
            data: {
              type: 'text',
              content: chunk.content,
              phase: 'clarification',
            },
          };
        }
      }

      conversationHistory.push({
        role: 'assistant',
        content: llmResponse,
      });

      // Check if LLM is ready to plan
      // Signal: LLM includes [READY_TO_PLAN] marker or reaches max turns
      if (llmResponse.includes('[READY_TO_PLAN]') || conversationTurns >= this.maxClarificationTurns) {
        readyForPlanning = true;

        yield {
          type: 'progress',
          sessionId,
          timestamp: new Date().toISOString(),
          data: {
            phase: 'clarification',
            message: 'Clarification complete. Proceeding to planning...',
          },
        };

        break;
      }

      // Parse questions from LLM response
      const parsedQuestions = this.parseQuestionsFromResponse(llmResponse);
      questions.push(...parsedQuestions);

      // Wait for user response
      // Note: In practice, this would be an event emitted to UI
      // For now, we'll simulate by checking if there are questions
      if (parsedQuestions.length > 0) {
        yield {
          type: 'progress',
          sessionId,
          timestamp: new Date().toISOString(),
          data: {
            phase: 'clarification',
            message: `${parsedQuestions.length} clarifying questions`,
            questions: parsedQuestions,
          },
        };

        // This is where we'd wait for user input in the real implementation
        // For the MVP, we'll treat no response as a signal to continue with what we have
        break;
      }
    }

    const result: ClarificationResult = {
      completedAt: new Date().toISOString(),
      model: 'claude-sonnet-4-20250514',
      tokensUsed: Math.floor((conversationHistory.reduce((sum, msg) => sum + msg.content.length, 0) / 4)),
      conversationTurns,
      questions,
      responses,
      readyForPlanning,
      finalContext: conversationHistory[conversationHistory.length - 1].content,
    };

    // Yield progress update with result so orchestrator can capture it
    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'clarification',
        message: 'Clarification phase complete',
        result,
      },
    };

    return result;
  }

  /**
   * Phase 3: Planning Phase
   * - Generate structured implementation plan
   * - Parse plan into TOML-compatible structure
   * - Include file references, steps, complexity estimate
   */
  private async *executePlanningPhase(
    sessionId: string,
    input: TaskInput,
    research: ResearchResult,
    clarification: ClarificationResult
  ): AsyncGenerator<WorkflowUpdate, Plan, unknown> {
    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'planning',
        message: 'Generating implementation plan...',
      },
    };

    // Build context for planning
    const context = await this.config.contextBuilder.build({
      searchQuery: input.message,
      files: research.relevantFiles,
      maxTokens: 16000,
      includeRepoMap: true,
      scope: 'architect',
      researchFindings: research,
    });

    // Generate planning prompt
    const planningPrompt = this.config.promptBuilder.buildPlanningPrompt({
      task: input.message,
      research,
      context,
      systemPrompt: this.getPlanningSystemPrompt(),
    });

    // Execute planning with Opus (best reasoning)
    let planContent = '';
    for await (const chunk of this.config.claudeProvider.execute({
      model: 'claude-opus-4-20250514',
      prompt: planningPrompt,
      systemPrompt: this.getPlanningSystemPrompt(),
      context,
      thinkingMode: 'extended',
    })) {
      if (chunk.type === 'text') {
        planContent += chunk.content;

        yield {
          type: 'chunk',
          sessionId,
          timestamp: new Date().toISOString(),
          data: {
            type: 'text',
            content: chunk.content,
            phase: 'planning',
          },
        };
      }
    }

    // Parse plan from markdown
    const parsedPlan = this.parsePlanFromMarkdown(planContent);

    const plan: Plan = {
      version: 1,
      status: 'pending_approval',
      createdAt: new Date().toISOString(),
      model: 'claude-opus-4-20250514',
      tokensUsed: Math.floor((planContent.length / 4)),
      estimatedCost: 0.015, // Rough estimate for Opus
      content: planContent,
      filesToModify: parsedPlan.filesToModify || [],
      filesToCreate: parsedPlan.filesToCreate || [],
      steps: parsedPlan.steps || [],
      complexity: parsedPlan.complexity || 'medium',
      estimatedTokens: parsedPlan.estimatedTokens || Math.floor(planContent.length / 4),
      overview: parsedPlan.overview,
    };

    yield {
      type: 'progress',
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: 'planning',
        message: 'Plan generated successfully',
        plan,
      },
    };

    return plan;
  }

  /**
   * Helper: Parse questions from LLM response
   */
  private parseQuestionsFromResponse(response: string): ClarificationQuestion[] {
    const questions: ClarificationQuestion[] = [];

    // Look for question patterns (lines ending with ?)
    const lines = response.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.endsWith('?') && trimmed.length > 10) {
        questions.push({
          question: trimmed,
          priority: 'medium',
          reason: 'Requires clarification',
        });
      }
    }

    return questions;
  }

  /**
   * Helper: Parse plan from markdown content
   */
  private parsePlanFromMarkdown(content: string): Partial<Plan> {
    const filesToModify: string[] = [];
    const filesToCreate: string[] = [];
    const steps: string[] = [];
    let overview = '';
    let complexity: 'low' | 'medium' | 'high' = 'medium';

    // Extract overview (first paragraph or summary section)
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
      for (const line of stepLines) {
        const stepMatch = line.match(/^\s*\d+\.\s+(.+)$/);
        if (stepMatch) {
          steps.push(stepMatch[1].trim());
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
      filesToModify,
      filesToCreate,
      steps,
      complexity,
      estimatedTokens: Math.floor(steps.length * 500), // Rough estimate
    };
  }

  /**
   * Helper: Build initial clarification prompt
   */
  private buildInitialClarificationPrompt(
    input: TaskInput,
    research: ResearchResult
  ): string {
    return `# Task
${input.message}

# Research Findings
${research.findings}

# Relevant Files
${research.relevantFiles.map(f => `- ${f}`).join('\n')}

# Your Role
You are in the clarification phase. Your goal is to ask any clarifying questions needed to fully understand the task before generating an implementation plan.

Review the research findings and identify:
1. Any ambiguities in the requirements
2. Missing information about the codebase
3. Technical decisions that need to be made
4. Potential edge cases or constraints

Ask clear, specific questions. You can also use KB tools to search for more context if needed.

When you have all the information needed to create a comprehensive plan, respond with [READY_TO_PLAN] at the end of your message.`;
  }

  /**
   * System prompt for research phase
   */
  private getResearchSystemPrompt(): string {
    return `You are an expert software architect conducting research on a codebase.

Your task:
1. Review the provided code snippets and context
2. Identify relevant patterns, architectures, and conventions
3. Summarize key findings that will inform the implementation
4. Note any potential challenges or constraints

Focus on:
- Existing architecture patterns
- Code organization and structure
- Dependencies and integrations
- Testing approaches
- Common conventions and best practices

Be concise but thorough. Your findings will guide the planning phase.`;
  }

  /**
   * System prompt for clarification phase
   */
  private getClarificationSystemPrompt(turnNumber: number): string {
    const urgencyNote = turnNumber >= 2
      ? '\n\nNote: You have limited remaining turns. Prioritize the most critical questions.'
      : '';

    return `You are an expert software architect in the clarification phase.

Your goal: Ask clarifying questions to ensure you have complete understanding before planning.

Guidelines:
- Ask specific, actionable questions
- Focus on ambiguities and unknowns
- Prioritize questions by importance
- Use KB tools if you need more code context
- When ready to plan, end your message with [READY_TO_PLAN]${urgencyNote}

Be efficient with questions - ask what's essential, not everything possible.`;
  }

  /**
   * System prompt for planning phase
   */
  private getPlanningSystemPrompt(): string {
    return `You are an expert software architect creating an implementation plan.

Your plan must include:

## Overview
Brief summary of the approach and key decisions

## Files to Modify
- List each file that needs changes
- Include file paths

## Files to Create
- List new files needed
- Include file paths

## Implementation Steps
1. Numbered list of concrete steps
2. Each step should be actionable
3. Order steps by logical dependencies

## Complexity
Estimate: low, medium, or high

## Estimated Effort
Rough time estimate

Guidelines:
- Reference specific files, functions, and classes from the codebase
- Follow existing architecture patterns
- Consider error handling and edge cases
- Think about testing strategy
- Be concrete and specific

Output as well-structured markdown.`;
  }

  /**
   * Abort the workflow
   */
  public abort(): void {
    this.aborted = true;
  }
}
