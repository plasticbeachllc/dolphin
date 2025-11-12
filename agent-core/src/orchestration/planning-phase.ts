/**
 * EP-11 Phase 2+3: Planning Conversation (Simplified)
 *
 * Single conversational phase that:
 * - Analyzes discovered code
 * - Asks clarifying questions
 * - Generates implementation plan
 * - Refines based on user feedback
 * - Saves to TOML when confirmed
 */

import type { ClaudeClient, Message } from "../llm/claude-client";
import type { DiscoveryResult, EnrichedChunk } from "./types";
import { parseMarkdownPlan, type ParsedPlan } from "./markdown-plan-parser";
import { PlanStore } from "../storage/plan-store";
import type { Plan as ExecutionPlan } from "../../../shared/types/state";
import { v4 as uuidv4 } from "uuid";

export interface PlanningSession {
  sessionId: string;
  messages: Message[];
  parsedPlan: ParsedPlan | null;
}

export interface SavedPlan {
  planId: string;
  path: string;
  parsedPlan: ParsedPlan;
}

export class PlanningPhase {
  private planStore: PlanStore;

  constructor(
    private claudeClient: ClaudeClient,
    workspaceRoot: string
  ) {
    this.planStore = new PlanStore(workspaceRoot);
  }

  /**
   * Start planning conversation
   */
  async start(
    userPrompt: string,
    discoveryResult: DiscoveryResult
  ): Promise<{ session: PlanningSession; response: string }> {
    console.error("[Planning] Starting planning conversation...");

    const systemPrompt = this.buildPlanningPrompt(userPrompt, discoveryResult);

    const messages: Message[] = [
      { role: "user", content: systemPrompt }
    ];

    const response = await this.claudeClient.sendMessage({
      messages,
      model: "claude-sonnet-4-5-20250929",
      maxTokens: 4000
    });

    const assistantResponse = response.content[0].text;

    messages.push({
      role: "assistant",
      content: assistantResponse
    });

    // Try to parse plan if Claude provided one
    const parsedPlan = this.tryParsePlan(assistantResponse);

    const session: PlanningSession = {
      sessionId: uuidv4(),
      messages,
      parsedPlan
    };

    console.error(`[Planning] Started session ${session.sessionId}`);
    if (parsedPlan) {
      console.error(`[Planning] Found ${parsedPlan.tasks.length} tasks in ${parsedPlan.phases.length} phases`);
    }

    return { session, response: assistantResponse };
  }

  /**
   * Continue conversation with user feedback
   */
  async refine(
    session: PlanningSession,
    userFeedback: string
  ): Promise<{ session: PlanningSession; response: string }> {
    console.error("[Planning] Refining plan based on feedback");

    session.messages.push({
      role: "user",
      content: userFeedback
    });

    const response = await this.claudeClient.sendMessage({
      messages: session.messages,
      model: "claude-sonnet-4-5-20250929",
      maxTokens: 4000
    });

    const assistantResponse = response.content[0].text;

    session.messages.push({
      role: "assistant",
      content: assistantResponse
    });

    // Update parsed plan
    session.parsedPlan = this.tryParsePlan(assistantResponse);

    return { session, response: assistantResponse };
  }

  /**
   * Confirm and save plan
   */
  async confirm(
    session: PlanningSession,
    userPrompt: string,
    workspaceRoot: string
  ): Promise<SavedPlan> {
    console.error("[Planning] Confirming and saving plan...");

    // Get last assistant message (the plan)
    const lastMessage = session.messages
      .slice()
      .reverse()
      .find(m => m.role === "assistant");

    if (!lastMessage) {
      throw new Error("No plan found in conversation");
    }

    // Parse plan from markdown
    const parsedPlan = parseMarkdownPlan(lastMessage.content);

    console.error(`[Planning] Parsed ${parsedPlan.tasks.length} tasks`);

    // Convert to execution plan format
    const planId = uuidv4();
    const executionPlan = this.convertToExecutionPlan(
      parsedPlan,
      planId,
      userPrompt,
      workspaceRoot
    );

    // Save to TOML
    await this.planStore.savePlan(executionPlan);

    const planPath = `.dolphin/state/plans/${planId}.toml`;

    console.error(`[Planning] Plan saved to ${planPath}`);

    return {
      planId,
      path: planPath,
      parsedPlan
    };
  }

  /**
   * Build initial planning prompt
   */
  private buildPlanningPrompt(
    userPrompt: string,
    discoveryResult: DiscoveryResult
  ): string {
    const formattedChunks = this.formatChunks(discoveryResult.retrievedChunks);

    return `You are helping plan an implementation in a codebase.

<user_request>
${userPrompt}
</user_request>

<relevant_code>
${formattedChunks}
</relevant_code>

<context>
- Chunks found: ${discoveryResult.retrievedChunks.length}
- Confidence: ${(discoveryResult.confidence * 100).toFixed(0)}%
- Information gaps: ${discoveryResult.gaps.join(", ") || "None"}
</context>

Your task:
1. **Ask clarifying questions** if you need more information
2. **Analyze the existing code** to understand patterns, architecture, dependencies
3. **Create an implementation plan** when ready

When providing a plan, use this EXACT format:

## Plan: [Short descriptive title]

[Brief summary of the approach]

### Phase 1: [Phase name]
- Task: [Specific task description] (Files: path/to/file.ts)
- Task: [Another task] (Files: file1.ts, file2.ts)

### Phase 2: [Next phase name]
- Task: [Task description] (Files: path/to/file.ts)

**Important formatting rules:**
- Each task must start with "- Task:" or just "-"
- Files are optional but helpful: "(Files: file1.ts, file2.ts)"
- Keep tasks atomic and actionable
- Order tasks logically within phases

Start by asking clarifying questions or providing the plan if you have enough information.`;
  }

  /**
   * Format code chunks for prompt
   */
  private formatChunks(chunks: EnrichedChunk[]): string {
    if (chunks.length === 0) {
      return "<no_relevant_code_found/>";
    }

    const sections: string[] = [];

    // Show top 10 chunks to keep prompt manageable
    const topChunks = chunks.slice(0, 10);

    for (const chunk of topChunks) {
      sections.push(`
<chunk>
<location>${chunk.repo}/${chunk.path}:${chunk.start_line}-${chunk.end_line}</location>
${chunk.symbol_name ? `<symbol>${chunk.symbol_name}</symbol>` : ''}
\`\`\`${chunk.language || 'text'}
${chunk.snippet}
\`\`\`
</chunk>`);
    }

    if (chunks.length > 10) {
      sections.push(`\n<note>...and ${chunks.length - 10} more chunks available</note>`);
    }

    return sections.join('\n');
  }

  /**
   * Try to parse plan from Claude's response
   */
  private tryParsePlan(response: string): ParsedPlan | null {
    try {
      const parsed = parseMarkdownPlan(response);
      // Only return if we found actual tasks
      if (parsed.tasks.length > 0 && parsed.tasks[0].description !== "Implement based on discussion") {
        return parsed;
      }
      return null;
    } catch (error) {
      console.error("[Planning] Failed to parse plan:", error);
      return null;
    }
  }

  /**
   * Convert parsed plan to execution plan format
   */
  private convertToExecutionPlan(
    parsedPlan: ParsedPlan,
    planId: string,
    task: string,
    workspaceRoot: string
  ): ExecutionPlan {
    const now = new Date().toISOString();

    // Convert tasks to execution steps
    const steps = parsedPlan.tasks.map((t, index) => ({
      id: t.id,
      order: index + 1,
      description: t.description,
      action_type: "tool_call" as const,
      tool: "edit_file",
      status: "pending" as const,
      input: {
        files: t.files
      }
    }));

    return {
      schema_version: "1.0",
      plan: {
        id: planId,
        created_at: now,
        updated_at: now,
        status: "pending",
        mode: "architect",
        task,
        workspace_root: workspaceRoot
      },
      steps
    };
  }
}
