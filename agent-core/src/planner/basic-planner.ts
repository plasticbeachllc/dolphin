// agent-core/src/planner/basic-planner.ts
import type { ClaudeClient, CompletionRequest } from "../llm/claude-client";
import type { AgentEvent } from "../../../shared/types/events";

export interface PlannerContext {
  userMessage: string;
  kbResults?: string;
  conversationHistory?: Array<{ role: "user" | "assistant"; content: string }>;
}

export interface PlannerConfig {
  enableStreaming?: boolean;
  maxTokens?: number;
  temperature?: number;
}

/**
 * Basic planner that uses Claude to generate responses and plans
 */
export class BasicPlanner {
  constructor(
    private claudeClient: ClaudeClient,
    private config: PlannerConfig = {}
  ) {}

  /**
   * Process a user message and generate a response
   * Emits events via callback for UI updates
   */
  async processMessage(
    context: PlannerContext,
    onEvent: (event: AgentEvent) => void
  ): Promise<void> {
    try {
      // Build the prompt with context
      const systemPrompt = this.buildSystemPrompt();
      const userPrompt = this.buildUserPrompt(context);

      // Prepare completion request
      const request: CompletionRequest = {
        system: systemPrompt,
        messages: [
          ...(context.conversationHistory || []),
          { role: "user", content: userPrompt },
        ],
        maxTokens: this.config.maxTokens || 8000,
        temperature: this.config.temperature || 1.0,
      };

      // Get auth mode to determine streaming capability
      const authStatus = await this.claudeClient.getAuthStatus();
      const canStream =
        authStatus.mode === "api_key" && this.config.enableStreaming !== false;

      if (canStream) {
        // Stream response for API mode
        await this.streamResponse(request, onEvent);
      } else {
        // Batch response for CLI mode
        await this.batchResponse(request, onEvent);
      }

      // Mark task as completed
      onEvent({
        type: "task_completed",
        success: true,
        result: { mode: authStatus.mode },
      });
    } catch (error: any) {
      onEvent({
        type: "error",
        error: {
          code: "SERVICE_UNAVAILABLE",
          message: error.message,
          suggestions: [
            "Check Claude authentication",
            "Verify network connection",
            "Try again in a moment",
          ],
          recoverable: true,
        },
      });
    }
  }

  /**
   * Stream response character-by-character (API mode)
   */
  private async streamResponse(
    request: CompletionRequest,
    onEvent: (event: AgentEvent) => void
  ): Promise<void> {
    for await (const chunk of this.claudeClient.completeStreaming(request)) {
      onEvent({
        type: "content_delta",
        delta: chunk,
      });
    }
  }

  /**
   * Show "thinking" indicator then emit full response (CLI mode)
   */
  private async batchResponse(
    request: CompletionRequest,
    onEvent: (event: AgentEvent) => void
  ): Promise<void> {
    // Show thinking indicator
    onEvent({
      type: "content_delta",
      delta: "🤔 Thinking...\n\n",
    });

    // Get complete response
    const result = await this.claudeClient.complete(request);

    // Emit full response
    onEvent({
      type: "content_delta",
      delta: result.content,
    });
  }

  /**
   * Build system prompt for Claude
   */
  private buildSystemPrompt(): string {
    return `You are Dolphin, an AI coding assistant integrated into VSCode.

Your capabilities:
- Access to a semantic code search (Knowledge Bank) to find relevant code
- File operations (read, write, modify)
- Command execution
- Planning and task breakdown

When responding:
- Be concise and helpful
- Use Knowledge Bank context when provided
- Suggest concrete next steps
- Format code with markdown code blocks
- Ask clarifying questions when needed

Current mode: Basic response generation (planning features coming soon)`;
  }

  /**
   * Build user prompt with KB context if available
   */
  private buildUserPrompt(context: PlannerContext): string {
    let prompt = "";

    // Add KB results if available
    if (context.kbResults && context.kbResults.trim()) {
      prompt += `# Relevant Code from Knowledge Bank\n\n${context.kbResults}\n\n---\n\n`;
    }

    // Add user message
    prompt += `# User Request\n\n${context.userMessage}`;

    return prompt;
  }
}