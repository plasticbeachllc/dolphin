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
} from "../types/index.js";

import type { ContextBuilder } from "../context/context-builder.js";
import type { PromptBuilder } from "../prompts/prompt-builder.js";
import type { ChatProvider } from "../execution/chat-provider.js";
import type { StateStore } from "../state/state-store.js";
import type { PlanStore } from "../storage/plan-store.js";
import { DEFAULT_MAX_CLARIFICATION_TURNS } from "./constants.js";
import type { ToolExecutorMessage, UsageStats } from "../llm/tool-executor.js";
import { parsePlanFromMarkdown, parseLegacyMarkdownPlan } from "./plan-parser.js";

type WorkflowPhaseName = "research" | "clarification" | "planning";

export interface ArchitectWorkflowConfig {
  chatProvider: ChatProvider;
  contextBuilder: ContextBuilder;
  promptBuilder: PromptBuilder;
  stateStore: StateStore;
  planStore: PlanStore;
  workspaceRoot: string;
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
    this.maxClarificationTurns = config.maxClarificationTurns || DEFAULT_MAX_CLARIFICATION_TURNS;
  }

  /**
   * Execute the architect workflow
   */
  async *execute(input: TaskInput): AsyncIterableIterator<WorkflowUpdate> {
    const sessionId = `architect_${Date.now()}`;
    this.aborted = false;
    const logPrefix = `[ArchitectWorkflow][${sessionId}]`;

    console.error(
      `${logPrefix} Starting architect workflow (mode=${input.mode ?? "architect"}) for task: ${
        input.message
      }`
    );

    try {
      // ========================================================================
      // Phase 1: Research - Discover codebase context
      // ========================================================================
      yield {
        type: "state_change",
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: "researching" },
      };

      const research = yield* this.executeResearchPhase(sessionId, input);

      // ========================================================================
      // Phase 2: Clarification - Interactive Q&A loop
      // ========================================================================
      yield {
        type: "state_change",
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: "clarifying" },
      };

      const clarification = yield* this.executeClarificationPhase(sessionId, input, research);

      // ========================================================================
      // Phase 3: Planning - Generate structured plan
      // ========================================================================
      yield {
        type: "state_change",
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: "planning" },
      };

      const plan = yield* this.executePlanningPhase(sessionId, input, research, clarification);

      // ========================================================================
      // Phase 4: Await User Approval
      // ========================================================================
      yield {
        type: "state_change",
        sessionId,
        timestamp: new Date().toISOString(),
        data: { state: "awaiting_approval" },
      };

      console.error(`${logPrefix} Plan ready, awaiting approval`);

      yield {
        type: "progress",
        sessionId,
        timestamp: new Date().toISOString(),
        data: {
          phase: "planning",
          message: "Plan ready for review",
          plan,
        },
      };

      // Note: Orchestrator will handle approval/rejection flow
      // This workflow yields and waits for orchestrator to resume
    } catch (error) {
      yield {
        type: "error",
        sessionId,
        timestamp: new Date().toISOString(),
        data: {
          error: error instanceof Error ? error.message : String(error),
        },
      };
      console.error(`${logPrefix} Workflow failed:`, error);
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
    const logPrefix = `[ArchitectWorkflow][${sessionId}]`;
    console.error(`${logPrefix} Research phase: building KB context`);

    const _startTime = Date.now();
    const kbSearches: KBSearch[] = [];
    const relevantFiles: string[] = [];

    yield {
      type: "progress",
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: "research",
        message: "Searching knowledge base for relevant context...",
      },
    };

    // Build context with KB search
    const contextStart = Date.now();
    const context = await this.config.contextBuilder.build({
      searchQuery: input.message,
      files: input.context.files,
      maxTokens: 12000,
      includeRepoMap: false,
      scope: "architect",
    });
    console.error(
      `${logPrefix} Research phase: KB context ready in ${Date.now() - contextStart}ms (results=${
        context.kbResults.length
      })`
    );

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
      type: "progress",
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: "research",
        message: "Analyzing codebase and generating research findings...",
      },
    };

    console.error(`${logPrefix} Research phase: invoking provider`);
    const researchCall = await this.callChatProvider({
      sessionId,
      phase: "research",
      prompt: researchPrompt,
    });
    console.error(`${logPrefix} Research phase: provider completed`);

    for (const chunkUpdate of researchCall.chunkUpdates) {
      yield chunkUpdate;
    }

    const findings = researchCall.text;
    const usageTokens = this.getUsageTotal(researchCall.usage);
    const providerInfo = this.config.chatProvider.getProviderMetadata();

    const result: ResearchResult = {
      completedAt: new Date().toISOString(),
      model: providerInfo.model,
      tokensUsed: usageTokens,
      findings,
      kbSearches,
      relevantFiles,
    };

    yield {
      type: "progress",
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: "research",
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
    const logPrefix = `[ArchitectWorkflow][${sessionId}]`;
    const questions: ClarificationQuestion[] = [];
    const responses: ClarificationResponse[] = [];
    let conversationTurns = 0;
    let readyForPlanning = false;
    let conversationHistory: Array<{ role: "user" | "assistant"; content: string }> = [];
    let clarificationTokensUsed = 0;

    // Initial clarification prompt with research context
    conversationHistory.push({
      role: "user",
      content: `${this.getClarificationSystemPrompt(1)}\n\n${this.buildInitialClarificationPrompt(
        input,
        research
      )}`,
    });

    yield {
      type: "progress",
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: "clarification",
        message: "Initiating clarification phase...",
      },
    };

    // Clarification loop: continue until LLM signals ready or max turns
    while (conversationTurns < this.maxClarificationTurns && !readyForPlanning) {
      if (this.aborted) {
        throw new Error("Workflow aborted");
      }

      conversationTurns++;

      yield {
        type: "progress",
        sessionId,
        timestamp: new Date().toISOString(),
        data: {
          phase: "clarification",
          message: `Clarification turn ${conversationTurns}/${this.maxClarificationTurns}`,
        },
      };

      const priorHistory =
        conversationHistory.length > 1 ? conversationHistory.slice(0, -1) : undefined;
      console.error(`${logPrefix} Clarification turn ${conversationTurns}: invoking provider`);
      const clarificationCall = await this.callChatProvider({
        sessionId,
        phase: "clarification",
        prompt: conversationHistory[conversationHistory.length - 1].content,
        conversationHistory: priorHistory,
      });
      console.error(`${logPrefix} Clarification turn ${conversationTurns}: provider completed`);

      for (const chunkUpdate of clarificationCall.chunkUpdates) {
        yield chunkUpdate;
      }

      const llmResponse = clarificationCall.text;
      clarificationTokensUsed += this.getUsageTotal(clarificationCall.usage);

      conversationHistory.push({
        role: "assistant",
        content: llmResponse,
      });

      // Check if LLM is ready to plan
      // Signal: LLM includes [READY_TO_PLAN] marker or reaches max turns
      if (
        llmResponse.includes("[READY_TO_PLAN]") ||
        conversationTurns >= this.maxClarificationTurns
      ) {
        readyForPlanning = true;

        console.error(
          `${logPrefix} Clarification produced ${parsedQuestions.length} question(s); pausing clarification loop`
        );

        yield {
          type: "progress",
          sessionId,
          timestamp: new Date().toISOString(),
          data: {
            phase: "clarification",
            message: "Clarification complete. Proceeding to planning...",
          },
        };

        break;
      }

      // Parse questions from LLM response
      let parsedQuestions = this.parseQuestionsFromResponse(llmResponse);
      if (parsedQuestions.length === 0 && llmResponse.includes("?")) {
        parsedQuestions = [
          {
            question:
              llmResponse
                .split(/\r?\n/)
                .find((line) => line.trim().endsWith("?"))
                ?.trim() ?? llmResponse,
            priority: "medium",
            reason: "Unable to extract individual questions",
          },
        ];
      }
      questions.push(...parsedQuestions);

      // Wait for user response
      // Note: In practice, this would be an event emitted to UI
      // For now, we'll simulate by checking if there are questions
      if (parsedQuestions.length > 0) {
        yield {
          type: "progress",
          sessionId,
          timestamp: new Date().toISOString(),
          data: {
            phase: "clarification",
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
      model: this.config.chatProvider.getProviderMetadata().model,
      tokensUsed: clarificationTokensUsed,
      conversationTurns,
      questions,
      responses,
      readyForPlanning,
      finalContext: conversationHistory[conversationHistory.length - 1].content,
    };

    // Yield progress update with result so orchestrator can capture it
    yield {
      type: "progress",
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: "clarification",
        message: "Clarification phase complete",
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
    _clarification: ClarificationResult
  ): AsyncGenerator<WorkflowUpdate, Plan, unknown> {
    const logPrefix = `[ArchitectWorkflow][${sessionId}]`;
    yield {
      type: "progress",
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: "planning",
        message: "Generating implementation plan...",
      },
    };

    console.error(`${logPrefix} Planning phase: building context + prompt`);

    // Build context for planning
    const context = await this.config.contextBuilder.build({
      searchQuery: input.message,
      files: research.relevantFiles,
      maxTokens: 16000,
      includeRepoMap: true,
      scope: "architect",
      researchFindings: research,
    });

    // Generate planning prompt
    const planningPrompt = this.config.promptBuilder.buildPlanningPrompt({
      task: input.message,
      research,
      context,
      systemPrompt: this.getPlanningSystemPrompt(),
    });

    console.error(`${logPrefix} Planning phase: invoking provider`);
    const planningCall = await this.callChatProvider({
      sessionId,
      phase: "planning",
      prompt: planningPrompt,
    });
    console.error(`${logPrefix} Planning phase: provider completed`);

    for (const chunkUpdate of planningCall.chunkUpdates) {
      yield chunkUpdate;
    }

    const planContent = planningCall.text;
    const planTokensUsed = this.getUsageTotal(planningCall.usage);

    // Parse plan from markdown with robust TOML extraction
    let parsedPlan: Partial<{
      files_to_modify?: string[];
      filesToModify?: string[];
      files_to_create?: string[];
      filesToCreate?: string[];
      steps?: Array<{ id: number; description: string; files: string[] } | string>;
      complexity?: "low" | "medium" | "high";
      estimated_tokens?: number;
      estimatedTokens?: number;
      overview?: string;
    }>;
    let _parseSource = "toml";

    try {
      // Try robust TOML parsing first
      const result = parsePlanFromMarkdown(planContent);
      parsedPlan = result.plan;
      _parseSource = result.source;
    } catch {
      // Fallback to legacy markdown parsing
      parsedPlan = parseLegacyMarkdownPlan(planContent);
      _parseSource = "legacy-markdown";
    }

    // Convert TOML snake_case to Plan camelCase
    const plan: Plan = {
      version: 1,
      status: "pending_approval",
      createdAt: new Date().toISOString(),
      model: this.config.chatProvider.getProviderMetadata().model,
      tokensUsed: planTokensUsed,
      estimatedCost: 0.015, // Rough estimate for Opus
      content: planContent,
      filesToModify: parsedPlan.files_to_modify || parsedPlan.filesToModify || [],
      filesToCreate: parsedPlan.files_to_create || parsedPlan.filesToCreate || [],
      steps: (parsedPlan.steps || []).map((s) => (typeof s === "string" ? s : s.description)),
      complexity: parsedPlan.complexity || "medium",
      estimatedTokens: parsedPlan.estimated_tokens || parsedPlan.estimatedTokens || planTokensUsed,
      overview: parsedPlan.overview,
    };

    console.error(
      `${logPrefix} Planning phase: parsed plan with ${plan.filesToModify.length} files to modify and ${
        plan.steps.length
      } steps`
    );

    yield {
      type: "progress",
      sessionId,
      timestamp: new Date().toISOString(),
      data: {
        phase: "planning",
        message: "Plan generated successfully",
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
    const lines = response.split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.endsWith("?") && trimmed.length > 10) {
        questions.push({
          question: trimmed,
          priority: "medium",
          reason: "Requires clarification",
        });
      }
    }

    return questions;
  }

  private async callChatProvider(options: {
    sessionId: string;
    phase: WorkflowPhaseName;
    prompt: string;
    conversationHistory?: Array<{ role: "user" | "assistant"; content: string }>;
  }): Promise<{ text: string; usage: UsageStats; chunkUpdates: WorkflowUpdate[] }> {
    const chunkUpdates: WorkflowUpdate[] = [];
    let collectedText = "";
    const startTime = Date.now();
    const logPrefix = `[ArchitectWorkflow][${options.sessionId}]`;
    console.error(`${logPrefix} LLM call (${options.phase}) started`);

    const result = await this.config.chatProvider.execute({
      message: options.prompt,
      conversationHistory: options.conversationHistory,
      onEvent: (event) => {
        if (event.type === "content_delta" && event.delta) {
          chunkUpdates.push({
            type: "chunk",
            sessionId: options.sessionId,
            timestamp: new Date().toISOString(),
            data: {
              type: "text",
              content: event.delta,
              phase: options.phase,
            },
          });
          collectedText += event.delta;
        }
      },
    });

    if (!collectedText) {
      collectedText = this.extractAssistantText(result.messages);
    }

    console.error(
      `${logPrefix} LLM call (${options.phase}) completed in ${Date.now() - startTime}ms (toolRounds=${
        result.toolRounds
      })`
    );

    return { text: collectedText, usage: result.usage, chunkUpdates };
  }

  private extractAssistantText(messages: ToolExecutorMessage[]): string {
    for (let i = messages.length - 1; i >= 0; i--) {
      const message = messages[i];
      if (message.role === "assistant") {
        return this.stringifyContent(message.content);
      }
    }
    return "";
  }

  private stringifyContent(content: unknown): string {
    if (typeof content === "string") {
      return content;
    }

    if (Array.isArray(content)) {
      return content.map((item) => this.stringifyContent(item)).join("");
    }

    if (content && typeof content === "object") {
      const typed = content as { text?: unknown; content?: unknown; type?: string };
      if (typeof typed.text === "string") {
        return typed.text;
      }
      if (typed.type === "text" && typeof typed.content === "string") {
        return typed.content;
      }
    }

    return "";
  }

  private getUsageTotal(usage: UsageStats): number {
    return usage.inputTokens + usage.outputTokens + usage.cacheReadTokens + usage.cacheWriteTokens;
  }

  /**
   * Helper: Build initial clarification prompt
   */
  private buildInitialClarificationPrompt(input: TaskInput, research: ResearchResult): string {
    return `# Task
${input.message}

# Research Findings
${research.findings}

# Relevant Files
${research.relevantFiles.map((f) => `- ${f}`).join("\n")}

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
    const urgencyNote =
      turnNumber >= 2
        ? "\n\nNote: You have limited remaining turns. Prioritize the most critical questions."
        : "";

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

CRITICAL: Your plan MUST be provided as a TOML code block. Use this exact structure:

\`\`\`toml
plan_version = 1

overview = """
Brief summary of the approach and key decisions.
Explain the overall strategy and important architectural choices.
"""

complexity = "medium"  # Options: "low", "medium", "high"

estimated_tokens = 5000  # Rough estimate of implementation tokens

files_to_modify = [
  "path/to/file1.ts",
  "path/to/file2.ts"
]

files_to_create = [
  "path/to/new-file1.ts",
  "path/to/new-file2.ts"
]

[[steps]]
id = 1
description = "First concrete step with specific actions"
files = ["path/to/file1.ts"]
estimated_tokens = 500

[[steps]]
id = 2
description = "Second step that builds on the first"
files = ["path/to/file2.ts"]
estimated_tokens = 1000

# Add more steps as needed

[[risks]]
description = "Potential risk or challenge"
mitigation = "How to mitigate this risk"

# Add dependencies if needed
dependencies = ["package-name"]

generated_at = "2025-01-15T10:30:00Z"
\`\`\`

REQUIREMENTS:
- MUST use TOML format in a fenced code block labeled \`toml\`
- Use snake_case for all keys (not camelCase)
- Each step MUST have: id (sequential), description, files array
- Complexity MUST be one of: "low", "medium", "high"
- Overview MUST be a clear multi-line string using triple quotes
- Steps MUST use [[steps]] array-of-tables syntax
- File paths MUST be actual paths from the codebase
- Be specific and actionable in step descriptions

Guidelines:
- Reference specific files, functions, and classes from the codebase
- Follow existing architecture patterns
- Consider error handling and edge cases
- Think about testing strategy
- Order steps by logical dependencies
- Estimate tokens realistically (consider file size and complexity)

You may include explanatory markdown before or after the TOML block, but the plan data MUST be in TOML format.`;
  }

  /**
   * Abort the workflow
   */
  public abort(): void {
    this.aborted = true;
  }
}
