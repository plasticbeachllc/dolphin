/**
 * EP-11 Phase 3: Planning Phase
 *
 * Interactive planning conversation with Claude to produce:
 * - Implementation plan with tasks
 * - File modifications needed
 * - Dependencies and order
 * - Saves final plan to TOML
 */

import type { ClaudeClient, Message } from "../llm/claude-client";
import type {
  SynthesisResult,
  Plan,
  PlanPhase,
  TodoItem,
  CodeReference
} from "./types";
import { PlanStore } from "../storage/plan-store";
import type { Plan as ExecutionPlan } from "../../../shared/types/state";
import { v4 as uuidv4 } from "uuid";

export interface PlanningSession {
  sessionId: string;
  status: "refining" | "confirmed";
  currentPlan: Plan | null;
  conversationMessages: Message[];
}

export interface SavedPlan {
  planId: string;
  path: string;
  plan: Plan;
}

export class PlanningPhase {
  private planStore: PlanStore;
  private conversationMessages: Message[] = [];

  constructor(
    private claudeClient: ClaudeClient,
    workspaceRoot: string
  ) {
    this.planStore = new PlanStore(workspaceRoot);
  }

  /**
   * Start planning phase - generate initial plan draft with questions
   */
  async startPlanning(
    userPrompt: string,
    synthesisResult: SynthesisResult,
    repoName: string
  ): Promise<PlanningSession> {
    console.error("[Planning] Starting planning phase...");

    // Build initial system prompt
    const systemPrompt = this.buildInitialPlanningPrompt(
      userPrompt,
      synthesisResult
    );

    this.conversationMessages = [
      { role: "user", content: systemPrompt }
    ];

    // Get initial plan from Claude
    const response = await this.claudeClient.sendMessage({
      messages: this.conversationMessages,
      model: "claude-sonnet-4-5-20250929",
      maxTokens: 4000
    });

    const assistantMessage = response.content[0].text;
    this.conversationMessages.push({
      role: "assistant",
      content: assistantMessage
    });

    // Try to parse plan from response
    const parsedPlan = this.extractPlanFromResponse(assistantMessage, userPrompt, repoName);

    console.error("[Planning] Generated initial plan draft");
    if (parsedPlan) {
      console.error(`[Planning] Plan has ${parsedPlan.phases.length} phases, ${parsedPlan.todoList.length} tasks`);
    }

    return {
      sessionId: uuidv4(),
      status: "refining",
      currentPlan: parsedPlan,
      conversationMessages: this.conversationMessages
    };
  }

  /**
   * Refine plan based on user feedback
   */
  async refine(
    session: PlanningSession,
    userFeedback: string,
    userPrompt: string,
    repoName: string
  ): Promise<PlanningSession> {
    console.error(`[Planning] Refining plan based on user feedback`);

    // Add user message
    this.conversationMessages.push({
      role: "user",
      content: userFeedback
    });

    // Get updated plan
    const response = await this.claudeClient.sendMessage({
      messages: this.conversationMessages,
      model: "claude-sonnet-4-5-20250929",
      maxTokens: 4000
    });

    const assistantMessage = response.content[0].text;
    this.conversationMessages.push({
      role: "assistant",
      content: assistantMessage
    });

    // Parse updated plan
    const updatedPlan = this.extractPlanFromResponse(assistantMessage, userPrompt, repoName);

    return {
      ...session,
      currentPlan: updatedPlan,
      conversationMessages: this.conversationMessages
    };
  }

  /**
   * Confirm and save final plan
   */
  async confirmPlan(
    session: PlanningSession,
    userPrompt: string,
    workspaceRoot: string
  ): Promise<SavedPlan> {
    console.error("[Planning] Confirming and saving plan...");

    if (!session.currentPlan) {
      throw new Error("No plan to confirm");
    }

    const planId = uuidv4();

    // Convert to execution plan format
    const executionPlan = this.convertToExecutionPlan(
      session.currentPlan,
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
      plan: session.currentPlan
    };
  }

  /**
   * Build initial planning prompt
   */
  private buildInitialPlanningPrompt(
    userPrompt: string,
    synthesisResult: SynthesisResult
  ): string {
    const questionsSection = synthesisResult.clarifyingQuestions.length > 0
      ? `<clarifying_questions>
${synthesisResult.clarifyingQuestions.map(q =>
  `- [${q.priority}] ${q.question}\n  Reason: ${q.reason}`
).join('\n')}
</clarifying_questions>`
      : '';

    return `You are helping create an implementation plan.

<user_request>
${userPrompt}
</user_request>

<synthesis_analysis>
${synthesisResult.analysis}

Assumptions:
${synthesisResult.assumptions.map(a => `- [${a.confidence}] ${a.statement}`).join('\n')}

Risks:
${synthesisResult.risks.map(r => `- [${r.severity}] ${r.description}`).join('\n')}
</synthesis_analysis>

${questionsSection}

Your task:
1. If there are clarifying questions above, ASK THEM FIRST before making the plan
2. Once you have enough info, generate an implementation plan
3. Structure the plan as phases with specific tasks
4. Identify files to create/modify
5. Note dependencies between tasks

Return your response in this format:

**Questions** (if any remain):
- Question 1
- Question 2

**Implementation Plan** (once ready):

### Phase 1: [Phase Name]
Description of what this phase accomplishes

Tasks:
1. [Specific task] - Files: path/to/file.ts
2. [Another task] - Files: path/to/other.ts

### Phase 2: [Next Phase]
...

**Files to Modify**:
- path/to/file1.ts
- path/to/file2.ts

**Dependencies**:
- Task 2 depends on Task 1
- Task 3 depends on Task 2

Keep it concise and actionable. Ask critical questions first!`;
  }

  /**
   * Extract plan structure from Claude's response
   */
  private extractPlanFromResponse(
    response: string,
    userPrompt: string,
    repoName: string
  ): Plan | null {
    try {
      // Try to parse structured plan
      // This is a simple extraction - can be made more robust

      const phases: PlanPhase[] = [];
      const todoList: TodoItem[] = [];
      const references: CodeReference[] = [];
      const assumptions: string[] = [];
      const risks: string[] = [];

      // Extract phases (look for ### Phase markers)
      const phaseRegex = /###\s*Phase\s+\d+:\s*(.+?)\n([\s\S]*?)(?=###\s*Phase|\*\*|$)/g;
      let match;
      let phaseIndex = 0;

      while ((match = phaseRegex.exec(response)) !== null) {
        const phaseName = match[1].trim();
        const phaseContent = match[2].trim();

        // Extract tasks from this phase
        const taskRegex = /\d+\.\s+(.+?)(?:\s*-\s*Files?:\s*(.+?))?(?=\n\d+\.|\n\n|$)/g;
        const steps: string[] = [];
        const affectedFiles: string[] = [];
        let taskMatch;

        while ((taskMatch = taskRegex.exec(phaseContent)) !== null) {
          const taskDesc = taskMatch[1].trim();
          steps.push(taskDesc);

          // Add to todo list
          todoList.push({
            id: `task-${todoList.length + 1}`,
            description: taskDesc,
            status: "pending",
            priority: phaseIndex + 1,
            dependencies: [],
            fileReferences: taskMatch[2] ? [taskMatch[2].trim()] : []
          });

          if (taskMatch[2]) {
            affectedFiles.push(taskMatch[2].trim());
          }
        }

        phases.push({
          name: phaseName,
          description: phaseContent.split('\n')[0] || phaseName,
          steps,
          affectedFiles: [...new Set(affectedFiles)],
          estimatedTime: "TBD"
        });

        phaseIndex++;
      }

      // Extract file references
      const filesRegex = /\*\*Files to (?:Modify|Create)\*\*:?\s*\n([\s\S]*?)(?=\n\*\*|$)/i;
      const filesMatch = filesRegex.exec(response);
      if (filesMatch) {
        const fileLines = filesMatch[1].trim().split('\n');
        for (const line of fileLines) {
          const cleanedLine = line.replace(/^[-*]\s*/, '').trim();
          if (cleanedLine) {
            references.push({
              file: cleanedLine,
              description: "File to be modified"
            });
          }
        }
      }

      // If we found phases, return a plan
      if (phases.length > 0) {
        return {
          title: userPrompt.length > 50 ? userPrompt.substring(0, 47) + "..." : userPrompt,
          summary: phases.map(p => p.name).join(", "),
          phases,
          todoList,
          risks,
          assumptions,
          estimatedComplexity: phases.length > 3 ? "high" : phases.length > 1 ? "medium" : "low",
          references
        };
      }

      return null;
    } catch (error) {
      console.error("[Planning] Failed to extract plan:", error);
      return null;
    }
  }

  /**
   * Convert orchestration Plan to execution Plan format
   */
  private convertToExecutionPlan(
    plan: Plan,
    planId: string,
    task: string,
    workspaceRoot: string
  ): ExecutionPlan {
    const now = new Date().toISOString();

    // Convert tasks to execution steps
    const steps = plan.todoList.map((todo, index) => ({
      id: todo.id,
      order: index + 1,
      description: todo.description,
      action_type: "tool_call" as const,
      tool: "edit_file",  // Default tool
      status: "pending" as const,
      input: {
        files: todo.fileReferences
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
