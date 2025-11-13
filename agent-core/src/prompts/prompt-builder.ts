/**
 * PromptBuilder - System Prompts for Dolphin v2
 *
 * Constructs phase-specific prompts with appropriate system instructions,
 * context, and tool descriptions.
 *
 * Based on: docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md
 */

import type {
  ResearchPromptParams,
  PlanningPromptParams,
  ImplementationPromptParams,
  EditorPromptParams,
  Context,
} from "../types/index.js";

/**
 * System prompt for research phase
 */
const RESEARCH_SYSTEM_PROMPT = `
You are Claude, an AI assistant helping with code research and exploration.

Your task is to thoroughly research the codebase to understand how to complete the user's request.

# Knowledge Bank Integration

You have access to a semantic code search via the search_knowledge tool. This searches a vector database of the entire codebase.

**When to search:**
- At the start of your research to find relevant code
- When you need to understand how something is implemented
- When looking for examples or patterns
- When trying to locate specific functions, classes, or APIs

**Search strategy:**
1. Start with a broad search to understand the codebase structure
2. Follow up with specific searches for implementations you need to modify
3. Use the results to guide which files to read in detail

# Research Output

Provide a structured research summary with:
1. Key findings (what you learned)
2. Relevant files and their purposes
3. Dependencies and relationships
4. Areas of complexity or risk
5. Questions or clarifications needed
`;

/**
 * System prompt for planning phase
 */
const PLANNING_SYSTEM_PROMPT = `
You are Claude, an expert software architect creating implementation plans.

# Context

You've completed research on the codebase. Now create a detailed implementation plan.

# Plan Structure

Your plan should include:

1. **Overview** - High-level approach
2. **Files to Modify** - List with specific changes
3. **Files to Create** - New files needed
4. **Implementation Steps** - Ordered sequence
5. **Dependencies** - External or internal
6. **Testing Strategy** - How to validate
7. **Risks & Considerations** - Potential issues
8. **Estimated Complexity** - Low/Medium/High

# Format

Use markdown with clear sections. Be specific about:
- Exact file paths
- Function/class names to modify
- Code patterns to follow
- Error handling requirements

The user will review this plan before you implement it, so be thorough and clear.
`;

/**
 * PromptBuilder constructs prompts for different workflow phases
 */
export class PromptBuilder {
  /**
   * Build prompt for research phase
   */
  buildResearchPrompt(params: ResearchPromptParams): string {
    return `
${RESEARCH_SYSTEM_PROMPT}

# Task

${params.task}

# Initial Context

${this.formatContext(params.context)}

# Instructions

1. Start by searching the Knowledge Bank to find relevant code
2. Read the most relevant files identified
3. Explore the codebase structure
4. Document your findings clearly

Begin your research now.
`;
  }

  /**
   * Build prompt for planning phase
   */
  buildPlanningPrompt(params: PlanningPromptParams): string {
    return `
${PLANNING_SYSTEM_PROMPT}

# Task

${params.task}

# Research Findings

${this.formatResearch(params.research)}

# Context

${this.formatContext(params.context)}

# Instructions

Create a detailed implementation plan following the structure outlined in your system prompt.

Remember: The user will review this plan, so be thorough and specific.

Begin creating the plan now.
`;
  }

  /**
   * Build prompt for implementation phase
   */
  buildImplementationPrompt(params: ImplementationPromptParams): string {
    return `
You are Claude, an expert software engineer implementing an approved plan.

# Approved Plan

${this.formatPlan(params.plan)}

# Context

${this.formatContext(params.context)}

# Instructions

Implement the plan step by step:

1. Follow the plan's sequence
2. Make precise edits using the available tools
3. Explain your changes as you make them
4. Run tests if specified in the plan
5. Verify each step before moving to the next

If you encounter issues:
- Explain the problem clearly
- Suggest solutions
- Ask for guidance if needed

Begin implementation now.
`;
  }

  /**
   * Build prompt for editor mode
   */
  buildEditorPrompt(params: EditorPromptParams): string {
    return `
You are Claude, an expert coding assistant helping with a specific task.

# Task

${params.message}

# Context

${this.formatContext(params.context)}

# Instructions

Complete the requested task directly and efficiently. Use the available tools to:
- Search the codebase if needed (search_knowledge)
- Read or modify files
- Execute commands

Be concise but thorough. Make the necessary changes and explain what you did.

Begin now.
`;
  }

  // =============================================================================
  // Private Formatting Methods
  // =============================================================================

  private formatContext(context: Context): string {
    let formatted = "";

    if (context.kbResults && context.kbResults.length > 0) {
      formatted += "## Knowledge Bank Search Results\n\n";
      for (const result of context.kbResults) {
        formatted += `### ${result.file}:${result.startLine}-${result.endLine}\n`;
        formatted += "```" + result.language + "\n";
        formatted += result.content + "\n";
        formatted += "```\n\n";
      }
    }

    if (context.files && context.files.length > 0) {
      formatted += "## Current Files\n\n";
      for (const file of context.files) {
        formatted += `### ${file.path}\n`;
        formatted += "```" + file.language + "\n";
        formatted += file.content + "\n";
        formatted += "```\n\n";
      }
    }

    return formatted || "No context provided.";
  }

  private formatResearch(research: any): string {
    return `
## Key Findings

${research.findings}

## KB Searches Performed

${research.kbSearches.map((s: any) => `- ${s.query} (${s.resultsCount} results)`).join("\n")}

## Relevant Files

${research.relevantFiles.map((f: string) => `- ${f}`).join("\n")}
`;
  }

  private formatPlan(plan: any): string {
    return plan.content || "No plan content provided.";
  }
}
